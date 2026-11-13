"""The launch script (contract C6): starts every Claude session with the kit's flags and settings.

    python -I .agents/kit/bin/launch.py orchestrator [--successor <launch id>] [--prompt <text>] [--check]
    python -I .agents/kit/bin/launch.py builder --ticket <n> [--base <branch>] [--effort <level> --reason <text>]
                                                [--prompt <text>] [--check]
    python -I .agents/kit/bin/launch.py builder --successor <launch id> [--prompt <text>] [--check]

Every start first runs C6 section 2's checks, printing one line each; `--check` runs checks 1-5 for that
start and writes nothing. `orchestrator` alone is your start command: an interactive session in this
terminal. A builder gets a worktree this script makes (decision 109) and one background session in it;
a successor takes its predecessor's place. The session's role and every setting it needs go in `--settings`, since a background
session inherits the background service's environment, not this script's (M53, M54). Standard library
only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # C1 section 2: imports by __file__ under -I
sys.path.insert(0, str(HERE.parent / "hooks"))

import formats  # noqa: E402
import kitconfig  # noqa: E402
import notices  # noqa: E402
import usage  # noqa: E402
import workfiles  # noqa: E402
from guard import launch_settings, selftest  # noqa: E402

NOTHING_STARTED = "Nothing was started."
EFFORTS = ["low", "medium", "high", "xhigh", "max"]  # decision 53 lowers one step down this list
AUTOCOMPACT_FLOOR = 100_000  # `claude --help`: auto, or 100k-1M tokens (M58)
ID_WAIT = 30  # seconds to find the session in `claude agents --json` (C6 section 8)
SHORT_ID = re.compile(r"backgrounded · ([0-9a-f]{8})")
# A Claude session's own markers in its shell. A claude started with them inherits them: an interactive one
# then saves no transcript, which the context barrier reads, and is not listed (M75).
PARENT_SESSION_VARS = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_CODE_CHILD_SESSION",
                       "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_BRIDGE_SESSION_ID",
                       "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                       "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH")


class Refused(Exception):
    """A refusal before anything that cannot be undone (C5's refusal shape)."""

    def __init__(self, check: str, failed: str, valid: str):
        super().__init__(f"REFUSED ({check}): {failed}. Valid: {valid}. {NOTHING_STARTED}")


class FailedAfterStart(Exception):
    pass


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def main_checkout() -> Path:
    """The main checkout: the parent of the shared git folder, whichever checkout holds this script."""
    return Path(git(HERE, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent


def default_branch(main: Path) -> str:
    """The remote's default branch: `origin/HEAD` when the clone recorded it, else asked of the remote.
    Never the main checkout's current branch, which may be a feature branch (C6 section 5)."""
    r = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd=main,
                       capture_output=True, text=True, timeout=120)
    if r.returncode == 0 and "/" in r.stdout:
        return r.stdout.strip().split("/", 1)[1]
    try:  # a network or credential stall must not hang a launch or a review (PR #82 review round 2)
        r = subprocess.run(["git", "ls-remote", "--symref", "origin", "HEAD"], cwd=main, capture_output=True,
                           text=True, timeout=120)
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess([], 1, "", "")
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", r.stdout, re.M)
    if m:
        return m.group(1)
    raise Refused("base", "the remote's default branch cannot be found (no origin/HEAD, and origin did not say)",
                  "launch.py builder --ticket <n> --base origin/<default branch>")


# ---------------------------------------------------------------- checks before every start (C6 sections 2, 4)


def free_memory_gb() -> float | None:
    """Free physical memory: `GlobalMemoryStatusEx` on Windows, `MemAvailable` on Linux, else None."""
    if sys.platform == "win32":
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                (f, ctypes.c_ulonglong) for f in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile",
                                                  "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual",
                                                  "ullAvailExtendedVirtual")]
        status = Status(dwLength=ctypes.sizeof(Status))
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return status.ullAvailPhys / 2**30
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 2**20  # kB
    except OSError:
        pass
    return None


def session_rows(cwd: Path) -> list[dict]:
    """Every session `claude agents --json` lists, whatever its status. A listing that fails refuses: an
    empty one would pass a duplicate name or a busy predecessor."""
    r = subprocess.run(["claude", "agents", "--json"], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=clean_env())
    try:
        rows = json.loads(r.stdout) if r.returncode == 0 else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        raise Refused("name", f"`claude agents --json` failed (exit {r.returncode}): "
                      f"{' '.join((r.stderr or r.stdout).split())[:300]}",
                      "run claude agents --json yourself to see why, then launch again")
    return [row for row in rows if isinstance(row, dict)]


def lowered(effort: str, percent, values: dict) -> tuple[str, str | None]:
    """(effort to run, effort it was lowered from or None): one level lower at `usage.lower_effort_at`."""
    if percent is None or percent < values["usage.lower_effort_at"][0] or effort == EFFORTS[0]:
        return effort, None
    return EFFORTS[EFFORTS.index(effort) - 1], effort


def check_config(main: Path) -> dict:
    """Check 1 (C6 section 2), also the review script's check 1 (C7 section 2): the effective config."""
    try:
        values = kitconfig.effective(main)
    except Exception as e:
        raise Refused("config", "; ".join(str(e).splitlines()),
                      "fix the setting it names (python -I .agents/kit/bin/kitconfig.py show)")
    print("config: ok")
    return values


def check_memory(values: dict) -> float | None:
    """Check 4, also the review script's check 2: free memory against `memory_floor_gb`. The free GB, or
    None when it cannot be read here (which passes)."""
    floor, free = float(values["memory_floor_gb"][0]), free_memory_gb()
    if free is None:
        print("memory: memory unknown, passing")
    elif free < floor:
        raise Refused("memory", f"{free:.1f} GB free, below memory_floor_gb {floor}",
                      "free memory (stop a session or a program), or lower memory_floor_gb in agent-kit.local.toml")
    else:
        print(f"memory: {free:.1f} GB free, floor {floor}")
    return free


def check_usage(coordination: Path, values: dict, name: str, percent, age, *, successor: bool, check_only: bool,
                what: str = "starting", valid: str = "wait for the usage window to reset; a replacement starts "
                "with --successor <launch id>"):
    """Check 5, also the review script's check 3: a reading at or above `usage.no_new_sessions_at` refuses,
    except for a successor, and writes the usage-stop notice unless `--check`. `age` is the reading's age
    in minutes, or a text saying where it came from."""
    stop_at = values["usage.no_new_sessions_at"][0]
    when = f"{age} min old" if isinstance(age, int) else age
    if percent is None:
        print(f"usage: usage unknown (no record, unreadable, or older than 30 minutes), {what}")
    elif percent >= stop_at and not successor:
        failed = f"usage {percent}% ({when}) is at or above usage.no_new_sessions_at {stop_at}"
        if not check_only:
            try:
                notices.write(coordination, "usage-stop", f"Usage {percent}%: {name} was not started; "
                              f"from {stop_at}% only replacements start.")
            except (OSError, ValueError) as e:
                failed += f" (its notice could not be written: {e})"
        raise Refused("usage", failed, valid)
    else:
        print(f"usage: {percent}% ({when})")


def checks(main: Path, name_of, *, successor: bool, check_only: bool) -> dict:
    """C6 section 2's checks 1-5 in order, one printed line each; the first that fails refuses. Returns
    the config's values with what the launch record keeps. Writes nothing except the usage stop's notice,
    and not that under `--check`."""
    values = check_config(main)
    problems = selftest(main)
    if problems:
        raise Refused("guard", "selftest failed: " + "; ".join(problems),
                      "restore the kit's guard entries and guard.py (python -I .agents/kit/hooks/guard.py selftest)")
    print("guard: selftest ok")
    rows = session_rows(main)
    name = name_of(values, rows)
    if name in {row.get("name") for row in rows}:
        raise Refused("name", f"{name} is already in claude agents --json",
                      "stop that session (claude stop <id>), or replace it with --successor <launch id>")
    print(f"name: {name} unused")
    free = check_memory(values)
    coordination = main / str(values["coordination"][0])  # C3: relative to the project, or absolute
    percent, age = usage.read(coordination)
    check_usage(coordination, values, name, percent, age, successor=successor, check_only=check_only)
    return {"values": values, "name": name, "coordination": coordination,
            "usage": None if percent is None else {"percent": percent, "age_minutes": age},
            "percent": percent, "memory_free_gb": None if free is None else round(free, 1)}


# ---------------------------------------------------------------- settings and command (C6 sections 3, 6)


def autocompact(handoff: int, window: int) -> int:
    """The compaction safety net, the handoff level plus 13 points (decision 115), never below the flag's
    minimum. The barrier reads one response behind (M77) and compaction fires up to 3.5 points below the
    size (M83), so the net needs room for one large response (up to 8.9 points seen)."""
    return max(AUTOCOMPACT_FLOOR, (handoff + 13) * window // 100)


def auto_mode_environment(main: Path, values: dict) -> list[str]:
    """Auto mode's description of this project (C6 section 6), rendered here, never copied from user
    settings (decision 84)."""
    r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=main, capture_output=True, text=True)
    remote = r.stdout.strip() if r.returncode == 0 else "none configured"
    secrets_list = ", ".join(f"`{s}`" for s in values["secret_files"][0]) or "none"
    return [
        f"**Project**: {values['project.name'][0]}, an agent-kit project",
        f"**Trusted repo**: {remote}; the main checkout is {main.as_posix()}",
        f"**Secrets**: {secrets_list} hold keys; never print, copy out or commit their contents",
        "**Default branch**: changes only by merged pull requests; never push to it directly",
    ]


def refresh_ticket(coordination: Path, ticket) -> bool:
    """The brief's `refresh: yes` (C9 section 2): the lesson refresh ticket (issue #160). No brief, or no
    such line, is an ordinary ticket: its builder then runs its subagents on its own model, which costs
    more and breaks nothing."""
    try:
        text = (coordination / "briefs" / f"t{ticket}.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return formats.front_matter(text)[0].get("refresh") == "yes"


def session_settings(main: Path, role: str, values: dict, refresh: bool = False) -> dict:
    """`guard.py settings <role>` (C5 section 1) plus C6 section 6's keys. `refresh`: a builder of the lesson
    refresh ticket."""
    settings = launch_settings(main, role)
    settings["env"] = {"KIT_ROLE": role, "CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP": "1"}
    settings["autoMode"] = {"environment": auto_mode_environment(main, values)}
    settings["agentPushNotifEnabled"] = True
    settings["inputNeededNotifEnabled"] = True
    settings["cleanupPeriodDays"] = 60
    if role == "orchestrator":  # the usage reading and its 80% notice (C6 section 4)
        coordination = main / str(values["coordination"][0])
        settings["statusLine"] = {"type": "command", "command": (
            f'python -I "{(main / ".agents/kit/bin/usage.py").as_posix()}" statusline "{coordination.as_posix()}" '
            f'--warn-at {values["usage.warn_at"][0]}')}
        # The orchestrator writes the coordination folder from the main checkout (T2). A background session there
        # (a rotation successor) has its Write and Edit calls refused until it enters a worktree, Claude Code's
        # background isolation; this is the switch the refusal names (M134).
        settings["worktree"] = {"bgIsolation": "none"}
    if role == "builder":  # unattended: a question to you waits forever; it goes through the orchestrator (C9)
        settings.setdefault("permissions", {}).setdefault("deny", []).append("AskUserQuestion")
        # No auto memory (issue #160): it is per repository and shared by its worktrees, so a builder's note
        # would load unreviewed into the orchestrator. A builder's lessons go to docs/solutions/, reviewed.
        settings["autoMemoryEnabled"] = False
        settings["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        if refresh:  # the refresh's investigation subagents: bounded read-only checks (the memory design, 2)
            settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] = "sonnet"
    return settings


def claude_command(*, name, model, effort, compact, settings: str, coordination, prompt, background=True,
                   extra=()) -> list[str]:
    """One list, no shell (C6 section 3). `--add-dir` takes several values, so another option follows it
    before the prompt."""
    cmd = ["claude"] + (["--bg"] if background else [])
    cmd += ["--name", name, "--model", model, "--effort", effort, "--autocompact", str(compact),
            "--setting-sources", "project,local", "--settings", settings,
            "--add-dir", str(coordination), "--permission-mode", "auto", *extra]
    return cmd + ([prompt] if prompt else [])


def clean_env() -> dict:
    """This process's environment without a calling Claude session's markers (M75)."""
    return {k: v for k, v in os.environ.items() if k not in PARENT_SESSION_VARS}


# ---------------------------------------------------------------- the worktree (C6 section 5)


def launch_records(coordination: Path) -> list[dict]:
    out = []
    for p in sorted((coordination / "launches").glob("launch-*.json")):
        if ".tmp-" not in p.name:
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def outside_project(entry: str) -> bool:
    return kitconfig.is_absolute(entry) or kitconfig.escapes(entry)


def check_secret_entries(entries: list[str]):
    for entry in entries:
        if outside_project(entry):
            raise Refused("secret files", f"{entry} is outside the project",
                          "a path inside the project, git-ignored")


def make_worktree(main: Path, coordination: Path, ticket: int, base: str | None) -> tuple[Path, str, str]:
    """(worktree, base as named, base commit). An existing worktree is reused when no launch record for
    the ticket names a session (a first start that failed); otherwise it is a successor's."""
    path, branch = main / ".claude" / "worktrees" / f"t{ticket}", f"t{ticket}"
    fetched = subprocess.run(["git", "fetch", "-q", "origin"], cwd=main, capture_output=True, text=True)
    if fetched.returncode != 0:  # a stale origin/<default> would be a silent wrong base (C6 section 5)
        raise Refused("fetch", f"git fetch origin failed: {(fetched.stderr or fetched.stdout).strip()[:300]}",
                      "fix the remote or the network, then launch again")
    base = base or f"origin/{default_branch(main)}"
    if path.exists():
        if any(r.get("ticket") == ticket and r.get("session_id") for r in launch_records(coordination)):
            raise Refused("worktree", f"{path.as_posix()} already has a session's work",
                          "launch.py builder --successor <launch id>")
        return path, base, git(path, "rev-parse", "HEAD")
    commit = git(main, "rev-parse", base)
    git(main, "worktree", "add", "-q", "-b", branch, str(path), base)
    return path, base, commit


def copy_secrets(main: Path, worktree: Path, entries: list[str]) -> list[str]:
    """Each secret file the main checkout has, copied when the worktree lacks it; never printed."""
    copied = []
    for entry in entries:
        src, dst = main / entry, worktree / entry
        if src.is_file() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(entry)
    return copied


# ---------------------------------------------------------------- starting and the record (C6 sections 1, 8)


def agents(cwd: Path) -> list[dict]:
    r = subprocess.run(["claude", "agents", "--json"], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                       env=clean_env())
    return json.loads(r.stdout or "[]")


def run_claude(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=clean_env())


def start_background(cmd: list[str], cwd: Path, name: str) -> tuple[str, str]:
    """(short id, full session id). Once `claude --bg` has run, a session may be working even when it
    exited 1 and printed no id (M69): only the trust refusal (M48) says nothing started. Anything else
    that leaves the session unidentified is a failure after the start (C6 section 1)."""
    r = run_claude(cmd, cwd)  # an error here (no claude on PATH) is before any start
    if "Workspace not trusted" in r.stdout + r.stderr:
        raise Refused("trust", f"{main_checkout().as_posix()} was never trusted interactively (its worktree "
                      f"{cwd.as_posix()} is kept; a retry reuses it)",
                      "run the start command once in the main checkout and accept the trust prompt")
    m = SHORT_ID.search(r.stdout)
    short = m.group(1) if m else None
    end, problem = time.time() + ID_WAIT, f"claude exited {r.returncode} and printed no session id"
    while time.time() < end:
        try:
            for row in agents(cwd):
                if (short and row.get("id") == short) or (not short and row.get("name") == name):
                    if row.get("sessionId"):
                        return row["id"], row["sessionId"]
            problem = "its session never appeared in `claude agents --json`"
        except Exception as e:  # the lookup itself failing must not lose the session
            problem = f"`claude agents --json` failed: {e}"
        time.sleep(1)
    raise FailedAfterStart(short or name, problem)


def stop(who: str, cwd: Path) -> bool:
    """`claude stop` takes a session id; a name is resolved to one first. False when it cannot be stopped."""
    try:
        if not re.fullmatch(r"[0-9a-f]{8}", who):
            who = next(row["id"] for row in agents(cwd) if row.get("name") == who and row.get("id"))
        return subprocess.run(["claude", "stop", who], cwd=cwd, capture_output=True).returncode == 0
    except Exception:
        return False


def compact_for(main: Path, role: str, values: dict) -> int:
    window = int(kitconfig.load_schema(main)["fixed"]["claude_context_window"])
    return autocompact(int(values[f"context.{role}.handoff"][0]), window)


def lowered_effort(effort: str, found: dict) -> tuple[str, str | None]:
    effort, lowered_from = lowered(effort, found["percent"], found["values"])
    if lowered_from:
        print(f"effort: {effort}, lowered from {lowered_from} (usage at or above usage.lower_effort_at)")
    return effort, lowered_from


def new_record(*, launch_id, role, ticket, name, successor_of, model, effort, lowered_from=None, reason=None,
               found, worktree, branch, base, base_commit, copied, settings) -> dict:
    """C6 section 8's launch record; the session's ids are added once known."""
    return {"format": "launch", "version": 1, "id": launch_id, "role": role, "ticket": ticket, "name": name,
            "successor_of": successor_of, "session_id": None, "short_id": None, "model": model, "effort": effort,
            "effort_lowered_from": lowered_from, "effort_reason": reason, "usage": found["usage"],
            "memory_free_gb": found["memory_free_gb"], "worktree": worktree, "branch": branch, "base": base,
            "base_commit": base_commit[:7] if base_commit else None, "secret_files_copied": copied,
            "claude_version": claude_version(), "settings_sha256": sha256(settings), "started_at": workfiles.utc_iso()}


def write_record(coordination: Path, record: dict):
    workfiles.write_atomic(coordination / "launches" / f"{record['id']}.json", json.dumps(record, indent=1) + "\n")


def start_and_record(cmd: list[str], cwd: Path, main: Path, coordination: Path, record: dict) -> str:
    """A background start, then its record with the session's ids. Any failure once claude has run takes
    one path (C6 section 1): the session is stopped and no record is written."""
    short, session_id = None, None
    try:
        short, session_id = start_background(cmd, cwd, record["name"])
        write_record(coordination, {**record, "session_id": session_id, "short_id": short})
    except FailedAfterStart as e:
        raise after_start(e.args[0], e.args[1], cwd, main)
    except Refused:
        raise
    except Exception as e:
        if short or session_id:
            raise after_start(short or record["name"], str(e), cwd, main)
        raise
    return f"launched {record['name']} {session_id} {record['id']}"


def builder(args, main: Path) -> str:
    if args.successor:
        return successor(args, main, "builder")
    found = checks(main, lambda v, rows: f"{v['project.name'][0]}-t{args.ticket}", successor=False,
                   check_only=args.check)
    values, name, coordination = found["values"], found["name"], found["coordination"]
    effort, lowered_from = lowered_effort(args.effort or values["sessions.builder.effort"][0], found)
    if args.check:
        return f"check: {name} would pass checks 1-5. {NOTHING_STARTED}"
    secret_entries = list(values["secret_files"][0])
    check_secret_entries(secret_entries)
    worktree, base, base_commit = make_worktree(main, coordination, args.ticket, args.base)
    copied = copy_secrets(main, worktree, secret_entries)
    settings = json.dumps(session_settings(main, "builder", values, refresh_ticket(coordination, args.ticket)))
    # one string: passed and fingerprinted
    prompt = args.prompt or f"Read {(coordination / 'briefs' / f't{args.ticket}.md').as_posix()} and follow it."
    model = values["sessions.builder.model"][0]
    cmd = claude_command(name=name, model=model, effort=effort, compact=compact_for(main, "builder", values),
                         settings=settings, coordination=coordination, prompt=prompt)
    record = new_record(launch_id=workfiles.event_id("launch", args.ticket, base_commit), role="builder",
                        ticket=args.ticket, name=name, successor_of=None, model=model, effort=effort,
                        lowered_from=lowered_from, reason=args.reason, found=found,
                        worktree=worktree.relative_to(main).as_posix(), branch=f"t{args.ticket}", base=base,
                        base_commit=base_commit, copied=copied, settings=settings)
    return start_and_record(cmd, worktree, main, coordination, record)


# ---------------------------------------------------------------- successors (C6 sections 1, 3, 8; decision 48)


def predecessor_of(coordination: Path, launch_id: str, role: str, rows: list[dict]) -> dict:
    """The launch record a successor replaces. Refused when it is missing or another role's, or when its
    session is busy, unless the caller is that session: a session hands off in its own last turn (M66)."""
    path = coordination / "launches" / f"{launch_id}.json"
    if not re.fullmatch(r"launch-[0-9A-Za-z-]+", launch_id) or not path.is_file():
        raise Refused("successor", f"no launch record {launch_id} in {path.parent.as_posix()}",
                      "--successor <launch id>, a record's file name there without .json")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("role") != role:
        raise Refused("successor", f"{launch_id} is a {record.get('role')}'s launch, not a {role}'s",
                      f"launch.py {record.get('role')} --successor {launch_id}")
    row = next((r for r in rows if r.get("sessionId") == record.get("session_id")), None)
    if row and row.get("status") == "busy" and os.environ.get("CLAUDE_CODE_SESSION_ID") != record.get("session_id"):
        raise Refused("successor", f"{record.get('name')} (session {record.get('session_id')}) is busy",
                      "wait until it is idle or stop it (claude stop <id>); a session may name itself at its handoff")
    return record


def successor_name(base: str, rows: list[dict]) -> str:
    """`<base>-<k>`, `<k>` the lowest number from 2 that no listed session uses (C6 section 3)."""
    names, k = {row.get("name") for row in rows}, 2
    while f"{base}-{k}" in names:
        k += 1
    return f"{base}-{k}"


def successor(args, main: Path, role: str) -> str:
    """A rotation successor or a takeover, in the predecessor's place: its ticket, worktree, model and
    effort; a background session with `/startup` (C6 section 3). It passes the usage stop."""
    held = {}

    def name_of(values, rows):
        coordination = main / str(values["coordination"][0])
        held["record"] = record = predecessor_of(coordination, args.successor, role, rows)
        project = values["project.name"][0]
        return successor_name(f"{project}-orch" if role == "orchestrator" else f"{project}-t{record['ticket']}", rows)

    found = checks(main, name_of, successor=True, check_only=args.check)
    values, name, coordination, old = found["values"], found["name"], found["coordination"], held["record"]
    if args.check:
        return f"check: {name} would pass checks 1-5. {NOTHING_STARTED}"
    copied, extra = [], ("--remote-control", name)
    cwd = main
    if role == "builder":
        cwd, extra = main / old["worktree"], ()
        if not (cwd / ".git").exists():
            raise Refused("successor", f"{old['worktree']} is not a worktree any more",
                          f"launch.py builder --ticket {old['ticket']} for a fresh start")
        secret_entries = list(values["secret_files"][0])
        check_secret_entries(secret_entries)
        copied = copy_secrets(main, cwd, secret_entries)
    settings = json.dumps(session_settings(main, role, values,
                                           role == "builder" and refresh_ticket(coordination, old.get("ticket"))))
    cmd = claude_command(name=name, model=old["model"], effort=old["effort"], compact=compact_for(main, role, values),
                         settings=settings, coordination=coordination, prompt=args.prompt or "/startup", extra=extra)
    record = new_record(launch_id=workfiles.event_id("launch", old.get("ticket"), git(cwd, "rev-parse", "HEAD")),
                        role=role, ticket=old.get("ticket"), name=name, successor_of=args.successor,
                        model=old["model"], effort=old["effort"], found=found, worktree=old["worktree"],
                        branch=old["branch"], base=old["base"], base_commit=old["base_commit"], copied=copied,
                        settings=settings)
    return start_and_record(cmd, cwd, main, coordination, record)


# ---------------------------------------------------------------- your start command (C6 section 1; decision 105)


def orchestrator(args, main: Path) -> int:
    """Your interactive orchestrator in this terminal: its id chosen here and its record written before
    claude starts, so there is no after-start step; then this script waits and passes on claude's exit code."""
    if args.successor:
        print(successor(args, main, "orchestrator"))
        return 0
    found = checks(main, lambda v, rows: f"{v['project.name'][0]}-orch", successor=False, check_only=args.check)
    values, name, coordination = found["values"], found["name"], found["coordination"]
    effort, lowered_from = lowered_effort(values["sessions.orchestrator.effort"][0], found)
    if args.check:
        print(f"check: {name} would pass checks 1-5. {NOTHING_STARTED}")
        return 0
    settings = json.dumps(session_settings(main, "orchestrator", values))
    model, session_id = values["sessions.orchestrator.model"][0], str(uuid.uuid4())
    commit = git(main, "rev-parse", "HEAD")
    record = new_record(launch_id=workfiles.event_id("launch", None, commit), role="orchestrator", ticket=None,
                        name=name, successor_of=None, model=model, effort=effort, lowered_from=lowered_from,
                        found=found, worktree=".", branch=git(main, "branch", "--show-current") or None, base=None,
                        base_commit=commit, copied=[], settings=settings)
    record["session_id"] = session_id
    cmd = claude_command(name=name, model=model, effort=effort, compact=compact_for(main, "orchestrator", values),
                         settings=settings, coordination=coordination, prompt=args.prompt, background=False,
                         extra=("--session-id", session_id, "--remote-control", name))
    write_record(coordination, record)  # a failed write is a failure before the start
    print(f"launched {name} {session_id} {record['id']}", flush=True)
    try:
        return subprocess.run(cmd, cwd=main, env=clean_env()).returncode
    except OSError as e:  # claude never ran: no session, so no record either
        (coordination / "launches" / f"{record['id']}.json").unlink(missing_ok=True)
        raise RuntimeError(f"claude could not be started: {e}") from e


def after_start(who: str, failed: str, worktree: Path, main: Path) -> SystemExit:
    stopped = stop(who, main)
    state = "stopped" if stopped else (f"could not be stopped: find it with `claude agents` (id or name {who}) "
                                       "and stop it with claude stop <id>")
    print(f"FAILED AFTER START: {failed}. Session {who} was started and {state}. It may have changed files in "
          f"{worktree.as_posix()}; a retry reuses that folder as it is.", file=sys.stderr)
    return SystemExit(2)


def claude_version() -> str:
    r = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    return r.stdout.split()[0] if r.returncode == 0 and r.stdout.split() else "unknown"


def sha256(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="launch.py", description="Start a kit session (contract C6).")
    sub = ap.add_subparsers(dest="role", required=True)
    check_help = "run checks 1-5 for this start; start and write nothing"
    o = sub.add_parser("orchestrator", help="your start command; with --successor, a background successor")
    o.add_argument("--successor", metavar="LAUNCH_ID", help="replace the session of this launch record")
    o.add_argument("--prompt", help="a first prompt (default: none for your start command, /startup for a successor)")
    o.add_argument("--check", action="store_true", help=check_help)
    b = sub.add_parser("builder", help="one background builder per ticket, in its own worktree")
    first = b.add_mutually_exclusive_group(required=True)
    first.add_argument("--ticket", type=int)
    first.add_argument("--successor", metavar="LAUNCH_ID", help="replace the session of this launch record")
    b.add_argument("--base")
    b.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    b.add_argument("--reason")
    b.add_argument("--prompt")
    b.add_argument("--check", action="store_true", help=check_help)
    args = ap.parse_args(argv)
    if args.role == "builder":
        if args.effort and not args.reason:
            ap.error("--effort needs --reason (decision 63)")
        if args.successor and (args.base or args.effort):
            ap.error("--successor takes its predecessor's base and effort")
    try:
        if args.role == "orchestrator":
            return orchestrator(args, main_checkout())
        print(builder(args, main_checkout()))
        return 0
    except Refused as r:
        print(r, file=sys.stderr)
        return 1
    except SystemExit as e:
        return int(e.code or 2)
    except Exception as e:
        print(f"{e}\n{NOTHING_STARTED}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
