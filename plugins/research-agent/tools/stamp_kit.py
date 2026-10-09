"""Stamp the consumer kit for a release: rewrite the first line of each file in kit/ with the
plugin version from .claude-plugin/plugin.json and the sha256 of the rest of the file (line endings
normalised to \n), as tools/doctor.py checks it. Run after setting the version: python tools/stamp_kit.py
"""

import hashlib
import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
COMMENT = {".py": "# {} ", ".md": "<!-- {} -->"}


def stamp(path: Path, version: str) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    rest = text.split("\n", 1)[1] if text.startswith(("# research-agent ", "<!-- research-agent ")) else text
    digest = hashlib.sha256(rest.encode("utf-8")).hexdigest()
    line = COMMENT[path.suffix].format(f"research-agent {version} sha256:{digest}").rstrip()
    return f"{line}\n{rest}"


if __name__ == "__main__":
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    for path in sorted((PLUGIN / "kit").glob("*.*")):
        if path.suffix in COMMENT:
            path.write_text(stamp(path, version), encoding="utf-8", newline="\n")
            print(f"stamped {path.name} {version}")
