"""The config validator, viewer and renderer (contract C3).

    python -I .agents/kit/bin/kitconfig.py check  [--project DIR]
    python -I .agents/kit/bin/kitconfig.py show   [--project DIR]
    python -I .agents/kit/bin/kitconfig.py render project|local [--project DIR] [--set key=VALUE ...]

Standard library only. The keys, types and defaults are data in .agents/kit/config/schema.toml; the
rules that are not data (V1-V11) are here; agent-kit tests the schema itself (V12). Other kit scripts import check() and effective().
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import posixpath
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA_PATH = ".agents/kit/config/schema.toml"
SCHEMA_FILE = "schema.toml"
FILES = {"project": "agent-kit.toml", "local": "agent-kit.local.toml"}
DEFAULT_SOURCE = "kit default"


@dataclass(frozen=True)
class Problem:
    file: str  # "agent-kit.toml", "agent-kit.local.toml" or "schema.toml"
    key: str  # dotted key; "" for a whole-file problem
    message: str
    valid: str

    def __str__(self):
        return f"{self.file}: {self.key}: {self.message}; valid: {self.valid}"


class ConfigError(Exception):
    def __init__(self, problems):
        super().__init__("\n".join(map(str, problems)))
        self.problems = problems


class CannotRun(Exception):
    """The check could not run at all (exit 2)."""


# ---------------------------------------------------------------- the schema


def load_schema(project: Path) -> dict:
    path = Path(project) / SCHEMA_PATH
    if not path.is_file():
        raise CannotRun(f"no schema at {path}")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise CannotRun(f"{path}: cannot parse: {e}") from e
    except (OSError, UnicodeDecodeError) as e:
        raise CannotRun(f"{path}: cannot read: {e}") from e


def schema_problems(schema: dict) -> list[Problem]:
    """The schema's version line (C2 section 7). The schema is kit-owned: agent-kit's own tests check
    the rest of it (V12), so a project does not pay for that check on every run."""
    version = schema.get("version")
    if schema.get("format") != "config-schema" or not isinstance(version, int):
        return [Problem(SCHEMA_FILE, "", "missing or wrong format/version line", 'format = "config-schema", version = 1')]
    if version > SCHEMA_VERSION:
        return [Problem(SCHEMA_FILE, "", f"version {version} is newer than this validator reads ({SCHEMA_VERSION})",
                        f"a kit release whose kitconfig.py reads version {version}")]
    return []


# ---------------------------------------------------------------- one value against its spec


def is_type(kind: str, value) -> bool:
    if kind in ("string", "path"):
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return isinstance(value, list) and all(isinstance(v, str) for v in value)  # the -list types


def norm(path: str) -> str:
    return path.replace("\\", "/")


def is_absolute(path: str) -> bool:
    """Rooted or drive-qualified, including drive-relative forms such as D:outside."""
    p = norm(path)
    return p.startswith("/") or bool(re.match(r"^[A-Za-z]:", p))


def escapes(path: str) -> bool:
    """A relative path that leaves the folder it is relative to, worked out without following links."""
    rel = posixpath.normpath(norm(path))
    return rel == ".." or rel.startswith("../")


def relative_inside(root: Path, path: str) -> str | None:
    """The path relative to the project root, lexically and without following links; None if outside."""
    p = norm(path)
    if is_absolute(p):
        try:
            p = norm(os.path.relpath(p, root))  # lexical; case-insensitive on Windows
        except ValueError:
            return None  # another drive
    return None if escapes(p) else posixpath.normpath(p)


def location(root: Path, path: str) -> str:
    """A path's location for comparison, as Windows sees it: abspath drops the trailing dots and spaces
    Windows ignores, links and junctions are followed (for the parts that exist), then case-folded. V9
    stays lexical (relative_inside), so a tracked link is checked as itself."""
    return os.path.normcase(os.path.realpath(os.path.abspath(Path(root) / norm(path))))


def climbs(path: str) -> bool:
    return ".." in norm(path).split("/")


def value_problems(spec: dict, value, fixed: dict) -> list[tuple[str, str]]:
    """V3 and V4 for one value: a list of (message, valid form)."""
    kind = spec["type"]
    if not is_type(kind, value):
        return [(f"{value!r} is not a {kind}", f"a {kind}")]
    out = []
    items = value if isinstance(value, list) else [value]
    if "allowed" in spec and any(v not in spec["allowed"] for v in items):
        out.append((f"{value!r} is not allowed", f"one of {spec['allowed']}"))
    if "choices" in spec:
        choices = fixed.get(spec["choices"], [])
        if any(v not in choices for v in items):
            out.append((f"{value!r} is not in fixed.{spec['choices']}", f"one of {choices}"))
    if "min" in spec and not value >= spec["min"]:  # positive form: NaN fails it
        out.append((f"{value} is below {spec['min']}", f"at least {spec['min']}"))
    if "max" in spec and not value <= spec["max"]:
        out.append((f"{value} is above {spec['max']}", f"at most {spec['max']}"))
    if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
        out.append((f"{value!r} does not match {spec['pattern']}", f"a string matching {spec['pattern']}"))
    if kind in ("path", "path-list"):
        if spec["file"] == "project" and any(is_absolute(v) or escapes(v) for v in items):
            out.append((f"{value!r} must be relative and inside the project", "a path relative to the project root"))
    if kind == "glob-list" and any(is_absolute(v) or climbs(v) or "\\" in v for v in items):
        out.append((f"{value!r} has an absolute glob or one containing ..", "globs relative to the project root, using /"))
    return out


# ---------------------------------------------------------------- reading a config file


def prefixes(keys) -> set[str]:
    return {".".join(k.split(".")[:i]) for k in keys for i in range(1, k.count(".") + 1)}


def flatten(data: dict, specs: dict, known_prefixes: set, base="") -> tuple[dict, list[str]]:
    """Dotted leaves and the keys that are neither a schema key nor a schema prefix (V2)."""
    leaves, unknown = {}, []
    for name, value in data.items():
        key = f"{base}{name}"
        if key in specs:
            leaves[key] = value  # a table here is caught as a type error (V3)
        elif isinstance(value, dict) and key in known_prefixes:
            sub_leaves, sub_unknown = flatten(value, specs, known_prefixes, key + ".")
            leaves.update(sub_leaves)
            unknown += sub_unknown
        else:
            unknown.append(key)  # including an empty table at an unknown prefix
    return leaves, unknown


def read_file(path: Path, name: str) -> tuple[dict | None, list[Problem]]:
    if not path.is_file():
        which = "project" if name == FILES["project"] else "local"
        return None, [Problem(name, "", "missing", f"write it with kitconfig.py render {which}")]
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise CannotRun(f"{path}: cannot read: {e}") from e
    try:
        text = raw.decode("utf-8-sig")  # PowerShell 5.1 writes UTF-8 with a byte-order mark
    except UnicodeDecodeError:
        return None, [Problem(name, "", "is not UTF-8 text", "a UTF-8 TOML file")]
    try:
        return tomllib.loads(text), []
    except tomllib.TOMLDecodeError as e:
        message = str(e)
        if "line" not in message:  # "at end of document": give the end's coordinates
            lines = text.replace("\r\n", "\n").split("\n")
            message += f" (line {len(lines)}, column {len(lines[-1]) + 1})"
        valid = "TOML 1.0"
        if "escape" in message.lower() or "hex value" in message.lower():  # a backslash in "..."
            valid += "; write a Windows path with / or in single quotes, e.g. 'C:\\Users\\you'"
        return None, [Problem(name, "", f"cannot parse: {message}", valid)]


def leaf_problems(which: str, data: dict, schema: dict) -> tuple[dict, set, list[Problem]]:
    """V2-V4 for one file's parsed data. Returns its valid leaves, every key it sets, and the problems."""
    specs, fixed, name = schema["key"], schema.get("fixed", {}), FILES[which]
    other = FILES["local" if which == "project" else "project"]
    leaves, unknown = flatten(data, specs, prefixes(specs))
    out, good = [], {}
    own_keys = [k for k, s in specs.items() if s["file"] == which]
    for key in unknown:
        near = difflib.get_close_matches(key, own_keys, n=1, cutoff=0.8)
        out.append(Problem(name, key, "unknown setting", near[0] if near else f"a setting listed in {SCHEMA_PATH}"))
    for key, value in leaves.items():
        spec = specs[key]
        if spec["file"] != which:
            out.append(Problem(name, key, f"belongs in {other}", f"move it to {other}"))
            continue
        found = value_problems(spec, value, fixed)
        out += [Problem(name, key, m, v) for m, v in found]
        if not found:
            good[key] = value
    return good, set(leaves), out


# ---------------------------------------------------------------- rules across keys


def cross_problems(values: dict, sources: dict, schema: dict, files: set[str], project: Path) -> list[Problem]:
    """V5-V8 and V10 on the effective values. A rule runs only when all its keys are valid, and
    reports only for keys of the files being checked."""
    out = []
    specs, fixed = schema["key"], schema.get("fixed", {})

    def report(key, message, valid):
        if specs[key]["file"] in files:
            out.append(Problem(FILES[specs[key]["file"]], key, message, valid))

    def have(*keys):
        return all(k in values for k in keys)

    if have("reviewer.engine"):  # V5
        models = fixed.get({"codex": "codex_models", "claude": "claude_models"}.get(values["reviewer.engine"], ""), None)
        for key in ("reviewer.model", "reviewer.fallback.model"):
            if models is not None and have(key) and values[key] not in models:
                report(key, f"{values[key]!r} is not a {values['reviewer.engine']} model", f"one of {models}")
    for role in ("orchestrator", "builder", "reviewer"):  # V6
        w, h = f"context.{role}.warn", f"context.{role}.handoff"
        if have(w, h) and not values[w] < values[h]:
            report(w, f"warn ({values[w]}) must be below handoff ({values[h]})", f"a value below {values[h]}")
    n = "usage.no_new_sessions_at"  # V7
    for key in ("usage.warn_at", "usage.lower_effort_at"):
        if have(key, n) and values[key] > values[n]:
            report(key, f"{values[key]} is above {n} ({values[n]})", f"at most {values[n]}")
    if have("reviewer_checkouts", "coordination"):  # V8
        root = Path(project).resolve()  # compare locations as Windows sees them, not spellings
        c = [location(root, p) for p in values["reviewer_checkouts"]]
        others = {location(root, "."), location(root, values["coordination"])}
        if len(c) != 2 or len(set(c)) != 2 or set(c) & others:
            report("reviewer_checkouts", f"{values['reviewer_checkouts']} is not two distinct checkouts",
                   "two paths, distinct from each other, the project root and the coordination folder")
    if have("modules.enabled") and values["modules.enabled"]:  # V10
        report("modules.enabled", f"{values['modules.enabled']} names modules, but none can be installed yet",
               "[] until build step 8 defines installed modules (C11)")
    return out


def git(project: Path, *args, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(project), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def ignore_problems(project: Path, values: dict) -> list[Problem]:
    """V9: configured paths inside the project must be ignored by git; a secret file must not be tracked."""
    local = FILES["local"]
    try:
        inside = git(project, "rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        return [Problem(local, "", "git is not installed, so ignored paths cannot be checked", "git on PATH")]
    if inside.returncode != 0:
        return [Problem(local, "", "the project is not a git repository, so ignored paths cannot be checked",
                        "run the check inside the project's git checkout")]
    root = Path(project).resolve()
    paths = [("coordination", values.get("coordination"), True)]
    paths += [("reviewer_checkouts", p, True) for p in values.get("reviewer_checkouts", [])]
    paths += [("secret_files", p, False) for p in values.get("secret_files", [])]
    out, checks = [], []  # checks: (key, path relative to the root, the form check-ignore needs)
    for key, path, is_dir in paths:
        if path is None:
            continue
        rel = relative_inside(root, path)
        if rel == ".":
            out.append(Problem(local, key, f"{path!r} is the project root itself", "a folder inside or outside the project"))
        elif rel is not None:
            checks.append((key, rel, rel + ("/" if is_dir else "")))
    if not checks:
        return out
    # Two git calls for all paths: which are tracked, which are ignored.
    # NUL-separated, so git does not quote non-ASCII paths.
    listed = git(project, "ls-files", "-z", "--", *[c[1] for c in checks])
    ignoring = git(project, "check-ignore", "--stdin", "-z", stdin="".join(c[2] + "\0" for c in checks))
    if listed.returncode != 0 or ignoring.returncode not in (0, 1):
        failed = listed if listed.returncode != 0 else ignoring
        return [Problem(local, "", f"git failed: {failed.stderr.strip()}", "a working git checkout")]
    tracked, ignored = set(listed.stdout.split("\0")), set(ignoring.stdout.split("\0"))
    for key, rel, form in checks:
        if rel in tracked:
            out.append(Problem(local, key, f"{rel} is tracked by git", f"git rm --cached {rel}, and ignore it"))
        elif form not in ignored:
            out.append(Problem(local, key, f"{rel} is inside the project but git does not ignore it",
                               f"add /{form} to .gitignore"))
    return out


# ---------------------------------------------------------------- the interface


def evaluate(project: Path) -> tuple[list[Problem], dict, dict]:
    """Every problem (V1-V11), plus the effective values and their sources."""
    project = Path(project)
    schema = load_schema(project)
    out = schema_problems(schema)
    if out:
        return out, {}, {}
    specs = schema["key"]
    values = {k: s["default"] for k, s in specs.items() if "default" in s}
    sources = {k: DEFAULT_SOURCE for k in values}
    present, parsed = set(), set()  # keys a file sets, valid or not; the files that parsed
    for which, name in FILES.items():
        data, problems = read_file(project / name, name)
        out += problems
        if data is None:
            continue
        parsed.add(name)
        good, written, problems = leaf_problems(which, data, schema)
        present |= written
        out += problems
        values.update(good)
        sources.update({k: name for k in good})
    for key, spec in specs.items():  # V11
        if "default" not in spec and key not in present and FILES[spec["file"]] in parsed:
            out.append(Problem(FILES[spec["file"]], key, "required setting is not set", f"set {key} in {FILES[spec['file']]}"))
    out += cross_problems(values, sources, schema, set(FILES), project)
    out += ignore_problems(project, values)
    return out, values, sources


def check(project: Path) -> list[Problem]:
    return evaluate(project)[0]


def effective(project: Path) -> dict[str, tuple[object, str]]:
    problems, values, sources = evaluate(project)
    if problems:
        raise ConfigError(problems)
    return {k: (values[k], sources[k]) for k in load_schema(project)["key"]}


# ---------------------------------------------------------------- render


def toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return "[" + ", ".join(toml_value(v) for v in value) + "]"


def parse_sets(which: str, sets: list[str], schema: dict) -> tuple[dict, list[Problem]]:
    specs, name = schema["key"], FILES[which]
    out, values = [], {}
    for item in sets:
        key, sep, raw = item.partition("=")
        key = key.strip()
        if not sep:
            out.append(Problem(name, key, "--set needs key=VALUE", "--set key=<TOML value>"))
        elif key in values:
            out.append(Problem(name, key, "set twice", "one --set per key"))
        elif key not in specs or specs[key]["file"] != which:
            out.append(Problem(name, key, f"not a setting of {name}", f"a {which} setting listed in {SCHEMA_PATH}"))
        else:
            try:
                parsed = tomllib.loads(f"v = {raw}")
                if set(parsed) != {"v"}:
                    raise tomllib.TOMLDecodeError("more than one value")
                values[key] = parsed["v"]
            except tomllib.TOMLDecodeError:
                out.append(Problem(name, key, f"{raw!r} is not one TOML value",
                                   "a TOML value; strings in quotes, e.g. --set \"project.name='x'\""))
    return values, out


def render(project: Path, which: str, sets: list[str]) -> tuple[str, list[Problem]]:
    """The full file for one side, at defaults or --set values, and the one-file rules' problems."""
    schema = load_schema(project)
    out = schema_problems(schema)
    if out:
        return "", out
    specs, fixed, name = schema["key"], schema.get("fixed", {}), FILES[which]
    given, out = parse_sets(which, sets, schema)
    values = {k: s["default"] for k, s in specs.items() if "default" in s}
    for key, value in given.items():
        found = value_problems(specs[key], value, fixed)
        out += [Problem(name, key, m, v) for m, v in found]
        if not found:
            values[key] = value
    for key, spec in specs.items():
        if spec["file"] == which and key not in values and key not in given:
            out.append(Problem(name, key, "required setting has no value", f"--set {key}=<TOML value>"))
    out += cross_problems(values, {}, schema, {which}, project)
    if out:
        return "", out
    lines = [f"# {line}" for line in schema.get("header", {}).get(which, [])]
    keys = [k for k, s in specs.items() if s["file"] == which and k in values]
    if which == "local":  # flat keys, each after a blank line
        groups = [(None, [(k, k) for k in keys])]
    else:  # undotted keys first, above any table; then one table per section, in first-seen order (issue #57)
        tables = {None: []}
        for key in keys:
            section, _, rest = key.partition(".")
            tables.setdefault(section if rest else None, []).append((key, rest or key))
        groups = list(tables.items())
    for section, members in groups:
        if section is not None:
            lines += ["", f"[{section}]"]
        for key, name in members:
            if section is None:
                lines.append("")
            lines.append(f"# {specs[key]['doc']} [{', '.join(specs[key]['labels'])}]")
            lines.append(f"{name} = {toml_value(values[key])}")
    return "\n".join(lines) + "\n", out


# ---------------------------------------------------------------- the command line


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kitconfig.py", description="Check, show or render the kit config (C3).")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "show"):
        sub.add_parser(command).add_argument("--project", default=".")
    r = sub.add_parser("render")
    r.add_argument("which", choices=list(FILES))
    r.add_argument("--project", default=".")
    r.add_argument("--set", action="append", default=[], dest="sets")
    args = parser.parse_args(argv)
    project = Path(args.project)
    try:
        if not project.is_dir():
            raise CannotRun(f"no project folder at {project}")
        if args.command == "render":
            text, problems = render(project, args.which, args.sets)
            if not problems:
                sys.stdout.write(text)
        else:
            problems, values, sources = evaluate(project)
            if args.command == "show":
                for key in load_schema(project)["key"]:
                    if key in values:
                        print(f"{key} = {toml_value(values[key])}   # {sources[key]}")
    except CannotRun as e:
        print(f"kitconfig.py: cannot run: {e}", file=sys.stderr)
        return 2
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
