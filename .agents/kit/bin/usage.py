"""Usage (contract C6 section 4): the orchestrator's status line writes the plan's usage for the launch.

    python -I .agents/kit/bin/usage.py statusline <coordination folder> [--warn-at <percent>]
                                                        (the status line's JSON on stdin)

Claude Code runs it on each status line refresh, also in background sessions, with `rate_limits` in its
input (M63). It rewrites `<coordination>/usage/claude.json` whole (C4 rules 3 and 4) and prints one short
line. With `--warn-at` (the launch passes `usage.warn_at`), a window at or above it writes a `usage-warn`
notice once per reset of that window (C6 sections 4, 7). It never fails the status line: on any error it
prints `usage ?`. Standard library only.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # C1 section 2: imports by __file__ under -I

import notices  # noqa: E402
import workfiles  # noqa: E402

RECORD = Path("usage") / "claude.json"
STALE_MINUTES = 30  # C6 section 4: older is `usage unknown`
WINDOWS = ("five_hour", "seven_day")
LABELS = {"five_hour": "5-hour", "seven_day": "7-day"}


def record_from(status: dict, now: datetime | None = None) -> dict | None:
    """C6 section 4's record from one status line input, or None when it carries no `rate_limits`."""
    limits = status.get("rate_limits") or {}
    windows = {w: limits[w] for w in WINDOWS if isinstance(limits.get(w), dict)}
    percents = [w["used_percentage"] for w in windows.values() if isinstance(w.get("used_percentage"), (int, float))]
    if not percents:
        return None
    return {"format": "usage", "version": 1, "id": "usage-claude", "observed_at": workfiles.utc_iso(now),
            "session_id": status.get("session_id"), **{w: windows.get(w) for w in WINDOWS},
            "percent": max(percents)}


def warn(coordination: Path, record: dict, warn_at: int) -> list[Path]:
    """A `usage-warn` notice for each window at or above `warn_at` that has none for its current reset.
    The reset time is in the notice's line, so the line itself says which reset it was written for."""
    written = []
    earlier = [p.read_text(encoding="utf-8") for p in (Path(coordination) / notices.FOLDER).glob("*-usage-warn-*.md")]
    for w in WINDOWS:
        window = record.get(w) or {}
        percent, resets = window.get("used_percentage"), window.get("resets_at")
        if not isinstance(percent, (int, float)) or percent < warn_at or not isinstance(resets, (int, float)):
            continue
        key = f"{LABELS[w]} limit resets {datetime.fromtimestamp(resets, timezone.utc):%Y-%m-%d %H:%M} UTC"
        if not any(key in text for text in earlier):
            written.append(notices.write(coordination, "usage-warn", f"Usage at {percent}% of your plan's "
                                         f"{LABELS[w]} limit (warning from {warn_at}%); the {key}."))
    return written


def statusline(coordination: Path, text: str, warn_at: int | None = None) -> str:
    status = json.loads(text)
    record = record_from(status)
    if record is not None:
        workfiles.write_atomic(Path(coordination) / RECORD, json.dumps(record, indent=1) + "\n")
    context = (status.get("context_window") or {}).get("used_percentage")
    parts = [f"usage {record['percent']}%" if record else "usage -"]
    if record is not None and warn_at is not None:
        try:
            if warn(coordination, record, warn_at):
                parts.append("usage notice written")
        except (OSError, ValueError) as e:  # the reading stands; the line says the notice failed
            parts.append(f"usage notice failed: {e}")
    if context is not None:
        parts.append(f"context {context}%")
    return " · ".join(parts)


def read(coordination: Path, now: datetime | None = None) -> tuple[int | float | None, int | None]:
    """(percent, age in minutes) for the launch, or (None, None): no file, one that does not parse, or one
    older than 30 minutes is `usage unknown` (C6 section 4)."""
    try:
        record = json.loads((Path(coordination) / RECORD).read_text(encoding="utf-8"))
        observed = datetime.strptime(record["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        seconds = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
        percent = record["percent"]
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
    if seconds > STALE_MINUTES * 60 or not isinstance(percent, (int, float)):  # before rounding the age
        return None, None
    return percent, int(seconds // 60)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        warn_at = None
        if len(argv) == 4 and argv[2] == "--warn-at":
            warn_at, argv = int(argv[3]), argv[:2]
        if len(argv) != 2 or argv[0] != "statusline":
            raise ValueError("usage: usage.py statusline <coordination folder> [--warn-at <percent>]")
        print(statusline(Path(argv[1]), sys.stdin.read(), warn_at))
    except Exception:
        print("usage ?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
