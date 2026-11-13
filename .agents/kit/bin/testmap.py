"""The kit's test command: runs the tests a change needs, as the test map names them, or the full offline suite.

    python -I .agents/kit/bin/testmap.py [--print] [--map FILE] [--diff BASE] [PATH ...]

The changed paths are each PATH (from the checkout root) and, with `--diff BASE`, every path the commits since BASE
change (`git diff BASE...HEAD`, renames as both paths): uncommitted work is not in that set, so commit first. Each
path maps, by the map (`tests/map.toml` at the checkout root unless `--map` names another), to: the full offline suite
when it is in the map's `core` list or matches no entry; else the tests of the most specific entry matching it (an
exact path before a glob, then the glob with the most fixed characters), and a test file to itself as well. The
union runs as one command: the project's `merge.clean_run` (agent-kit.toml) when it is a pytest command, the
selected files appended; else pytest run by this Python with the checkout's own pytest settings; a
`merge.clean_run` that is not pytest runs whole for any selection (issue #188). `--print` prints it instead. Exit: pytest's
own code, but 0 when nothing needs running, when pytest ran no test (its 5: the selected files hold only live tests,
which the settings leave out) and with `--print`; 2 refused, nothing run (a missing or broken map, a path outside
the checkout, git failing). Other kit scripts import `load_map`, `select` and `command`. Standard library only.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

FORMAT, VERSION = "test-map", 1
DEFAULT_MAP = "tests/map.toml"
FULL = "the full offline suite"
TOP_KEYS = {"format", "version", "core", "entry"}
ENTRY_KEYS = {"paths", "tests"}
GLOB_VALID = "a path from the checkout root with / between folders; * within a folder, ** across folders"


@dataclass(frozen=True)
class Problem:
    """One reason the command refuses, in kitconfig.py's shape: `<file>: <key>: <message>; valid: <valid>`."""
    file: str
    key: str
    message: str
    valid: str

    def __str__(self):
        return f"{self.file}: {self.key + ': ' if self.key else ''}{self.message}; valid: {self.valid}"


class Refused(Exception):
    def __init__(self, problems: list[Problem]):
        super().__init__("\n".join(map(str, problems)))
        self.problems = problems


@dataclass(frozen=True)
class TestMap:
    __test__ = False  # not a pytest test class
    shown: str  # the map's path as messages name it
    core: tuple[str, ...]
    entries: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]  # (paths, tests), in file order


@dataclass(frozen=True)
class Selection:
    full: bool  # the full offline suite
    tests: tuple[str, ...]  # sorted, each once; empty when full
    lines: tuple[str, ...]  # one per changed path: `<path>: <why>: <what it runs>`


# ---------------------------------------------------------------- paths and globs


def shown_path(path: Path, root: Path) -> str:
    """From the checkout root when inside it, else in full."""
    try:
        rel = Path(os.path.relpath(path, root)).as_posix()
    except ValueError:  # another drive
        return Path(path).as_posix()
    return Path(path).as_posix() if rel == ".." or rel.startswith("../") else rel


def glob_problem(glob) -> str | None:
    if not isinstance(glob, str) or not glob:
        return "not a path"
    if "\\" in glob:
        return "has a backslash"
    if glob.startswith("/") or re.match(r"^[A-Za-z]:", glob):
        return "is absolute"
    if ".." in glob.split("/") or "." in glob.split("/"):
        return "has a . or .. folder"
    return None


def glob_regex(glob: str) -> re.Pattern:
    """`**/` any folders (none included), `**` anything, `*` anything within one folder, `?` one character."""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out))


def specificity(glob: str) -> tuple[bool, int]:
    """An exact path before any glob; between globs, the one with more fixed characters."""
    wild = glob.count("*") + glob.count("?")
    return wild == 0, len(glob) - wild


def is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.startswith("test_") and name.endswith(".py")


def changed_path(raw: str, root: Path) -> str:
    """A changed path as git names it: from the checkout root, with /. A path outside the checkout is refused."""
    p = raw.replace("\\", "/")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        try:
            p = Path(os.path.relpath(p, root)).as_posix()
        except ValueError:
            p = "../"  # another drive
    p = posixpath.normpath(p)
    if p in (".", "..") or p.startswith("../"):
        raise Refused([Problem("testmap.py", raw, "not a path inside this checkout", "a changed file's path from the "
                               "checkout root, such as tools/setup.py")])
    return p


# ---------------------------------------------------------------- the map


def load_map(path: Path, root: Path) -> TestMap:
    """The map, checked whole: every problem is reported at once, and any problem refuses (nothing is guessed)."""
    shown = shown_path(Path(path), root)
    if not Path(path).is_file():
        raise Refused([Problem(shown, "", "no test map here", 'a test map (format = "test-map", version = 1), or '
                               "--map <file>; without one, run the offline suite as the project documents it")])
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise Refused([Problem(shown, "", f"cannot parse: {e}", "TOML")]) from e
    except (OSError, UnicodeDecodeError) as e:
        raise Refused([Problem(shown, "", f"cannot read: {e}", "a UTF-8 TOML file")]) from e
    out = []
    if data.get("format") != FORMAT or data.get("version") != VERSION:
        out.append(Problem(shown, "format", "missing or wrong format/version line", f'format = "{FORMAT}", version = '
                           f"{VERSION}"))
    out += [Problem(shown, key, "not a key of the test map", "format, version, core and [[entry]] tables")
            for key in sorted(set(data) - TOP_KEYS)]
    core = data.get("core")
    seen = {}
    if not isinstance(core, list):
        out.append(Problem(shown, "core", "missing, or not a list", 'core = ["<path or glob>", ...]'))
        core = []
    for glob in core:
        if (why := glob_problem(glob)) is not None:
            out.append(Problem(shown, f"core: {glob}", why, GLOB_VALID))
        elif glob in seen:
            out.append(Problem(shown, f"core: {glob}", "listed twice", "each path or glob once"))
        seen[str(glob)] = "core"
    entries = data.get("entry", [])
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        out.append(Problem(shown, "entry", "not a list of [[entry]] tables", "[[entry]] tables, each with paths and "
                           "tests"))
        entries = []
    kept = []
    for n, e in enumerate(entries, 1):
        where = f"entry {n}"
        out += [Problem(shown, f"{where}: {key}", "not a key of an entry", "paths and tests")
                for key in sorted(set(e) - ENTRY_KEYS)]
        paths, tests = e.get("paths"), e.get("tests")
        if not isinstance(paths, list) or not paths:
            out.append(Problem(shown, f"{where}: paths", "missing, empty or not a list", 'paths = ["<path or glob>", '
                               '...]'))
            paths = []
        for glob in paths:
            if (why := glob_problem(glob)) is not None:
                out.append(Problem(shown, f"{where}: paths: {glob}", why, GLOB_VALID))
            elif glob in seen:
                out.append(Problem(shown, f"{where}: paths: {glob}", f"also in {seen[glob]}",
                                   "each path or glob in one place: core or one entry"))
            else:
                seen[glob] = where
        if not isinstance(tests, list) or not all(isinstance(t, str) for t in tests):
            out.append(Problem(shown, f"{where}: tests", "missing, or not a list of test files",
                               'tests = ["tests/test_<name>.py", ...], or tests = [] for none'))
            tests = []
        for test in tests:
            if glob_problem(test) is not None or "*" in test or not (root / test).is_file():
                out.append(Problem(shown, f"{where}: tests: {test}", "not a file in this checkout",
                                   "a test file's path from the checkout root"))
            elif not is_test_file(test):  # PR #159 review round 1: pytest finds no test in it, and "no tests ran" is 0
                out.append(Problem(shown, f"{where}: tests: {test}", "not a test file (test_*.py)",
                                   "a test file named test_<name>.py; a file it imports or runs goes in paths"))
        kept.append((tuple(paths), tuple(tests)))
    if out:
        raise Refused(out)
    return TestMap(shown, tuple(core), tuple(kept))


def select(test_map: TestMap, root: Path, paths) -> Selection:
    """The tests the changed paths need: core or unmapped means the full suite; else the most specific entry's tests
    (ties: each tied entry's), and a test file itself."""
    core = [glob_regex(g) for g in test_map.core]
    globs = [(n, g, glob_regex(g), tests) for n, (gs, tests) in enumerate(test_map.entries, 1) for g in gs]
    full, chosen, lines = False, set(), []
    for path in sorted(set(paths)):
        if any(rx.fullmatch(path) for rx in core):
            full = True
            lines.append(f"{path}: core: {FULL}")
            continue
        here = (root / path).is_file()
        own = [path] if here and is_test_file(path) else []
        matching = [(n, g, tests) for n, g, rx, tests in globs if rx.fullmatch(path)]
        top = max((specificity(g) for _, g, _ in matching), default=None)
        best = [(n, g, tests) for n, g, tests in matching if specificity(g) == top]
        if not own and not best:
            full = True
            lines.append(f"{path}: no entry{'' if here else ' (not a file in this checkout)'}: {FULL}")
            continue
        tests = sorted(set(own) | {t for _, _, ts in best for t in ts})
        why = ", ".join((["a test file"] if own else []) + [f"entry {n} ({g})" for n, g, _ in best])
        lines.append(f"{path}: {why}: {' '.join(tests) or 'no tests'}")
        chosen.update(tests)
    return Selection(full, () if full else tuple(sorted(chosen)), tuple(lines))


def is_pytest(argv) -> bool:
    """True for a pytest command: a program named pytest, or a Python (`python*`, `py`) given `-m pytest`; a shell
    running several (`cmd /c "... && ..."`) is not one, so it runs whole."""
    argv = [str(a) for a in argv or ()]
    if not argv:
        return False
    name = Path(argv[0]).name.lower().removesuffix(".exe")
    return name in ("pytest", "py.test") or ((name.startswith("python") or name == "py")
                                              and any(a == "-m" and b == "pytest" for a, b in zip(argv, argv[1:])))


def clean_run(root: Path) -> list[str]:
    """The project's `merge.clean_run` from agent-kit.toml at `root` ([] when there is none, or it does not read)."""
    try:
        data = tomllib.loads((root / "agent-kit.toml").read_text(encoding="utf-8-sig"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    found = data.get("merge", {}).get("clean_run", [])
    return [str(a) for a in found] if isinstance(found, list) else []


def reviewer_checkouts(root: Path) -> list[str]:
    """The reviewer checkouts inside `root` (agent-kit.local.toml's `reviewer_checkouts`, default codex and codex-b;
    decision 78 keeps them in the project's folder) that exist: clones of the project, so pytest run from the root
    would collect their tests too, the same file names twice ("import file mismatch", finance-hub, 2026-11-13)."""
    try:
        data = tomllib.loads((root / "agent-kit.local.toml").read_text(encoding="utf-8-sig"))
        found = data.get("reviewer_checkouts", ["codex", "codex-b"])
    except (OSError, tomllib.TOMLDecodeError):
        found = ["codex", "codex-b"]
    out = []
    for c in found if isinstance(found, list) else []:
        path = Path(str(c)) if Path(str(c)).is_absolute() else root / str(c)
        try:
            rel = path.resolve().relative_to(root.resolve())
        except ValueError:
            continue  # outside the checkout: pytest never reaches it
        if path.is_dir() and rel.parts:
            out.append(rel.as_posix())
    return out


def skip_checkouts(argv: list[str] | None, root: Path) -> list[str] | None:
    """A pytest command with `--ignore=<checkout>` for each reviewer checkout inside `root` (issue #190); any other
    command, or none, unchanged."""
    if not argv or not is_pytest(argv):
        return argv
    return [*argv, *(f"--ignore={c}" for c in reviewer_checkouts(root))]


def command(selection: Selection, python: str = sys.executable, clean: list[str] | None = None) -> list[str] | None:
    """The pytest command for a selection (no file named: pytest's own test paths, the full suite); None for none.
    `clean` is the project's `merge.clean_run` (issue #188): a pytest command is kept as it is, its program (the
    project's own .venv Python, which kit setup writes, or a pytest launcher) and its options, the selected files
    appended; a command that is not pytest (`uv run ...`, `npm test`) cannot have files picked, so any selection
    runs it whole. With no clean run, `python` runs pytest."""
    if clean:
        if not is_pytest(clean) or selection.full:
            return list(clean) if selection.full or selection.tests else None
        return [*clean, *selection.tests] if selection.tests else None
    if selection.full:
        return [python, "-I", "-m", "pytest"]
    return [python, "-I", "-m", "pytest", *selection.tests] if selection.tests else None


# ---------------------------------------------------------------- git and the command line


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def checkout_root(cwd: Path) -> Path:
    r = git(cwd, "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        raise Refused([Problem("testmap.py", "", f"{cwd.as_posix()} is not in a git checkout",
                               "run it inside the checkout whose tests it picks")])
    return Path(r.stdout.strip())


def diff_paths(root: Path, base: str) -> list[str]:
    r = git(root, "diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD")
    if r.returncode != 0:
        raise Refused([Problem("testmap.py", "--diff", f"git diff {base}...HEAD failed: {r.stderr.strip()}",
                               "a branch or commit of this checkout, such as main")])
    return [p for p in r.stdout.split("\0") if p]


def shown_command(argv: list[str], root: Path) -> str:
    python = shown_path(Path(argv[0]), root)
    return " ".join(f'"{a}"' if " " in a else a for a in [python, *argv[1:]])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="testmap.py", description="Run, or print, the tests the test map names "
                                     "for the changed paths.")
    parser.add_argument("paths", nargs="*", metavar="PATH", help="a changed path, from the checkout root")
    parser.add_argument("--diff", metavar="BASE", help="add every path the commits since BASE change "
                        "(git diff BASE...HEAD); uncommitted work is not included")
    parser.add_argument("--map", help=f"the test map (default: {DEFAULT_MAP} at the checkout root)")
    parser.add_argument("--print", action="store_true", dest="print_only",
                        help="print the command instead of running it")
    args = parser.parse_args(argv)
    if not args.paths and args.diff is None:
        parser.error("name the changed paths, or --diff BASE")
    try:
        root = checkout_root(Path.cwd())
        test_map = load_map(Path(args.map) if args.map else root / DEFAULT_MAP, root)
        paths = [changed_path(p, root) for p in args.paths]
        if args.diff is not None:
            paths += diff_paths(root, args.diff)
            if git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
                print("testmap.py: note: uncommitted changes are not in --diff; commit them first, or name them",
                      file=sys.stderr)
        selection = select(test_map, root, paths)
    except Refused as e:
        for problem in e.problems:
            print(problem, file=sys.stderr)
        return 2
    for line in selection.lines:
        print(line)
    argv_ = skip_checkouts(command(selection, clean=clean_run(root)), root)
    if argv_ is None:
        print("command: none, " + ("no changed path maps to a test" if paths else "no changed paths"))
        return 0
    print("command: " + shown_command(argv_, root), flush=True)
    if args.print_only:
        return 0
    code = subprocess.run(argv_, cwd=root).returncode
    if code == 5 and is_pytest(argv_):  # pytest's "no tests ran": no error, nothing selected (the settings keep -m 'not live')
        print("testmap.py: pytest ran no test: the selected files hold only live tests (this command runs the "
              "offline suite only), or no tests at all", file=sys.stderr)
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
