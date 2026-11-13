"""The review script (contract C7): one review round of a pushed head, from the checks to the verdict.

    python -I <main checkout>/.agents/kit/bin/review.py --ticket <n> --branch <branch> --head <40-hex sha>
                                                        [--base <branch>] [--check]

Run main's copy, after READY, in the background (a review outlasts a Bash tool call). It runs section 2's
checks in order (a round after an approval, on a head that adds only clean updates from main, is skipped
there: the record and a `skipped` verdict, nothing run), reserves one of the two standing reviewer checkouts
through the kit's lock helper, prepares it (the candidate, main's control files over it, the secret files,
the export, the test copy), reads each changed file's kinds from its path, runs the lint and main's mapped
tests in the test copy (a red one stops the round), proves that only allowed skills load and that main's
hooks fire (sections 1-5), then runs the reviewer (continued at its handoff, once on the fallback model at a
capacity error, asked once more for a missing `line`), the triager, and writes the review record and then
the verdict, and at the round cap or past five open blockers the escalation record (sections 6-10). Exit 0
approved or skipped, 4 changes needed, 5 a stop for the user, 1 refused, 3 both checkouts busy, 2 failed
after reserving. `--check` runs the checks
and the renders, and reserves, starts and writes nothing. `codex`, `claude` and `gh` are found on PATH, so
tests put fakes first there (C7 section 12). Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # C1 section 2: imports by __file__ under -I
sys.path.insert(0, str(HERE.parent / "hooks"))

import kitconfig  # noqa: E402
import kitlock  # noqa: E402
import merge  # noqa: E402  (C8: the clean-update chain an approval reaches, reused for the skip, not copied)
import testmap  # noqa: E402  (the test map: its globs, the mapped tests)
import usage  # noqa: E402
import workfiles  # noqa: E402
from guard import launch_settings, matches, ready_problem  # noqa: E402
from launch import (NOTHING_STARTED, Refused, check_config, check_memory, check_usage, clean_env,  # noqa: E402
                    copy_secrets, default_branch, outside_project)

# Open question 1 (C7 section 6): the reviewer sandbox is option A, the elevated one (the user, 2026-10-17),
# set up once in the reviewer home. It cannot run a Python under your profile (M118), so the reviewer's own
# Python (`reviewer_python`) goes first on PATH, and pytest's temp root is a fresh folder in the checkout,
# as it cannot read an earlier `pytest-of-<you>` (M117). See research/design-integration/verify/c7-review-2026-10-17.md.
SANDBOX = ("--sandbox", "workspace-write", "-c", 'windows.sandbox="elevated"')
CANARY_TIMEOUT = 600  # seconds [judgment]: a one-command run at effort low
# M181: Codex's elevated sandbox can fail its setup refresh before a command (a file held by another process)
# and a rerun succeeds (M126); the canary retries this, and only this, twice after a short wait [judgment].
REFRESH_ERROR = "setup refresh had errors"
REFRESH_RETRIES = 2
REFRESH_WAIT = 30  # seconds; KIT_REVIEW_REFRESH_WAIT_SECONDS can only shorten it (a test hook)
CHILD_TIMEOUT = 600  # seconds [judgment]: any other child (git, gh, a render), so none holds a checkout forever
RUN_TIMEOUT = 90 * 60  # seconds [judgment]: one reviewer run (C7 section 6), then the tree is killed
TRIAGE_TIMEOUT = 15 * 60  # seconds [judgment]: the triager (C7 section 7)
MAX_CONTINUATIONS = 2  # [judgment]: runs after the first in a round, at the reviewer's handoff (C7 section 6)
TRIAGER_ROLE = "triager"  # C7 section 7: `guard.py settings triager` with KIT_ROLE=triager (C5 section 1)
VERDICTS = ("fix", "defer", "needs_decision", "wont_fix")
EXIT = {"approved": 0, "skipped": 0, "changes_needed": 4, "needs_decision": 5, "escalated": 5}
BLOCKED_TEXT = "Command blocked by PreToolUse hook"  # what Codex shows for a hook's deny (M25, M44)
# Codex's own hook event lines, each a line of its own: a hook that failed (M29: the command runs anyway), one that
# started, and one that ended (`Completed`, or `Blocked` for a deny: measured in issue #176's pilot, 46 starts, 43
# Completed, 3 Blocked).
HOOK_FAILED = re.compile(r"^hook: PreToolUse Failed", re.M)
HOOK_STARTED = re.compile(r"^hook: PreToolUse\r?$", re.M)
HOOK_ENDED = re.compile(r"^hook: PreToolUse (?:Completed|Blocked)\r?$", re.M)
SKILL_ROOT = re.compile(r"^- `(r\d+)` = `([^`]+)`\s*$", re.M)
# A name runs to the first ": " and has no space; a plugin's skill keeps its colon (`plugin:skill`, 5.2).
SKILL_LINE = re.compile(r"^- (\S+?): .*\(file: (r\d+)/[^)\n]*\)\s*$", re.M)
AGENTS_BLOCK = re.compile(r"^# AGENTS\.md instructions for (.+?)\n\n<INSTRUCTIONS>\n(.*?)\n?</INSTRUCTIONS>", re.S | re.M)
FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
PATHLIKE = re.compile(r"(?<![\w/.-])([\w.-]+(?:/[\w.-]+)*\.[A-Za-z0-9]+)(?![\w/-])")


class Failed(Exception):
    """A failure after reserving (C7 section 10): no verdict, the checkout released."""

    def __init__(self, stage: str, failed: str):
        super().__init__(failed)
        self.stage, self.failed = stage, failed


def refuse(check: str, failed: str, valid: str) -> Refused:
    return Refused(check, failed, valid)


# ---------------------------------------------------------------- small helpers


def run(args, cwd: Path, *, env=None, input_text=None, timeout=CHILD_TIMEOUT, lock=None,
        binary=False) -> subprocess.CompletedProcess:
    """One child, as text (bytes with `binary`), always with a timeout (C7 section 3). Under a held lock it
    runs inside the lock's job object, so it and its own children end when this script ends, however it ends
    (C7 section 3, M86); on its timeout `TimeoutExpired` is raised and the lock's release, on the way out,
    ends it."""
    args = [str(a) for a in args]
    as_text = {} if binary else {"text": True, "encoding": "utf-8", "errors": "replace"}
    if lock is None:
        return subprocess.run(args, cwd=str(cwd), capture_output=True, env=env, input=input_text, timeout=timeout,
                              **as_text)
    # No `with` block and no wait after a timeout (kitlock's note): a grandchild holding the output pipe would
    # keep it from returning. The timeout leaves through the caller's release, which ends the whole tree.
    proc = lock.popen(args, cwd=str(cwd), stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **as_text)
    out, err = proc.communicate(input_text, timeout=timeout)
    return subprocess.CompletedProcess(args, proc.returncode, out, err)


def git(cwd: Path, *args, lock=None, check=True) -> str:
    r = run(["git", *args], cwd, lock=lock)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(map(str, args))} in {Path(cwd).as_posix()}: "
                           f"{(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout.strip()


def tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"`{name}` is not on PATH")
    return found


def main_checkout() -> Path:
    return Path(git(HERE, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent


def same(a, b, base: Path = Path(".")) -> bool:
    """Whether two paths name one place; a relative one is read from `base`, this script's own folder unless given."""
    return kitconfig.location(base, str(a)) == kitconfig.location(base, str(b))


def under(path, root) -> bool:
    loc, top = kitconfig.location(Path("."), str(path)), kitconfig.location(Path("."), str(root))
    try:
        rel = os.path.relpath(loc, top)
    except ValueError:
        return False
    return not (rel == ".." or rel.startswith(".." + os.sep))


def resolve(main: Path, value: str) -> Path:
    """C3: a relative path is resolved from the project root."""
    return Path(value) if kitconfig.is_absolute(value) else main / kitconfig.norm(value)


def front_matter(text: str) -> dict:
    """C9 section 1's flat front matter: `key: value` lines between `---` lines."""
    m = FRONT.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repository(main: Path) -> tuple[str, str, bool]:
    """(`owner/name` when origin is on GitHub, else origin's URL; origin's URL; whether it is GitHub)."""
    url = git(main, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return (m.group(1) if m else url), url, bool(m)


# ---------------------------------------------------------------- the kinds of change (design 2.1)


KINDS_FORMAT, KINDS_VERSION = "review-kinds", 1
UNCLASSIFIED = "unclassified"


class KindsProblem(ValueError):
    """The kinds file does not load; every problem at once, and any problem refuses (nothing is guessed)."""


def load_kinds(path: Path) -> list[dict]:
    """`.agents/kit/review/kinds.toml`: the kinds 1 to 9, each with its globs (agent-kit's and a project's,
    both read) and, for the core files' kind, the test map's `core` list."""
    shown = Path(path).as_posix()
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise KindsProblem(f"{shown}: cannot read: {e}") from e
    out = []
    if data.get("format") != KINDS_FORMAT or data.get("version") != KINDS_VERSION:
        out.append(f'format and version: not format = "{KINDS_FORMAT}", version = {KINDS_VERSION}')
    out += [f"{key}: not a key of the kinds file" for key in sorted(set(data) - {"format", "version", "kind"})]
    raw = data.get("kind")
    if not isinstance(raw, list) or not all(isinstance(k, dict) for k in raw):
        out.append("kind: not a list of [[kind]] tables")
        raw = []
    kinds, seen = [], set()
    for i, k in enumerate(raw, 1):
        where = f"kind {i}"
        out += [f"{where}: {key}: not a key of a kind" for key in sorted(set(k) - {"n", "name", "paths", "project", "core"})]
        n, name = k.get("n"), k.get("name")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 9:
            out.append(f"{where}: n: not 1 to 9")
        elif n in seen:
            out.append(f"{where}: n: kind {n} twice")
        seen.add(n)
        if not isinstance(name, str) or not name.strip():
            out.append(f"{where}: name: missing or blank")
        globs = []
        for key in ("paths", "project"):
            value = k.get(key)
            if not isinstance(value, list):
                out.append(f"{where}: {key}: missing, or not a list of globs")
                continue
            for g in value:
                why = testmap.glob_problem(g)
                if why:
                    out.append(f"{where}: {key}: {g}: {why} ({testmap.GLOB_VALID})")
                else:
                    globs.append(g)
        if not isinstance(k.get("core", False), bool):
            out.append(f"{where}: core: not true or false")
        kinds.append({"n": n, "name": name, "globs": [testmap.glob_regex(g) for g in globs],
                      "core": k.get("core") is True})
    if not out and sorted(seen) != list(range(1, 10)):
        out.append(f"kind: the kinds are n = 1 to 9, each once; found {sorted(seen)}")
    if out:
        raise KindsProblem(f"{shown}: " + f"; {shown}: ".join(out))
    return sorted(kinds, key=lambda k: k["n"])


def kinds_of(paths, kinds: list[dict], core=()) -> list[dict]:
    """Each path, in path order, with every kind one of whose globs matches it (the core files' kind: the test
    map's `core` globs), in kind order; a path no kind matches is `unclassified`, never dropped."""
    core_rx = [testmap.glob_regex(g) for g in core]
    out = []
    for path in sorted(set(paths)):
        names = [k["name"] for k in kinds
                 if any(rx.fullmatch(path) for rx in k["globs"] + (core_rx if k["core"] else []))]
        out.append({"path": path, "kinds": names or [UNCLASSIFIED]})
    return out


# ---------------------------------------------------------------- main's copy only (C7 section 1)


def check_main_copy(main: Path):
    mine = Path(__file__).resolve()
    if not same(mine, main / ".agents/kit/bin/review.py"):
        raise refuse("main copy", f"review.py ran from {mine.as_posix()}",
                     f"python -I {(main / '.agents/kit/bin/review.py').as_posix()}")


# ---------------------------------------------------------------- the checks before reserving (C7 section 2)


def codex_usage(home: Path | None, now: datetime | None = None) -> tuple[float | None, str]:
    """Codex's reading: the newest rollout's last `token_count` record with `rate_limits`, the larger
    `used_percent` of the windows that have not reset yet (M97). (None, why) when there is none."""
    if home is None or not (home / "sessions").is_dir():
        return None, "no Codex sessions"
    rollouts = sorted((home / "sessions").glob("**/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not rollouts:
        return None, "no Codex sessions"
    now_ts = (now or datetime.now(timezone.utc)).timestamp()
    try:
        lines = rollouts[-1].read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, "the newest Codex rollout cannot be read"
    for line in reversed(lines):
        if '"token_count"' not in line:
            continue
        try:
            limits = (json.loads(line).get("payload") or {}).get("rate_limits")
        except ValueError:
            continue
        if not isinstance(limits, dict):
            continue
        live = [w.get("used_percent") for w in (limits.get("primary"), limits.get("secondary"))
                if isinstance(w, dict) and isinstance(w.get("used_percent"), (int, float))
                and isinstance(w.get("resets_at"), (int, float)) and w["resets_at"] > now_ts]
        if live:
            return max(live), "Codex"
        return None, "Codex's windows have reset since its last session"
    return None, "no Codex rate limits recorded"


def check_head(main: Path, branch: str, head: str, base: str | None) -> dict:
    fetched = run(["git", "fetch", "-q", "origin"], main)
    if fetched.returncode != 0:
        raise refuse("head", f"git fetch origin failed: {(fetched.stderr or fetched.stdout).strip()[:300]}",
                     "fix the remote or the network, then run the review again")
    remote = run(["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"], main).stdout.strip()
    if not remote:
        raise refuse("head", f"origin/{branch} does not exist (the branch is not pushed)",
                     f"git push -u origin {branch}, then review the pushed head")
    if remote != head:
        raise refuse("head", f"origin/{branch} is {remote}, not --head {head} (unpushed or moved)",
                     "push the branch and pass the pushed head: --head <git rev-parse origin/<branch>>")
    base_name = (base or default_branch(main)).removeprefix("origin/")
    base_ref = f"origin/{base_name}"
    if not run(["git", "rev-parse", "--verify", "--quiet", base_ref], main).stdout.strip():
        raise refuse("head", f"the base {base_ref} does not exist", "--base <a pushed branch>")
    listed = run(["git", "diff", "--name-status", "-z", "-M", f"{base_ref}...{head}"], main)
    if listed.returncode != 0:
        raise RuntimeError(f"git diff --name-status {base_ref}...{head}: {(listed.stderr or listed.stdout).strip()[:400]}")
    changed = name_status(listed.stdout)
    if not changed:
        raise refuse("head", f"git diff {base_ref}...{head[:7]} is empty", "commit and push the change to review")
    main_ref = f"origin/{default_branch(main)}"
    return {"base": base_name, "base_ref": base_ref, "base_commit": git(main, "merge-base", base_ref, head),
            "main_ref": main_ref, "main_commit": git(main, "rev-parse", main_ref), "changed_paths": changed}


def name_status(text: str) -> list[list[str]]:
    """`git diff --name-status -z`: [status, path], or [status, old, new] for a rename or copy. Its NUL-delimited
    form never quotes a path, where the line form writes a non-ASCII one quoted with octal escapes (PR #175 review
    round 1: a quoted `src/<s-cedilla>.py` was skipped by the lint, a doc lost its kind and its map entry)."""
    tokens, out, i = text.split("\0"), [], 0
    while i < len(tokens) and tokens[i]:
        n = 2 if tokens[i][:1] in ("R", "C") else 1
        out.append(tokens[i:i + 1 + n])
        i += 1 + n
    return out


def counted_verdicts(coordination: Path, ticket: int) -> list[dict]:
    """C7 section 9: a ticket's verdict files that a review record names by path and hash, oldest first."""
    named: dict[str, set] = {}  # a crashed attempt's record names the same path with another hash (section 9)
    for path in sorted((coordination / "reviews").glob("review-*.json"), key=lambda p: p.name, reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if record.get("ticket") == ticket and record.get("verdict"):
            named.setdefault(record["verdict"], set()).add(record.get("verdict_sha256"))
    out = []
    for path in sorted((coordination / "verdicts" / f"t{ticket}").glob("round-*.json"),
                       key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        rel = path.relative_to(coordination).as_posix()
        data = path.read_bytes()
        if sha256(data) in named.get(rel, ()):
            out.append({**json.loads(data.decode("utf-8")), "path": rel})
    return out


def fix_answers(coordination: Path, ticket: int) -> list[dict]:
    """Your `fix` answers to this ticket's escalations (C8 section 8, C9 section 4)."""
    escalations = {}
    for path in (coordination / "merges").glob("escalation-*.md"):
        fm = front_matter(path.read_text(encoding="utf-8", errors="replace"))
        if fm.get("ticket", "").lstrip("t") == str(ticket):
            escalations[fm.get("id") or path.stem] = fm
    out = []
    for path in (coordination / "merges").glob("answer-*.md"):
        fm = front_matter(path.read_text(encoding="utf-8", errors="replace"))
        if fm.get("escalation") in escalations and fm.get("answer") == "fix":
            out.append({**fm, "verdict": escalations[fm["escalation"]].get("verdict")})
    return out


def skip_of(main: Path, verdicts: list[dict], head: str, main_ref: str) -> dict | None:
    """Design 3.3's skip (research decision B; the lead's reading, 2026-11-09: "a re-review is a review asked again
    of reviewed work; new commits are not a re-review"): the previous counted verdict left no blocker or fix
    finding open (it approved, or it was a skip covering an approval), and the head is that approval's head plus
    nothing but clean updates from main, the reach merge.py binds an approval to (C8 section 4, its own
    `update_chain`). Then what the skip covers; else None, and the round runs in full."""
    if not verdicts or verdicts[-1].get("outcome") not in ("approved", "skipped"):
        return None
    last = verdicts[-1]
    approval = ({"id": last.get("id"), "head": last.get("head"), "path": last["path"]} if last["outcome"] == "approved"
                else last.get("covers") or {})
    ref = approval.get("head")
    if not (isinstance(ref, str) and re.fullmatch(r"[0-9a-f]{40}", ref)):
        return None
    chain = merge.update_chain(main, ref, head, main_ref)
    if isinstance(chain, str):
        return None
    return {"id": approval.get("id"), "head": ref, "path": approval.get("path"), "updates": chain}


def check_round(coordination: Path, ticket: int, head: str, max_fix_rounds: int, main: Path,
                main_ref: str) -> tuple[int, int, dict | None]:
    """C7 section 9's refusals; the round this review would be (its number, counting every verdict), its place in
    the fix-round budget (counting only the rounds that ran: a skip runs nothing, PR #175 review round 1), and
    what it skips on (design 3.3), or None."""
    verdicts, answers = counted_verdicts(coordination, ticket), fix_answers(coordination, ticket)
    for v in verdicts:
        if v.get("head") == head:
            raise refuse("round", f"{head[:7]} was already reviewed in round {v.get('round')} ({v.get('outcome')}, "
                         f"{v['path']})", "push a new head with the fixes and review that")
    if verdicts and verdicts[-1].get("outcome") in ("needs_decision", "escalated"):
        last = verdicts[-1]
        if not any(a.get("verdict") == last["path"] for a in answers):
            raise refuse("round", f"round {last.get('round')} ended {last.get('outcome')} ({last['path']}) and no "
                         "fix answer is recorded for its escalation", "wait for the user's answer (escalate.py answer)")
    r = len(verdicts) + 1
    budget = sum(1 for v in verdicts if v.get("outcome") != "skipped") + 1
    skip = skip_of(main, verdicts, head, main_ref)  # a skip runs nothing, so the round cap does not stop it
    if skip is None and budget >= max_fix_rounds + 2 + len(answers):
        raise refuse("round", f"round {r} is past the round cap ({max_fix_rounds} fix rounds, {len(answers)} fix answers"
                     + (f"; skips not counted, it is round {budget} of the budget" if budget != r else "") + ")",
                     "the ticket is the user's: wait for an answer to its escalation")
    return r, budget, skip


def check_ready(coordination: Path, project: str, ticket: int, branch: str, head: str) -> Path:
    """C7 check 6: the newest READY for this ticket and head from its builder, or for a control branch from
    the orchestrator, passing guard.py's READY check (C5 section 3)."""
    sender = (re.compile(rf"^{re.escape(project)}-orch(-\d+)?$") if branch.startswith("control/")
              else re.compile(rf"^{re.escape(project)}-t{ticket}(-\d+)?$"))
    who = f"{project}-orch" if branch.startswith("control/") else f"{project}-t{ticket}"
    found = []
    for path in (coordination / "messages").glob("*/*.md"):
        if ".tmp-" in path.name:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fm = front_matter(text)
        sent_by = fm.get("from") or path.stem.split("-", 1)[-1]
        claimed = fm.get("head", "")
        if (fm.get("kind") == "ready" and fm.get("ticket", "").lstrip("t") == str(ticket) and sender.match(sent_by)
                and len(claimed) >= 7 and head.startswith(claimed)):
            found.append((path.name, path, text))
    if not found:
        raise refuse("READY", f"no READY from {who} (or {who}-<k>) for ticket {ticket} at {head[:7]} in "
                     f"{(coordination / 'messages').as_posix()}", "send READY for this head first (C9 section 3)")
    _, path, text = max(found)
    if text.rstrip().splitlines()[-1].strip() != "<!-- end -->":
        raise refuse("READY", f"{path.name} has no end line: still being written, or broken",
                     "finish the READY message with its end line <!-- end -->")
    problem = ready_problem(text)
    if problem:
        raise refuse("READY", f"{path.name}: {problem}",
                     "a fenced block with the command you ran ($ ...) and its output, showing tests that ran and passed")
    return path


def check_reviewer_home(main: Path, values: dict) -> Path:
    raw = str(values["reviewer_home"][0])
    home = resolve(main, raw)
    valid = "reviewer_home in agent-kit.local.toml: its own folder outside %TEMP%, logged in once with CODEX_HOME=<it> codex login"
    if not home.is_dir():
        raise refuse("reviewer home", f"{home.as_posix()} does not exist", valid)
    if same(home, Path.home() / ".codex"):
        raise refuse("reviewer home", f"{home.as_posix()} is your own ~/.codex", valid)
    if under(home, tempfile.gettempdir()):
        raise refuse("reviewer home", f"{home.as_posix()} is under the temp folder (5.2 finding 5)", valid)
    r = run([tool("codex"), "login", "status"], main, env={**os.environ, "CODEX_HOME": str(home)}, timeout=120)
    if r.returncode != 0:
        raise refuse("reviewer home", f"codex login status with CODEX_HOME={home.as_posix()} exited {r.returncode}: "
                     f"{' '.join((r.stderr or r.stdout).split())[:200]}", valid)
    python = str(values["reviewer_python"][0])
    if python and not (kitconfig.is_absolute(python) and Path(python).is_file()):
        raise refuse("reviewer python", f"{python} is not an absolute path to a file",
                     "reviewer_python in agent-kit.local.toml: the reviewer's own python.exe, outside your profile (M118)")
    return home


def checkout_paths(main: Path, values: dict, origin_url: str) -> list[Path]:
    """C7 section 3: the two standing checkouts, each a clone of origin."""
    out = []
    for raw in values["reviewer_checkouts"][0]:
        co = resolve(main, raw)
        valid = f"git clone {origin_url} {co.as_posix()}"
        if not (co / ".git").exists():
            raise refuse("checkout", f"{co.as_posix()} is not a clone", valid)
        r = run(["git", "remote", "get-url", "origin"], co)
        url = r.stdout.strip()
        if r.returncode != 0 or not (url == origin_url or (Path(url).exists() and same(url, origin_url))):
            raise refuse("checkout", f"{co.as_posix()}'s origin is {url or 'missing'}, not {origin_url}", valid)
        out.append(co)
    if len({co.name.lower() for co in out}) != len(out):  # the lock is named by the folder name (section 3)
        raise refuse("checkout", "the reviewer checkouts " + " and ".join(co.as_posix() for co in out)
                     + " have the same folder name, so they would share one lock",
                     "reviewer_checkouts in agent-kit.local.toml with two different folder names")
    return out


def checks(args, main: Path) -> dict:
    """C7 section 2, in order; the first that fails refuses (exit 1); nothing is reserved or written,
    except check 3's usage-stop notice (C6 section 4), and not that under --check."""
    values = check_config(main)
    if values["reviewer.engine"][0] != "codex":
        raise refuse("config", "reviewer.engine is claude: the claude engine is not built",
                     'reviewer.engine = "codex" in agent-kit.toml')
    free = check_memory(values)
    coordination = resolve(main, str(values["coordination"][0]))
    home_raw = resolve(main, str(values["reviewer_home"][0]))
    claude_pct, claude_age = usage.read(coordination)  # C6 section 4: the triager's
    codex_pct, _ = codex_usage(home_raw if home_raw.is_dir() else None)
    known = [(p, src) for p, src in ((claude_pct, f"Claude, {claude_age} min old"), (codex_pct, "Codex")) if p is not None]
    percent, source = max(known) if known else (None, None)
    check_usage(coordination, values, f"the review of t{args.ticket}", percent, source, successor=False,
                check_only=args.check, what="reviewing",
                valid="wait for the usage window to reset, then run the review again")
    head = check_head(main, args.branch, args.head, args.base)
    print(f"head: origin/{args.branch} is {args.head[:7]}; {len(head['changed_paths'])} changed paths "
          f"against {head['base_ref']}")
    rnd, budget, skip = check_round(coordination, args.ticket, args.head, int(values["reviewer.max_fix_rounds"][0]),
                                    main, head["main_ref"])
    print(f"round: {rnd}" + (f", a skip: {args.head[:7]} is the approved head {skip['head'][:7]} ({skip['path']}) "
                             f"plus {len(skip['updates'])} clean updates from main" if skip else ""))
    ready = check_ready(coordination, str(values["project.name"][0]), args.ticket, args.branch, args.head)
    print(f"READY: {ready.relative_to(coordination).as_posix()}")
    home = check_reviewer_home(main, values)
    print(f"reviewer home: {home.as_posix()}, logged in")
    repo, origin_url, github = repository(main)
    checkouts = checkout_paths(main, values, origin_url)
    print("checkouts: " + ", ".join(co.name for co in checkouts))
    secret_entries = [e for e in values["secret_files"][0] if not outside_project(e)]
    return {"main": main, "values": values, "coordination": coordination, "home": home, "round": rnd,
            "budget": budget, "skip": skip,
            "ready": ready, "repository": repo, "github": github, "checkouts": checkouts, "secret_entries": secret_entries,
            "memory_free_gb": None if free is None else round(free, 1),
            "usage": {"claude": claude_pct, "codex": codex_pct}, **head}


# ---------------------------------------------------------------- reserving a checkout (C7 section 3)


def holder_record(review_id: str, co: Path, args) -> dict:
    return {"format": "review-lock", "version": 1, "id": review_id, "checkout": co.name, "ticket": args.ticket,
            "head": args.head, "holder": os.environ.get("CLAUDE_CODE_SESSION_ID") or "terminal", "pid": os.getpid(),
            "acquired_at": workfiles.utc_iso()}


def busy_text(co: Path, held: dict | None) -> str:
    if not held:
        return f"{co.name} is held (its holder wrote nothing readable)"
    return (f"{co.name} is held by review {held.get('id')} (ticket {held.get('ticket')}) since "
            f"{held.get('acquired_at')}")


class Busy(Exception):
    pass


def reserve(found: dict, review_id: str, args):
    """The first free checkout in config order, held by this process until it ends (C7 section 3). Both
    held: Busy (exit 3). The ticket already held in the other checkout: refused (exit 1)."""
    locks = found["coordination"] / "locks"
    held = {}
    for co in found["checkouts"]:
        try:
            lock = kitlock.claim(locks / f"review-{co.name}.lock", holder_record(review_id, co, args))
        except kitlock.Busy as busy:
            held[co] = busy.holder
            continue
        for other in found["checkouts"]:
            if other == co:
                continue
            path = locks / f"review-{other.name}.lock"
            if other not in held:
                if (kitlock.read_holder(path) or {}).get("ticket") != args.ticket:
                    continue
                try:  # the file names this ticket, but says who holds the lock only while it is held
                    kitlock.claim(path, {"format": "review-lock-probe"}).release()
                    continue
                except kitlock.Busy as busy:
                    held[other] = busy.holder
            info = held[other]
            if info and info.get("ticket") == args.ticket:
                lock.release()
                raise refuse("busy", f"ticket {args.ticket} is already under review in {other.name} "
                             f"(review {info.get('id')})", "wait for that review to finish")
        return co, lock
    raise Busy("REFUSED (busy): " + "; ".join(busy_text(co, held.get(co)) for co in found["checkouts"])
               + ". Valid: retry when one finishes. " + NOTHING_STARTED)


# ---------------------------------------------------------------- preparing the checkout (C7 section 4)


def control_files(co: Path, commit: str, patterns, lock) -> list[str]:
    return [p for p in git(co, "ls-tree", "-r", "--name-only", commit, lock=lock).splitlines() if matches(p, patterns)]


def prepare(found: dict, co: Path, args, review_id: str, lock) -> dict:
    """Steps 1-5: the candidate, main's control files over it, the secret files, the export, the test copy."""
    main_commit, schema = found["main_commit"], kitconfig.load_schema(found["main"])
    patterns = schema["fixed"]["control_paths"]
    fetched = run(["git", "fetch", "-q", "origin"], co, lock=lock)  # step 1: the candidate
    if fetched.returncode != 0:
        raise Failed("prepare", f"git fetch origin in {co.as_posix()} failed: {(fetched.stderr or fetched.stdout).strip()[:300]}")
    try:
        run(["git", "worktree", "remove", "--force", ".kit-review/candidate"], co, lock=lock)  # "not a worktree" is fine
        git(co, "worktree", "prune", lock=lock)
        git(co, "checkout", "-q", "--force", "--detach", args.head, lock=lock)
        git(co, "clean", "-ffdxq", lock=lock)
    except RuntimeError as e:
        raise Failed("prepare", f"{e}. Valid: delete {co.as_posix()} and clone it again")
    exclude = Path(git(co, "rev-parse", "--git-path", "info/exclude", lock=lock))
    exclude = exclude if exclude.is_absolute() else co / exclude
    listed = exclude.read_text(encoding="utf-8", errors="replace").split() if exclude.is_file() else []
    if ".kit-review/" not in listed:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as f:
            f.write("\n.kit-review/\n")
    # Step 2: main's control files over the candidate; the index stays at the head.
    from_main = control_files(co, main_commit, patterns, lock)
    if from_main:
        r = run(["git", "restore", f"--source={main_commit}", "--worktree", "--pathspec-from-file=-",
                 "--pathspec-file-nul"], co, input_text="\0".join(from_main), lock=lock)
        if r.returncode != 0:
            raise Failed("prepare", f"git restore of main's control files failed: {r.stderr.strip()[:300]}")
    gone = sorted(set(control_files(co, args.head, patterns, lock)) - set(from_main))
    for rel in gone:  # the candidate added it: it goes
        (co / rel).unlink(missing_ok=True)
    # Step 3: the secret files, never printed; and main's local settings for main's guard (M120).
    copied = copy_secrets(found["main"], co, found["secret_entries"])
    local_settings(found, co)
    # Step 4: the export.
    kr = co / ".kit-review"
    (kr / "out").mkdir(parents=True, exist_ok=True)
    (kr / "tmp").mkdir(exist_ok=True)  # pytest's temp root (M117), which codex_env names
    export(found, co, kr, args, review_id, lock)
    # Step 5: the test copy, the candidate exactly.
    git(co, "worktree", "add", "-q", "--detach", str(kr / "candidate"), args.head, lock=lock)
    copy_secrets(found["main"], kr / "candidate", found["secret_entries"])
    return {"restored": from_main, "removed": gone, "secret_files_copied": copied, "test_copy": kr / "candidate"}


def local_settings(found: dict, co: Path):
    """The checkout is a clone, with no agent-kit.local.toml (not in git), and main's guard reads the config of
    the checkout it runs in, so it refused every command but the canary (M120). Main's local settings go there,
    each single path resolved from the main checkout, so the guard reads main's coordination folder. Not
    `reviewer_checkouts`: resolved from the checkout, any value but the default can name the checkout itself
    (absolute paths, or the sibling layout `../codex`), which C3 V8 refuses; the guard does not read it, so the
    copy keeps the default."""
    main, specs = found["main"], kitconfig.load_schema(found["main"])["key"]
    sets = []
    for key, spec in specs.items():
        if spec["file"] != "local" or key == "reviewer_checkouts":
            continue
        value = found["values"][key][0]
        if spec["type"] == "path" and value:
            value = resolve(main, value).as_posix()
        sets.append(f"{key}={kitconfig.toml_value(value)}")
    text, problems = kitconfig.render(co, "local", sets)
    if problems:
        raise Failed("prepare", "main's local settings do not render for the checkout: "
                     + "; ".join(str(p) for p in problems)[:300])
    workfiles.write_atomic(co / "agent-kit.local.toml", text)


def export(found: dict, co: Path, kr: Path, args, review_id: str, lock):
    """C7 section 4 step 4: what the sandbox cannot fetch itself (decision 78)."""
    main, coordination = found["main"], found["coordination"]
    gh = [tool("gh"), "issue", "view", str(args.ticket), "--json", "number,title,body,labels,comments"]
    if found["github"]:
        gh += ["--repo", found["repository"]]
    r = run(gh, main, timeout=120, lock=lock)
    try:
        issue = json.loads(r.stdout) if r.returncode == 0 else None
    except ValueError:
        issue = None
    if not isinstance(issue, dict):
        raise Failed("export", f"gh issue view {args.ticket} failed (exit {r.returncode}): "
                     f"{' '.join((r.stderr or r.stdout).split())[:300]}")
    labels = ", ".join(lb.get("name", "") for lb in issue.get("labels") or []) or "none"
    lines = ["---", "format: review-ticket", "version: 1", f"ticket: {args.ticket}",
             f"fetched_at: {workfiles.utc_iso()}", "---", "", f"# Issue #{issue.get('number')}: {issue.get('title')}",
             "", f"Labels: {labels}", "", issue.get("body") or "", ""]
    for c in issue.get("comments") or []:
        who = (c.get("author") or {}).get("login", "?")
        lines += [f"## Comment by {who} at {c.get('createdAt', '?')}", "", c.get("body") or "", ""]
    ticket_text = "\n".join(lines)
    workfiles.write_atomic(kr / "ticket.md", ticket_text)
    brief = coordination / "briefs" / f"t{args.ticket}.md"
    brief_text = brief.read_text(encoding="utf-8", errors="replace") if brief.is_file() else ""
    if brief_text:
        workfiles.write_atomic(kr / "brief.md", brief_text)
    workfiles.write_atomic(kr / "ready.md", found["ready"].read_text(encoding="utf-8", errors="replace"))
    for rel in sorted({p.removeprefix("./") for p in PATHLIKE.findall(ticket_text + "\n" + brief_text)}):
        if kitconfig.escapes(rel) or kitconfig.is_absolute(rel):
            continue
        if run(["git", "cat-file", "-t", f"{found['main_commit']}:{rel}"], co, lock=lock).stdout.strip() == "blob":
            blob = run(["git", "show", f"{found['main_commit']}:{rel}"], co, lock=lock, binary=True)
            target = kr / "spec" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob.stdout)
    standard = git(co, "log", "-1", "--format=%H", found["main_commit"], "--", ".agents/skills/review/", lock=lock)
    found["standard_commit"] = standard or None
    review = {"format": "review-input", "version": 1, "id": review_id, "repository": found["repository"],
              "ticket": args.ticket, "branch": args.branch, "head": args.head, "base": found["base"],
              "base_commit": found["base_commit"], "main_commit": found["main_commit"],
              "standard_commit": found["standard_commit"], "diff": f"git diff {found['base_commit']}...{args.head}",
              "round": found["round"], "checkout": co.as_posix(), "test_copy": (kr / "candidate").as_posix(),
              "python": str(found["values"]["reviewer_python"][0]) or None,
              "KIT_REVIEW_OUT": (kr / "out" / "handoff-1.json").as_posix()}
    workfiles.write_atomic(kr / "review.json", json.dumps(review, indent=1) + "\n")
    schema = co / ".agents/kit/review/findings.schema.json"  # main's, restored in step 2
    if not schema.is_file():
        raise Failed("export", f"main has no {schema.relative_to(co).as_posix()}")
    shutil.copyfile(schema, kr / "findings.schema.json")


# ---------------------------------------------------------------- before the reviewer: the lint, the mapped tests (design 2.7, 3.2)


TAIL = 20  # the output's last lines a red stage's finding carries [judgment]
LOCATION = {"lint": re.compile(r"^(\S[^:\n]*\.py):(\d+):\d+: ", re.M),  # ruff's concise `path:row:col: CODE ...`
            "tests": re.compile(r"^(\S[^:\n]*\.py):(\d+): ", re.M)}   # pytest's `path:line: <Error>` under a traceback


def changed_paths(found: dict) -> tuple[list[str], list[str]]:
    """Every path the diff names, both sides of a rename (as the test map reads them), and those the head holds."""
    every, current = set(), set()
    for status, *paths in found["changed_paths"]:
        every.update(paths)
        if not status.startswith("D"):
            current.add(paths[-1])
    return sorted(every), sorted(current)


def shown_argv(argv) -> str:
    return " ".join(f'"{a}"' if " " in str(a) else str(a) for a in argv)


def main_map(co: Path, kr: Path, main_commit: str, lock) -> tuple[object | None, tuple, str | None]:
    """Main's test map (`tests/map.toml` at the main commit, never the candidate's: a pull request cannot pick its
    own tests), checked against the test copy; its `core` list (read alone when the whole map does not load, so
    the core files' kind still shows); and why there is no map to run, or None."""
    spec = f"{main_commit}:{testmap.DEFAULT_MAP}"
    if run(["git", "cat-file", "-e", spec], co, lock=lock).returncode != 0:
        return None, (), f"main has no {testmap.DEFAULT_MAP}"
    blob = run(["git", "show", spec], co, lock=lock, binary=True)
    if blob.returncode != 0:
        raise Failed("prepare", f"git show {spec} failed: {blob.stderr.decode('utf-8', 'replace').strip()[:300]}")
    path = kr / "map.toml"
    path.write_bytes(blob.stdout)
    try:
        test_map = testmap.load_map(path, kr / "candidate")
    except testmap.Refused as e:
        try:
            raw = tomllib.loads(blob.stdout.decode("utf-8")).get("core")
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            raw = None
        core = tuple(g for g in raw if not testmap.glob_problem(g)) if isinstance(raw, list) else ()
        return None, core, (f"main's {testmap.DEFAULT_MAP} does not load against the candidate: "
                            + "; ".join(str(p) for p in e.problems)[:600])
    return test_map, test_map.core, None


def stage(ctx: dict, name: str, argv: list[str]) -> dict:
    """One stage, in the test copy, inside the lock's job and with a calling session's markers stripped (as the
    merge's clean run); its whole output kept with the record. Past the reviewer-run bound: the round fails."""
    copy, keep = ctx["co"] / ".kit-review" / "candidate", ctx["keep"]
    limit = timeout_for(RUN_TIMEOUT)
    try:
        r = run(argv, copy, env=clean_env(), timeout=limit, lock=ctx["lock"])
    except subprocess.TimeoutExpired:
        raise Failed("tests", f"the {name} stage (`{shown_argv(argv)}`) did not finish in {limit} s")
    text = (r.stdout or "") + (r.stderr or "")
    out = keep / f"{name}-output.txt"
    workfiles.write_atomic(out, text)
    lines = [ln.strip(" =") for ln in text.splitlines() if ln.strip(" =")]
    ruffs = [ln for ln in lines if ln.startswith(("Found ", "All checks passed"))] if name == "lint" else []
    return {"ran": True, "command": argv, "exit_code": r.returncode, "summary": (ruffs or lines or [""])[-1],
            "output": out.relative_to(ctx["found"]["coordination"]).as_posix(), "text": text}


def stage_entry(name: str, result: dict, copy: Path) -> dict:
    """The stage in the verdict's `tests`, in the findings schema's shape, with the stage named."""
    return {"command": shown_argv(result["command"]), "summary": result["summary"], "exit_code": result["exit_code"],
            "ran_in": copy.as_posix(), "stage": name}


def red_finding(name: str, result: dict, text: str, first: str) -> dict:
    """A red stage as one `fix` finding: where its output points (ruff's first error, pytest's last traceback
    line in the project), else the first file it ran, and the output's last lines."""
    found = list(LOCATION[name].finditer(text))
    m = (found[0] if name == "lint" else found[-1]) if found else None
    file, line = (m.group(1).replace("\\", "/"), int(m.group(2))) if m else (first, 1)
    what = "the lint" if name == "lint" else "the mapped tests"
    tail = "\n".join(text.rstrip().splitlines()[-TAIL:])
    return {"id": "F1", "severity": "fix", "file": file, "line": line,
            "title": f"{what} {'is' if name == 'lint' else 'are'} red in the test copy",
            "what": f"`{shown_argv(result['command'])}` exited {result['exit_code']} in the test copy "
                    f"({result['summary']}). Its last lines:\n{tail}"
                    + ("" if m else "\n(The output names no file and line; this is the first file it ran.)"),
            "why": f"a red stage stops the round before the reviewer reads (design 2.7); the whole output is "
                   f"{result['output']} in the coordination folder",
            "real_use": "the merge's clean run runs the same code and would refuse it",
            "fix": f"make {what} green on the branch, push, and request the review again", "real_data_count": None}


def before_reading(ctx: dict, test_map, map_note: str | None) -> dict:
    """Design 3.2 and 2.7, in the test copy: the lint on the changed Python files (ruff from the reviewer's
    Python, the kit home's, else this one; absent ruff is not run, never a refusal), then the tests main's map
    names for the changed paths as one command, in place of the clean run. With no map, a map that does not load
    against the candidate, or one naming the full suite, the reviewer runs the clean run as before. A red stage
    stops the next, and the caller stops the round."""
    found, copy = ctx["found"], ctx["co"] / ".kit-review" / "candidate"
    python = str(found["values"]["reviewer_python"][0]) or sys.executable
    every, current = changed_paths(found)
    stages = {"lint": None, "tests": None, "clean_run": "yours"}
    tests, not_run, red, stopped = [], [], None, None
    py_files = [p for p in current if p.endswith(".py") and (copy / p).is_file()]
    if not py_files:
        stages["lint"] = {"ran": False, "why": "no changed Python file"}
    else:
        argv = [python, "-m", "ruff", "check", "--isolated", "--select", "E9,F", "--output-format", "concise", *py_files]
        result = stage(ctx, "lint", argv)
        text = result.pop("text")
        if result["exit_code"] != 0 and "No module named ruff" in text:
            why = f"ruff is not installed for {Path(python).as_posix()}"
            stages["lint"] = {"ran": False, "command": argv, "why": why, "output": result["output"]}
            not_run.append({"command": shown_argv(argv), "why": why})
        else:
            stages["lint"] = result
            tests.append(stage_entry("lint", result, copy))
            if result["exit_code"] != 0:
                red, stopped = red_finding("lint", result, text, py_files[0]), "lint"
    if red:
        stages["tests"] = {"ran": False, "why": "the lint was red: a red stage stops the next (design 2.7)"}
        not_run.append({"command": "the mapped tests", "why": stages["tests"]["why"]})
    elif test_map is None:
        stages["tests"] = {"ran": False, "why": f"{map_note}: the reviewer runs the clean run"}
    else:
        selection = testmap.select(test_map, copy, every)
        clean = [str(a) for a in found["values"].get("merge.clean_run", ([],))[0] or ()]
        argv = testmap.command(selection, python, clean)
        if clean and not testmap.is_pytest(clean):
            stages["tests"] = {"ran": False, "selection": list(selection.lines),
                               "why": "merge.clean_run is not a pytest command, so its tests cannot be picked by "
                                      "file: the reviewer runs the clean run"}
        elif selection.full:
            stages["tests"] = {"ran": False, "selection": list(selection.lines),
                               "why": "main's test map names the full offline suite: the reviewer runs the clean run"}
        elif argv is None:
            stages["tests"] = {"ran": False, "selection": list(selection.lines), "why": "no changed path maps to a test"}
            stages["clean_run"] = "replaced"
        else:
            result = stage(ctx, "tests", argv)
            text = result.pop("text")
            stages["tests"] = {**result, "selection": list(selection.lines)}
            stages["clean_run"] = "replaced"
            tests.append(stage_entry("tests", result, copy))
            if result["exit_code"] not in (0, 5):  # 5: no test ran, the selected files hold only live tests (testmap.py)
                red, stopped = red_finding("tests", result, text, selection.tests[0]), "tests"
    return {"stages": stages, "tests": tests, "not_run": not_run, "red": red, "stopped": stopped}


def export_stages(kr: Path, stages: dict):
    """The stages reach the reviewer in review.json (its prompt's JSON block, C7 section 6)."""
    review = json.loads((kr / "review.json").read_text(encoding="utf-8"))
    review["stages"] = stages
    workfiles.write_atomic(kr / "review.json", json.dumps(review, indent=1) + "\n")


# ---------------------------------------------------------------- the isolation check (C7 section 5)


def bundled(main: Path) -> set[tuple[str, str]]:
    data = tomllib.loads((main / ".agents/kit/review/codex-bundled-skills.toml").read_text(encoding="utf-8"))
    return {(s["name"], s["source"]) for s in data.get("skill", [])}


def codex_env(home: Path, co: Path, values: dict, k: int = 1) -> dict:
    """The variables reach Codex's hooks (M27) and the commands it runs (M94): the reviewer's Python first on
    PATH (M118) and pytest's temp root in the checkout (M117)."""
    env = {**os.environ, "CODEX_HOME": str(home), "KIT_ROLE": "reviewer",
           "KIT_REVIEW_OUT": str(co / ".kit-review" / "out" / f"handoff-{k}.json")}
    python = str(values["reviewer_python"][0])
    if python:
        env["PATH"] = str(Path(python).parent) + os.pathsep + env.get("PATH", "")
    env["PYTEST_DEBUG_TEMPROOT"] = str(co / ".kit-review" / "tmp")  # made at step 4; writing here would break --check
    return env


def render_flags(values: dict, effort: str | None = None) -> list[str]:
    """Section 6's settings as `-c` values, the only form `codex debug prompt-input` takes."""
    return ["-c", f'model="{values["reviewer.model"][0]}"',
            "-c", f'model_reasoning_effort="{effort or values["reviewer.effort"][0]}"',
            "-c", 'sandbox_mode="workspace-write"', "-c", SANDBOX[3], "-c", "sandbox_workspace_write.network_access=true"]


def skills_config(names) -> str:
    return "skills.config=[" + ",".join(f'{{name="{n}",enabled=false}}' for n in sorted(names)) + "]"


def parse_render(data) -> dict:
    """The skills (name, root) from `<skills_instructions>`, and each AGENTS.md block (folder, text)."""
    texts = [c.get("text", "") for item in data if isinstance(item, dict)
             for c in item.get("content") or [] if isinstance(c, dict)]
    skills, agents = [], []
    for text in texts:
        if "<skills_instructions>" in text:
            roots = dict(SKILL_ROOT.findall(text))
            for name, root in SKILL_LINE.findall(text):
                skills.append((name.strip(), roots.get(root, root)))
        agents += [(folder.strip(), body) for folder, body in AGENTS_BLOCK.findall(text)]
    return {"skills": skills, "agents": agents}


def not_allowed(skills, co: Path, home: Path, allowed: set[tuple[str, str]]) -> list[tuple[str, str]]:
    """Every skill whose root is neither the checkout's .agents/skills/ nor an allowed bundled one, by name
    and source together (a user skill named like a bundled one is not allowed)."""
    out = []
    for name, root in skills:
        if same(root, co / ".agents/skills"):
            continue
        if any(name == n and same(root, home / "skills" / src) for n, src in allowed):
            continue
        out.append((name, root))
    return out


def agents_problem(agents, co: Path) -> str | None:
    """AGENTS.md instructions from outside the checkout (5.2 finding 1): a global file shows as text in the
    checkout's own block, before `--- project-doc ---`, so the block must be the checkout's file exactly."""
    def lines(text: str) -> str:  # the render keeps the file's CRLF as git checked it out (M96)
        return text.replace("\r\n", "\n").strip()

    own = lines((co / "AGENTS.md").read_bytes().decode("utf-8")) if (co / "AGENTS.md").is_file() else None
    for folder, body in agents:
        if not same(folder, co):
            return f"AGENTS.md instructions for {folder}, outside {co.as_posix()}"
        if lines(body) != own:
            return "the AGENTS.md instructions are not only the checkout's own AGENTS.md (a global file loads)"
    if own is not None and not agents:
        return "the checkout's AGENTS.md is not in the render"
    return None


def render(co: Path, home: Path, values: dict, extra: list[str], lock=None) -> tuple[str, dict]:
    r = run([tool("codex"), "debug", "prompt-input", *render_flags(values), *extra], co, env=codex_env(home, co, values),
            timeout=300, lock=lock)
    try:
        data = json.loads(r.stdout)
    except ValueError:
        data = None
    if r.returncode != 0 or not isinstance(data, list):
        raise Failed("isolation", f"codex debug prompt-input exited {r.returncode}: "
                     f"{' '.join((r.stderr or r.stdout).split())[:300]}")
    return r.stdout, parse_render(data)


def isolate(co: Path, home: Path, main: Path, values: dict, lock=None, keep: Path | None = None) -> dict:
    """Steps 1-3: render, disable every skill not allowed by name, render again; fail if one remains."""
    allowed = bundled(main)
    first, parsed = render(co, home, values, [], lock)
    disable = sorted({name for name, _ in not_allowed(parsed["skills"], co, home, allowed)})
    extra = ["-c", skills_config(disable)] if disable else []
    second, parsed2 = render(co, home, values, extra, lock)
    if keep is not None:
        workfiles.write_atomic(keep / "render-1.json", first)
        workfiles.write_atomic(keep / "render-2.json", second)
    left = not_allowed(parsed2["skills"], co, home, allowed)
    if left:
        name, root = left[0]
        raise Failed("isolation", f"skill {name} from {Path(root).as_posix()} still loads")
    problem = agents_problem(parsed2["agents"], co)
    if problem:
        raise Failed("isolation", problem)
    return {"skills_disabled": disable, "skills_left": [n for n, _ in parsed2["skills"]], "flags": extra,
            "render_sha256": sha256(second.encode("utf-8"))}


def hook_failure(text: str) -> str | None:
    """Why Codex's output shows a PreToolUse hook that failed, or None. Only Codex's own event lines count, each at
    the start of a line: a file the reviewer printed that quotes the failure text is not a failure (issue #176:
    PR #83's substring test voided a review of agent-kit's own guard, whose docs and tests quote it). A hook that
    started and never ended `Completed` or `Blocked` voids too, whatever its failure line says."""
    if HOOK_FAILED.search(text):
        return "shows `hook: PreToolUse Failed`"
    started, ended = len(HOOK_STARTED.findall(text)), len(HOOK_ENDED.findall(text))
    if started > ended:
        return f"shows {started} PreToolUse hooks started and {ended} ended (`Completed` or `Blocked`)"
    return None


def canary(co: Path, home: Path, values: dict, flags: list[str], keep: Path, lock) -> str:
    """Step 4: main's guard denies the canary command; its refusal, naming the nonce, must show, and the
    nonce must never show as the command's output. Hooks off, it only echoes (M24)."""
    nonce = f"KIT-HOOK-CANARY-{secrets.token_hex(4)}"
    prompt = f"Run exactly this shell command and report its output: echo {nonce}"
    cmd = [tool("codex"), "exec", "--cd", str(co), "-m", values["reviewer.model"][0],
           "-c", "model_reasoning_effort=low", *SANDBOX, "-c", "sandbox_workspace_write.network_access=true",
           "--dangerously-bypass-hook-trust", *flags, "-o", str(keep / "canary-last.md"), "-"]
    workfiles.write_atomic(keep / "canary-prompt.txt", prompt)
    raw_wait = os.environ.get("KIT_REVIEW_REFRESH_WAIT_SECONDS", "")
    wait = min(REFRESH_WAIT, int(raw_wait)) if raw_wait.isdigit() else REFRESH_WAIT
    for attempt in range(REFRESH_RETRIES + 1):
        try:
            r = run(cmd, co, env=codex_env(home, co, values), input_text=prompt, timeout=CANARY_TIMEOUT, lock=lock)
        except subprocess.TimeoutExpired:
            raise Failed("hooks", f"the canary run did not finish in {CANARY_TIMEOUT} s")
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        workfiles.write_atomic(keep / "canary-output.txt", out)
        failure = hook_failure(out)
        if failure:  # on every attempt: a failed hook in any run voids it (M29, C7 section 10)
            raise Failed("hooks", f"the canary's output {failure}: a hook failed, so its deny proves nothing")
        if REFRESH_ERROR not in out:
            break
        workfiles.write_atomic(keep / f"canary-output-refresh-{attempt + 1}.txt", out)
        if attempt == REFRESH_RETRIES:
            raise Failed("hooks", f"Codex's sandbox failed to set up {attempt + 1} times (`{REFRESH_ERROR}`, M181), "
                         "so the canary never ran; see the sandbox log in the reviewer home's .sandbox folder")
        print(f"canary: Codex's sandbox failed to set up (`{REFRESH_ERROR}`); retrying in {wait} s (M181)")
        time.sleep(wait)
    if r.returncode != 0:
        raise Failed("hooks", f"the canary run exited {r.returncode}")
    if any(line.strip() == nonce for line in out.splitlines()):
        raise Failed("hooks", f"{nonce} ran: the canary's output shows it, so main's hooks did not block it")
    if not any(BLOCKED_TEXT in line and nonce in line for line in out.splitlines()):
        raise Failed("hooks", f"the canary's output has no `{BLOCKED_TEXT}` naming {nonce} (exit {r.returncode})")
    if not any(BLOCKED_TEXT in line and "BLOCKED (canary," in line for line in out.splitlines()):  # M120
        raise Failed("hooks", f"main's guard blocked {nonce}, but not with its canary refusal `BLOCKED (canary, ...)`: "
                     "it refused for another reason, such as its own error, so it would refuse every command")
    return nonce


# ---------------------------------------------------------------- the reviewer run (C7 section 6)


def timeout_for(default: int) -> int:
    """KIT_REVIEW_TIMEOUT_SECONDS, a test hook like C8's KIT_MERGE_*: it can only shorten a timeout."""
    raw = os.environ.get("KIT_REVIEW_TIMEOUT_SECONDS", "")
    return min(default, max(1, int(raw))) if raw.isdigit() else default


def is_type(value, kind: str) -> bool:
    return {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
            "boolean": isinstance(value, bool), "null": value is None,
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool)}.get(kind, False)


def schema_problem(value, schema: dict, where: str = "the output") -> str | None:
    """The first way `value` misses `schema`, for the JSON Schema keywords findings.schema.json uses (type,
    enum, pattern, required, properties, additionalProperties, items, minItems); None when it fits."""
    kinds = schema.get("type")
    kinds = [kinds] if isinstance(kinds, str) else kinds
    if kinds and not any(is_type(value, k) for k in kinds):
        return f"{where} is not {' or '.join(kinds)}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{where} is {value!r}, not one of {', '.join(map(str, schema['enum']))}"
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        return f"{where} {value!r} does not match {schema['pattern']}"
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                return f"{where} has no {key}"
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                return f"{where} has an unknown field {extra[0]}"
        for key, sub in props.items():
            if key in value:
                problem = schema_problem(value[key], sub, f"{where}.{key}")
                if problem:
                    return problem
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            return f"{where} has fewer than {schema['minItems']} items"
        for i, item in enumerate(value):
            problem = schema_problem(item, schema.get("items", {}), f"{where}[{i}]")
            if problem:
                return problem
    return None


def read_output(path: Path, schema: dict, what: str) -> dict:
    """A run's `-o` or handoff file: JSON in the findings schema, with ids unique (C7 sections 6, 10). A leading
    byte-order mark is dropped: Windows PowerShell 5.1 writes UTF-8 with one (B2, 2026-10-20), as kitconfig reads."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        raise Failed("reviewer", f"{what} was not written ({path.as_posix()})")
    try:
        data = json.loads(text)
    except ValueError:
        raise Failed("output", f"{what} is not JSON: {' '.join(text.split())[:120]!r}")
    problem = schema_problem(data, schema)
    if problem:
        raise Failed("output", f"{what} misses the findings schema: {problem}")
    ids = [f["id"] for f in data["findings"]]
    if len(set(ids)) != len(ids):
        raise Failed("output", f"{what} uses a finding id twice: {sorted(i for i in set(ids) if ids.count(i) > 1)[0]}")
    return data


def capacity_lists(main: Path) -> tuple[list[str], list[str]]:
    data = tomllib.loads((main / ".agents/kit/review/codex-bundled-skills.toml").read_text(encoding="utf-8"))
    return [p.lower() for p in data.get("capacity", [])], [p.lower() for p in data.get("not_capacity", [])]


def is_capacity(text: str, lists: tuple[list[str], list[str]]) -> bool:
    """Decision 77: a capacity error falls back once; a usage limit never does. Unmatched text is no capacity
    error, so the review fails (a wrong list fails closed)."""
    low, (yes, no) = text.lower(), lists
    return any(p in low for p in yes) and not any(p in low for p in no)


def transcript(home: Path, co: Path, since: float) -> str | None:
    """The newest rollout begun after the run started whose first line, `session_meta`, has the checkout as
    its `cwd` (M102)."""
    found = []
    for path in (home / "sessions").glob("**/rollout-*.jsonl"):
        try:
            if path.stat().st_mtime < since:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                first = json.loads(f.readline() or "{}")
        except (OSError, ValueError):
            continue
        if same((first.get("payload") or {}).get("cwd") or "?", co):
            found.append((path.stat().st_mtime, path))
    return max(found)[1].as_posix() if found else None


def merge_into(state: dict, part: dict):
    """A run's findings join the round's by id (a later run's copy wins); tests and not-run entries are kept
    once each."""
    for f in part["findings"]:
        state["findings"][f["id"]] = f
    for key in ("tests", "not_run"):
        for entry in part[key]:
            if entry not in state[key]:
                state[key].append(entry)
    if part["cold_read"]:
        state["cold_read"] = part["cold_read"]


def continuation(k: int, state: dict, remaining: list, co: Path) -> str:
    if k == 1:
        return ""
    ids = [int(i[1:]) for i in state["findings"]]
    return ("\n\n## Continuing an earlier run\n\n"
            f"This is run {k} of this round: the run before handed off before it finished. Its findings so far "
            "are below; keep them in your answer (change one only if you find it wrong) and number new findings "
            f"from F{max(ids, default=0) + 1}. Review what it left: the `remaining` list. Its tests are kept; run "
            "again only what you need. Your handoff file, if you need one, is "
            f"`{(co / '.kit-review' / 'out' / f'handoff-{k}.json').as_posix()}` (KIT_REVIEW_OUT).\n\n"
            "Findings so far:\n\n```json\n" + json.dumps(list(state["findings"].values()), indent=1) + "\n```\n\n"
            "Tests so far:\n\n```json\n" + json.dumps(state["tests"], indent=1) + "\n```\n\n"
            "Remaining:\n\n```json\n" + json.dumps(remaining) + "\n```\n")


def kinds_text(entries: list[dict]) -> str:
    """The prompt's first lines (design 2.1, 3.2): each changed file with the kinds the script read from its path."""
    named = {k for e in entries for k in e["kinds"] if k != UNCLASSIFIED}
    lines = ["# The kinds of change in this review", "",
             "The review script read each changed file's kinds from its path (`.agents/kit/review/kinds.toml`, and "
             "the core files from main's test map). Apply the review rules' checks to each file by its kinds, each "
             "kind its row of the rules' table; `unclassified`: no kind's paths match it.", ""]
    lines += [f"- `{e['path']}`: {'; '.join(e['kinds'])}" for e in entries]
    if len(named) > 1:
        lines += ["", "Several kinds: this change spans more than one kind, so each file takes its own row, and "
                  "Guard and Probe come from the strictest row."]
    return "\n".join(lines) + "\n\n"


def line_problems(findings, co: Path, head: str, lock) -> list[str]:
    """Design 3.2's evidence rule in the schema: `line` is an integer, null only when `file` is a path the
    change deleted or should have added, so no file of that path is at the head."""
    out = []
    for f in findings:
        if f["line"] is None and run(["git", "cat-file", "-e", f"{head}:{f['file']}"], co, lock=lock).returncode == 0:
            out.append(f"{f['id']} ({f['file']}): `line` is null, but {f['file']} is a file in the candidate")
    return out


def reask_text(k: int, state: dict, problems: list[str]) -> str:
    return ("\n\n## Your answer broke the line rule\n\n"
            f"This is run {k} of this round, asked once more. `line` is the finding's line number in the candidate; it "
            "may be null only when `file` is a path the change deleted or should have added, and then `what` says "
            "which. These findings break it:\n\n" + "".join(f"- {p}\n" for p in problems)
            + "\nAnswer again with the whole answer below, every finding kept and each `line` set, `complete` true; "
            "run nothing new unless you need it to find a line. Your answer so far:\n\n```json\n"
            + json.dumps({"findings": list(state["findings"].values()), "tests": state["tests"],
                          "not_run": state["not_run"], "cold_read": state["cold_read"]}, indent=1) + "\n```\n")


def reviewer_attempt(ctx: dict, k: int, prompt: str, model: str, effort: str, fallback: bool, reask: bool = False):
    """One `codex exec` of the reviewer (C7 section 6); its prompt, output and files kept with the record."""
    co, keep, lock = ctx["co"], ctx["keep"], ctx["lock"]
    out = co / ".kit-review" / "out"
    tag = f"{k}-fallback" if fallback else f"{k}"
    target, handoff = out / f"reviewer-{tag}.json", out / f"handoff-{k}.json"
    target.unlink(missing_ok=True)
    handoff.unlink(missing_ok=True)  # an earlier attempt's handoff is not this run's
    cmd = [tool("codex"), "exec", "--cd", str(co), "-m", model, "-c", f"model_reasoning_effort={effort}", *SANDBOX,
           "-c", "sandbox_workspace_write.network_access=true", "--dangerously-bypass-hook-trust", *ctx["flags"],
           "--output-schema", str(co / ".kit-review" / "findings.schema.json"), "-o", str(target), "-"]
    workfiles.write_atomic(keep / f"prompt-{tag}.md", prompt)
    info = {"k": k, "model": model, "effort": effort, "fallback": fallback, "reask": reask, "exit_code": None,
            "hook_failed": None, "complete": None, "transcript": None, "started_at": workfiles.utc_iso(),
            "finished_at": None}
    ctx["record"]["runs"].append(info)
    started, limit = datetime.now(timezone.utc).timestamp() - 1, timeout_for(RUN_TIMEOUT)
    try:
        r = run(cmd, co, env=codex_env(ctx["home"], co, ctx["found"]["values"], k), input_text=prompt, timeout=limit, lock=lock)
    except subprocess.TimeoutExpired:
        info["finished_at"] = workfiles.utc_iso()
        raise Failed("reviewer", f"run {k} did not finish in {limit} s")
    info.update(exit_code=r.returncode, finished_at=workfiles.utc_iso(),
                hook_failed=hook_failure((r.stdout or "") + "\n" + (r.stderr or "")) is not None,
                transcript=transcript(ctx["home"], co, started))
    workfiles.write_atomic(keep / f"run-{tag}.stdout.txt", r.stdout or "")
    workfiles.write_atomic(keep / f"run-{tag}.stderr.txt", r.stderr or "")
    for path in (target, handoff):
        if path.is_file():
            shutil.copyfile(path, keep / path.name)
    return r, info, target, handoff


def reviewer(ctx: dict) -> dict:
    """The reviewer's runs for one round: the continuation at its handoff (at most MAX_CONTINUATIONS), the
    capacity fallback once, and every failure that voids the round (C7 sections 6, 10)."""
    co, values = ctx["co"], ctx["found"]["values"]
    schema = json.loads((co / ".kit-review" / "findings.schema.json").read_text(encoding="utf-8"))
    lists = capacity_lists(ctx["found"]["main"])
    primary = (str(values["reviewer.model"][0]), str(values["reviewer.effort"][0]))
    fallback = (str(values["reviewer.fallback.model"][0]), str(values["reviewer.fallback.effort"][0]))
    use, fallback_used = primary, False
    skill = (co / ".agents/skills/review/SKILL.md").read_text(encoding="utf-8")  # main's, restored in section 4
    review_json = (co / ".kit-review" / "review.json").read_text(encoding="utf-8")
    base = (kinds_text(ctx["record"]["kinds"]) + skill.rstrip() + "\n\n## This review\n\n```json\n"
            + review_json.rstrip() + "\n```\n")
    state = {"findings": {}, "tests": [], "not_run": [], "cold_read": []}
    remaining: list = []

    def one_run(k: int, prompt: str, reask: bool = False) -> dict:
        nonlocal use, fallback_used
        while True:
            r, info, target, handoff = reviewer_attempt(ctx, k, prompt, *use, fallback_used, reask)
            text = (r.stdout or "") + "\n" + (r.stderr or "")
            failure = hook_failure(text)
            if failure:  # Codex runs the command anyway (M29): the review is void
                raise Failed("hooks", f"run {k}'s output {failure}: a guarded command ran with its hook failed")
            if r.returncode == 0:
                break
            if not fallback_used and is_capacity(text, lists):
                print(f"reviewer: run {k} hit a capacity error on {use[0]}; once more on {fallback[0]}")
                use, fallback_used = fallback, True
                continue
            raise Failed("reviewer", f"run {k} exited {r.returncode}{' on the fallback' if fallback_used else ''}: "
                         f"{' '.join(text.split())[-300:]}")
        data = read_output(target, schema, f"run {k}'s -o output")
        if handoff.is_file():
            merge_into(state, read_output(handoff, schema, f"run {k}'s handoff file"))
        merge_into(state, data)
        info["complete"] = data["complete"]
        return data

    for k in range(1, MAX_CONTINUATIONS + 2):
        data = one_run(k, base + continuation(k, state, remaining, co))
        if data["complete"]:
            print(f"reviewer: run {k} complete; {len(state['findings'])} findings, {len(state['tests'])} test runs")
            break
        remaining = data["remaining"]
        print(f"reviewer: run {k} handed off; {len(state['findings'])} findings so far, remaining: "
              f"{', '.join(map(str, remaining)) or 'unnamed'}")
    else:
        raise Failed("incomplete", f"the reviewer handed off {MAX_CONTINUATIONS + 1} times without finishing "
                     f"(at most {MAX_CONTINUATIONS} continuations a round)")
    head = ctx["args"].head
    problems = line_problems(state["findings"].values(), co, head, ctx["lock"])
    if problems:  # asked once more with the problem, then a failed round, as any bad output (C7 section 10)
        print(f"reviewer: {problems[0]}{f' (and {len(problems) - 1} more)' if len(problems) > 1 else ''}; asking once more")
        k += 1
        data = one_run(k, base + reask_text(k, state, problems), reask=True)
        problems = line_problems(state["findings"].values(), co, head, ctx["lock"])
        if problems or not data["complete"]:
            raise Failed("output", f"run {k}, asked again, still breaks the line rule: "
                         + (problems[0] if problems else "its answer is not complete"))
    if not state["tests"] and ctx["record"]["stages"]["clean_run"] != "replaced":  # tests not run never approve (section 10)
        raise Failed("output", "the reviewer listed no tests, and the stages left the clean run to it "
                     "(stages.clean_run is yours)")
    copy = co / ".kit-review" / "candidate"
    for t in state["tests"]:  # the reviewer runs in `co`, so a relative ran_in is read from there (issue #185)
        if not same(t["ran_in"], copy, base=co):
            raise Failed("tests", f"`{t['command']}` ran in {t['ran_in']}, not the test copy {copy.as_posix()}")
    return {"findings": list(state["findings"].values()), "tests": state["tests"], "not_run": state["not_run"],
            "cold_read": state["cold_read"], "model": use[0], "effort": use[1], "fallback_used": fallback_used}


# ---------------------------------------------------------------- the triager (C7 section 7)


def triager_input(ctx: dict, found_: dict, previous: dict | None) -> str:
    co, args, found = ctx["co"], ctx["args"], ctx["found"]
    rnd, budget, cap = found["round"], found["budget"], int(found["values"]["reviewer.max_fix_rounds"][0]) + 1
    kr = co / ".kit-review"
    standard = "\n\n".join((co / ".agents/skills/review" / name).read_text(encoding="utf-8")
                           for name in ("kit-standard.md", "standard.md") if (co / ".agents/skills/review" / name).is_file())
    diff = git(co, "diff", f"{found['base_commit']}...{args.head}", lock=ctx["lock"])
    parts = [(co / ".agents/kit/review/triager.md").read_text(encoding="utf-8").rstrip(),
             f"# This round\n\nTicket t{args.ticket}, branch {args.branch}, head {args.head}, review round {rnd}."
             + (f" This is the round cap (round {budget} of the fix-round budget, skips not counted; the cap is round "
                f"{cap}): give each fix or needs_decision finding a root_cause." if budget >= cap else ""),
             "## The reviewer's findings\n\n<findings>\n" + json.dumps(found_["findings"], indent=1) + "\n</findings>",
             f"## The diff (git diff {found['base_commit'][:7]}...{args.head[:7]})\n\n```diff\n{diff}\n```",
             "## The review standard\n\n" + standard,
             "## The ticket\n\n" + (kr / "ticket.md").read_text(encoding="utf-8")]
    if previous:
        since = run(["git", "diff", f"{previous['head']}..{args.head}"], co, lock=ctx["lock"])
        parts += ["## The previous round's verdict\n\n```json\n" + json.dumps(
                      {k: v for k, v in previous.items() if k != "path"}, indent=1) + "\n```",
                  f"## The diff since its head (git diff {previous['head'][:7]}..{args.head[:7]})\n\n```diff\n"
                  + (since.stdout if since.returncode == 0 else f"(not available: {since.stderr.strip()[:200]})")
                  + "\n```"]
    return "\n\n".join(parts) + "\n"


def triager(ctx: dict, found_: dict, previous: dict | None) -> dict:
    """One fresh one-shot Claude process, read-only, in the checkout; its verdict per finding id."""
    co, main, values, keep = ctx["co"], ctx["found"]["main"], ctx["found"]["values"], ctx["keep"]
    model, effort = str(values["sessions.triager.model"][0]), str(values["sessions.triager.effort"][0])
    settings = launch_settings(main, TRIAGER_ROLE)  # main's guard by absolute path (M22)
    settings["env"] = {"KIT_ROLE": TRIAGER_ROLE}
    settings_path = keep / "triager-settings.json"
    workfiles.write_atomic(settings_path, json.dumps(settings, indent=1) + "\n")
    text = triager_input(ctx, found_, previous)
    workfiles.write_atomic(keep / "triager-input.md", text)
    cmd = [tool("claude"), "-p", "--model", model, "--effort", effort, "--setting-sources", "project,local",
           "--settings", str(settings_path), "--strict-mcp-config", "--permission-mode", "dontAsk",
           "--allowedTools", "Read,Grep,Glob", "--output-format", "json"]
    info = {"model": model, "effort": effort, "exit_code": None, "is_error": None, "model_usage": None,
            "headline_original": None, "unwrapped": None}
    ctx["record"]["triager"] = info
    limit = timeout_for(TRIAGE_TIMEOUT)
    try:
        r = run(cmd, co, env=clean_env(), input_text=text, timeout=limit, lock=ctx["lock"])
    except subprocess.TimeoutExpired:
        raise Failed("triager", f"the triager did not finish in {limit} s")
    workfiles.write_atomic(keep / "triager-output.json", r.stdout or "")
    info["exit_code"] = r.returncode
    if r.returncode != 0:
        raise Failed("triager", f"the triager exited {r.returncode}: {' '.join((r.stderr or r.stdout).split())[:300]}")
    try:
        outer = json.loads(r.stdout)
    except ValueError:
        outer = None
    if not isinstance(outer, dict):
        raise Failed("triager", "the triager's output is not Claude's JSON result")
    info.update(is_error=outer.get("is_error"), model_usage=outer.get("modelUsage"))
    if outer.get("is_error") is not False:
        raise Failed("triager", f"the triager's result has is_error {outer.get('is_error')}")
    body = str(outer.get("result") or "").strip()
    answer, info["unwrapped"] = triage_answer(body)
    triage = check_triage(answer, [f["id"] for f in found_["findings"]])
    info["headline_original"] = triage["headline_original"]
    return triage


def triage_answer(body: str) -> tuple:
    """(the triager's answer, whether it was cut out of prose): the body as JSON, or one fenced block, or else, for a
    body that is neither, the text from its first `{` to its last `}` (prose around the object, issue #183); a fenced
    block whose content is not JSON is not unwrapped further (PR #184 round 1). check_triage then checks it as any
    answer; anything that does not parse fails the round (C7 section 7)."""
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*)\n```", body, re.S)  # the instructions ask for no fence
    try:
        return json.loads(fenced.group(1) if fenced else body), False
    except ValueError:
        pass
    start, end = body.find("{"), body.rfind("}")
    try:
        if not fenced and 0 <= start < end:
            return json.loads(body[start:end + 1]), True
    except ValueError:
        pass
    raise Failed("triager", f"the triager's answer is not JSON: {' '.join(body.split())[:120]!r}")


def check_triage(answer, ids: list[str]) -> dict:
    """One entry per finding id, each a known verdict, and a headline (C7 section 7). Anything else fails."""
    if not isinstance(answer, dict) or not isinstance(answer.get("findings"), list):
        raise Failed("triager", "the triager's answer has no findings list")
    original = answer.get("headline")
    if not isinstance(original, str) or not original.strip() or "\n" in original:
        raise Failed("triager", f"the triager's headline is not one line: {original!r}")
    headline = original.strip()
    if len(headline) >= 80:  # a display limit, not the review's: shortened at a word, the record keeps it whole
        keep = headline[:77]
        headline = (keep.rsplit(" ", 1)[0] if " " in keep else keep[:76]).rstrip() + "..."
    out = {}
    for entry in answer["findings"]:
        fid = entry.get("id") if isinstance(entry, dict) else None
        if fid not in ids:
            raise Failed("triager", f"the triager judged {fid!r}, which is not a finding of this round")
        if fid in out:
            raise Failed("triager", f"the triager judged {fid} twice")
        if entry.get("verdict") not in VERDICTS:
            raise Failed("triager", f"the triager's verdict for {fid} is {entry.get('verdict')!r}, not one of "
                         + ", ".join(VERDICTS))
        if not isinstance(entry.get("reason"), str) or not isinstance(entry.get("persistent"), bool):
            raise Failed("triager", f"the triager's entry for {fid} needs a reason and persistent true or false")
        out[fid] = entry
    missing = [i for i in ids if i not in out]
    if missing:
        raise Failed("triager", f"the triager gave no verdict for {missing[0]}")
    return {"headline": headline, "headline_original": original if headline != original.strip() else None,
            "verdicts": out}


# ---------------------------------------------------------------- the verdict, rounds and round 4 (C7 section 9)


MAX_NOTES = 5  # design 3.3, research decision C's max_notes_per_review: the notes a round shows
MAX_BLOCKERS = 5  # design 3.3: "More than five blockers means escalate, not a fix list"


def open_blockers(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f["severity"] == "blocker" and f["verdict"] in ("fix", "needs_decision")]


def mark_shown(findings: list[dict]) -> str:
    """Design 3.3: a round shows every blocker and fix finding (by the reviewer's severity, or the triager's
    `fix` or `needs_decision`: such a note blocks too) and at most five notes, the first in the reviewer's order,
    which is the review rules' order; every finding is kept, each marked. Its "N found, M shown"."""
    must = [f for f in findings if f["severity"] in ("blocker", "fix") or f["verdict"] in ("fix", "needs_decision")]
    notes = [f for f in findings if f not in must][:MAX_NOTES]
    for f in findings:
        f["shown"] = f in must or f in notes
    return f"{len(findings)} found, {len(must) + len(notes)} shown"


def outcome_of(findings: list[dict], rnd: int, max_fix_rounds: int) -> str:
    """In order: more than five open blockers escalate (design 3.3); at the round cap or after it, a fix or
    needs_decision finding escalates; before it a needs_decision stops for the user, a fix asks for changes;
    else approved, zero findings included."""
    verdicts = {f["verdict"] for f in findings}
    if len(open_blockers(findings)) > MAX_BLOCKERS:
        return "escalated"
    if rnd >= max_fix_rounds + 1 and verdicts & {"fix", "needs_decision"}:
        return "escalated"
    if "needs_decision" in verdicts:
        return "needs_decision"
    return "changes_needed" if "fix" in verdicts else "approved"


def escalation(ctx: dict, findings: list[dict], previous: list[dict], verdict_rel: str) -> tuple[dict, str]:
    """The script's escalation record (C8 section 8, in C9 section 4's shape) and the verdict's copy: at the round
    cap (`round-cap`), or for more than five open blockers before it (`blockers`, design 3.3)."""
    args, found, co = ctx["args"], ctx["found"], ctx["co"]
    rnd, budget, max_fix = found["round"], found["budget"], int(found["values"]["reviewer.max_fix_rounds"][0])
    esc_id = workfiles.event_id("escalation", args.ticket, args.head)
    open_ = [f for f in findings if f["verdict"] in ("fix", "needs_decision")]
    trigger = "round-cap" if budget >= max_fix + 1 else "blockers"
    blockers = len(open_blockers(findings))
    heads = [(v.get("round"), v.get("head")) for v in previous] + [(rnd, args.head)]
    fixes = []
    for (r1, h1), (r2, h2) in zip(heads, heads[1:]):
        log = run(["git", "log", "--oneline", f"{h1}..{h2}"], co, lock=ctx["lock"])
        fixes.append({"from_round": r1, "to_round": r2, "from": h1, "to": h2,
                      "log": log.stdout.strip() if log.returncode == 0 else f"(not available: {log.stderr.strip()[:200]})"})
    causes = [{"id": f["id"], "root_cause": f["root_cause"]} for f in open_ if f.get("root_cause")]
    answers = ["fix", "defer", "known-limitation", "ask-research", "cancel"]
    content = {"id": esc_id, "path": f"merges/{esc_id}.md", "trigger": trigger,
               "persistent": [f["id"] for f in open_ if f.get("persistent")], "fixes_tried": fixes,
               "root_cause": causes, "answers": answers}
    if trigger == "round-cap":
        headline = f"t{args.ticket} needs you: {len(open_)} findings open after review round {rnd}"[:79]
        choice = (f"Review round {rnd} of t{args.ticket} at {args.head[:7]} is not approved, and it is the round cap "
                  f"(round {budget} of the budget, skips not counted; reviewer.max_fix_rounds is {max_fix}; each fix "
                  "answer allows one more round). The review loop "
                  f"stops here: t{args.ticket} waits for your answer.")
    else:
        headline = f"t{args.ticket} needs you: {blockers} open blockers in review round {rnd}"[:79]
        choice = (f"Review round {rnd} of t{args.ticket} at {args.head[:7]} found {blockers} open blockers, more than "
                  f"{MAX_BLOCKERS}: the review rules escalate that rather than send a fix list. The review loop stops "
                  f"here: t{args.ticket} waits for your answer.")
    lines = ["---", "format: escalation", "version: 1", f"id: {esc_id}", f"ticket: {args.ticket}", f"trigger: {trigger}",
             f"headline: {headline}", "by: review.py", f"review: {ctx['review_id']}", f"round: {rnd}",
             f"head: {args.head}", f"verdict: {verdict_rel}", f"holds: {args.ticket}", f"answers: {', '.join(answers)}",
             f"written_at: {workfiles.utc_iso()}", "---", "", "## The choice", "", choice, "", "## Findings", ""]
    for f in open_:
        where = f"{f['file']}:{f['line']}" if f.get("line") is not None else f["file"]
        lines.append(f"- {f['id']} ({f['verdict']}; {'persistent, seen in an earlier round' if f.get('persistent') else 'new this round'}): "
                     f"{f['title']}, {where}. Triager: {f['verdict_reason']}")
    lines += ["", "Earlier rounds' open findings:", ""]
    for v in previous:
        for f in v.get("findings") or []:
            if f.get("verdict") in ("fix", "needs_decision"):
                lines.append(f"- round {v.get('round')}: {f.get('id')} ({f.get('verdict')}): {f.get('title')}, {f.get('file')}")
    lines += ["", "Fixes tried:", ""]
    for x in fixes:
        log = "; ".join(x["log"].splitlines()) or "no commits"
        lines.append(f"- round {x['from_round']} ({x['from'][:7]}) to round {x['to_round']} ({x['to'][:7]}): {log}")
    lines += ["", "Likely root cause (the triager's): " + (" ".join(f"{c['id']}: {c['root_cause']}" for c in causes)
                                                         or "none given."), "", "## Options", "",
              "- fix: one more review round after the builder's next fix; a second failure comes back to you.",
              "- defer: park the ticket; nothing more runs on it.",
              "- known-limitation: merge it as it is with these findings recorded; only your own `! python -I .agents/kit/bin/merge.py yours <N>` does it.",
              "- ask-research: the research module investigates the root cause first.",
              "- cancel: stop the builder and close the ticket.", "", "## Recommendation", "",
              "The script does not choose. With a root cause above that the builder has not tried yet, fix; "
              "with none, ask-research.", ""]
    return content, "\n".join(lines)


def verdict_fields(ctx: dict, outcome: str, findings: list[dict], *, reviewer=None, triager=None, tests=(), not_run=(),
                   cold_read=(), headline: str, stopped=None, covers=None) -> dict:
    """C7 section 9's verdict, every outcome with the same fields: `found_shown` and each finding's `shown`
    (design 3.3), `stopped` (the stage that stopped the round before the reviewer, or null), `covers` (what a
    skip covers, or null)."""
    args, found = ctx["args"], ctx["found"]
    found_shown = mark_shown(findings)
    return {"format": "verdict", "version": 1, "id": ctx["review_id"], "repository": found["repository"],
            "ticket": args.ticket, "branch": args.branch, "head": args.head, "base_commit": found["base_commit"],
            "main_commit": found["main_commit"], "standard_commit": found.get("standard_commit"),
            "round": found["round"], "max_fix_rounds": int(found["values"]["reviewer.max_fix_rounds"][0]),
            "outcome": outcome, "reviewer": reviewer, "triager": triager, "findings": findings,
            "found_shown": found_shown, "tests": list(tests), "not_run": list(not_run), "cold_read": list(cold_read),
            "stopped": stopped, "covers": covers, "escalation": None, "headline": headline,
            "written_at": workfiles.utc_iso()}


def build_verdict(ctx: dict, reviewed: dict, triage: dict, pre: dict) -> dict:
    findings = [{**f, "verdict": triage["verdicts"][f["id"]]["verdict"],
                 "verdict_reason": triage["verdicts"][f["id"]]["reason"],
                 "persistent": triage["verdicts"][f["id"]]["persistent"],
                 **({"root_cause": triage["verdicts"][f["id"]].get("root_cause")}
                    if triage["verdicts"][f["id"]].get("root_cause") else {})} for f in reviewed["findings"]]
    return verdict_fields(
        ctx, "approved", findings, headline=triage["headline"],
        reviewer={"engine": "codex", "model": reviewed["model"], "effort": reviewed["effort"],
                  "fallback_used": reviewed["fallback_used"]},
        triager={"model": ctx["record"]["triager"]["model"], "effort": ctx["record"]["triager"]["effort"]},
        tests=pre["tests"] + reviewed["tests"], not_run=pre["not_run"] + reviewed["not_run"],
        cold_read=reviewed["cold_read"])


def stopped_verdict(ctx: dict, pre: dict) -> dict:
    """A red stage before the reviewer (design 2.7): its one `fix` finding, judged by the script, as no
    reviewer and no triager ran."""
    finding = {**pre["red"], "verdict": "fix", "persistent": False,
               "verdict_reason": "a red stage before the reviewer: the review script stopped the round there"}
    what = "the lint" if pre["stopped"] == "lint" else "the mapped tests"
    return verdict_fields(ctx, "changes_needed", [finding], tests=pre["tests"], not_run=pre["not_run"],
                          headline=f"t{ctx['args'].ticket}: {what} red; stopped before the reviewer"[:79],
                          stopped=pre["stopped"])


def new_record(found: dict, args, review_id: str, co: Path | None) -> dict:
    """C7 section 8's fields, filled in as the review goes; written once, at its end however it ends."""
    return {"format": "review", "version": 1, "id": review_id, "repository": found["repository"],
            "ticket": args.ticket, "branch": args.branch, "head": args.head, "base": found["base"],
            "base_commit": found["base_commit"], "main_commit": found["main_commit"], "standard_commit": None,
            "round": None, "checkout": co.as_posix() if co else None, "test_copy": None,
            "changed_paths": found["changed_paths"],
            "kinds": None, "stages": None,
            "isolation": None, "canary": None, "runs": [], "triager": None, "usage": found["usage"],
            "memory_free_gb": found["memory_free_gb"], "secret_files_copied": [], "codex_version": None,
            "claude_version": None, "outcome": None, "failure": None, "verdict": None, "verdict_sha256": None,
            "escalation": None, "started_at": workfiles.utc_iso(), "finished_at": None}


def version(name: str, cwd: Path, lock) -> str | None:
    r = run([tool(name), "--version"], cwd, timeout=120, lock=lock)
    return (r.stdout or "").strip().splitlines()[0] if r.returncode == 0 and (r.stdout or "").strip() else None


def write_record(coordination: Path, record: dict):
    record["finished_at"] = workfiles.utc_iso()
    workfiles.write_new(coordination / "reviews" / f"{record['id']}.json",
                        (json.dumps(record, indent=1) + "\n").encode("utf-8"))


# ---------------------------------------------------------------- the command line


def head_sha(text: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", text):
        raise argparse.ArgumentTypeError("a full 40-hex commit")
    return text


def parse(argv):
    ap = argparse.ArgumentParser(prog="review.py", description="Review a pushed head (contract C7).")
    ap.add_argument("--ticket", type=int, required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--head", type=head_sha, required=True)
    ap.add_argument("--base", help="a stacked ticket's lower branch; default origin's default branch")
    ap.add_argument("--check", action="store_true", help="the checks and the renders; reserve and write nothing")
    return ap.parse_args(argv)


def review(args, main: Path) -> int:
    check_main_copy(main)
    found = checks(args, main)
    if found["skip"]:
        if args.check:
            print(f"check: the review of t{args.ticket} at {args.head[:7]} would be skipped. {NOTHING_STARTED}")
            return 0
        return skip_round(args, found)
    if args.check:
        info = isolate(main, found["home"], main, found["values"])
        print(f"isolation: {len(info['skills_disabled'])} skills would be disabled; left: "
              f"{', '.join(info['skills_left']) or 'none'}")
        print(f"check: the review of t{args.ticket} at {args.head[:7]} would pass the checks. {NOTHING_STARTED}")
        return 0
    review_id = workfiles.event_id("review", args.ticket, args.head)
    co, lock = reserve(found, review_id, args)
    coordination = found["coordination"]
    keep = coordination / "reviews" / review_id
    record = new_record(found, args, review_id, co)
    record_path = coordination / "reviews" / f"{review_id}.json"
    ctx = {"args": args, "found": found, "co": co, "lock": lock, "keep": keep, "home": found["home"],
           "review_id": review_id, "record": record, "flags": []}
    written, esc_path = False, None
    try:
        print(f"reserved: {co.name} for review {review_id}")
        keep.mkdir(parents=True, exist_ok=True)
        record["codex_version"], record["claude_version"] = version("codex", co, lock), version("claude", co, lock)
        prepared = prepare(found, co, args, review_id, lock)
        record.update(test_copy=prepared["test_copy"].as_posix(), secret_files_copied=prepared["secret_files_copied"],
                      standard_commit=found.get("standard_commit"))
        print(f"prepared: {co.as_posix()} at {args.head[:7]}; {len(prepared['restored'])} control files from main "
              f"{found['main_commit'][:7]}, {len(prepared['removed'])} removed; test copy {prepared['test_copy'].as_posix()}")
        # Before reading (design 2.1, 3.2): the kind of each changed file, then the lint and the mapped tests.
        kr = co / ".kit-review"
        test_map, core, map_note = main_map(co, kr, found["main_commit"], lock)
        try:
            kinds = load_kinds(co / ".agents/kit/review/kinds.toml")  # main's, restored in step 2
        except KindsProblem as e:
            raise Failed("prepare", f"main's kinds file does not load: {e}")
        record["kinds"] = kinds_of(changed_paths(found)[0], kinds, core)
        for entry in record["kinds"]:
            print(f"kind: {entry['path']}: {'; '.join(entry['kinds'])}")
        pre = before_reading(ctx, test_map, map_note)
        record["stages"] = pre["stages"]
        export_stages(kr, pre["stages"])
        for name in ("lint", "tests"):
            s = pre["stages"][name]
            print(f"{name}: " + (f"exit {s['exit_code']}, {s['summary']} (`{shown_argv(s['command'])}`)" if s["ran"]
                                 else f"not run: {s['why']}"))
        previous = counted_verdicts(coordination, args.ticket)
        if pre["red"]:  # a red stage stops the round here (design 2.7): no reviewer, no triager
            verdict = stopped_verdict(ctx, pre)
        else:
            info = isolate(co, found["home"], main, found["values"], lock, keep)
            record["isolation"] = {"skills_disabled": info["skills_disabled"],
                                   "bundled_allowed": sorted(n for n, _ in bundled(main)),
                                   "render_sha256": info["render_sha256"]}
            ctx["flags"] = info["flags"]
            print(f"isolation: {len(info['skills_disabled'])} skills disabled; left: {', '.join(info['skills_left']) or 'none'}")
            record["canary"] = {"passed": False, "nonce": None}
            nonce = canary(co, found["home"], found["values"], info["flags"], keep, lock)
            record["canary"] = {"passed": True, "nonce": nonce}
            print(f"canary: {nonce} blocked by main's PreToolUse hook")
            # Section 6 onward: the reviewer, the triager, then the record and the verdict.
            reviewed = reviewer(ctx)
            triage = triager(ctx, reviewed, previous[-1] if previous else None)
            print(f"triager: {triage['headline']}")
            verdict = build_verdict(ctx, reviewed, triage, pre)
        max_fix = int(found["values"]["reviewer.max_fix_rounds"][0])
        outcome = verdict["outcome"] = outcome_of(verdict["findings"], found["budget"], max_fix)
        rel = f"verdicts/t{args.ticket}/round-{found['round']}.json"
        esc_text = None
        if outcome == "escalated":  # the round cap, or too many blockers: this script writes the stop (decision 112)
            verdict["escalation"], esc_text = escalation(ctx, verdict["findings"], previous, rel)
        data = (json.dumps(verdict, indent=1) + "\n").encode("utf-8")
        record.update(round=found["round"], outcome=outcome, verdict=rel, verdict_sha256=sha256(data),
                      escalation=verdict["escalation"]["path"] if esc_text else None)
        write_record(coordination, record)  # first the record, naming the verdict by path and hash
        written = True
        if os.environ.get("KIT_REVIEW_CRASH_AT") == "verdict":  # a test hook, like C8's KIT_MERGE_CRASH_AT
            os._exit(9)
        # The round cap's stop is written before the verdict, so a verdict never counts without it (PR #83
        # review round 1); a failure before the verdict removes it again, and the round is not used.
        if esc_text:
            if os.environ.get("KIT_REVIEW_FAIL_AT") == "escalation":  # the test hook for that failure
                raise OSError("planted: the escalation record could not be written")
            esc_path = coordination / verdict["escalation"]["path"]
            workfiles.write_atomic(esc_path, esc_text)
        workfiles.write_new(coordination / rel, data)  # create-only: a second writer of the round fails
        esc_path = None
        if esc_text:
            print(f"escalation: {verdict['escalation']['path']}")
    except Exception as e:  # any exception after reserving fails the review (C7 section 10)
        stage, failed = (e.stage, e.failed) if isinstance(e, Failed) else ("error", f"{type(e).__name__}: {e}")
        where = record_path.as_posix()
        if not written:
            record.update(round=None, outcome="failed", failure={"stage": stage, "reason": failed}, verdict=None,
                          verdict_sha256=None, escalation=None)
            try:
                write_record(coordination, record)
            except Exception as w:
                where = f"not written ({type(w).__name__}: {w}); raw files in {keep.as_posix()}/"
        else:  # the record is written once, so the failure goes beside it; its verdict is missing: no round used
            if esc_path is not None:
                esc_path.unlink(missing_ok=True)
            workfiles.write_atomic(keep / "failure.json", json.dumps({"stage": stage, "reason": failed}) + "\n")
            where += f" (it names a verdict that was not written: a failed attempt; {keep.as_posix()}/failure.json)"
        print(f"FAILED ({stage}): {failed}. No verdict was written. Review record: {where}", file=sys.stderr)
        return 2
    finally:
        lock.release()
    print(f"findings: {verdict['found_shown']}")
    for f in (f for f in verdict["findings"] if f["shown"]):
        print(f"  {f['id']} {f['severity']}, triaged {f['verdict']}: {f['file']}:{f['line']} {f['title']}")
    print(f"VERDICT {outcome} {rel} {review_id}")
    return EXIT[outcome]


def skip_round(args, found: dict) -> int:
    """Design 3.3's skip: no checkout, no reviewer, no triager; the record and then the verdict, as a round
    writes them (C7 section 9), the verdict naming what it covers. Exit 0, as the approval it repeats."""
    coordination, skip = found["coordination"], found["skip"]
    review_id = workfiles.event_id("review", args.ticket, args.head)
    record = new_record(found, args, review_id, None)
    rel = f"verdicts/t{args.ticket}/round-{found['round']}.json"
    ctx = {"args": args, "found": found, "review_id": review_id}
    headline = (f"t{args.ticket}: skipped; {args.head[:7]} is approved {skip['head'][:7]} plus updates from main")[:79]
    verdict = verdict_fields(ctx, "skipped", [], headline=headline, covers=skip)
    data = (json.dumps(verdict, indent=1) + "\n").encode("utf-8")
    record.update(round=found["round"], outcome="skipped", verdict=rel, verdict_sha256=sha256(data))
    try:
        write_record(coordination, record)  # first the record, naming the verdict by path and hash
        workfiles.write_new(coordination / rel, data)
    except Exception as e:
        print(f"FAILED (skip): {type(e).__name__}: {e}. No verdict was written. Review record: "
              f"{(coordination / 'reviews' / f'{review_id}.json').as_posix()}", file=sys.stderr)
        return 2
    print(f"skip: no review round runs: {skip['path']} approved {skip['head'][:7]}, and {args.head[:7]} adds only "
          f"{len(skip['updates'])} clean updates from main")
    print(f"VERDICT skipped {rel} {review_id}")
    return EXIT["skipped"]


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):  # under -I a pipe takes the code page, which lacks many path characters
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = parse(argv)  # a malformed command line exits 2 with the usage message
    try:
        return review(args, main_checkout())
    except Refused as r:
        print(r, file=sys.stderr)
        return 1
    except Busy as b:
        print(b, file=sys.stderr)
        return 3
    except Exception as e:  # before reserving: nothing is held or written
        print(f"REFUSED (error): {type(e).__name__}: {e}. Valid: fix what it names. {NOTHING_STARTED}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
