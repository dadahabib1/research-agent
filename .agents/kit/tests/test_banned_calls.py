"""No merge, admin override or protection change outside the guarded merge (C5 section 5, decisions 93, 99).

Fails on `gh pr merge`, `--admin`, `/protection`, `rulesets` or `pulls/<n>/merge` in the project's tracked
code and settings. Not scanned: the guarded merge (`.agents/kit/bin/merge.py`, step 5), the guard and its
tests (they name these calls to refuse them), this file, C5 section 4's deny rules, and Markdown.

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path, PurePosixPath

KIT = Path(__file__).resolve().parent.parent  # .agents/kit
ROOT = KIT.parent.parent  # template/ in agent-kit, the project root in a project

CODE = ("*.py", "*.ps1", "*.sh", "*.cmd", "*.bat", "*.js", "*.ts")
SETTINGS = (".claude/settings*.json", ".codex/*.json")
BANNED = re.compile(r"gh pr merge|--admin\b|/protection\b|rulesets|pulls/[^/\s\"']+/merge\b")
EXEMPT = (".agents/kit/bin/merge.py", ".agents/kit/hooks/*", ".agents/kit/tests/test_guard.py",
          ".agents/kit/tests/test_banned_calls.py")


def without_deny_rules(text: str) -> str:
    """A settings file's text with its `permissions.deny` rules taken out: a deny rule names a banned call
    to refuse it (C5 section 4). A file that is not JSON is scanned as it is."""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    if isinstance(data, dict) and isinstance(data.get("permissions"), dict):
        data["permissions"].pop("deny", None)
    return json.dumps(data, indent=0)


def banned_calls(root: Path) -> list[str]:
    """`path:line: text` for each banned call in the tracked files of `root` (C5 section 5)."""
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)  # names unquoted
    if listed.returncode != 0:
        raise RuntimeError(f"git ls-files in {root}: {listed.stderr.decode(errors='replace').strip()}")
    found = []
    for rel in filter(None, listed.stdout.decode("utf-8").split("\0")):
        path = PurePosixPath(rel)
        settings = any(path.match(p) for p in SETTINGS)
        if not (settings or any(path.match(p) for p in CODE)) or any(path.match(p) for p in EXEMPT):
            continue
        try:
            raw = (root / rel).read_bytes()
        except FileNotFoundError:
            continue  # deleted in the working tree
        try:  # PowerShell 5.1 writes UTF-16 with a byte-order mark
            text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            found.append(f"{rel}: cannot be read as UTF-8 or UTF-16, so it cannot be checked")
            continue
        for number, line in enumerate((without_deny_rules(text) if settings else text).splitlines(), 1):
            if BANNED.search(line):
                found.append(f"{rel}:{number}: {line.strip()[:120]}")
    return found


class BannedCalls(unittest.TestCase):
    def test_the_project_has_none(self):
        self.assertEqual(banned_calls(ROOT), [])

    def test_planted_calls_are_found(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        subprocess.run(["git", "init", "-q", str(tmp)], check=True)
        files = {
            "scripts/release.sh": "gh pr merge 12 --squash\n",
            "tools/protect.py": "run(['gh', 'api', '-X', 'PUT', 'repos/o/r/branches/main/protection'])\n",
            ".claude/settings.json": '{"permissions": {"allow": ["Bash(gh pr merge --admin *)"]}}\n',
            "ci/merge.ps1": "Invoke-RestMethod -Method Put \"$api/pulls/$n/merge\"\n",
            # not findings: Markdown, the deny rules of C5 section 4, the guard, a lookalike word
            "README.md": "Never run gh pr merge yourself.\n",
            ".codex/hooks.json": '{"hooks": {}}\n',
            ".claude/settings.local.json": '{"permissions": {"deny": ["Bash(gh pr merge)", "Bash(gh pr merge *)"]}}\n',
            ".agents/kit/hooks/guard.py": "BANNED = 'gh pr merge'\n",
            "src/app.py": "administrator = True  # an --administrative flag\n",
        }
        for rel, text in files.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_text(text, encoding="utf-8")
        # review round 1: a non-ASCII name (git quotes it) and PowerShell 5.1's UTF-16 Out-File are still read
        (tmp / "scripts/über.sh").write_text("gh pr merge 3\n", encoding="utf-8")
        (tmp / "ci/release16.ps1").write_text("gh pr merge 4\n", encoding="utf-16")
        subprocess.run(["git", "-C", str(tmp), "add", "-A"], check=True)
        found = sorted(f.split(":")[0] for f in banned_calls(tmp))
        self.assertEqual(found, [".claude/settings.json", "ci/merge.ps1", "ci/release16.ps1", "scripts/release.sh",
                                 "scripts/über.sh", "tools/protect.py"])
        (tmp / "tools/odd.py").write_bytes(b"\xff\xfe\x00gh pr merge\x80")  # unreadable: reported, not skipped
        subprocess.run(["git", "-C", str(tmp), "add", "-A"], check=True)
        self.assertTrue(any(f.startswith("tools/odd.py") for f in banned_calls(tmp)))


if __name__ == "__main__":
    unittest.main()
