"""The guarded merge (contract C8): the only way into main.

    python -I .agents/kit/bin/merge.py yours <N> [--head <sha>]   your mode (kit merge <N> from step 7)
    python -I .agents/kit/bin/merge.py auto <N>                   automatic mode, the orchestrator only
    python -I .agents/kit/bin/merge.py check <N>                  items 1-9 without the refresh; writes nothing
    python -I .agents/kit/bin/merge.py reconcile                  section 6's pass alone, then paid suites due
    python -I .agents/kit/bin/merge.py status                     the earning state
    python -I .agents/kit/bin/merge.py resume --reason <text>     yours: lifts a stop

A PR lands only if its head is the one approved (or shown to you), the clean run passed on exactly what lands,
and nobody merged in between; a red main is reverted and stops automatic merges. Built (issues #71, #73, #74,
#85):
the readiness list with head binding and the refresh from main, the merge lock, the clean runs before and
after the merge, the merge call with `--match-head-commit`, the tag, the record and the earning state derived
from the event files; the in-progress marker and the reconcile pass (recovery, and outside writes walked from
the baseline), red main (a stop and a revert PR), `resume`, the merged ticket's worktree removal and the paid
suite under its own lock; the prose PR shape and the unanswered-comment rule (the session block is the
guard's, C5); the pure revert's patch-id check (#85), and for a `kit rollback` branch against the commit its
revert's message names (#181). Standard library only; calls git, gh and `claude agents`
as subprocesses.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # C1 section 2: imports by __file__ under -I
sys.path.insert(0, str(HERE.parent / "hooks"))

import kitconfig  # noqa: E402
import kitlock  # noqa: E402
import launch  # noqa: E402  (C6: clean_env, copy_secrets, the default branch; reused, not copied)
import notices  # noqa: E402
import workfiles  # noqa: E402
from guard import matches  # noqa: E402

NOTHING = "Nothing was merged."
CALL_TIMEOUT = 120  # seconds, each git or gh call [judgment] (C8 section 5)
WAIT_PRINT, WAIT_POLL = 60, 10  # a busy merge lock: a line each minute, a try every 10 s (C8 section 5)
MAX_RERUNS = 3  # pre-merge reruns under the lock before `main keeps moving` (C8 section 7)
PAUSE_LIMIT = 600  # KIT_MERGE_PAUSE_AT waits up to 10 minutes (C8 section 13)
STAGES = ("pre-run-done", "locked", "merge-called", "merged", "tagged", "paid-start")
CODE = (".py", ".ps1", ".sh", ".cmd", ".bat", ".js", ".ts")  # C5 section 5's scan list
CONTROL_CONFIG = [".claude/settings.json", ".claude/settings.local.json", ".codex/**", "agent-kit.toml"]
EVENT = re.compile(r"(merge|escalation|stop|resume|paid)-(\d{8}T\d{6}Z)-[0-9A-Za-z-]+\.(json|md)")
SHA = re.compile(r"[0-9a-f]{40}")
# GitHub's own refusals of a merge call (M98, M99): nothing merged. Any other failure leaves the result unknown.
GITHUB_REFUSALS = ("Head branch was modified", "Base branch was modified", "Pull Request is not mergeable",
                   "not mergeable")
FIELDS = ("state,isDraft,baseRefName,headRefName,headRefOid,headRepositoryOwner,isCrossRepository,title,body,"
          "mergeable,reviewDecision")


class Refused(Exception):
    """A refusal: nothing merged (C5's refusal shape)."""

    def __init__(self, item: str, failed: str, valid: str):
        self.item = item
        super().__init__(f"REFUSED ({item}): {failed}. Valid: {valid}. {NOTHING}")


class Failed(Exception):
    """An error before the merge call: nothing merged (exit 2)."""


class Unrecorded(Exception):
    """Merged, but the run ended before its record (exit 4; the marker stays)."""


# ---------------------------------------------------------------- git and gh


HELD: dict = {"lock": None}  # the merge lock while this process holds it: its children go in the lock's job


def run(args: list[str], cwd: Path, *, check=True, timeout=CALL_TIMEOUT, env=None) -> subprocess.CompletedProcess:
    """One git or gh call with a timeout. While the merge lock (or a paid run's lock) is held the child runs
    in the lock's kill-on-close job (C8 section 5), so a crashed merge.py leaves no push or merge call going on."""
    popen = HELD["lock"].popen if HELD["lock"] is not None else subprocess.Popen
    try:
        proc = popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                     text=True, encoding="utf-8", errors="replace", env=env)
    except OSError as e:
        raise Failed(f"{args[0]} could not run: {e}") from None
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc)  # the whole tree, so no grandchild keeps the pipes open
        raise Failed(f"{' '.join(args[:3])} took longer than {timeout} s") from None
    r = subprocess.CompletedProcess(args, proc.returncode, out, err)
    if check and r.returncode != 0:
        raise Failed(f"{' '.join(args[:4])} exited {r.returncode}: {' '.join((r.stderr or r.stdout).split())[:400]}")
    return r


def git(cwd: Path, *args: str, check=True) -> str:
    return run(["git", *args], cwd, check=check).stdout.strip()


def gh(cwd: Path, *args: str, check=True) -> subprocess.CompletedProcess:
    return run(["gh", *args], cwd, check=check)


def is_ancestor(cwd: Path, a: str, b: str) -> bool:
    r = run(["git", "merge-base", "--is-ancestor", a, b], cwd, check=False)
    if r.returncode not in (0, 1):
        raise Failed(f"git merge-base --is-ancestor {a[:12]} {b[:12]}: {r.stderr.strip()[:300]}")
    return r.returncode == 0


def parents(cwd: Path, commit: str) -> list[str]:
    return git(cwd, "rev-list", "--parents", "-n", "1", commit).split()[1:]


# ---------------------------------------------------------------- the project


class Project:
    """The main checkout, its config, the coordination folder, `owner/name` and the default branch."""

    def __init__(self, main: Path):
        self.main = main
        try:
            self.values = kitconfig.effective(main)
        except Exception as e:
            raise Refused("config", "; ".join(str(e).splitlines()),
                          "fix the setting it names (python -I .agents/kit/bin/kitconfig.py show)") from None
        self.coordination = main / str(self.value("coordination"))
        self.merges = self.coordination / "merges"
        try:
            self.default = launch.default_branch(main)
        except launch.Refused as e:
            raise Failed(str(e)) from None

    def value(self, key: str):
        return self.values[key][0]

    @functools.cached_property
    def repo(self) -> str:
        """`owner/name` from origin's URL, asked when GitHub is first needed (after main's copy)."""
        url = git(self.main, "remote", "get-url", "origin")
        m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
        if not m:
            raise Refused("repository", f"origin is {url}, not a GitHub repository", "a GitHub origin")
        return f"{m.group(1)}/{m.group(2)}"


def main_checkout() -> Path:
    return Path(git(HERE, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent


# ---------------------------------------------------------------- item 1: main's copy (C8 section 1)


def main_copy(p: Project) -> None:
    if kitconfig.location(p.main, ".agents/kit/bin") != kitconfig.location(HERE, "."):
        raise Refused("main's copy", f"merge.py ran from {HERE.as_posix()}, not from the main checkout "
                      f"{p.main.as_posix()}", f"python -I {(p.main / '.agents/kit/bin/merge.py').as_posix()}")
    git(p.main, "fetch", "-q", "origin")
    differs = git(p.main, "diff", "--name-only", f"origin/{p.default}", "--", ".agents/kit/bin",
                  ".agents/kit/config", "agent-kit.toml").splitlines()
    if differs:
        raise Refused("main's copy", f"{differs[0]} differs from origin/{p.default}",
                      "git pull --ff-only in the main checkout, then rerun")
    print(f"ok main's copy: {p.main.as_posix()} matches origin/{p.default}")


# ---------------------------------------------------------------- item 2: the reconcile pass (C8 section 6)


def markers(p: Project) -> list[Path]:
    return sorted(f for f in p.merges.glob("in-progress-*.json") if ".tmp-" not in f.name) if p.merges.is_dir() else []


def reconcile_item(p: Project) -> None:
    """Item 2 of a merging run: claim the merge lock, reconcile, release (decision 95's serialized recovery).
    A red main it finds writes its stop, which item 4 then reads."""
    locked_pass(p)
    print("ok reconcile: no merge left unrecorded, outside writes recorded")


def locked_pass(p: Project) -> int:
    lock = take_lock(p, {"format": "merge-lock", "version": 1, "id": f"reconcile-{workfiles.utc_stamp()}",
                         "pr": None, "entry": "reconcile", "host": socket.gethostname()})
    try:
        return reconcile_pass(p, lock)
    finally:
        HELD["lock"] = None
        lock.release()


def reconcile_pass(p: Project, lock: kitlock.Lock) -> int:
    """Steps 1 and 2, the merge lock held: every marker belongs to a run that has ended, so recovering it
    never races a live merge. 3 when it found a red main, else 0. GitHub unreadable: Failed (exit 2), and
    the marker stays, so automatic merges stay blocked until a pass finishes."""
    code = 0
    for f in markers(p):
        code = max(code, recover(p, f, lock))
    return max(code, outside_writes(p, lock))


def recover(p: Project, f: Path, lock: kitlock.Lock) -> int:
    """Step 1 for one marker: the kit's merge (merged with the marker's head as second parent) is continued
    from its stage and recorded with `recovered: true`; an unmerged PR gets a `not-merged` record; a PR merged
    at another head a `not-merged` record, its merge commit then an outside write (step 2)."""
    try:
        m = json.loads(f.read_text(encoding="utf-8"))
        n, merge_id, entry, head = int(m["pr"]), str(m["id"]), str(m["entry"]), str(m["head"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Failed(f"merges/{f.name} cannot be read ({e}); settle it by hand") from None
    if (p.merges / f"{merge_id}.json").exists():  # the record was written, the marker not yet deleted
        f.unlink(missing_ok=True)
        print(f"ok reconcile: PR #{n}'s record merges/{merge_id}.json was written; its marker removed")
        return 0
    pr = json.loads(gh(p.main, "pr", "view", str(n), "--repo", p.repo, "--json", "state,mergeCommit").stdout)
    commit = (pr.get("mergeCommit") or {}).get("oid") if pr.get("state") == "MERGED" else None
    rec = {"info": m.get("info") or {}, "pr": n, "head": head, "main_before": m.get("main_before"),
           "pre_run": m.get("pre_run"), "started_at": m.get("started_at"), "merged_at": m.get("merged_at"),
           "tag": m.get("tag"), "post_run": m.get("post_run"), "stop": m.get("stop"),
           "revert_pr": m.get("revert_pr"), "worktree": m.get("worktree")}
    if commit:
        git(p.main, "fetch", "-q", "origin")
        ps = parents(p.main, commit)
        if len(ps) == 2 and ps[1] == head:
            print(f"recovering PR #{n} ({merge_id}): merged as {commit[:12]}; the run ended at {m.get('stage')}",
                  flush=True)
            return finish(p, n, entry, rec, merge_id, commit, lock, recovered=True)
        why = f"PR #{n} was merged as {commit[:12]}, not at the marker's head {head[:12]}: an outside write"
    else:
        why = f"the run ended at {m.get('stage')} and GitHub shows PR #{n} {str(pr.get('state')).lower()}, not merged"
    refusal = f"REFUSED (reconcile): {why}. Valid: rerun the merge. {NOTHING}"
    record(p, merge_id, entry, rec, result="not-merged", refusal=refusal, recovered=True)
    f.unlink(missing_ok=True)
    say(p, "merge-interrupted", f"Interrupted merge of PR #{n} ({merge_id}) settled: not merged.")
    print(f"ok reconcile: PR #{n} ({merge_id}) recorded not-merged: {why}")
    return 0


def merge_records(p: Project) -> list[dict]:
    out = []
    for f in sorted(p.merges.glob("merge-*.json")) if p.merges.is_dir() else []:
        if ".tmp-" in f.name:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Failed(f"merges/{f.name} cannot be read ({e})") from None
        if isinstance(d, dict) and d.get("format") == "merge":
            out.append(d)
    return out


def baseline(p: Project, tip: str) -> str:
    """The walk's start (C8 section 6): `main_after` of the project's first baseline, written by its first
    pass at the tip, so nothing before the install is an outside write."""
    found = sorted(f for f in p.merges.glob("baseline-*.json") if ".tmp-" not in f.name) if p.merges.is_dir() else []
    if found:
        try:
            start = json.loads(found[0].read_text(encoding="utf-8"))["main_after"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise Failed(f"merges/{found[0].name} cannot be read ({e})") from None
        if not SHA.fullmatch(str(start)):
            raise Failed(f"merges/{found[0].name}'s main_after is not a commit")
        return start
    bid = workfiles.event_id("baseline", None, tip)
    workfiles.write_atomic(p.merges / f"{bid}.json", json.dumps(
        {"format": "baseline", "version": 1, "id": bid, "main_after": tip, "written_at": workfiles.utc_iso()},
        indent=1) + "\n")
    print(f"ok baseline: merges/{bid}.json at {tip[:12]}; nothing before it is an outside write")
    return tip


def outside_writes(p: Project, lock: kitlock.Lock) -> int:
    """Step 2: each first-parent commit from the baseline to origin/<default> that no record names gets an
    outside record (decisions 69, 95, 99). The walk starts at the baseline, not at the newest record, so an
    outside commit a guarded merge then landed on top of is still found. One post-merge run on the newest
    is written into each; red is red main. 3 when red, else 0."""
    git(p.main, "fetch", "-q", "origin")
    tip = git(p.main, "rev-parse", f"origin/{p.default}")
    start = baseline(p, tip)
    named = set()
    for d in merge_records(p):
        named.update(str(d[k]) for k in ("merge_commit", "commit") if d.get(k))
    found = [c for c in git(p.main, "rev-list", "--first-parent", f"{start}..{tip}").split() if c not in named]
    if not found:
        return 0
    rows = []
    for c in reversed(found):  # oldest first: the ids keep the order
        pr = pr_of_commit(p, c)
        branch = pr.get("head", {}).get("ref") if pr else None
        m = re.fullmatch(r"t(\d+)", branch or "")
        rows.append({"commit": c, "pr": pr.get("number") if pr else None, "branch": branch,
                     "title": pr.get("title") if pr else git(p.main, "log", "-1", "--format=%s", c),
                     "ticket": int(m.group(1)) if m else None,
                     "id": workfiles.event_id("merge", int(m.group(1)) if m else None, c)})
    newest = rows[-1]
    label = ", ".join(f"PR #{r['pr']}" if r["pr"] else r["commit"][:12] for r in rows)
    control, paid = outside_needs(p, rows)
    print(f"outside write(s) on {p.default}: {label}; running the post-merge run on {newest['commit'][:12]}"
          f"{' with the machinery tests' if control else ''}", flush=True)
    post = clean_run(p, newest["id"], "post", newest["commit"], None, control, popen=lock.popen)
    print(run_line("post", post), flush=True)
    stop = revert = None
    if red(post):
        stop, revert = red_main(p, newest["id"], newest["ticket"], f"outside write {label}"[:60], found, post)
    for r in rows:
        wt = remove_worktree(p, r["branch"], r["commit"]) if r["branch"] else None
        data = {"format": "merge", "version": 1, "id": r["id"], "result": "merged", "entry": "outside",
                "recovered": False, "repository": p.repo, "pr": r["pr"], "ticket": r["ticket"],
                "branch": r["branch"], "title": r["title"], "class": None, "yours_because": [], "kind": "outside",
                "clearance": {"by": "none"}, "commit": r["commit"], "merge_commit": r["commit"],
                "main_before": (parents(p.main, r["commit"]) or [None])[0], "main_after": tip, "tag": None,
                "paid_suite": paid[r["commit"]], "post_run": post, "run_on": newest["commit"], "stop": stop,
                "revert_pr": revert, "worktree": wt, "counts_toward_earning": False, "earning_after": None,
                "kit_version": kit_version(p.main), "recorded_at": workfiles.utc_iso()}
        stamp = event_time("merge", r["id"].split("-")[1], data)
        data["earning_after"] = earning_now(p, [(stamp, "merge", f"{r['id']}.json", data)])
        workfiles.write_atomic(p.merges / f"{r['id']}.json", json.dumps(data, indent=1) + "\n")
        print(f"ok outside write: {r['commit'][:12]} ({'PR #' + str(r['pr']) if r['pr'] else 'no PR'}) recorded as "
              f"merges/{r['id']}.json; not counted")
    say(p, "outside-write", f"Outside write(s) on {p.default}: {label}; post-merge run {post['result']}"[:190])
    return 3 if red(post) else 0


def outside_needs(p: Project, rows: list[dict]) -> tuple[bool, dict]:
    """What the outside writes' runs owe C8 section 7, from the paths each commit changed against its
    first parent: the machinery tests if any changed control code (review round 1: a web merge of kit code
    ran without them), and per commit whether its paid suite is due, which `reconcile` then runs after the
    merge lock is released."""
    control, paid = False, {}
    for r in rows:
        first = (parents(p.main, r["commit"]) or [None])[0]
        changed = changed_paths(p.main, first, r["commit"]) if first else \
            git(p.main, "show", "--name-only", "--format=", r["commit"]).splitlines()
        control = control or any(is_control_code(x) for x in changed)
        paid[r["commit"]] = paid_due(p, changed)
    return control, paid


def pr_of_commit(p: Project, commit: str) -> dict | None:
    """The PR GitHub associates with a commit on main (`gh api repos/<o>/<r>/commits/<sha>/pulls`, M106):
    the one whose merge commit it is, else the first, else None. That index can lag a fresh merge by seconds
    (M218: still `[]` 7 s after T17's API merge), so without its merge commit there the PR the commit's subject
    names (`Merge pull request #<N> from ...`, a squash's `... (#<N>)`) is read and kept only when GitHub
    names this commit as its merge commit."""
    rows = json.loads(gh(p.main, "api", f"repos/{p.repo}/commits/{commit}/pulls").stdout or "[]")
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    found = next((r for r in rows if r.get("merge_commit_sha") == commit), None)
    subject = git(p.main, "log", "-1", "--format=%s", commit)
    named = re.match(r"Merge pull request #(\d+) ", subject) or re.search(r"\(#(\d+)\)$", subject)
    if found is None and named:
        r = gh(p.main, "api", f"repos/{p.repo}/pulls/{named.group(1)}", check=False)
        try:
            pr = json.loads(r.stdout) if r.returncode == 0 else None
        except ValueError:
            pr = None
        if isinstance(pr, dict) and pr.get("merge_commit_sha") == commit:
            found = pr
    return found or (rows[0] if rows else None)


def say(p: Project, kind: str, text: str) -> None:
    """A notice (C6 section 7); one that cannot be written is printed, never fatal."""
    try:
        notices.write(p.coordination, kind, text)
    except (OSError, ValueError) as e:
        print(f"note: the {kind} notice could not be written: {e}")


# ---------------------------------------------------------------- red main: the stop and the revert PR (C8 section 9)


def red_main(p: Project, merge_id: str, ticket: int | None, label: str, commits: list[str],
             run_: dict) -> tuple[str, int | None]:
    """Write `merges/stop-<id>.json`, then open a revert PR of `commits` (newest first) from a temporary
    worktree of origin/<default>; a conflicting revert opens none. (stop id, revert PR number or None)."""
    stop_id = workfiles.event_id("stop", ticket, commits[0])
    workfiles.write_atomic(p.merges / f"{stop_id}.json", json.dumps(
        {"format": "stop", "version": 1, "id": stop_id, "reason": f"red main: {run_['log']} is {run_['result']} on "
         f"{run_['commit'][:12]}", "merge": merge_id, "written_at": workfiles.utc_iso()},
        indent=1) + "\n")
    print(f"RED MAIN: automatic merges stopped (merges/{stop_id}.json)", flush=True)
    revert = None
    try:
        revert = open_revert(p, merge_id, label, commits, run_)
    except Failed as e:
        print(f"note: no revert PR: {e}")
    say(p, "red-main", f"Red main after {label} ({merge_id}): " + (f"revert PR #{revert} opened" if revert else
        "no revert PR (revert by hand)") + "; automatic merges stopped.")
    return stop_id, revert


def open_revert(p: Project, merge_id: str, label: str, commits: list[str], run_: dict) -> int | None:
    git(p.main, "fetch", "-q", "origin")
    wt = scratch(p, "revert")
    git(p.main, "worktree", "add", "-q", "--detach", str(wt), git(p.main, "rev-parse", f"origin/{p.default}"))
    try:
        for c in commits:
            r = run(["git", "revert", "--no-edit", *(["-m", "1"] if len(parents(p.main, c)) == 2 else []), c], wt,
                    check=False)
            if r.returncode != 0:
                run(["git", "revert", "--abort"], wt, check=False)
                print(f"note: reverting {c[:12]} conflicts: no revert PR; revert it by hand")
                return None
        head, branch = git(wt, "rev-parse", "HEAD"), f"revert/{merge_id}"
        git(wt, "push", "-q", "origin", f"{head}:refs/heads/{branch}")
    finally:
        drop_worktree(p, wt)
    try:
        tail = (p.coordination / run_["log"]).read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    except OSError:
        tail = ["(the log could not be read)"]
    fence = "````"
    body = (f"Red main after {label} ({merge_id}): the run on {run_['commit'][:12]} is {run_['result']}; "
            f"automatic merges are stopped.\n\nThe run log's last 40 lines (`{run_['log']}`):\n\n{fence}text\n"
            + "\n".join(tail) + f"\n{fence}\n\nMerge it in your mode: `python -I .agents/kit/bin/merge.py yours "
            f"<this PR's number> --head {head[:12]}` (`kit merge` from step 7); then "
            "`merge.py resume --reason <text>` restarts automatic merges.\n")
    title = f"Revert {label}: red main after {merge_id}"
    url = gh(p.main, "pr", "create", "--repo", p.repo, "--base", p.default, "--head", branch, "--title", title,
             "--body", body).stdout.strip()
    number = int(url.rsplit("/", 1)[1])
    print(f"revert PR #{number} opened: {url}", flush=True)
    return number


# ---------------------------------------------------------------- the merged ticket's worktree (C8 section 10)


def list_sessions(cwd: Path) -> list[dict]:
    """Every session `claude agents --json` lists (M50: each row has `id`, `name`, `cwd`). A failed listing
    is Failed: an empty one would remove a worktree a session still works in."""
    r = run(["claude", "agents", "--json"], cwd, check=False, env=launch.clean_env())
    try:
        rows = json.loads(r.stdout) if r.returncode == 0 else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        raise Failed(f"claude agents --json failed (exit {r.returncode})")
    return [row for row in rows if isinstance(row, dict)]


def stop_session(session: str, cwd: Path) -> bool:
    return run(["claude", "stop", session], cwd, check=False, env=launch.clean_env()).returncode == 0


def inside(path: str, folder: Path) -> bool:
    a, b = os.path.normcase(str(Path(path).resolve())), os.path.normcase(str(folder.resolve()))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def remove_worktree(p: Project, branch: str | None, commit: str) -> dict:
    """The `git worktree list` entry on the PR's head branch (`t<n>` or `control/<topic>`), never another:
    sessions working in it are stopped first (a session ends when its ticket merges), then it is removed only
    when clean and integrated (reachable from origin/<default>, or tree-equal to the PR's merge commit: a
    squash, even after main moved on), with `git worktree remove`, never `--force`. Branches are kept."""
    out = {"path": None, "removed": False, "kept_because": None, "sessions_stopped": []}
    if not re.fullmatch(r"t\d+|control/\S+", branch or ""):
        out["kept_because"] = "not a ticket or control branch"
        return out
    try:
        wt = None
        for block in git(p.main, "worktree", "list", "--porcelain").split("\n\n"):
            lines = dict(line.split(" ", 1) if " " in line else (line, "") for line in block.splitlines())
            if lines.get("branch") == f"refs/heads/{branch}":
                wt = Path(lines["worktree"])
        if wt is None:
            out["kept_because"] = f"no worktree on {branch}"
            return out
        try:
            out["path"] = wt.resolve().relative_to(p.main.resolve()).as_posix()
        except ValueError:
            out["path"] = wt.as_posix()
        if os.path.normcase(str(wt.resolve())) == os.path.normcase(str(p.main.resolve())):
            raise Failed("it is the main checkout")
        for row in list_sessions(p.main):
            if row.get("cwd") and inside(str(row["cwd"]), wt):
                who = str(row.get("id") or row.get("name"))
                if not stop_session(who, p.main):
                    raise Failed(f"session {row.get('name') or who} could not be stopped")
                out["sessions_stopped"].append(str(row.get("name") or who))
        dirty = git(wt, "status", "--porcelain", "--untracked-files=all")
        if dirty:
            raise Failed(f"it has uncommitted or untracked files ({dirty.splitlines()[0].strip()})")
        ahead = git(wt, "rev-list", "--count", f"origin/{p.default}..HEAD")
        if ahead != "0":
            same = run(["git", "diff", "--quiet", commit, "HEAD"], wt, check=False).returncode
            if same not in (0, 1):
                raise Failed(f"git diff {commit[:12]} HEAD failed")
            if same == 1:
                raise Failed(f"its HEAD is not on origin/{p.default} and its tree is not the merge's ({commit[:12]})")
        r = run(["git", "worktree", "remove", str(wt)], p.main, check=False)
        if r.returncode != 0:
            raise Failed(f"git worktree remove: {' '.join((r.stderr or r.stdout).split())[:200]}")
        out["removed"] = True
        print(f"ok worktree: {out['path']} removed (branch {branch} kept)")
    except Failed as e:
        out["kept_because"] = str(e)
        say(p, "worktree-kept", f"Kept the worktree of {branch} ({out['path']}): {e}"[:190])
        print(f"note: kept the worktree of {branch}: {e}")
    return out


# ---------------------------------------------------------------- the paid suite (C8 section 7)


def paid_result(p: Project, merge_id: str) -> str | None:
    for f in sorted(p.merges.glob("paid-*.json")) if p.merges.is_dir() else []:
        if ".tmp-" in f.name:
            continue
        try:
            if json.loads(f.read_text(encoding="utf-8")).get("merge") == merge_id:
                return f.name
        except (OSError, ValueError, AttributeError) as e:
            raise Failed(f"merges/{f.name} cannot be read ({e})") from None
    return None


def run_paid(p: Project, merge_id: str, commit: str, ticket: int | None, label: str) -> int:
    """The paid suite for one merge, after the merge lock is released, under its own lock
    `locks/paid-<merge id>.lock` for the whole run: one still running holds it, an abandoned one's is free.
    Once held, a result for that merge means the run finished: not repeated. The result's id carries the time
    the run ended (C4 rule 6), so the earning walk orders a late red after the merges before it ended."""
    try:
        lock = kitlock.claim(p.coordination / "locks" / f"paid-{merge_id}.lock",
                             {"format": "paid-lock", "version": 1, "id": merge_id, "host": socket.gethostname()})
    except kitlock.Busy as busy:
        print(f"-- paid suite for {merge_id}: running in pid {(busy.holder or {}).get('pid', '?')}; not started again")
        return 0
    HELD["lock"] = lock
    try:
        done = paid_result(p, merge_id)
        if done:
            print(f"-- paid suite for {merge_id}: finished already (merges/{done}); not run again")
            return 0
        hook(p, "paid-start")
        r = clean_run(p, merge_id, "paid", commit, None, False, popen=lock.popen, argv=p.value("merge.paid_suite"))
        print(run_line("paid", r), flush=True)
        pid = workfiles.event_id("paid", ticket, commit)  # the run's end
        stop = revert = None
        if red(r):
            stop, revert = red_main(p, merge_id, ticket, label, [commit], r)
        workfiles.write_atomic(p.merges / f"{pid}.json", json.dumps(
            {"format": "paid", "version": 1, "id": pid, "merge": merge_id, "commit": commit, "run": r, "stop": stop,
             "revert_pr": revert, "written_at": workfiles.utc_iso()}, indent=1) + "\n")
        print(f"ok paid suite: merges/{pid}.json")
        return 3 if red(r) else 0
    finally:
        HELD["lock"] = None
        lock.release()


def paid_due_now(p: Project) -> int:
    """Step 3 of `reconcile`, after the merge lock is released: every merge whose paid suite is due and has
    no result."""
    code = 0
    for d in merge_records(p):
        if d.get("result") == "merged" and d.get("paid_suite") == "due" and not paid_result(p, str(d.get("id"))):
            code = max(code, run_paid(p, str(d["id"]), str(d["merge_commit"]), d.get("ticket"),
                                      f"PR #{d.get('pr')}"))
    return code


# ---------------------------------------------------------------- item 3: the PR


def pr_view(p: Project, n: int) -> dict:
    return json.loads(gh(p.main, "pr", "view", str(n), "--repo", p.repo, "--json", FIELDS).stdout)


def pr_open(p: Project, n: int, pr: dict) -> None:
    if pr["state"] != "OPEN":
        raise Refused("PR", f"PR #{n} is {pr['state'].lower()}", "an open PR")
    if pr["isDraft"]:
        raise Refused("PR", f"PR #{n} is a draft", "gh pr ready <N> once it is cleared")
    if pr["baseRefName"] != p.default:
        raise Refused("PR", f"PR #{n} is based on {pr['baseRefName']}, not {p.default}",
                      f"merge its lower PR first, then retarget it to {p.default}")
    owner = (pr.get("headRepositoryOwner") or {}).get("login")
    if pr.get("isCrossRepository") or owner != p.repo.split("/")[0]:
        raise Refused("PR", f"PR #{n}'s branch is in another repository ({owner})", "a branch in this repository")
    print(f"ok PR: #{n} open, {pr['headRefName']} into {p.default}, head {pr['headRefOid'][:12]}")


def fetch_head(p: Project, branch: str, head: str) -> None:
    git(p.main, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
    if run(["git", "cat-file", "-e", f"{head}^{{commit}}"], p.main, check=False).returncode != 0:
        raise Failed(f"the PR's head {head[:12]} is not on origin's {branch} any more; rerun")


# ---------------------------------------------------------------- item 4: class and eligibility (C8 section 2)


def changed_paths(cwd: Path, base: str, head: str) -> list[str]:
    """Every path of the whole diff, both sides of renames and deleted paths."""
    words = run(["git", "diff", "--name-status", "-M", "-z", f"{base}...{head}"], cwd).stdout.split("\0")
    out, i = [], 0
    while i < len(words) and words[i]:
        status = words[i]
        take = 2 if status[:1] in ("R", "C") else 1
        out += words[i + 1:i + 1 + take]
        i += 1 + take
    return list(dict.fromkeys(out))


def is_control_code(path: str) -> bool:
    """Files that run or configure what runs (C8 section 11, decision 114)."""
    low = path.lower()
    return (low.endswith(CODE) or matches(path, CONTROL_CONFIG)
            or (matches(path, [".agents/kit/**"]) and not low.endswith(".md")))


def classify(paths: list[str], branch: str, control_paths: list[str], your_paths: list[str], body: str = "") -> dict:
    """The class by path (section 2), the control code and instruction text in it, and what the PR body says
    of instruction text (section 11): `kit_change` and, for a customization, the prose shape's problem."""
    yours = [x for x in paths if matches(x, list(control_paths) + list(your_paths))]
    revert = branch.startswith(("revert/", "revert-", "kit-rollback-"))  # kit-rollback-<tag>: issue #181
    text = [x for x in paths if x.lower().endswith(".md") and matches(x, control_paths)]
    change = kit_change(body)
    return {"class": "yours" if yours or revert else "ticket", "yours_because": yours[:20], "revert": revert,
            "code": [x for x in paths if is_control_code(x)], "text": text, "kit_change": change,
            "prose": prose_problem(body, text) if text and change == "customization" else None}


# ---------------------------------------------------------------- item 6: the prose PR shape (C8 section 11)


PROSE_HEADINGS = ("## Instructions changed", "## Behaviour that should change", "## Before and after")


def kit_change(body: str | None) -> str:
    """The body's first line, `Kit change: customization` or `Kit change: workflow unit`; a missing or other
    line reads as a workflow unit (the safe reading, decision 114)."""
    lines = (body or "").replace("\r\n", "\n").split("\n")
    return "customization" if lines[0].strip() == "Kit change: customization" else "workflow unit"


def filled(text: str) -> bool:
    """A section says something: not empty, and not only the template's `<...>` placeholders and labels."""
    left = re.sub(r"<[^>\n]*>|^\s*(?:[-*]|Before:|After:)|[`:]", "", text, flags=re.MULTILINE)
    return bool(left.strip())


def prose_problem(body: str | None, text_paths: list[str]) -> str | None:
    """The first part of the prose shape the body lacks, or None: the three headings in order, each section
    filled, and every changed instruction-text path named under Instructions changed."""
    lines = (body or "").replace("\r\n", "\n").split("\n")[1:]
    at = {}
    for heading in PROSE_HEADINGS:
        found = [i for i, line in enumerate(lines) if line.strip() == heading]
        if not found:
            return heading
        at[heading] = found[0]
    starts = [at[h] for h in PROSE_HEADINGS]
    if starts != sorted(starts):
        return "the headings in order (" + ", ".join(PROSE_HEADINGS) + ")"
    sections = {}
    for k, heading in enumerate(PROSE_HEADINGS):
        # a section ends at the next heading of its level or above, so a footer after the last one
        # (`## Validation`, test output) does not fill it (review round 1)
        end = next((i for i in range(starts[k] + 1, len(lines)) if re.match(r"#{1,2}\s", lines[i])), len(lines))
        sections[heading] = "\n".join(lines[starts[k] + 1:end])
        if not filled(sections[heading]):
            return f"the text under {heading}"
    named = folded(sections[PROSE_HEADINGS[0]])
    for path in text_paths:
        if folded(path) not in named:
            return f"`{path}` under {PROSE_HEADINGS[0]}"
    return None


def folded(text: str) -> str:
    text = text.replace("\\", "/")
    return text.lower() if os.name == "nt" else text


def eligibility(entry: str, cls: dict, approved: bool, earning: dict, auto_merge: bool, earn_after: int,
                n: int) -> tuple[str, str]:
    """(kind, clearance.by) for this PR and entry point, or Refused (C8 section 2's table)."""
    yours_cmd = f"you merge it: merge.py yours {n} --head <12 hex> (kit merge {n} from step 7)"
    if entry == "auto":
        if cls["class"] == "yours":
            why = cls["yours_because"][0] if cls["yours_because"] else "a revert branch"
            raise Refused("class", f"PR #{n} is always yours ({why})", yours_cmd)
        if not approved:
            raise Refused("clearance", f"PR #{n} has no approving verdict", f"a review of its head, or {yours_cmd}")
        if not auto_merge:
            raise Refused("auto merge", "tickets.auto_merge is off", f"{yours_cmd}; automatic merges start when you "
                          "turn tickets.auto_merge on (C8 section 2)")
        if earning["stopped"]:
            raise Refused("stopped", "automatic merges are stopped", "merge.py resume --reason <text> (yours)")
        if not earning["earned"]:
            raise Refused("earned", f"not earned: {earning['clean_streak']} of {earn_after}", yours_cmd)
        return "ticket", "verdict"
    if cls["class"] == "ticket":
        return ("ticket", "verdict") if approved else ("known-limitation", "your command")
    approved_kind = "revert" if cls["revert"] else "control"  # a revert is a hand-back however it is cleared
    if cls.get("pure_revert"):  # decision 117: the inverse of a merge main had needs no Codex approval
        return "revert", "your command"
    impure = f" (not a pure revert: {cls['impure_because']})" if cls.get("impure_because") else ""
    if cls["code"]:
        if approved:
            return approved_kind, "verdict"
        raise Refused("Codex approval", f"control code {cls['code'][0]} needs a Codex approval bound to the "
                      f"head{impure}", "a review of the head (review.py --ticket <n> --branch <branch> --head <sha>)")
    if cls["text"]:
        if approved:
            return approved_kind, "verdict"
        if cls.get("kit_change") != "customization":
            raise Refused("Codex approval", f"instruction text {cls['text'][0]} shipped as a workflow unit (the PR "
                          "body's first line is not `Kit change: customization`) needs a Codex approval bound to "
                          f"the head{impure}", "a review of the head, or for a customization `Kit change: customization` "
                          "and the body in .agents/kit/templates/prose-pr.md's shape")
        if cls.get("prose"):
            raise Refused("prose shape", f"{cls['prose']} missing",
                          "the body in .agents/kit/templates/prose-pr.md's shape, or a Codex approval")
        return ("revert" if cls["revert"] else "prose"), "your command"
    return ("revert", "your command") if cls["revert"] else ("spec", "your command")


# ---------------------------------------------------------------- the earning state (C8 section 8)


def front_matter(text: str) -> dict:
    """The `key: value` lines of a Markdown event file's front matter (C4 rule 7)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("no front matter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("its front matter is not closed")
    return {k.strip(): v.strip() for k, v in (x.split(":", 1) for x in lines[1:end] if ":" in x)}


def events(merges: Path) -> list[tuple[str, str, str, dict]]:
    """(UTC, kind, file name, content) for each event file, in time order: `event_time` (a merge record's
    `recorded_at`, every other file's id UTC part, C4 rule 6)."""
    out = []
    for f in sorted(merges.iterdir()) if merges.is_dir() else []:
        m = EVENT.fullmatch(f.name)
        if not m or ".tmp-" in f.name:
            continue
        try:
            text = f.read_text(encoding="utf-8")
            data = json.loads(text) if m.group(3) == "json" else front_matter(text)
        except (OSError, ValueError) as e:
            raise Failed(f"merges/{f.name} cannot be read ({e}), so the earning state is unknown") from None
        out.append((event_time(m.group(1), m.group(2), data), m.group(1), f.name, data))
    return sorted(out, key=lambda e: (e[0], e[2]))


def event_time(kind: str, stamp: str, data: dict) -> str:
    """When an event counts: a merge record when it was recorded (under the lock, so in merge order; its id
    carries the attempt's start, before the clean run and the lock wait: review round 1), the rest by their
    ids (a paid result's id carries the run's end)."""
    recorded = data.get("recorded_at") if kind == "merge" else None
    if isinstance(recorded, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", recorded):
        return recorded.replace("-", "").replace(":", "")
    return stamp


def red(run_: object) -> bool:
    return isinstance(run_, dict) and run_.get("result") in ("red", "timeout")


def earning(evts, earn_after: int, hand_back_after: int) -> dict:
    """Walk the events: a counting merge adds to the clean streak; a hand-back (a merged revert, a red
    post-merge run or paid suite, `hand_back_after` escalations in a row) resets it; a stop stops automatic
    merges until a resume (decisions 17, 70, 112)."""
    clean = esc = 0
    stopped = False
    for _, kind, _, d in evts:
        if kind == "merge":
            if d.get("counts_toward_earning"):
                clean, esc = clean + 1, 0
            elif red(d.get("post_run")) or (d.get("result") == "merged" and d.get("kind") == "revert"):
                clean = 0
        elif kind == "escalation":
            esc += 1
            if esc >= hand_back_after:
                clean, esc = 0, 0
        elif kind == "paid" and red(d.get("run")):
            clean = 0
        elif kind == "stop":
            stopped = True
        elif kind == "resume":
            stopped = False
    return {"clean_streak": clean, "escalation_streak": esc, "earned": clean >= earn_after, "stopped": stopped}


def earning_now(p: Project, extra=()) -> dict:
    evts = events(p.merges) + list(extra)
    return earning(sorted(evts, key=lambda e: (e[0], e[2])), int(p.value("tickets.earn_after")),
                   int(p.value("tickets.hand_back_after_escalations")))


# ---------------------------------------------------------------- item 5: head binding (C8 section 4)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def approving_verdict(coordination: Path, branch: str, repo: str) -> tuple[dict | None, list[str]]:
    """The newest approving verdict for `branch` in `repo` whose review record names it by path and hash with
    the same head (decision 93), as {path, verdict, record}; and why each other approving one is not one."""
    best, skipped = None, []
    for vp in sorted((coordination / "verdicts").glob("*/round-*.json")):
        if ".tmp-" in vp.name:
            continue
        rel = vp.relative_to(coordination).as_posix()
        try:
            raw = vp.read_bytes()
            v = json.loads(raw)
        except (OSError, ValueError):
            skipped.append(f"{rel}: not JSON")
            continue
        if not (isinstance(v, dict) and v.get("format") == "verdict" and v.get("outcome") == "approved"
                and v.get("branch") == branch):
            continue
        why = None
        rid, head = str(v.get("id", "")), str(v.get("head", ""))
        if v.get("repository") != repo:
            why = f"its repository is {v.get('repository')}, not {repo}"
        elif not SHA.fullmatch(head) or not re.fullmatch(r"review-[0-9A-Za-z-]+", rid):
            why = "its head or id is malformed"
        else:
            try:
                rec = json.loads((coordination / "reviews" / f"{rid}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                rec, why = None, f"no review record reviews/{rid}.json"
            if rec is not None:
                named = rec.get("verdict")
                if (rec.get("format"), rec.get("id"), rec.get("head")) != ("review", rid, head):
                    why = "its review record is for another review or head"
                elif not named or (coordination / str(named)).resolve() != vp.resolve():
                    why = "its review record names another verdict"
                elif rec.get("verdict_sha256") != sha256(raw):
                    why = "its bytes differ from the hash its review record holds"
        if why:
            skipped.append(f"{rel}: {why}")
            continue
        key = (str(v.get("written_at", "")), rid)
        if best is None or key > best[0]:
            best = (key, {"path": rel, "verdict": v, "record": rec})
    return (best[1] if best else None), skipped


def update_chain(cwd: Path, ref: str, head: str, main_ref: str) -> list[str] | str:
    """The clean-update commits from `ref` to `head`, oldest first ([] when they are equal), or why `head`
    is not `ref` plus a clean update from main (checklist AU3, AU5)."""
    if head == ref:
        return []
    if not is_ancestor(cwd, ref, head):
        return f"{ref[:12]} is not an ancestor of {head[:12]} (a rebase or another history)"
    chain, c = [], head
    while c != ref:
        ps = parents(cwd, c)
        if len(ps) != 2:
            return f"{c[:12]} is not a merge from main (a commit after approval)"
        p1, p2 = ps
        if not is_ancestor(cwd, p2, main_ref):
            return f"{c[:12]} merges {p2[:12]}, which is not on {main_ref}"
        r = run(["git", "merge-tree", "--write-tree", p1, p2], cwd, check=False)
        if r.returncode not in (0, 1):
            raise Failed(f"git merge-tree --write-tree {p1[:12]} {p2[:12]}: {r.stderr.strip()[:300]}")
        if r.returncode == 1:
            return f"{c[:12]} resolves a conflict by hand"
        if r.stdout.split()[0] != git(cwd, "rev-parse", f"{c}^{{tree}}"):
            return f"{c[:12]}'s tree is not the clean merge of its parents (changed by hand)"
        chain.append(c)
        c = p1
        if len(chain) > 200:
            return "more than 200 updates from main"
    if set(git(cwd, "rev-list", "--ancestry-path", f"{ref}..{head}").split()) != set(chain):
        return f"the history from {ref[:12]} to {head[:12]} holds commits off the update chain"
    return list(reversed(chain))


def bind(cwd: Path, ref: str, head: str, main_ref: str, what: str, valid: str) -> list[str]:
    chain = update_chain(cwd, ref, head, main_ref)
    if isinstance(chain, str):
        raise Refused("head", f"{what} is for {ref}; the head is {head}: {chain}", valid)
    return chain


def resolve_shown(cwd: Path, shown: str) -> str:
    r = run(["git", "rev-parse", "--verify", "--quiet", f"{shown}^{{commit}}"], cwd, check=False)
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", shown) or r.returncode != 0:
        raise Refused("head", f"--head {shown} is not a commit here", "--head <12 hex> as merge.py printed it")
    return r.stdout.strip()


# ---------------------------------------------------------------- the refresh (AU5) and the clean runs (C8 section 7)


def scratch(p: Project, stage: str) -> Path:
    return p.main / ".claude" / "worktrees" / f"merge-{secrets.token_hex(2)}-{stage}"


def drop_worktree(p: Project, wt: Path) -> None:
    run(["git", "worktree", "remove", "--force", str(wt)], p.main, check=False)
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
        run(["git", "worktree", "prune"], p.main, check=False)


def refresh(p: Project, branch: str, head: str, main_sha: str) -> str:
    """Merge `main_sha` (origin/<default> as this run read it, never the shared ref again: another run may
    have fetched a newer one) into the head in a temporary worktree and push it to the PR branch: a clean
    update by construction. A conflict refuses."""
    wt = scratch(p, "refresh")
    git(p.main, "worktree", "add", "-q", "--detach", str(wt), head)
    try:
        r = run(["git", "merge", "--no-edit", "-q", "-m", f"Merge {p.default} into {branch} (kit merge refresh)",
                 main_sha], wt, check=False)
        if r.returncode != 0:
            conflicted = git(wt, "diff", "--name-only", "--diff-filter=U", check=False)
            run(["git", "merge", "--abort"], wt, check=False)
            if conflicted:
                raise Refused("refresh", f"merging origin/{p.default} into {head[:12]} conflicts in "
                              f"{conflicted.splitlines()[0]}", "the builder merges main; back to review")
            raise Failed(f"git merge origin/{p.default}: {' '.join((r.stderr or r.stdout).split())[:300]}")
        new = git(wt, "rev-parse", "HEAD")
        pushed = run(["git", "push", "-q", "origin", f"{new}:refs/heads/{branch}"], wt, check=False)
        if pushed.returncode != 0:
            raise Refused("refresh", f"pushing the update to {branch} failed: "
                          f"{' '.join(pushed.stderr.split())[:200]}", "rerun: the branch may have moved")
    finally:
        drop_worktree(p, wt)
    print(f"ok refresh: merged {p.default} {main_sha[:12]} into {branch} as {new[:12]}, pushed")
    return new


def kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    proc.kill()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def clean_run(p: Project, merge_id: str, stage: str, commit: str, changed: list[str] | None, control: bool,
              popen=subprocess.Popen, tag: str = "", argv=None) -> dict:
    """`merge.clean_run` (and, with control code, the machinery tests), or `argv` (the paid suite), in a
    temporary worktree of `commit`, with the secret files copied in and a calling session's markers stripped.
    Before the merge the changed paths are in the file KIT_CHANGED_PATHS_FILE names; after it the variable is
    not set. Red: a non-zero exit, or none within merge.run_timeout_minutes (the tree is killed)."""
    argv = [str(a) for a in (p.value("merge.clean_run") if argv is None else argv)]
    minutes = p.value("merge.run_timeout_minutes")
    timeout = float(minutes) * 60
    log_rel = f"merges/logs/{merge_id}-{stage}{tag}.log"
    log = p.coordination / log_rel
    log.parent.mkdir(parents=True, exist_ok=True)
    env = launch.clean_env()
    env.pop("KIT_CHANGED_PATHS_FILE", None)
    env["KIT_RUN"] = "paid" if stage == "paid" else f"merge-{stage}"
    if changed is not None:
        listed = p.coordination / f"merges/logs/{merge_id}-{stage}{tag}-paths.txt"
        workfiles.write_atomic(listed, "".join(f"{x}\n" for x in changed))
        env["KIT_CHANGED_PATHS_FILE"] = str(listed)
    secret_entries = list(p.value("secret_files"))
    launch.check_secret_entries(secret_entries)
    commands = [argv] + ([[sys.executable, "-I", "-m", "unittest", "discover", "-s", ".agents/kit/tests"]]
                         if control else [])
    wt = scratch(p, stage)
    git(p.main, "worktree", "add", "-q", "--detach", str(wt), commit)
    start, result, code = time.monotonic(), "green", 0
    try:
        launch.copy_secrets(p.main, wt, secret_entries)
        with open(log, "w", encoding="utf-8", errors="replace") as out:
            out.write(f"# {merge_id} {stage}{tag} run of {commit} in {wt.as_posix()}\n")
            for cmd in commands:
                out.write(f"$ {' '.join(cmd)}\n")
                out.flush()
                try:
                    proc = popen(cmd, cwd=wt, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
                except OSError as e:
                    out.write(f"could not start: {e}\n")
                    result, code = "red", None
                    break
                try:
                    code = proc.wait(timeout=max(1.0, start + timeout - time.monotonic()))
                except subprocess.TimeoutExpired:
                    kill_tree(proc)
                    out.write(f"\nno exit within merge.run_timeout_minutes ({minutes}); the tree was killed\n")
                    result, code = "timeout", None
                    break
                if code != 0:
                    result = "red"
                    break
    finally:
        drop_worktree(p, wt)
    return {"commit": commit, "result": result, "exit": code, "seconds": round(time.monotonic() - start),
            "log": log_rel}


def run_line(stage: str, r: dict) -> str:
    return f"{stage}-merge run: {r['result']} on {r['commit'][:12]} in {r['seconds']} s (exit {r['exit']}; {r['log']})"


# ---------------------------------------------------------------- the lock, the marker and the test hooks


def take_lock(p: Project, fields: dict) -> kitlock.Lock:
    """The merge lock (C8 section 5): wait while another run holds it, a line each minute, a try every 10 s."""
    path, said = p.coordination / "locks" / "merge.lock", None
    while True:
        try:
            HELD["lock"] = kitlock.claim(path, fields)
            return HELD["lock"]
        except kitlock.Busy as busy:
            if said is None or time.monotonic() - said >= WAIT_PRINT:
                h = busy.holder or {}
                what = "a reconcile pass" if h.get("entry") == "reconcile" else f"PR #{h.get('pr', '?')}"
                print(f"waiting for the merge lock: {h.get('id', 'an unknown run')}, {what}, "
                      f"since {h.get('acquired_at', '?')}", flush=True)
                said = time.monotonic()
            time.sleep(WAIT_POLL)


def hook(p: Project, stage: str) -> None:
    """KIT_MERGE_PAUSE_AT and KIT_MERGE_CRASH_AT (C8 section 13): they change no decision."""
    if os.environ.get("KIT_MERGE_CRASH_AT") == stage:
        print(f"test hook: crash at {stage}", flush=True)
        os._exit(9)
    if os.environ.get("KIT_MERGE_PAUSE_AT") == stage:
        flag = p.merges / f"paused-{stage}"
        workfiles.write_atomic(flag, f"{os.getpid()}\n")
        print(f"test hook: paused at {stage} until {flag.as_posix()} is deleted", flush=True)
        end = time.monotonic() + PAUSE_LIMIT
        while flag.exists() and time.monotonic() < end:
            time.sleep(0.5)
        flag.unlink(missing_ok=True)


def write_marker(p: Project, n: int, fields: dict) -> None:
    workfiles.write_atomic(p.merges / f"in-progress-{n}.json", json.dumps(
        {"format": "merge-in-progress", "version": 1, **fields, "pid": os.getpid(), "host": socket.gethostname(),
         "updated_at": workfiles.utc_iso()}, indent=1) + "\n")


def kit_version(main: Path) -> str | None:
    try:
        return tomllib.loads((main / "kit.lock").read_text(encoding="utf-8")).get("kit_version")
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- the readiness list (C8 section 3)


class Ready:
    """What items 1-9 found: the PR, its head, class, changed paths, kind, clearance, the approving verdict
    (or None), the head you were shown (or None) and the clean-update chain from the approved head."""


def classify_head(p: Project, branch: str, main_ref: str, head: str, body: str = "") -> tuple[list[str], dict]:
    changed = changed_paths(p.main, main_ref, head)
    cls = classify(changed, branch, kitconfig.load_schema(p.main)["fixed"]["control_paths"],
                   p.value("tickets.your_paths"), body)
    if cls["revert"]:
        cls["impure_because"] = revert_of_record(p, branch, main_ref, head)
        cls["pure_revert"] = cls["impure_because"] is None
    return changed, cls


# ---------------------------------------------------------------- the pure revert (C8 sections 2 and 9, decision 117)


def git_bytes(cwd: Path, args: list[str], data: bytes | None = None) -> bytes:
    """A git call on bytes: a diff is compared as git wrote it, never through a lossy text decode. Under a
    held lock the child is in the lock's job, as run()'s are."""
    popen = HELD["lock"].popen if HELD["lock"] is not None else subprocess.Popen
    proc = popen(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                 stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL)
    try:
        out, err = proc.communicate(data, timeout=CALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        raise Failed(f"git {' '.join(args[:2])} took longer than {CALL_TIMEOUT} s") from None
    if proc.returncode != 0:
        raise Failed(f"git {' '.join(args[:2])} exited {proc.returncode}: {err.decode('utf-8', 'replace')[:300]}")
    return out


def patch_id(cwd: Path, a: str, b: str) -> str:
    """`git patch-id --stable` of the diff from `a` to `b` ('' for an empty diff), as `git diff-tree -p`, the
    plumbing `git diff`, writes it: no diff config of yours (an external diff, textconv, colour) changes it.
    A binary file's id hashes its `index` line, so another content is another id (PureRevert's rows)."""
    diff = git_bytes(cwd, ["diff-tree", "-p", "-r", a, b])
    words = git_bytes(cwd, ["patch-id", "--stable"], diff).decode("ascii", "replace").split() if diff else []
    return words[0] if words else ""


def pure_revert(cwd: Path, merge_commit: str, main_ref: str, head: str) -> str | None:
    """None when `head` is a pure revert of `merge_commit`: one commit of its own, on main, whose patch id
    equals that of `git diff <merge commit> <merge commit>^1`, plus only clean updates from main (the
    refresh); else why it is not."""
    try:
        if not is_ancestor(cwd, merge_commit, main_ref):
            return f"{merge_commit[:12]} is not on main"
        own = git(cwd, "rev-list", "--no-merges", f"{main_ref}..{head}").split()
        if len(own) != 1:
            return f"it has {len(own)} commits of its own, not one"
        ps = parents(cwd, own[0])
        if len(ps) != 1 or not is_ancestor(cwd, ps[0], main_ref):
            return f"{own[0][:12]} is not one commit on main"
        chain = update_chain(cwd, own[0], head, main_ref)
        if isinstance(chain, str):
            return chain
        want = patch_id(cwd, merge_commit, f"{merge_commit}^1")
        if not want or patch_id(cwd, ps[0], own[0]) != want:
            return f"{own[0][:12]} is not the revert of {merge_commit[:12]} (its patch id differs: edited)"
    except Failed as e:
        return str(e)
    return None


def revert_of_record(p: Project, branch: str, main_ref: str, head: str) -> str | None:
    """A revert PR this script opened (branch `revert/<merge id>`): pure_revert() against the merge commit its
    record names; a `kit rollback` PR (branch `kit-rollback-<tag>`): against the commit its one commit reverts
    (revert_of_message). None when pure, else why not."""
    if branch.startswith("kit-rollback-"):
        return revert_of_message(p.main, main_ref, head)
    m = re.fullmatch(r"revert/(merge-\d{8}T\d{6}Z-[0-9A-Za-z-]+)", branch)
    if not m:
        return "not a revert branch this script opened (revert/<merge id>)"
    try:
        rec = json.loads((p.merges / f"{m.group(1)}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return f"merges/{m.group(1)}.json cannot be read ({e.__class__.__name__})"
    commit = rec.get("merge_commit") if isinstance(rec, dict) and rec.get("result") == "merged" else None
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        return f"merges/{m.group(1)}.json names no merge commit"
    return pure_revert(p.main, commit, main_ref, head)


def revert_of_message(cwd: Path, main_ref: str, head: str) -> str | None:
    """pure_revert() against the commit the branch's one own commit names in the message `git revert` writes, the
    first line `This reverts commit <sha>` (tools/rollback.py makes that commit; no record is read, issue #181)."""
    try:
        own = git(cwd, "rev-list", "--no-merges", f"{main_ref}..{head}").split()
        if len(own) != 1:
            return f"it has {len(own)} commits of its own, not one"
        m = re.search(r"^This reverts commit ([0-9a-f]{40})\b", git(cwd, "log", "-1", "--format=%B", own[0]), re.M)
    except Failed as e:
        return str(e)
    if not m:
        return f'{own[0][:12]}\'s message names no reverted commit ("This reverts commit <sha>")'
    return pure_revert(cwd, m.group(1), main_ref, head)


def reclassify(p: Project, n: int, entry: str, branch: str, main_ref: str, head: str, approved: bool,
               by: str, body: str = "") -> tuple[list[str], dict, str]:
    """Class and kind again after an update from main (review round 2): a file main moved into an
    always-yours path carries the ticket's edit there, so the head can be always yours now. A change of
    clearance refuses."""
    changed, cls = classify_head(p, branch, main_ref, head, body)
    kind, now_by = eligibility(entry, cls, approved, earning_now(p), bool(p.value("tickets.auto_merge")),
                               int(p.value("tickets.earn_after")), n)
    if now_by != by:
        raise Refused("class", f"after the update from main, PR #{n} is {kind} ({cls['yours_because'][:1]}), "
                      "cleared another way", "a new review round of the head")
    print(f"ok class after the update: {'always yours' if cls['class'] == 'yours' else 'ticket PR'} ({kind})")
    return changed, cls, kind


def machinery(cls: dict) -> bool:
    """Control code in an always-yours PR: the clean run adds the kit's machinery tests (decision 100)."""
    return cls["class"] == "yours" and bool(cls["code"])


def readiness(p: Project, n: int, entry: str, shown: str | None, refresh_head: bool) -> Ready:
    ready = Ready()
    main_copy(p)                                                                     # 1
    if refresh_head:                                                                 # 2
        reconcile_item(p)
    else:  # check and a bare `yours` write nothing: they only say what a pass would find
        left = markers(p)
        print(f"-- reconcile: {len(left)} marker(s) wait for a merging run or merge.py reconcile" if left
              else "-- reconcile: no marker; outside writes are recorded by a merging run")
    pr = pr_view(p, n)                                                               # 3
    pr_open(p, n, pr)
    branch, head = pr["headRefName"], pr["headRefOid"]
    fetch_head(p, branch, head)
    # main as this run read it, one commit used from here on: the shared origin/<default> ref may move under a
    # concurrent run's fetch, and the run must test, bind against and record the same main (review round 1)
    main_ref = git(p.main, "rev-parse", f"origin/{p.default}")
    changed, cls = classify_head(p, branch, main_ref, head, pr.get("body") or "")
    found, skipped = approving_verdict(p.coordination, branch, p.repo)
    for line in skipped:
        print(f"note: {line}: not an approval")
    state = earning_now(p)
    kind, by = eligibility(entry, cls, found is not None, state, bool(p.value("tickets.auto_merge")),
                           int(p.value("tickets.earn_after")), n)                      # 4
    print(f"ok class: {'always yours' if cls['class'] == 'yours' else 'ticket PR'} ({kind}), entry {entry}; "
          f"earning {state['clean_streak']} of {p.value('tickets.earn_after')}"
          f"{', stopped' if state['stopped'] else ''}")
    full_shown = resolve_shown(p.main, shown) if shown else None                      # 5
    shown_valid = f"merge.py yours {n} --head {head[:12]}, after reading its changes"
    review_valid = "a new review round of the head"
    chain = []
    if by == "verdict":
        chain = bind(p.main, found["verdict"]["head"], head, main_ref, "approval", review_valid)
    if full_shown:
        bind(p.main, full_shown, head, main_ref, "the head you were shown", shown_valid)
    if refresh_head and not is_ancestor(p.main, main_ref, head):
        head = refresh(p, branch, head, main_ref)
        changed, cls, kind = reclassify(p, n, entry, branch, main_ref, head, found is not None, by,
                                        pr.get("body") or "")
        if by == "verdict":
            chain = bind(p.main, found["verdict"]["head"], head, main_ref, "approval", review_valid)
        pr = wait_for_head(p, n, head)
    clearance = {"by": by, "verdict": None, "review_id": None, "reviewed_head": None, "standard_commit": None,
                 "standard_changed_since": None}
    if by == "verdict":
        v = found["verdict"]
        clearance.update(verdict=found["path"], review_id=v["id"], reviewed_head=v["head"],
                         standard_commit=v.get("standard_commit"),
                         standard_changed_since=standard_changed(p, v.get("standard_commit")))
        print(f"ok clearance: {found['path']} approves {v['head'][:12]}"
              f"{'' if not chain else f' plus {len(chain)} clean update(s) from main'}; the head is {head[:12]}")
    else:
        print(f"ok clearance: your command ({kind}){'; --head ' + shown if shown else ''}")
    if prose_shape(cls):  # what the body says of the instruction text, however it is cleared (review round 1)
        print(f"-- Kit change: {prose_shape(cls)} ({len(cls['text'])} instruction-text path(s))")
    if needs_codex(cls):                                                             # 6
        print(f"ok Codex approval: {found['path']} bound to the head")
    elif prose_shape(cls) == "customization" and by != "verdict":
        print(f"ok prose shape: Kit change: customization; {len(cls['text'])} instruction-text path(s) named")
    else:
        print(f"ok Codex approval: not required{' (a pure revert)' if cls.get('pure_revert') else ''}")
    if pr.get("reviewDecision") == "CHANGES_REQUESTED":                              # 7
        raise Refused("change request", f"PR #{n} has a change request", "answer it and have it dismissed")
    print("ok change request: none")
    check_comments(p, n)                                                             # 8
    mergeable(p, n, pr)                                                              # 9
    ready.pr, ready.head, ready.cls, ready.changed, ready.kind = pr, head, cls, changed, kind
    ready.clearance, ready.reference, ready.shown, ready.update_commits = clearance, found, full_shown, chain
    ready.main = main_ref
    return ready


def needs_codex(cls: dict) -> bool:
    """An always-yours PR with control code, or instruction text shipped as a workflow unit (C8 section 11),
    unless it is a pure revert (decision 117)."""
    return (cls["class"] == "yours" and not cls.get("pure_revert")
            and bool(cls["code"] or (cls["text"] and cls.get("kit_change") != "customization")))


def prose_shape(cls: dict) -> str | None:
    """The record's `prose_shape`: what the body says of the PR's instruction text, or None without any."""
    return cls.get("kit_change") if cls["class"] == "yours" and cls["text"] else None


def standard_changed(p: Project, commit: str | None) -> bool | None:
    if not commit or not SHA.fullmatch(commit):
        return None
    r = run(["git", "rev-list", "--count", f"{commit}..origin/{p.default}", "--", ".agents/skills/review/"],
            p.main, check=False)
    return int(r.stdout.strip()) > 0 if r.returncode == 0 and r.stdout.strip().isdigit() else None


def wait_for_head(p: Project, n: int, head: str, tries=10) -> dict:
    """GitHub shows a pushed head a moment later; read the PR again until it does."""
    for _ in range(tries):
        pr = pr_view(p, n)
        if pr["headRefOid"] == head:
            return pr
        time.sleep(3)
    raise Failed(f"GitHub still shows PR #{n} at {pr['headRefOid'][:12]}, not the pushed {head[:12]}")


# ---------------------------------------------------------------- item 8: the unanswered-comment rule (C8 section 12)


MARK = re.compile(r"\s*<!-- kit(?: reply-to: ([^>]*?))? -->")
THREADS = ("query($owner:String!,$name:String!,$number:Int!,$endCursor:String){repository(owner:$owner,name:$name)"
           "{pullRequest(number:$number){reviewThreads(first:100,after:$endCursor){pageInfo{hasNextPage endCursor}"
           "nodes{isResolved comments(last:1){nodes{author{login} body url}}}}}}}")


def gh_pages(p: Project, *args: str) -> list:
    """Every page of a gh api call (`--paginate --slurp`: a list of the pages)."""
    return json.loads(gh(p.main, "api", "--paginate", "--slurp", *args).stdout or "[]")


def pr_comments(p: Project, n: int) -> dict:
    """The PR's conversation comments, review bodies and review threads (each thread's last comment), and the
    login gh runs as: yours, since sessions use your account too."""
    owner, name = p.repo.split("/")
    conversation = [{"id": c["id"], "node_id": c.get("node_id"), "url": c["html_url"], "author": (c.get("user") or
                     {}).get("login"), "body": c.get("body") or "", "at": c.get("created_at") or ""}
                    for page in gh_pages(p, f"repos/{p.repo}/issues/{n}/comments") for c in page]
    reviews = [{"id": r["id"], "node_id": r.get("node_id"), "url": r["html_url"], "author": (r.get("user") or
                {}).get("login"), "body": r.get("body") or "", "at": r.get("submitted_at") or ""}
               for page in gh_pages(p, f"repos/{p.repo}/pulls/{n}/reviews") for r in page
               if r.get("state") != "PENDING"]
    threads = []
    for page in gh_pages(p, "graphql", "-f", f"query={THREADS}", "-F", f"owner={owner}", "-F", f"name={name}",
                         "-F", f"number={n}"):
        for t in page["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]:
            last = (t["comments"]["nodes"] or [None])[-1]
            threads.append({"resolved": t["isResolved"], "last": last and {
                "author": (last.get("author") or {}).get("login"), "body": last.get("body") or "", "url": last["url"]}})
    login = gh(p.main, "api", "user", "--jq", ".login").stdout.strip()
    return {"login": login, "conversation": conversation, "reviews": reviews, "threads": threads}


def unanswered(found: dict) -> tuple[list[str], list[str]]:
    """(the URLs of your unanswered comments, the URLs of other accounts' comments). Yours: by your login
    without the `<!-- kit` marker. Unanswered: a thread not resolved whose last comment is yours; a
    conversation comment or review body of yours with no later marked reply naming its id."""
    login = found["login"]

    def yours(c: dict) -> bool:
        return c["author"] == login and not MARK.match(c["body"])

    posts = found["conversation"] + [r for r in found["reviews"] if r["body"].strip()]
    replies = [(m.group(1).strip(), c["at"]) for c in posts if (m := MARK.match(c["body"])) and m.group(1)]
    out = [t["last"]["url"] for t in found["threads"] if not t["resolved"] and t["last"] and yours(t["last"])]
    for c in posts:
        if yours(c) and not any(ref in (str(c["id"]), str(c["node_id"])) and at >= c["at"] for ref, at in replies):
            out.append(c["url"])
    others = [c["url"] for c in posts + [t["last"] for t in found["threads"] if t["last"]]
              if c["author"] != login]
    return out, others


def check_comments(p: Project, n: int) -> None:
    mine, others = unanswered(pr_comments(p, n))
    for url in others:
        print(f"-- comment by another account: {url} (listed, not checked)")
    if mine:
        raise Refused("comment", f"{mine[0]} is unanswered", "answer it (reply-to marker) or resolve the thread")
    print("ok comments: none of yours unanswered")


def mergeable(p: Project, n: int, pr: dict) -> None:
    for _ in range(3):
        if pr.get("mergeable") != "UNKNOWN":
            break
        time.sleep(5)
        pr = pr_view(p, n)
    if pr.get("mergeable") != "MERGEABLE":
        raise Refused("mergeable", f"GitHub says PR #{n} is {pr.get('mergeable')}",
                      "the builder merges main; back to review" if pr.get("mergeable") == "CONFLICTING"
                      else "rerun in a minute")
    print("ok mergeable: MERGEABLE")


# ---------------------------------------------------------------- the merge (C8 sections 3-9)


def ticket_of(ready: Ready) -> int | None:
    if ready.reference:
        return ready.reference["verdict"].get("ticket")
    m = re.fullmatch(r"t(\d+)", ready.pr["headRefName"])
    return int(m.group(1)) if m else None


def paid_due(p: Project, changed: list[str]) -> str:
    due = p.value("merge.paid_suite") and any(matches(x, p.value("merge.paid_paths")) for x in changed)
    return "due" if due else "not due"


def merge(p: Project, n: int, entry: str, shown: str | None) -> int:
    started = workfiles.utc_iso()
    if not p.value("merge.clean_run"):
        raise Refused("clean run", "merge.clean_run is empty", "set merge.clean_run in agent-kit.toml")
    ready = readiness(p, n, entry, shown, refresh_head=True)
    head = ready.head
    merge_id = workfiles.event_id("merge", ticket_of(ready), head)
    main_tested = ready.main
    pre = clean_run(p, merge_id, "pre", head, ready.changed, machinery(ready.cls))      # 10
    print(run_line("pre", pre), flush=True)
    if pre["result"] != "green":
        raise Refused("clean run", f"the pre-merge run is {pre['result']} on {head[:12]} (see {pre['log']})",
                      "fix it on the branch; back to review")
    hook(p, "pre-run-done")
    base = {"id": merge_id, "pr": n, "entry": entry}
    rec = {"ready": ready, "pr": n, "head": head, "main_before": main_tested, "pre_run": {**pre, "reruns": 0},
           "started_at": started}
    lock = take_lock(p, {"format": "merge-lock", "version": 1, **base, "host": socket.gethostname()})
    try:
        print(f"ok merge lock: {(p.coordination / 'locks/merge.lock').as_posix()}", flush=True)
        try:
            hook(p, "locked")
            item_11(p, n, entry, ready, rec, merge_id, lock)
        except (Refused, Failed) as e:
            rec["info"] = info_of(p, ready)
            record(p, merge_id, entry, rec, result="not-merged", refusal=str(e))
            raise
        rec["info"] = info_of(p, ready)  # what a recovery needs to write the record (C8 section 6)
        head = rec["head"]
        write_marker(p, n, marker_of(rec, merge_id, entry, "merge-called", None))
        hook(p, "merge-called")
        try:
            call = gh(p.main, "pr", "merge", str(n), "--repo", p.repo, "--merge", "--match-head-commit", head,
                      "--subject", f"Merge PR #{n}: {ready.pr['title']}", "--body", f"kit merge id: {merge_id}",
                      check=False)
        except Failed as e:  # sent, maybe accepted (a timeout): the result is unknown, never "nothing merged"
            call, unknown = None, str(e)
        merged = None
        try:
            for _ in range(5 if call is None or call.returncode == 0 else 1):  # GitHub may show a merge late
                merged = merge_commit_of(p, n, head)
                if merged:
                    break
                time.sleep(3)
        except Failed as e:
            raise Unrecorded(f"the merge call's result is unknown: {e}") from None
        if not merged and call is None:
            raise Unrecorded(f"the merge call failed ({unknown}) and GitHub does not show PR #{n} merged yet")
        if not merged and call.returncode == 0:
            raise Unrecorded(f"gh reported PR #{n} merged, but GitHub does not show it merged at {head[:12]}")
        why = "" if merged else " ".join((call.stderr or call.stdout).split())[:300] or f"gh exited {call.returncode}"
        if not merged and not any(text in why for text in GITHUB_REFUSALS):
            # not one of GitHub's own refusals (a dropped connection, say): GitHub may still have merged it
            raise Unrecorded(f"the merge call failed ({why}) and GitHub does not show PR #{n} merged yet")
        if not merged:
            refusal = f"REFUSED (merge call): GitHub did not merge PR #{n} at {head[:12]}: {why}. " \
                      f"Valid: rerun once the head is reviewed or shown to you again. {NOTHING}"
            record(p, merge_id, entry, rec, result="not-merged", refusal=refusal)
            (p.merges / f"in-progress-{n}.json").unlink(missing_ok=True)
            print(refusal, file=sys.stderr)
            return 1
        code = finish(p, n, entry, rec, merge_id, merged, lock)
    finally:
        HELD["lock"] = None
        lock.release()
    if rec["info"]["paid_suite"] == "due":  # after the merge lock is released (decision 113)
        code = max(code, run_paid(p, merge_id, merged, rec["info"]["ticket"], f"PR #{n}"))
    return code


def info_of(p: Project, ready: Ready) -> dict:
    """The PR's side of the record, kept in the marker so a recovery can write the record."""
    return {"ticket": ticket_of(ready), "branch": ready.pr["headRefName"], "title": ready.pr["title"],
            "class": ready.cls["class"], "yours_because": ready.cls["yours_because"], "kind": ready.kind,
            "clearance": ready.clearance, "shown_head": ready.shown, "codex_approval_required": needs_codex(ready.cls),
            "update_commits": ready.update_commits, "paid_suite": paid_due(p, ready.changed),
            "control": machinery(ready.cls), "prose_shape": prose_shape(ready.cls)}


def marker_of(rec: dict, merge_id: str, entry: str, stage: str, commit: str | None) -> dict:
    return {"id": merge_id, "pr": rec["pr"], "entry": entry, "head": rec["head"], "main_before": rec["main_before"],
            "pre_run": rec["pre_run"], "stage": stage, "merge_commit": commit, "tag": rec.get("tag"),
            "post_run": rec.get("post_run"), "stop": rec.get("stop"), "revert_pr": rec.get("revert_pr"),
            "worktree": rec.get("worktree"), "info": rec["info"], "started_at": rec.get("started_at"),
            "merged_at": rec.get("merged_at")}


def item_11(p: Project, n: int, entry: str, ready: Ready, rec: dict, merge_id: str, lock: kitlock.Lock) -> None:
    """Under the lock, just before the merge call: reconcile, items 3, 4, 7 and 8 again, and head and main
    unchanged since the run; else refresh and rerun, at most 3 times."""
    branch = ready.pr["headRefName"]
    while True:
        reconcile_pass(p, lock)  # again, right after the claim: a merge or a crash since item 2 is found here
        state = earning_now(p)
        eligibility(entry, ready.cls, ready.reference is not None, state, bool(p.value("tickets.auto_merge")),
                    int(p.value("tickets.earn_after")), n)
        pr = pr_view(p, n)
        pr_open(p, n, pr)  # item 3 again: closed, a draft, or retargeted during the run (issue #102)
        if pr.get("reviewDecision") == "CHANGES_REQUESTED":
            raise Refused("change request", f"PR #{n} got a change request during the run", "answer it")
        check_comments(p, n)  # item 8 again: a comment of yours made during the run refuses
        refs = dict(reversed(line.split("\t")) for line in git(
            p.main, "ls-remote", "origin", f"refs/heads/{p.default}", f"refs/heads/{branch}").splitlines())
        now_head, now_main = refs.get(f"refs/heads/{branch}"), refs.get(f"refs/heads/{p.default}")
        if (now_head, now_main) == (rec["head"], rec["main_before"]):
            print(f"ok unchanged: head {now_head[:12]} and {p.default} {now_main[:12]} as tested", flush=True)
            return
        if rec["pre_run"]["reruns"] >= MAX_RERUNS:
            raise Refused("main keeps moving", f"{p.default} or the head moved after {MAX_RERUNS} reruns",
                          "rerun when merges quieten")
        print(f"moved: head {rec['head'][:12]} -> {(now_head or '?')[:12]}, {p.default} {rec['main_before'][:12]} -> "
              f"{(now_main or '?')[:12]}; refreshing and running again", flush=True)
        if not now_head or not now_main:
            raise Refused("PR", f"origin has no {branch if not now_head else p.default} branch now", "an open PR")
        git(p.main, "fetch", "-q", "origin")
        head, main_ref = now_head, now_main  # the commits ls-remote named, whatever the shared ref says by now
        fetch_head(p, branch, head)
        by_verdict = ready.clearance["by"] == "verdict"  # a verdict a pure revert does not need binds nothing
        if by_verdict:
            ready.update_commits = bind(p.main, ready.reference["verdict"]["head"], head, main_ref, "approval",
                                        "a new review round of the head")
        if ready.shown:
            bind(p.main, ready.shown, head, main_ref, "the head you were shown",
                 f"merge.py yours {n} --head {head[:12]}, after reading its changes")
        if not is_ancestor(p.main, main_ref, head):
            head = refresh(p, branch, head, main_ref)
            if by_verdict:
                ready.update_commits = bind(p.main, ready.reference["verdict"]["head"], head, main_ref,
                                            "approval", "a new review round of the head")
            wait_for_head(p, n, head)
        reruns = rec["pre_run"]["reruns"] + 1
        main_tested = main_ref
        ready.changed, ready.cls, ready.kind = reclassify(p, n, entry, branch, main_ref, head,
                                                          ready.reference is not None, ready.clearance["by"],
                                                          pr.get("body") or "")
        pre = clean_run(p, merge_id, "pre", head, ready.changed, machinery(ready.cls), popen=lock.popen,
                        tag=f"-r{reruns}")
        print(run_line("pre", pre), flush=True)
        rec.update(head=head, main_before=main_tested, pre_run={**pre, "reruns": reruns})
        if pre["result"] != "green":
            raise Refused("clean run", f"the pre-merge rerun is {pre['result']} on {head[:12]} (see {pre['log']})",
                          "fix it on the branch; back to review")


def merge_commit_of(p: Project, n: int, head: str) -> str | None:
    """The PR's merge commit when GitHub merged it at `head` (its second parent), else None."""
    pr = json.loads(gh(p.main, "pr", "view", str(n), "--repo", p.repo, "--json", "state,mergeCommit").stdout)
    commit = (pr.get("mergeCommit") or {}).get("oid")
    if pr.get("state") != "MERGED" or not commit:
        return None
    git(p.main, "fetch", "-q", "origin")
    ps = parents(p.main, commit)
    if len(ps) != 2 or ps[1] != head:
        raise Unrecorded(f"PR #{n} merged as {commit[:12]}, whose parents {ps} are not main and {head[:12]}")
    return commit


def finish(p: Project, n: int, entry: str, rec: dict, merge_id: str, commit: str, lock: kitlock.Lock, *,
           recovered: bool = False) -> int:
    """After the merge, under the lock: the tag, the post-merge run, red main, the worktree, the record. A
    recovery (C8 section 6) continues from the marker's stage: what is done is not done again."""
    info, head = rec["info"], rec["head"]
    tag = f"merge/pr-{n}"
    try:
        rec["merge_commit"] = commit
        if not recovered:
            rec["merged_at"] = workfiles.utc_iso()
            write_marker(p, n, marker_of(rec, merge_id, entry, "merged", commit))
            hook(p, "merged")
        if not git(p.main, "ls-remote", "--tags", "origin", f"refs/tags/{tag}"):
            git(p.main, "tag", "-f", "-a", tag, "-m", f"{merge_id} {entry} head {head}", commit)
            git(p.main, "push", "-q", "origin", f"refs/tags/{tag}")
        rec["tag"] = tag
        write_marker(p, n, marker_of(rec, merge_id, entry, "tagged", commit))
        if not recovered:
            hook(p, "tagged")
        if rec.get("post_run") is None:
            rec["post_run"] = clean_run(p, merge_id, "post", commit, None, bool(info.get("control")), popen=lock.popen)
            print(run_line("post", rec["post_run"]), flush=True)
            write_marker(p, n, marker_of(rec, merge_id, entry, "post-run-done", commit))
        post = rec["post_run"]
        if red(post) and not rec.get("stop"):
            rec["stop"], rec["revert_pr"] = red_main(p, merge_id, info.get("ticket"), f"PR #{n}", [commit], post)
            write_marker(p, n, marker_of(rec, merge_id, entry, "post-run-done", commit))
        if rec.get("worktree") is None:  # a recovery after the removal keeps its result (decision 128)
            rec["worktree"] = remove_worktree(p, info.get("branch"), commit)
            write_marker(p, n, marker_of(rec, merge_id, entry, "worktree-done", commit))
        if not recovered:
            hook(p, "worktree-done")
        path = record(p, merge_id, entry, rec, result="merged", recovered=recovered)
        (p.merges / f"in-progress-{n}.json").unlink(missing_ok=True)
    except Exception as e:
        raise Unrecorded(f"PR #{n} merged as {commit[:12]}, then: {e}") from None
    if entry == "auto":
        say(p, "merge-auto", f"Merged PR #{n} automatically ({merge_id}): {str(info.get('title'))[:80]}")
    if recovered:
        say(p, "merge-interrupted", f"Interrupted merge of PR #{n} ({merge_id}) recovered: merged as {commit[:12]}.")
    verb = "recovered" if recovered else "merged"
    if red(post):
        print(f"{verb} PR #{n} at {head} as {commit}; tag {tag}; post-merge run {post['result']}: RED MAIN "
              f"(see {post['log']}); revert PR {'#' + str(rec['revert_pr']) if rec.get('revert_pr') else 'none'}; "
              f"record {path}")
        return 3
    print(f"{verb} PR #{n} at {head} as {commit}; tag {tag}; post-merge run green; record {path}")
    return 0


def record(p: Project, merge_id: str, entry: str, rec: dict, *, result: str, refusal: str | None = None,
           recovered: bool = False) -> str:
    """The merge record (C8 section 8), written once, with the earning state after it."""
    info = rec["info"]
    post, commit = rec.get("post_run"), rec.get("merge_commit")
    counts = (result == "merged" and info.get("kind") == "ticket" and (info.get("clearance") or {}).get("by") == "verdict"
              and entry in ("yours", "auto") and isinstance(post, dict) and post.get("result") == "green")
    main_after = git(p.main, "rev-parse", f"origin/{p.default}") if commit else None
    first_parent = parents(p.main, commit)[0] if commit else None
    data = {"format": "merge", "version": 1, "id": merge_id, "result": result, "entry": entry,
            "recovered": recovered, "repository": p.repo, "pr": rec["pr"], "ticket": info.get("ticket"),
            "branch": info.get("branch"), "title": info.get("title"), "class": info.get("class"),
            "yours_because": info.get("yours_because"), "kind": info.get("kind"), "clearance": info.get("clearance"),
            "shown_head": info.get("shown_head"), "codex_approval_required": info.get("codex_approval_required"),
            "prose_shape": info.get("prose_shape"), "head": rec["head"], "update_commits": info.get("update_commits"),
            "main_before": rec["main_before"], "merge_commit": commit, "main_after": main_after,
            "main_moved_during_merge": bool(commit) and first_parent != rec["main_before"],
            "paid_suite": info.get("paid_suite"), "tag": rec.get("tag"), "revert_pr": rec.get("revert_pr"),
            "pre_run": rec["pre_run"], "post_run": post, "worktree": rec.get("worktree"), "refusal": refusal,
            "counts_toward_earning": counts, "earning_after": None, "kit_version": kit_version(p.main),
            "started_at": rec.get("started_at"), "merged_at": rec.get("merged_at"),
            "recorded_at": workfiles.utc_iso()}
    stamp = event_time("merge", merge_id.split("-")[1], data)
    data["earning_after"] = earning_now(p, [(stamp, "merge", f"{merge_id}.json", data)])
    path = p.merges / f"{merge_id}.json"
    if path.exists():
        raise Failed(f"merges/{path.name} exists already: a record is written once")
    workfiles.write_atomic(path, json.dumps(data, indent=1) + "\n")
    return f"merges/{path.name}"


# ---------------------------------------------------------------- the commands


def check(p: Project, n: int) -> int:
    ready = readiness(p, n, "yours", None, refresh_head=False)
    if not is_ancestor(p.main, ready.main, ready.head):
        print(f"-- refresh: the head lacks origin/{p.default}; a merging run merges it in first")
    try:
        eligibility("auto", ready.cls, ready.reference is not None, earning_now(p),
                    bool(p.value("tickets.auto_merge")), int(p.value("tickets.earn_after")), n)
        print("automatic mode: would merge")
    except Refused as r:
        print(f"automatic mode: would refuse: {str(r).split(': ', 1)[1].split('. Valid')[0]}")
    print(f"ready: PR #{n} at {ready.head[:12]} passes items 1-9 for your mode")
    return 0


def status(p: Project) -> int:
    s = earning_now(p)
    after = int(p.value("tickets.earn_after"))
    print(f"clean_streak {s['clean_streak']} of {after}, escalation_streak {s['escalation_streak']} of "
          f"{p.value('tickets.hand_back_after_escalations')}; earned {'yes' if s['earned'] else 'no'}; "
          f"stopped {'yes' if s['stopped'] else 'no'}; tickets.auto_merge {'on' if p.value('tickets.auto_merge') else 'off'}")
    for f in markers(p):
        print(f"-- merges/{f.name} waits for a reconcile pass")
    return 0


def reconcile(p: Project) -> int:
    """`merge.py reconcile`: main's copy, then section 6's pass (claim, reconcile, release), then the paid
    suites due, each under its own lock. 3 when it found a red main, else 0."""
    main_copy(p)
    code = max(locked_pass(p), paid_due_now(p))
    print(f"reconciled: {'RED MAIN, automatic merges stopped' if code == 3 else 'nothing left unrecorded'}")
    return code


def resume(p: Project, reason: str) -> int:
    """`merge.py resume --reason <text>` (yours, decision 112): lifts a stop with `merges/resume-<id>.json`."""
    if os.environ.get("KIT_ROLE"):
        raise Refused("role", f"KIT_ROLE is {os.environ['KIT_ROLE']}; resume is yours", "run it yourself in a terminal")
    if not " ".join(reason.split()):
        raise Refused("resume", "the reason is empty", "merge.py resume --reason <why main is green again>")
    if not earning_now(p)["stopped"]:
        raise Refused("resume", "automatic merges are not stopped", "nothing to resume")
    main_sha = run(["git", "rev-parse", f"origin/{p.default}"], p.main, check=False).stdout.strip() or "0000000"
    rid = workfiles.event_id("resume", None, main_sha)
    workfiles.write_atomic(p.merges / f"{rid}.json", json.dumps(
        {"format": "resume", "version": 1, "id": rid, "reason": " ".join(reason.split()),
         "written_at": workfiles.utc_iso()}, indent=1) + "\n")
    print(f"resumed: merges/{rid}.json; automatic merges may run again once earned")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="merge.py", description="The guarded merge (contract C8).")
    sub = ap.add_subparsers(dest="command", required=True)
    y = sub.add_parser("yours", help="your mode: any PR that passes the readiness list")
    y.add_argument("pr", type=int)
    y.add_argument("--head", help="the head you were shown (12 hex or more)")
    sub.add_parser("auto", help="automatic mode, the orchestrator only: earned ticket PRs").add_argument("pr", type=int)
    sub.add_parser("check", help="items 1-9 without the refresh; writes nothing").add_argument("pr", type=int)
    sub.add_parser("status", help="the earning state")
    sub.add_parser("reconcile", help="the reconcile pass alone, then the paid suites due")
    sub.add_parser("resume", help="yours: lifts a stop").add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    try:
        if args.command == "auto" and os.environ.get("KIT_ROLE") not in (None, "orchestrator"):
            raise Refused("role", f"KIT_ROLE is {os.environ['KIT_ROLE']}; automatic mode is the orchestrator's",
                          "the orchestrator runs merge.py auto; you run merge.py yours")
        p = Project(main_checkout())
        if args.command == "status":
            return status(p)
        if args.command == "reconcile":
            return reconcile(p)
        if args.command == "resume":
            return resume(p, args.reason)
        if args.command == "check":
            return check(p, args.pr)
        if args.command == "yours" and not args.head:
            ready = readiness(p, args.pr, "yours", None, refresh_head=False)
            print(f"PR #{args.pr}: {ready.pr['title']}\nhead {ready.head}\nclass {ready.cls['class']} ({ready.kind})")
            print("changed paths:\n" + "\n".join(f"  {x}" for x in ready.changed))
            raise Refused("head", "no --head: read the head and its changes first",
                          f"merge.py yours {args.pr} --head {ready.head[:12]} (kit merge {args.pr} --head "
                          f"{ready.head[:12]} from step 7)")
        return merge(p, args.pr, args.command, getattr(args, "head", None))
    except Refused as r:
        print(r, file=sys.stderr)
        return 1
    except Failed as e:
        print(f"FAILED: {e}. {NOTHING}", file=sys.stderr)
        return 2
    except Unrecorded as e:
        print(f"MERGED, NOT RECORDED: {e}. The in-progress marker stays; reconcile settles it.", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
