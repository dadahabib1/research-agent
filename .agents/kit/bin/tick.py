"""The orchestrator loop's cheap first check (contract C9 section 16): what changed since the last turn.

    python -I .agents/kit/bin/tick.py

Prints one line per change, or exactly `nothing changed`, and exits 0. A change is:
- `message <name>`: a complete file in the orchestrator's inbox `messages/<project.name>-orch/` that is
  new or rewritten since the last run; one without its end line shows as `(incomplete)`, and once more as
  `(still incomplete)` on the next run if unchanged (C9 section 3: two turns on, it goes under Needs you);
- `record <path>` (or `record removed <path>`): a file under `merges/`, `verdicts/` or `launches/` that is
  new, rewritten or gone (a launch record, so a builder that dies before any listing saw it is noticed);
- `notice <name>`: every pending notice (no `notices/sent/` file), each run until it is sent;
- `session <name> (<short id>) waiting: <waitingFor>`, `... no longer waiting` or `... gone`: a project
  session (its folder is the main checkout or inside it) in `claude agents --json` that started or
  stopped waiting, or that was listed with a status last run and is now absent or listed without one;
- `escalated <name> (<short id>) waited <h> h: hand off` or `... idle <m> min: keepalive`, every run while
  it holds: an idle builder of a ticket with an open escalation (no answer record) that has waited
  `sessions.escalation_wait_hours` or longer, or else whose transcript was last written more than 40
  minutes ago (`unknown` when none is found), so its prompt cache, kept an hour, is refreshed in time
  (decision 123, C9 section 16).

Each run first reads, then saves what it saw to `<coordination>/state/tick.json` (C4 rule 3), so a change
that lands after the reading shows on the next run. Run it at the start of every loop turn: a turn that
skipped it would see its changes again on the next timer turn. A run with no saved snapshot reports itself
as a change. Anything the check cannot read (the config, the session list) is printed as a change, so the
turn goes ahead: the check can cost a turn, never skip one. Standard library only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # C1 section 2: imports by __file__ under -I

import formats  # noqa: E402
import kitconfig  # noqa: E402
import launch  # noqa: E402  (clean_env: no calling session's markers, M75)
import notices  # noqa: E402
import workfiles  # noqa: E402

SNAPSHOT = "state/tick.json"
RECORDS = ("merges", "verdicts", "launches")  # launches: a builder that dies before any listing saw it
LIVE = {"busy", "idle", "waiting"}  # the statuses test I and M81 saw on running sessions
# Measured 2026-10-17: a session's transcript is `<projects>/<its cwd, each non-alphanumeric a dash>/<sessionId>.jsonl`.
PROJECTS = Path.home() / ".claude" / "projects"
KEEPALIVE_AFTER_MINUTES = 40  # decision 123: the cache lasts an hour (C9 section 16), the timer fires every 15
KEEPALIVE, HAND_OFF = "keepalive", "hand off"  # the orchestrator skill acts on these words


def main_checkout() -> Path:
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git rev-parse: {r.stderr.strip()}")
    return Path(r.stdout.strip()).parent


def files_under(folder: Path, root: Path) -> dict[str, list[int]]:
    """Each file's `[mtime_ns, size]` by its path relative to `root`; C4 rule 3's `*.tmp-*` skipped."""
    if not folder.is_dir():
        return {}
    out = {}
    for p in folder.rglob("*"):
        if p.is_file() and ".tmp-" not in p.name:
            st = p.stat()
            out[p.relative_to(root).as_posix()] = [st.st_mtime_ns, st.st_size]
    return out


def complete(path: Path) -> bool:
    """C9 section 3's reader rule, the reader's own check (issue #98): parsed front matter and the end line."""
    return formats.complete(path)


def inside(cwd: str, main: Path) -> bool:
    a, b = os.path.normcase(os.path.abspath(cwd)), os.path.normcase(str(main))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def project_sessions(main: Path) -> dict[str, dict]:
    """The project's rows of `claude agents --json` by short id: name, status, waitingFor."""
    r = subprocess.run(["claude", "agents", "--json"], cwd=main, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=launch.clean_env())
    rows = json.loads(r.stdout) if r.returncode == 0 else None
    if not isinstance(rows, list):
        raise RuntimeError(f"claude agents --json exited {r.returncode}: {' '.join((r.stderr or '').split())[:200]}")
    return {str(row.get("id")): {"name": row.get("name"), "status": row.get("status"),
                                 "waitingFor": row.get("waitingFor"), "sessionId": row.get("sessionId")}
            for row in rows if isinstance(row, dict) and row.get("cwd") and inside(row["cwd"], main)}


def escalated(coordination: Path, project: str, wait_hours: float, sessions: dict) -> list[str]:
    """Decision 123: each idle builder of a ticket with an open escalation that must hand off or be nudged."""
    merges, now, lines = coordination / "merges", time.time(), []
    for path in sorted(merges.glob("escalation-*.md")) if merges.is_dir() else []:
        try:
            fields = formats.front_matter(path.read_text(encoding="utf-8", errors="replace"))[0]
            since = datetime.strptime(fields["written_at"], "%Y-%m-%dT%H:%M:%SZ")
            since = since.replace(tzinfo=timezone.utc).timestamp()
        except (OSError, KeyError, ValueError) as e:
            lines.append(f"escalation {path.name} unreadable: {e}")
            continue
        if (merges / f"answer-{fields.get('id') or path.stem}.md").exists():
            continue
        base = f"{project}-t{fields.get('ticket', '').lstrip('t')}"
        for sid, row in sorted(sessions.items()):
            name = row.get("name") or ""
            if row.get("status") != "idle" or not (name == base or name.startswith(base + "-")):
                continue
            waited = (now - since) / 3600
            if waited >= wait_hours:
                lines.append(f"escalated {name} ({sid}) waited {waited:.1f} h: {HAND_OFF}")
                continue
            found = list(PROJECTS.glob(f"*/{row.get('sessionId')}.jsonl")) if row.get("sessionId") else []
            idle = round((now - max(p.stat().st_mtime for p in found)) / 60) if found else None
            if idle is None or idle > KEEPALIVE_AFTER_MINUTES:
                since_last = "unknown" if idle is None else f"{idle} min"
                lines.append(f"escalated {name} ({sid}) idle {since_last}: {KEEPALIVE}")
    return lines


def compare(before: dict, now: dict, coordination: Path) -> list[str]:
    lines = []
    old, new = before.get("files", {}), now["files"]
    seen, now["incomplete"] = before.get("incomplete", {}), {}
    for path in sorted(new):
        unchanged = old.get(path) == new[path]
        if path.startswith("messages/"):
            name = path.rsplit("/", 1)[-1]
            if not complete(coordination / path):  # C9 section 3: two turns on, it goes under Needs you
                times = (seen.get(path, 0) if unchanged else 0) + 1
                now["incomplete"][path] = times
                if times <= 2:
                    lines.append(f"message {name} " + ("(incomplete)" if times == 1 else "(still incomplete)"))
            elif not unchanged:
                lines.append(f"message {name}")
        elif not unchanged:
            lines.append(f"record {path}")
    lines += [f"record removed {p}" for p in sorted(set(old) - set(new)) if not p.startswith("messages/")]
    lines += [f"notice {name}" for name in now["notices"]]
    was, sessions = before.get("sessions", {}), now["sessions"]
    for sid in sorted(set(was) | set(sessions)):
        a, b = was.get(sid, {}), sessions.get(sid, {})
        who = f"session {b.get('name') or a.get('name')} ({sid})"
        if b.get("status") == "waiting" and a.get("status") != "waiting":
            lines.append(f"{who} waiting: {b.get('waitingFor') or 'unknown'}")
        elif a.get("status") == "waiting" and b.get("status") in LIVE - {"waiting"}:
            lines.append(f"{who} no longer waiting")
        elif a.get("status") in LIVE and b.get("status") not in LIVE:
            lines.append(f"{who} gone")
    return lines


def tick(main: Path) -> list[str]:
    """The change lines since the last run (empty: nothing changed); saves this run's snapshot."""
    values = kitconfig.effective(main)
    coordination = main / str(values["coordination"][0])  # C3: relative to the project, or absolute
    inbox = Path("messages") / f"{values['project.name'][0]}-orch"
    files = files_under(coordination / inbox, coordination)
    for folder in RECORDS:
        files.update(files_under(coordination / folder, coordination))
    problems = []
    try:
        sessions = project_sessions(main)
    except (OSError, ValueError, RuntimeError) as e:
        sessions, problems = None, [f"sessions unknown: {e}"]
    snapshot = coordination / SNAPSHOT
    try:
        before = json.loads(snapshot.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        before = None
    now = {"files": files, "notices": notices.pending(coordination), "sessions": sessions or {}, "incomplete": {}}
    if before is None:
        lines = ["no earlier snapshot: a full turn reads everything"]
    else:
        if sessions is None:  # unknown is not gone: keep the last listing
            now["sessions"] = before.get("sessions", {})
        lines = compare(before, now, coordination)
    if sessions is not None:
        lines += escalated(coordination, str(values["project.name"][0]),
                           float(values["sessions.escalation_wait_hours"][0]), sessions)
    record ={"format": "tick", "version": 1, "id": "tick", "taken_at": workfiles.utc_iso(),
              "files": now["files"], "incomplete": now["incomplete"], "sessions": now["sessions"]}
    workfiles.write_atomic(snapshot, json.dumps(record, indent=1) + "\n")
    return problems + lines


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    try:
        lines = tick(main_checkout())
    except Exception as e:  # the check never skips a turn: an error is a change
        lines = [f"check failed: {' '.join(str(e).split())[:300]}"]
    print("\n".join(lines) if lines else "nothing changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
