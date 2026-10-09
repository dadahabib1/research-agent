import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env={**os.environ, **GIT_ENV}).stdout


def write(repo: Path, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        path = repo / rel
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def commit(repo: Path, files: dict[str, str | None], message: str = "change", origin: bool = True) -> str:
    """Write files (None deletes), commit, and move origin/main to the commit unless origin is False."""
    write(repo, files)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    if origin:
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return git(repo, "rev-parse", "--short", "HEAD").strip()


def init(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "core.autocrlf", "false")
    return repo


def make_host(root: Path, config: str, lock: str | None = None) -> Path:
    """A host repository with research-agent.toml, the lock and the kit's drift tool copied in."""
    root.mkdir(parents=True, exist_ok=True)
    write(root, {"research-agent.toml": config})
    if lock is not None:
        write(root, {"docs/research-lock.md": lock})
    (root / ".research-agent").mkdir(exist_ok=True)
    shutil.copy(KIT / "research_drift.py", root / ".research-agent" / "research_drift.py")
    return root


def drift(host: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(host / ".research-agent" / "research_drift.py"), *args],
                          cwd=cwd or host, capture_output=True, text=True, env={**os.environ, **GIT_ENV})


def lock(decisions: list[tuple] = (), rules: list[tuple] = ()) -> str:
    lines = ["# Research lock", "", "## Locked decisions", "",
             "| Decision | Record | Research commit | Content hash | Used by | Read |",
             "|---|---|---|---|---|---|"]
    lines += [f"| {d} | `{r}` | {c} | {h} | ticket | 2026-10-09 |" for d, r, c, h in decisions]
    lines += ["", "## Pinned rules", "", "| Rule | Research commit | Content hash | Implemented in | Read |",
              "|---|---|---|---|---|"]
    lines += [f"| {r} | {c} | {h} | src/x.py | 2026-10-09 |" for r, c, h in rules]
    return "\n".join(lines) + "\n"


@pytest.fixture
def tmp(tmp_path):
    return tmp_path
