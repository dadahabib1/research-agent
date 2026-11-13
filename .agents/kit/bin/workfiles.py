"""Working files in the coordination folder (contract C4 section 1): the one helper every kit script uses
to write them, and the event ids. Standard library only; imported by `__file__` (C1 section 2).
"""

from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

RETRIES, PAUSE = 5, 0.1  # C4 rule 3: Windows refuses a replace while another process has the target open


def write_atomic(path: Path, text: str) -> None:
    """C4 rule 3: write `<name>.tmp-<pid>` beside the target, flush and fsync, then replace the target,
    retrying the replace up to 5 times 100 ms apart. Readers skip `*.tmp-*`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == RETRIES - 1:
                tmp.unlink(missing_ok=True)
                raise PermissionError(f"could not replace {path}: another process has it open")
            time.sleep(PAUSE)


def write_new(path: Path, data: bytes) -> None:
    """C4 rule 3 in create-only mode: write `<name>.tmp-<pid>` beside the target, flush and fsync, then hard
    link it to the target, which fails if the target exists, and remove the temporary file. So a second
    writer of the same file fails (FileExistsError) rather than overwrites."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def utc_stamp(now: datetime | None = None) -> str:
    """`yyyymmddThhmmssZ`, the time part of every event id (C4 rule 6)."""
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def utc_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_id(kind: str, ticket: int | None, commit: str) -> str:
    """C4 rule 6: `<kind>-<UTC>-<t<n> or none>-<commit, 7 hex>-<4 random hex>`."""
    return f"{kind}-{utc_stamp()}-{'none' if ticket is None else f't{ticket}'}-{commit[:7]}-{secrets.token_hex(2)}"
