import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import doctor  # noqa: E402

FIXTURES = HERE / "fixtures"
ENV_NAMES = ("FETCH_RAW_IDENTITY_HOSTS", "DEMO_IDENTITY", "DEMO_API_KEY", "EDGAR_IDENTITY", "FRED_API_KEY")


def copy_fixture(name: str, dest: Path) -> Path:
    """Copy a fixture project to dest, restoring CLAUDE.md from _CLAUDE.md."""
    shutil.copytree(FIXTURES / name, dest)
    stored = dest / "_CLAUDE.md"
    if stored.exists():
        stored.rename(dest / "CLAUDE.md")
    readme = dest / "README.md"
    if name.startswith("equity") and readme.exists():
        readme.unlink()
    return dest


def stamped(body: str, version: str) -> str:
    return f"# research-agent {version} sha256:{doctor.stamp_hash(body)}\n{body}"


def write_kit(repo: Path, version: str) -> None:
    kit = repo / ".research-agent"
    kit.mkdir(exist_ok=True)
    for name in doctor.KIT_FILES:
        (kit / name).write_text(stamped(f"kit file {name}\n", version), encoding="utf-8", newline="\n")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def valid(tmp_path, monkeypatch):
    """The valid generalist project (research and consumer, research = "self"), with its env set."""
    repo = copy_fixture("valid", tmp_path / "valid")
    write_kit(repo, doctor.installed_version())
    monkeypatch.setenv("FETCH_RAW_IDENTITY_HOSTS", "example.gov=DEMO_IDENTITY")
    monkeypatch.setenv("DEMO_IDENTITY", "demo identity")
    monkeypatch.setenv("DEMO_API_KEY", "demo key")
    return repo


@pytest.fixture
def equity(tmp_path):
    """equity_research at 2712374: no config, paths in CLAUDE.md prose, rules as bullets."""
    return copy_fixture("equity-2712374", tmp_path / "equity")


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    full = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", **(env or {})}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env=full).stdout
