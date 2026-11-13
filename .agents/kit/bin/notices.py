"""Notices (contract C6 section 7): short lines for you when you may have walked away.

    python -I .agents/kit/bin/notices.py write <coordination> <kind> <text>
    python -I .agents/kit/bin/notices.py pending <coordination>          # one file name per line
    python -I .agents/kit/bin/notices.py sent <coordination> <name> <the PushNotification result>

A script or session with news writes a notice once; the orchestrator sends each pending one with its
`PushNotification` tool and records it under `sent/`, so each file has one writer (C4 rules 4 and 5).
Standard library only.
"""

from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # C1 section 2: imports by __file__ under -I

import workfiles  # noqa: E402

FOLDER = "notices"
MAX = 200  # characters: mobile systems cut longer notices (the tool's own rule)
KIND = re.compile(r"[a-z][a-z0-9-]{0,39}")


def front(fields: dict) -> str:
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "---\n"


def write(coordination: Path, kind: str, text: str) -> Path:
    """`notices/<UTC>-<kind>-<8 hex>.md`, written once (C6 section 7). The text is one line under 200
    characters. The random part keeps two producers in the same second apart without checking first,
    since a check and a write are not one step (C4 rule 6's way)."""
    if not KIND.fullmatch(kind):
        raise ValueError(f"kind {kind!r}: lower-case letters, digits and dashes")
    line = " ".join(text.split())
    if not line or len(line) >= MAX:
        raise ValueError(f"a notice is one line of 1-{MAX - 1} characters, not {len(line)}")
    folder = Path(coordination) / FOLDER
    path = folder / f"{workfiles.utc_stamp()}-{kind}-{secrets.token_hex(4)}.md"
    workfiles.write_atomic(path, front({"format": "notice", "version": 1, "id": path.stem, "kind": kind}) + line + "\n")
    return path


def pending(coordination: Path) -> list[str]:
    """Notices with no `sent/` record, oldest first."""
    folder = Path(coordination) / FOLDER
    if not folder.is_dir():
        return []
    sent = {p.name for p in (folder / "sent").glob("*.md")}
    return sorted(p.name for p in folder.glob("*.md") if ".tmp-" not in p.name and p.name not in sent)


def mark_sent(coordination: Path, name: str, result: str) -> Path:
    folder = Path(coordination) / FOLDER
    if not (folder / name).is_file():
        raise FileNotFoundError(f"no notice {name}")
    path = folder / "sent" / name
    if path.exists():
        raise FileExistsError(f"{name} is already recorded as sent")
    workfiles.write_atomic(path, front({"format": "notice-sent", "version": 1, "id": Path(name).stem,
                                        "sent_at": workfiles.utc_iso()}) + " ".join(result.split()) + "\n")
    return path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["write"] and len(argv) == 4:
            path = write(Path(argv[1]), argv[2], argv[3])
            print(f"notice {path.name}: {path.read_text(encoding='utf-8').splitlines()[-1]}")  # C6: written and printed
        elif argv[:1] == ["pending"] and len(argv) == 2:
            print("\n".join(pending(Path(argv[1]))))
        elif argv[:1] == ["sent"] and len(argv) == 4:
            print(mark_sent(Path(argv[1]), argv[2], argv[3]).name)
        else:
            print("\n".join(__doc__.strip().splitlines()[2:5]), file=sys.stderr)
            return 2
    except (ValueError, OSError) as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
