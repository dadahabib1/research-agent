"""The selector (tools/next_task.py): parallel runs take different tasks, the claim is atomic, and
each branch and pull request state is read as CONTRACT.md "The queue" says. Git runs for real
against a local bare remote; gh is replaced by a fake that answers `gh pr list` from a table."""

import json
import subprocess
from pathlib import Path

import pytest

import next_task as nt

CONFIG = 'requires = ">=0.7.0, <0.8.0"\n[project]\nroot = "research"\ndecider = "requester"\n'
QUEUE = """# Research queue

| Task | Prompt | Deliverable | Prerequisites | Status |
|---|---|---|---|---|
| Topic A | prompts/a.md | topic-a.md | none | todo |
| Topic B | prompts/b.md | topic-b.md | none | todo |
| Topic C | prompts/c.md | topic-c.md | topic a | todo |
| Topic D | prompts/d.md | topic-d.md | none | accepted |
"""


def g(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture(autouse=True)
def no_gh(monkeypatch):
    for key, value in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.invalid"),
                       ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.invalid")):
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(nt, "gh_works", lambda path: False)


@pytest.fixture
def origin(tmp_path):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    write(seed, {"research-agent.toml": CONFIG, "research/research-queue.md": QUEUE})
    g(seed, "add", "-A")
    g(seed, "commit", "-q", "-m", "seed")
    g(seed, "remote", "add", "origin", str(bare))
    g(seed, "push", "-q", "origin", "main")
    return bare


def clone(origin: Path, name: str) -> Path:
    dest = origin.parent / name
    subprocess.run(["git", "clone", "-q", str(origin), str(dest)], check=True)
    return dest


def select(repo: Path, *args: str, capsys=None) -> tuple[int, str]:
    code = nt.main(["--project", str(repo), *args])
    return code, capsys.readouterr().out if capsys else ""


def selected(out: str) -> str:
    return next(line for line in out.splitlines() if line.startswith("selected: "))


def hand_back(repo: Path, topic: str, status: str) -> None:
    """Finish a run on the checked-out branch: deliverable and log (ending in the hand-back), pushed."""
    write(repo, {f"research/{topic}.md": f"# {topic}\n",
                 f"research/logs/{topic}-log.md": f"# Research log: {topic}\n\n## Hand-back\n\n- Status: {status}\n"})
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", f"run {topic}")
    g(repo, "push", "-q", "origin", f"research/{topic}")


def merge(repo: Path, topic: str, delete: bool = False) -> None:
    g(repo, "fetch", "-q", "origin")
    g(repo, "checkout", "-q", "main")
    g(repo, "pull", "-q", "--ff-only")
    g(repo, "merge", "-q", "--no-ff", "-m", f"merge {topic}", f"origin/research/{topic}")
    g(repo, "push", "-q", "origin", "main")
    if delete:
        g(repo, "push", "-q", "origin", "--delete", f"research/{topic}")


# ---------- parallel runs ----------

def test_two_runs_back_to_back_take_different_tasks(origin, capsys):
    a, b = clone(origin, "a"), clone(origin, "b")
    code, out = select(a, capsys=capsys)
    assert code == 0 and selected(out) == "selected: new topic-a", out
    code, out = select(b, capsys=capsys)
    assert code == 0 and selected(out) == "selected: new topic-b", out
    assert g(a, "branch", "--show-current") == "research/topic-a"
    assert g(b, "branch", "--show-current") == "research/topic-b"
    # the claim is an empty commit: it changes no file, so it never conflicts
    assert g(a, "rev-parse", "HEAD^{tree}") == g(a, "rev-parse", "HEAD~1^{tree}")
    assert g(a, "log", "-1", "--format=%s").startswith(nt.CLAIM)


def test_a_stale_view_loses_the_claim_and_takes_the_next_row(origin, capsys):
    a, b = clone(origin, "a"), clone(origin, "b")
    repo_b = nt.open_repo(b)  # b reads the remote before a claims
    rows_b = nt.parse_queue(nt.queue_text(repo_b))
    assert select(a, capsys=capsys)[0] == 0
    row, commit, reasons = nt.select(repo_b, rows_b, None)
    assert row.topic == "topic-b" and commit
    assert "topic-a: claimed by another run a moment ago" in reasons


def test_finished_runs_merge_in_either_order_without_conflict(origin, capsys):
    a, b = clone(origin, "a"), clone(origin, "b")
    select(a, capsys=capsys)
    select(b, capsys=capsys)
    hand_back(a, "topic-a", "in review")
    hand_back(b, "topic-b", "in review")
    merge(a, "topic-b")
    merge(a, "topic-a")  # neither run touched the queue, so no conflict
    assert (a / "research" / "research-queue.md").read_text(encoding="utf-8") == QUEUE


# ---------- states without gh: branches and the log's hand-back ----------

def test_states_from_branches(origin, capsys):
    a = clone(origin, "a")
    select(a, capsys=capsys)
    code, out = select(a, "--list", capsys=capsys)
    assert code == 0
    assert "mode: branches (gh unavailable for this remote)" in out
    assert any(l.split()[:2] == ["todo", "running"] and "topic-a" in l for l in out.splitlines()), out
    hand_back(a, "topic-a", "stopped: usage limit")
    code, out = select(clone(origin, "b"), capsys=capsys)
    assert selected(out) == "selected: resume topic-a", out


def test_waiting_and_in_review_are_skipped(origin, capsys):
    a = clone(origin, "a")
    select(a, capsys=capsys)
    hand_back(a, "topic-a", "waiting on requester")
    b = clone(origin, "b")
    select(b, capsys=capsys)
    hand_back(b, "topic-b", "in review")
    code, out = select(clone(origin, "c"), capsys=capsys)
    assert code == 1, out
    assert "topic-a: waiting (research/topic-a)" in out
    assert "topic-b: in review (research/topic-b)" in out
    assert "topic-c: prerequisites not accepted: topic a" in out
    assert "topic-d: status accepted, not todo" in out


def test_a_merged_run_is_done_even_after_its_branch_is_deleted(origin, capsys):
    a = clone(origin, "a")
    select(a, capsys=capsys)
    hand_back(a, "topic-a", "in review")
    merge(a, "topic-a", delete=True)
    code, out = select(clone(origin, "b"), capsys=capsys)
    assert selected(out) == "selected: new topic-b", out
    assert "topic-a: done" in out


def test_a_crashed_run_holds_its_row_until_named(origin, capsys):
    a = clone(origin, "a")
    select(a, capsys=capsys)  # claimed, then the session died
    b = clone(origin, "b")
    code, out = select(b, capsys=capsys)
    assert selected(out) == "selected: new topic-b"
    c = clone(origin, "c")
    code, out = select(c, "--topic", "Topic A", capsys=capsys)
    assert code == 0 and selected(out) == "selected: resume topic-a", out
    assert g(c, "rev-parse", "HEAD~1") == g(a, "rev-parse", "HEAD")  # claimed on the old tip


# ---------- states from pull requests ----------

def body(status: str) -> str:
    return f"Run of a topic.\n\n## Hand-back\n\n- Status: {status}\n- Answer: x\n"


@pytest.fixture
def prs(monkeypatch):
    """Turn on the pull request mode with a fake gh that answers `gh pr list --head <branch> --json
    <fields>` from {branch: [pull requests]}, in the order gh gives (not sorted)."""
    table: dict[str, list[dict]] = {}
    real_run = nt.run

    def fake_run(cmd, cwd):
        if cmd[0] != "gh":
            return real_run(cmd, cwd)
        assert cmd[:3] == ["gh", "pr", "list"], cmd
        fields = cmd[cmd.index("--json") + 1].split(",")
        listed = [{f: item[f] for f in fields} for item in table.get(cmd[cmd.index("--head") + 1], [])]
        return subprocess.CompletedProcess(cmd, 0, json.dumps(listed), "")

    monkeypatch.setattr(nt, "gh_works", lambda path: True)
    monkeypatch.setattr(nt, "run", fake_run)
    return table


def pr(number: int, state: str, status: str | None = None, fork: bool = False) -> dict:
    return {"number": number, "state": state, "url": f"https://example.invalid/pull/{number}",
            "body": body(status) if status else "no hand-back", "isCrossRepository": fork}


def test_open_pull_requests(origin, prs, capsys):
    a = clone(origin, "a")
    select(a, capsys=capsys)
    hand_back(a, "topic-a", "stopped: budget")  # the log says stopped, but the PR body decides
    prs["research/topic-a"] = [pr(1, "OPEN", "in review")]
    b = clone(origin, "b")
    select(b, capsys=capsys)
    hand_back(b, "topic-b", "in review")
    prs["research/topic-b"] = [pr(2, "OPEN", "stopped: usage limit")]
    code, out = select(clone(origin, "c"), capsys=capsys)
    assert selected(out) == "selected: resume topic-b", out
    assert "topic-a: in review (https://example.invalid/pull/1)" in out
    assert "pull request: https://example.invalid/pull/2" in out
    assert "mode: pull requests" in out


def test_a_closed_pull_request_frees_its_row(origin, prs, capsys):
    a = clone(origin, "a")
    select(a, capsys=capsys)
    hand_back(a, "topic-a", "in review")
    old_tip = g(a, "rev-parse", "HEAD")
    prs["research/topic-a"] = [pr(1, "CLOSED", "in review")]
    c = clone(origin, "c")
    code, out = select(c, capsys=capsys)
    assert selected(out) == "selected: new topic-a", out
    # the abandoned branch was replaced by a claim on the default branch, not built on
    assert g(c, "rev-parse", "HEAD~1") == g(c, "rev-parse", "origin/main")
    assert g(c, "rev-parse", "origin/research/topic-a") != old_tip


def test_an_abandoned_branch_is_replaced_only_if_nobody_moved_it(origin, prs, capsys):
    a = clone(origin, "a")
    select(a, capsys=capsys)
    hand_back(a, "topic-a", "in review")
    prs["research/topic-a"] = [pr(1, "CLOSED", "in review")]
    c = nt.open_repo(clone(origin, "c"))
    rows = nt.parse_queue(nt.queue_text(c))
    nt.assess(c, rows[0])
    assert rows[0].state == "abandoned"
    write(a, {"research/later.md": "x\n"})  # someone moves the branch after c read it
    g(a, "add", "-A")
    g(a, "commit", "-q", "-m", "later")
    g(a, "push", "-q", "origin", "research/topic-a")
    assert nt.claim(c, rows[0]) is None


def test_merged_and_newer_pull_requests(origin, prs, capsys):
    a = clone(origin, "a")
    select(a, capsys=capsys)
    hand_back(a, "topic-a", "in review")
    prs["research/topic-a"] = [pr(1, "MERGED", "in review")]
    code, out = select(clone(origin, "b"), "--list", capsys=capsys)
    assert any("done" in l and "topic-a" in l for l in out.splitlines()), out
    prs["research/topic-a"].append(pr(5, "OPEN", "stopped: usage limit"))  # a re-run, newer than the merge
    code, out = select(clone(origin, "c"), capsys=capsys)
    assert selected(out) == "selected: resume topic-a", out


# ---------- a named topic ----------

def test_named_topic(origin, prs, capsys):
    a = clone(origin, "a")
    select(a, "--topic", "topic-b", capsys=capsys)
    hand_back(a, "topic-b", "waiting on requester")
    prs["research/topic-b"] = [pr(1, "OPEN", "waiting on requester")]
    code, out = select(clone(origin, "b"), capsys=capsys)
    assert selected(out) == "selected: new topic-a"  # the named run did not change the order
    c = clone(origin, "c")
    code, out = select(c, "--topic", "TOPIC-B", capsys=capsys)
    assert selected(out) == "selected: resume topic-b", out  # the requester answered
    hand_back(c, "topic-b", "in review")

    prs["research/topic-b"] = [pr(1, "OPEN", "in review")]
    code, out = select(clone(origin, "d"), "--topic", "topic-b", capsys=capsys)
    assert code == 1 and "topic-b: in review" in out
    code, out = select(clone(origin, "e"), "--topic", "topic-c", capsys=capsys)
    assert code == 1 and "prerequisites not accepted" in out
    code, out = select(clone(origin, "f"), "--topic", "nothing", capsys=capsys)
    assert code == 1 and "no queue row" in out

    prs["research/topic-b"] = [pr(1, "MERGED", "in review")]
    code, out = select(clone(origin, "g"), "--topic", "topic-b", capsys=capsys)
    assert selected(out) == "selected: new topic-b", out  # a re-run of a merged task


# ---------- no remote ----------

def test_no_remote_uses_local_branches(tmp_path, capsys):
    repo = tmp_path / "local"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    write(repo, {"research-agent.toml": CONFIG, "research/research-queue.md": QUEUE})
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", "seed")
    code, out = select(repo, capsys=capsys)
    assert selected(out) == "selected: new topic-a" and "mode: local (no remote)" in out
    assert g(repo, "log", "-1", "--format=%s") == "seed"  # no claim commit without a remote
    write(repo, {"research/logs/topic-a-log.md": "## Hand-back\n\n- Status: stopped: budget\n"})
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", "stopped")
    code, out = select(repo, capsys=capsys)
    assert code == 2 and "start from the default branch" in out
    g(repo, "checkout", "-q", "main")
    code, out = select(repo, capsys=capsys)
    assert selected(out) == "selected: resume topic-a", out


# ---------- small parts ----------

def test_handback_status_reads_the_last_block():
    text = "## Hand-back\n\n- Status: in review\n\nedited\n\n## Hand-back\n\n- Status: Stopped: budget\n"
    assert nt.handback_status(text) == "stopped: budget"
    assert nt.handback_status("no block") is None
    assert nt.by_status("stopped: x") == "stopped"
    assert nt.by_status("waiting on requester") == "waiting"
    assert nt.by_status(None) == "in review"


def test_queue_rows_and_topics():
    rows = nt.parse_queue("intro\n\n| Task | Prompt | Deliverable | Prerequisites | Extra | Status |\n"
                          "|---|---|---|---|---|---|\n| One | `p/1.md` | `out/one-v1.md` | none | x | Todo |\n\nafter\n")
    assert [(r.topic, r.status, r.prerequisites) for r in rows] == [("one-v1", "todo", [])]
    with pytest.raises(nt.CannotRun):
        nt.parse_queue("| Task | Status |\n|---|---|\n")


def test_cannot_run_without_a_project(tmp_path, capsys):
    repo = tmp_path / "consumer"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    write(repo, {"research-agent.toml": 'requires = ">=0.7.0"\n[consumes]\nresearch = "o/r"\n'})
    code, out = select(repo, capsys=capsys)
    assert code == 2 and "no [project] root" in out


# ---------- review round 1 (H1, M1, M2, L1, L2) ----------

def test_fork_pull_requests_are_ignored(origin, prs, capsys):
    """H1: a fork's closed pull request from a branch of the same name, newer than the run's open
    one, must not make the task look abandoned (which would replace the run's branch)."""
    a = clone(origin, "a")
    select(a, capsys=capsys)
    hand_back(a, "topic-a", "in review")
    run_tip = g(a, "rev-parse", "HEAD")
    prs["research/topic-a"] = [pr(1, "OPEN", "in review"), pr(2, "CLOSED", "in review", fork=True),
                               pr(3, "OPEN", "stopped: x", fork=True)]
    code, out = select(clone(origin, "b"), capsys=capsys)
    assert selected(out) == "selected: new topic-b", out
    assert "passed over: topic-a: in review (https://example.invalid/pull/1)" in out
    assert g(a, "ls-remote", "origin", "refs/heads/research/topic-a").split()[0] == run_tip


def test_a_push_failure_other_than_a_lost_race_exits_2(origin, capsys):
    """M1: no push rights, a bad URL or a protection rule is an error, not 'claimed by another run'."""
    a = clone(origin, "a")
    g(a, "remote", "set-url", "--push", "origin", str(origin.parent / "missing.git"))
    code, out = select(a, capsys=capsys)
    assert code == 2, out
    assert "git push of the claim on research/topic-a failed" in out
    assert "claimed by another run" not in out
    assert g(a, "branch", "--show-current") == "main"
    assert not g(a, "branch", "--list", "research/topic-a")


def test_a_blocked_checkout_leaves_no_claim(origin, capsys):
    """M2: when the claim cannot be checked out, nothing is pushed, and a stopped run stays stopped."""
    a = clone(origin, "a")
    select(a, capsys=capsys)
    hand_back(a, "topic-a", "stopped: budget")
    b = clone(origin, "b")
    write(b, {"research/topic-a.md": "an untracked file in the way\n"})
    code, out = select(b, capsys=capsys)
    assert code == 2, out
    assert g(b, "log", "-1", "--format=%s", "origin/research/topic-a") == "run topic-a"
    g(b, "ls-remote", "--exit-code", "origin", "refs/heads/research/topic-a")
    assert g(origin, "log", "-1", "--format=%s", "research/topic-a") == "run topic-a"
    code, out = select(b, "--list", capsys=capsys)
    assert any(l.split()[:2] == ["todo", "stopped"] and "topic-a" in l for l in out.splitlines()), out


def test_invalid_and_duplicate_topics_are_passed_over(tmp_path, capsys):
    """L1: an empty, shared or unusable deliverable stem never reaches a git ref."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    queue = ("| Task | Prompt | Deliverable | Prerequisites | Status |\n|---|---|---|---|---|\n"
             "| Empty | p.md |  | none | todo |\n| Colon | p.md | x:main.md | none | todo |\n"
             "| Space | p.md | bad name.md | none | todo |\n| Twin 1 | p.md | twin.md | none | todo |\n"
             "| Twin 2 | p.md | out/twin.md | none | todo |\n| Good | p.md | good.md | none | todo |\n")
    write(seed, {"research-agent.toml": CONFIG, "research/research-queue.md": queue})
    g(seed, "add", "-A")
    g(seed, "commit", "-q", "-m", "seed")
    g(seed, "remote", "add", "origin", str(bare))
    g(seed, "push", "-q", "origin", "main")
    code, out = select(clone(bare, "a"), capsys=capsys)
    assert selected(out) == "selected: new good", out
    assert "passed over: : no deliverable file name" in out
    assert "passed over: x:main: research/x:main is not a valid branch name" in out
    assert "passed over: bad name: research/bad name is not a valid branch name" in out
    assert out.count("2 rows share the deliverable stem twin") == 2
    assert g(bare, "for-each-ref", "--format=%(refname)") == "refs/heads/main\nrefs/heads/research/good"


def test_unpushed_local_commits_are_never_reset(origin, capsys):
    """L2: a local research/<topic> with commits the remote lacks is not reset by the claim."""
    a = clone(origin, "a")
    g(a, "checkout", "-q", "-b", "research/topic-a")
    write(a, {"research/topic-a.md": "local work\n"})
    g(a, "add", "-A")
    g(a, "commit", "-q", "-m", "unpushed work")
    work = g(a, "rev-parse", "HEAD")
    g(a, "checkout", "-q", "main")
    code, out = select(a, capsys=capsys)
    assert code == 2 and "has 1 commit(s) the remote does not have" in out, out
    assert g(a, "rev-parse", "research/topic-a") == work
    assert not g(origin, "branch", "--list", "research/topic-a")
