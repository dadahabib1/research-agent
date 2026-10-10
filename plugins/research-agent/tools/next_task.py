# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""research-agent selector: pick the next research task from the queue and claim its branch, so
runs started at the same time take different tasks.

Usage: uv run --script ${CLAUDE_PLUGIN_ROOT}/tools/next_task.py [--topic NAME] [--list] [--project PATH]

Reads research-queue.md from the remote's default branch (from the working tree when there is no
remote) and gives each row a state from its branch research/<topic>:
  running    the branch's last commit is a claim commit, or the branch has no pull request yet
  stopped    the open pull request's hand-back says "stopped: ..."
  waiting    the open pull request's hand-back says "waiting on requester"
  in review  the open pull request's hand-back says anything else, or it has none
  done       the latest pull request was merged, or the run's log is on the default branch
  abandoned  the latest pull request was closed unmerged and its branch is still there
  free       no branch and no pull request
With no gh, the hand-back is read from the last section of the branch's log instead of a pull
request; with no remote, from local branches.

Selection: the first row in table order whose status is todo, whose prerequisites are all
accepted, and whose state is free, abandoned or stopped. --topic NAME (the deliverable's stem or
the task's name, case ignored) takes that row instead, and may also resume a waiting or running
row or re-run a done one; it never takes a row in review. The claim is an empty commit, pushed
without force (a replaced abandoned or done branch is pushed with --force-with-lease on the tip
read), so of two runs that pick one row, one push is rejected and that run takes the next row.
The branch is checked out before the claim is pushed, and a local branch with unpushed commits is
never reset. Pull requests from forks are ignored, and a row whose deliverable stem is empty, shared
or not a valid branch name is passed over. --list prints every row's state and claims nothing.

Exit codes: 0 a task selected (or --list printed); 1 no row qualifies; 2 the selector could not run.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

CONFIG = "research-agent.toml"
CLAIM = "research-agent claim:"
COLUMNS = ("Task", "Prompt", "Deliverable", "Prerequisites", "Status")
AUTO = {"free", "abandoned", "stopped"}
NAMED = AUTO | {"waiting", "running", "done"}
RESUME = {"stopped", "waiting", "running"}
LOST_RACE = ("[rejected]", "stale info", "non-fast-forward", "fetch first")  # another run's push won


class CannotRun(Exception):
    """The selector itself cannot run (exit 2)."""


@dataclass
class Row:
    task: str
    prompt: str
    deliverable: str
    prerequisites: list[str]
    status: str
    topic: str = ""
    state: str = ""
    tip: str | None = None          # the branch's last commit, where it exists
    pull_request: str | None = None  # the latest pull request's URL
    invalid: str = ""               # why the topic cannot name a branch, if it cannot

    @property
    def branch(self) -> str:
        return f"research/{self.topic}"


@dataclass
class Repo:
    path: Path
    mode: str            # "pull requests", "branches" or "local"
    reason: str          # why branches or local
    default: str         # the default branch's ref: origin/main, or the local branch name
    root: str


# ---------- git and gh ----------

def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError as exc:
        raise CannotRun(f"{cmd[0]} is not on the PATH") from exc


def git(repo: Path, *args: str, check: bool = True) -> str:
    out = run(["git", *args], repo)
    if check and out.returncode != 0:
        raise CannotRun(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip() if out.returncode == 0 else ""


def gh_works(repo: Path) -> bool:
    return shutil.which("gh") is not None and run(["gh", "repo", "view", "--json", "name"], repo).returncode == 0


def pull_requests(repo: Path, branch: str) -> list[dict]:
    """Every pull request from this repository's branch, newest first: number, state (OPEN, CLOSED,
    MERGED), url, body. A fork's branch of the same name is another run's, or nobody's: ignored."""
    out = run(["gh", "pr", "list", "--head", branch, "--state", "all", "--limit", "50",
               "--json", "number,state,url,body,isCrossRepository"], repo)
    if out.returncode != 0:
        raise CannotRun(f"gh pr list --head {branch} failed: {out.stderr.strip()}")
    prs = [pr for pr in json.loads(out.stdout or "[]") if not pr.get("isCrossRepository")]
    return sorted(prs, key=lambda pr: pr["number"], reverse=True)


# ---------- the queue ----------

def handback_status(text: str | None) -> str | None:
    """The Status label of the last ## Hand-back block in text, lowercased."""
    if not text or "## Hand-back" not in text:
        return None
    block = text[text.rfind("## Hand-back"):]
    match = re.search(r"^\s*[-*]\s*Status:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    return match.group(1).lower() if match else None


def by_status(status: str | None) -> str:
    if status and status.startswith("stopped"):
        return "stopped"
    if status and status.startswith("waiting on requester"):
        return "waiting"
    return "in review"


def parse_queue(text: str) -> list[Row]:
    """The rows of the first table with the five required columns."""
    header, rows = None, []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.startswith("|"):
            if header is not None:
                break
            continue
        cells = [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells if all(c in cells for c in COLUMNS) else None
        elif not all(set(c) <= set("-: ") for c in cells):
            row = dict(zip(header, cells, strict=False))
            prereqs = [p.strip().lower() for p in row.get("Prerequisites", "").split(",")]
            rows.append(Row(task=row.get("Task", ""), prompt=row.get("Prompt", ""),
                            deliverable=row.get("Deliverable", ""),
                            prerequisites=[p for p in prereqs if p and p != "none"],
                            status=row.get("Status", "").lower(),
                            topic=PurePosixPath(row.get("Deliverable", "")).name.removesuffix(".md")))
    if header is None:
        raise CannotRun(f"the queue has no table with the columns {', '.join(COLUMNS)}")
    counts = Counter(r.topic for r in rows)
    for row in rows:
        if not row.topic:
            row.invalid = "no deliverable file name"
        elif counts[row.topic] > 1:
            row.invalid = f"{counts[row.topic]} rows share the deliverable stem {row.topic}"
        elif run(["git", "check-ref-format", f"refs/heads/research/{row.topic}"], Path.cwd()).returncode != 0:
            row.invalid = f"research/{row.topic} is not a valid branch name"
    return rows


# ---------- the repository ----------

def open_repo(path: Path) -> Repo:
    try:
        config = tomllib.loads((path / CONFIG).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {CONFIG}: {exc}") from exc
    project = config.get("project")
    if not isinstance(project, dict) or not project.get("root"):
        raise CannotRun(f"{CONFIG} has no [project] root: this repository runs no research")
    root = project["root"].strip("/")
    if run(["git", "remote", "get-url", "origin"], path).returncode != 0:
        current = git(path, "symbolic-ref", "--short", "HEAD")
        if current.startswith("research/"):
            raise CannotRun(f"on {current}: start from the default branch")
        return Repo(path, "local", "no remote", current, root)
    git(path, "fetch", "-q", "--prune", "origin")
    head = git(path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    if not head:
        listed = git(path, "ls-remote", "--symref", "origin", "HEAD")
        match = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", listed, flags=re.MULTILINE)
        if not match:
            raise CannotRun("cannot tell the remote's default branch")
        head = f"origin/{match.group(1)}"
    if gh_works(path):
        return Repo(path, "pull requests", "", head, root)
    return Repo(path, "branches", "gh unavailable for this remote", head, root)


def show(repo: Repo, ref: str, rel: str) -> str | None:
    out = run(["git", "show", f"{ref}:{rel}"], repo.path)
    return out.stdout if out.returncode == 0 else None


def queue_text(repo: Repo) -> str:
    rel = f"{repo.root}/research-queue.md"
    text = (repo.path / rel).read_text(encoding="utf-8") if repo.mode == "local" and (repo.path / rel).is_file() \
        else show(repo, repo.default, rel)
    if text is None:
        raise CannotRun(f"no {rel} on {repo.default}")
    return text


def branch_ref(repo: Repo, row: Row) -> str:
    return row.branch if repo.mode == "local" else f"origin/{row.branch}"


def assess(repo: Repo, row: Row) -> None:
    """Set row.state, row.tip and row.pull_request from the branch, its pull requests and its log."""
    ref = branch_ref(repo, row)
    row.tip = git(repo.path, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False) or None
    subject = git(repo.path, "log", "-1", "--format=%s", ref, check=False) if row.tip else ""
    log = f"{repo.root}/logs/{row.topic}-log.md"
    prs = pull_requests(repo.path, row.branch) if repo.mode == "pull requests" else []
    latest = prs[0] if prs else None
    row.pull_request = latest["url"] if latest else None
    if subject.startswith(CLAIM):
        row.state = "running"
    elif latest and latest["state"] == "OPEN":
        row.state = by_status(handback_status(latest.get("body")))
    elif latest and latest["state"] == "MERGED":
        row.state = "done"
    elif show(repo, repo.default, log) is not None:
        row.state = "done"
    elif row.tip and repo.mode != "pull requests":
        status = handback_status(show(repo, ref, log))
        row.state = by_status(status) if status else "running"
    elif row.tip and latest and latest["state"] == "CLOSED":
        row.state = "abandoned"
    elif row.tip:
        row.state = "running"
    else:
        row.state = "free"


def claim(repo: Repo, row: Row) -> str | None:
    """Claim row's branch and check it out; returns the claim commit, or None when another run's
    push won. A resumed branch gets the claim on its tip; a new one on the default branch."""
    resume = row.state in RESUME
    if repo.mode == "local":
        if resume:
            git(repo.path, "checkout", "-q", row.branch)
        else:
            keep_unpushed(repo, row)
            git(repo.path, "checkout", "-q", "-B", row.branch, repo.default)
        return git(repo.path, "rev-parse", "--short", "HEAD")
    keep_unpushed(repo, row)
    base = row.tip if resume else git(repo.path, "rev-parse", repo.default)
    tree = git(repo.path, "rev-parse", f"{base}^{{tree}}")
    message = f"{CLAIM} {row.branch} {uuid.uuid4().hex[:12]}"
    commit = git(repo.path, "commit-tree", tree, "-p", base, "-m", message)
    previous = git(repo.path, "symbolic-ref", "-q", "--short", "HEAD", check=False) or git(repo.path, "rev-parse", "HEAD")
    git(repo.path, "checkout", "-q", "-B", row.branch, commit)  # a failure here leaves nothing on the remote
    # every step that can fail runs before the push, and nothing runs after it, so no failure strands a claim
    for key, value in (("remote", "origin"), ("merge", f"refs/heads/{row.branch}")):
        out = run(["git", "config", f"branch.{row.branch}.{key}", value], repo.path)
        if out.returncode != 0:
            drop_local(repo, row, previous, commit)
            raise CannotRun(f"git config branch.{row.branch}.{key} failed: {out.stderr.strip()}")
    push = ["git", "push", "-q"]
    if row.tip and not resume:  # an abandoned or done branch: replace it only if nobody moved it
        push.append(f"--force-with-lease=refs/heads/{row.branch}:{row.tip}")
    out = run([*push, "origin", f"{commit}:refs/heads/{row.branch}"], repo.path)
    if out.returncode != 0:
        drop_local(repo, row, previous, commit)
        if any(mark in out.stderr for mark in LOST_RACE):
            return None
        raise CannotRun(f"git push of the claim on {row.branch} failed: {out.stderr.strip()}")
    return commit[:7]


def drop_local(repo: Repo, row: Row, previous: str, commit: str) -> None:
    """Leave the claim branch and delete it, but only while it still holds our claim commit."""
    git(repo.path, "checkout", "-q", previous)
    if run(["git", "update-ref", "-d", f"refs/heads/{row.branch}", commit], repo.path).returncode == 0:
        git(repo.path, "config", "--remove-section", f"branch.{row.branch}", check=False)
    else:
        print(f"note: kept {row.branch}: it moved after the claim, so it holds work that is not ours to delete")


def keep_unpushed(repo: Repo, row: Row) -> None:
    """Refuse to reset a local branch that holds commits the remote does not have."""
    if not git(repo.path, "rev-parse", "--verify", "-q", f"refs/heads/{row.branch}", check=False):
        return
    ahead = git(repo.path, "rev-list", row.branch, "--not", repo.default, "--remotes=origin").split()
    if ahead:
        raise CannotRun(f"the local branch {row.branch} has {len(ahead)} commit(s) the remote does not have "
                        f"({', '.join(c[:7] for c in ahead[:3])}); push or remove them, then run again")


# ---------- selection ----------

def eligible(row: Row, rows: list[Row], named: bool) -> str | None:
    """Why row cannot be taken, or None when it can."""
    if row.status != "todo":
        return f"status {row.status}, not todo"
    if row.invalid:
        return row.invalid
    statuses = {r.task.lower(): r.status for r in rows}
    waiting = [p for p in row.prerequisites if statuses.get(p) != "accepted"]
    if waiting:
        return f"prerequisites not accepted: {', '.join(waiting)}"
    if row.state not in (NAMED if named else AUTO):
        where = f" ({row.pull_request})" if row.pull_request else f" ({row.branch})" if row.tip else ""
        return f"{row.state}{where}"
    return None


def select(repo: Repo, rows: list[Row], topic: str | None) -> tuple[Row | None, str | None, list[str]]:
    """(selected row, its claim commit, reasons for each row passed over)."""
    reasons = []
    if topic:
        matches = [r for r in rows if topic.lower() in (r.topic.lower(), r.task.lower())]
        if not matches:
            return None, None, [f"{topic}: no queue row has this deliverable stem or task name"]
        candidates = matches[:1]
    else:
        candidates = rows
    for row in candidates:
        if row.status == "todo" and not row.invalid:
            assess(repo, row)
        why = eligible(row, rows, named=bool(topic))
        if why:
            reasons.append(f"{row.topic}: {why}")
            continue
        commit = claim(repo, row)
        if commit:
            return row, commit, reasons
        reasons.append(f"{row.topic}: claimed by another run a moment ago")
    return None, None, reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=__doc__.split("\n\n", 2)[2],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", help="take this row: its deliverable's stem or its task name")
    parser.add_argument("--list", action="store_true", help="print every row's state; claim nothing")
    parser.add_argument("--project", type=Path, default=Path("."), help="repository root (default: .)")
    args = parser.parse_args(argv)
    try:
        repo = open_repo(args.project.resolve())
        rows = parse_queue(queue_text(repo))
        mode = repo.mode + (f" ({repo.reason})" if repo.reason else "")
        if args.list:
            print(f"mode: {mode}")
            for row in rows:
                if row.invalid:
                    row.state = "invalid"
                else:
                    assess(repo, row)
                where = row.pull_request or (row.branch if row.tip else "-")
                print(f"{row.status:<21} {row.state:<10} {row.topic}  {where}")
            return 0
        current = git(repo.path, "symbolic-ref", "-q", "--short", "HEAD", check=False)
        if current.startswith("research/"):
            raise CannotRun(f"on {current}: start from the default branch")
        row, commit, reasons = select(repo, rows, args.topic)
    except CannotRun as exc:
        print(f"selector could not run: {exc}")
        return 2
    if row is None:
        print("none: no queue row qualifies")
        for reason in reasons:
            print(f"  {reason}")
        return 1
    print(f"selected: {'resume' if row.state in RESUME else 'new'} {row.topic}")
    print(f"task: {row.task}")
    print(f"prompt: {row.prompt}")
    print(f"branch: {row.branch} (claim {commit})")
    print(f"pull request: {row.pull_request if row.state in RESUME and row.pull_request else 'none yet'}")
    print(f"mode: {mode}")
    for reason in reasons:
        print(f"passed over: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
