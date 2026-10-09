# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml==6.0.3",
# ]
# ///
"""research-agent doctor: compare a repository's research-agent.toml with its files, and stop on
any mismatch.

Usage: uv run --script ${CLAUDE_PLUGIN_ROOT}/tools/doctor.py --mode run|setup [--project PATH]

Each item prints as FAIL, WARN or DEPRECATED with its check number. Exit codes: 0 no FAIL;
1 at least one FAIL (the run or setup stops); 2 the doctor could not run. Environment variables
are named, never printed.

Checks (0.6.x; "legacy" is a repository with no config whose CLAUDE.md has a "Research" section):
  1  the config parses, has no unknown key, and requires includes the installed version
     (legacy: DEPRECATED, range not checked)
  2  every fixed path and configured file exists
  3  the brief has headings 1 to 9 and its §6 "Domain rules:" line names the domain rules file
  4a the domain rules have headings 1 to 8; each ### rule has Check, Scope, Source and Added;
     IDs are unique kebab-case; each Host: names the configured consumer (legacy: a Host: line
     is DEPRECATED, since it cannot be checked without a config)
  4b a rule is still a bullet with no ID (DEPRECATED; FAIL from 0.7.0)
  5  the queue has the required columns and known statuses; each prompt file exists; each
     prerequisite names a task row (case ignored) or is "none"
  6  each decision header parses, has the core keys, and matches its INDEX.md row on name and status
  7  CLAUDE.md points to research-agent.toml (legacy: DEPRECATED)
  8  consumer: each kit file's stamp names a version inside requires and its hash matches; the
     lock parses
  9  FETCH_RAW_IDENTITY_HOSTS equals [project.fetch_identity] and each variable it names is set
     (FAIL with --mode run, WARN with --mode setup); when FETCH_RAW_IDENTITY_HOSTS is set but
     the config declares no [project.fetch_identity], WARN in both modes
  10 each other name in project.env is set (WARN)
  11 .gitignore has the Python cache lines (WARN)
  12 consumer: the research repository's consumer context file is no older than this
     repository's latest release tag (WARN)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CONFIG = "research-agent.toml"
LEGACY_LINE = "legacy CLAUDE.md prose (deprecated; removed in 0.7.0)"
KIT_FILES = ("INTEGRATION.md", "research_drift.py")
LOCK = "docs/research-lock.md"
STATUSES = {"todo", "waiting on requester", "in review", "accepted", "rejected", "deferred"}
QUEUE_COLUMNS = ("Task", "Prompt", "Deliverable", "Prerequisites", "Status")
DECISION_KEYS = ("name", "status", "decided", "decided_by", "depends_on", "supersedes", "parameters")
DECISION_STATUSES = {"accepted", "rejected", "deferred", "superseded", "withdrawn"}
RULE_FIELDS = ("Check", "Scope", "Source", "Added")
LOCK_DECISIONS = ["Decision", "Record", "Research commit", "Content hash", "Used by", "Read"]
LOCK_RULES = ["Rule", "Research commit", "Content hash", "Implemented in", "Read"]
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STAMP = re.compile(r"research-agent (\d+\.\d+\.\d+) sha256:([0-9a-f]{64})")

# key -> type, or a nested schema; "*" means any key with that value type
SCHEMA = {
    "requires": str,
    "project": {
        "root": str,
        "brief": str,
        "decider": str,
        "env": list,
        "consumer": {"name": str, "context": str},
        "fetch_identity": {"*": str},
        "run_defaults": {"model": str, "effort": str},
    },
    "consumes": {"research": str, "clone": str},
}
REQUIRED = {"": ["requires"], "project": ["root", "decider"], "project.consumer": ["name", "context"],
            "consumes": ["research"]}


class CannotRun(Exception):
    """The doctor itself cannot run (exit 2)."""


@dataclass
class Report:
    mode: str
    items: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, level: str, check: str, message: str) -> None:
        self.items.append((level, check, message))

    def fail(self, check: str, message: str) -> None:
        self.add("FAIL", check, message)

    def warn(self, check: str, message: str) -> None:
        self.add("WARN", check, message)

    def deprecated(self, check: str, message: str) -> None:
        self.add("DEPRECATED", check, message)

    def levels(self, check: str | None = None) -> list[str]:
        return [lvl for lvl, c, _ in self.items if check is None or c == check]


@dataclass
class Layout:
    """Where a research project's files are, relative to the repository root."""

    root: str
    brief: str
    rules: str
    queue: str
    prompts: str
    logs: str
    decisions: str
    context: str | None
    consumer: str | None
    legacy: bool


# ---------- versions ----------

def parse_version(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", text)
    if not match:
        raise ValueError(f"not a version: {text!r}")
    return tuple(int(x) for x in match.groups())  # type: ignore[return-value]


def in_range(version: str, spec: str) -> bool:
    """Whether version satisfies spec, comparators >=, >, <=, <, == joined by commas ("and")."""
    v = parse_version(version)
    ops = {">=": v.__ge__, ">": v.__gt__, "<=": v.__le__, "<": v.__lt__, "==": v.__eq__}
    for part in spec.split(","):
        match = re.fullmatch(r"\s*(>=|<=|==|>|<)\s*(\d+\.\d+\.\d+)\s*", part)
        if not match:
            raise ValueError(f"bad requirement {part.strip()!r} in {spec!r}")
        if not ops[match.group(1)](parse_version(match.group(2))):
            return False
    return True


def installed_version() -> str:
    try:
        manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        return manifest["version"]
    except (OSError, ValueError, KeyError) as exc:
        raise CannotRun(f"cannot read the plugin version from plugin.json: {exc}") from exc


# ---------- stamps ----------

def split_stamp(text: str) -> tuple[str, str]:
    """(stamp line, rest of the file), line endings normalised to \\n."""
    text = text.replace("\r\n", "\n")
    first, _, rest = text.partition("\n")
    return first, rest


def stamp_hash(rest: str) -> str:
    return hashlib.sha256(rest.encode("utf-8")).hexdigest()


# ---------- small parsers ----------

def read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError:
        return None


def strip_fences(text: str) -> list[str]:
    """The text's lines, with fenced code blocks blanked so examples are not parsed."""
    out, fenced = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else line)
    return out


def tables(text: str) -> list[list[list[str]]]:
    """Markdown tables as lists of rows of cells (backticks stripped), separator rows dropped."""
    found, current = [], None
    for line in text.split("\n"):
        if line.startswith("|"):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if current is None:
                current = [cells]
                found.append(current)
            elif not all(set(c) <= set("-: ") for c in cells):
                current.append(cells)
        else:
            current = None
    return found


def table_with(text: str, columns) -> tuple[list[str], list[dict[str, str]]] | None:
    for table in tables(text):
        header = table[0]
        if all(c in header for c in columns):
            return header, [dict(zip(header, row, strict=False)) for row in table[1:]]
    return None


def numbered_headings(lines: list[str]) -> set[int]:
    return {int(m.group(1)) for line in lines if (m := re.match(r"^## (\d+)\.", line))}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              encoding="utf-8")
    except FileNotFoundError as exc:
        raise CannotRun("git is not on the PATH") from exc


# ---------- check 1: the config ----------

def schema_errors(data: dict, schema: dict, prefix: str = "") -> list[str]:
    errors = []
    for key, value in data.items():
        name = f"{prefix}{key}"
        expected = schema.get(key, schema.get("*"))
        if expected is None:
            errors.append(f"unknown key {name}")
        elif isinstance(expected, dict):
            if not isinstance(value, dict):
                errors.append(f"{name} must be a table")
            else:
                errors += schema_errors(value, expected, f"{name}.")
        elif not isinstance(value, expected):
            errors.append(f"{name} must be a {expected.__name__}")
        elif expected is list and not all(isinstance(x, str) for x in value):
            errors.append(f"{name} must list strings")
    table = prefix.rstrip(".")
    for key in REQUIRED.get(table, []):
        if key not in data:
            errors.append(f"missing key {prefix}{key}")
    return errors


def check_config(data: dict, version: str, report: Report) -> None:
    for error in schema_errors(data, SCHEMA):
        report.fail("1", f"{CONFIG}: {error}")
    if "project" not in data and "consumes" not in data:
        report.fail("1", f"{CONFIG}: has neither [project] nor [consumes]")
    if data.get("consumes", {}).get("research") == "self" and "project" not in data:
        report.fail("1", f'{CONFIG}: research = "self" needs a [project] table')
    research = data.get("consumes", {}).get("research")
    if isinstance(research, str) and research != "self" and not re.fullmatch(r"[\w.-]+/[\w.-]+", research):
        report.fail("1", f'{CONFIG}: consumes.research must be owner/repo or "self", not {research!r}')
    requires = data.get("requires")
    if isinstance(requires, str):
        try:
            if not in_range(version, requires):
                report.fail("1", f'installed research-agent {version} is outside requires = "{requires}"')
        except ValueError as exc:
            report.fail("1", f"{CONFIG}: requires: {exc}")


# ---------- the layout ----------

def config_layout(project: dict) -> Layout:
    root = project.get("root", "docs/research").strip("/")
    consumer = project.get("consumer") or {}
    return Layout(
        root=root,
        brief=f"{root}/{project.get('brief', 'research-brief.md')}",
        rules=f"{root}/domain-rules.md",
        queue=f"{root}/research-queue.md",
        prompts=f"{root}/prompts",
        logs=f"{root}/logs",
        decisions=f"{root}/decisions",
        context=f"{root}/{consumer['context']}" if consumer.get("context") else None,
        consumer=consumer.get("name"),
        legacy=False,
    )


LEGACY_LABELS = {"brief": "brief", "domain rules": "rules", "queue": "queue", "prompts": "prompts",
                 "logs": "logs", "decision records": "decisions", "decisions": "decisions"}


def legacy_layout(claude_md: str | None) -> Layout | None:
    """Paths from a 0.5.0-style CLAUDE.md "Research" section, or None when there is none."""
    if not claude_md:
        return None
    match = re.search(r"^## Research\s*$(.*?)(?=^## |\Z)", claude_md, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return None
    paths: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        item = re.match(r"^\s*[-*]\s+([^:`]{1,40}):\s*`([^`]+)`", line)
        if not item:
            continue
        label, path = item.group(1).strip().lower(), item.group(2).strip()
        key = LEGACY_LABELS.get(label) or ("context" if label.endswith("context") else None)
        if key and key not in paths:
            if "<" in path:  # a pattern such as decisions/<topic>-<date>.md names its folder
                prefix = path.split("<")[0]
                path = prefix if prefix.endswith("/") else prefix.rsplit("/", 1)[0]
            paths[key] = path.strip("/")
    root = paths["queue"].rsplit("/", 1)[0] if "/" in paths.get("queue", "") else "docs/research"
    return Layout(
        root=root,
        brief=paths.get("brief", f"{root}/strategy-research-brief.md"),
        rules=paths.get("rules", f"{root}/domain-rules.md"),
        queue=paths.get("queue", f"{root}/research-queue.md"),
        prompts=paths.get("prompts", f"{root}/prompts"),
        logs=paths.get("logs", f"{root}/logs"),
        decisions=paths.get("decisions", f"{root}/decisions"),
        context=paths.get("context"),
        consumer=None,
        legacy=True,
    )


# ---------- checks 2 to 6: the research project ----------

def check_paths(repo: Path, lay: Layout, report: Report) -> None:
    wanted = [(lay.root, True), (lay.brief, False), (lay.rules, False), (lay.queue, False),
              (lay.prompts, True), (lay.logs, True), (f"{lay.decisions}/INDEX.md", False)]
    if lay.context:
        wanted.append((lay.context, False))
    for rel, is_dir in wanted:
        path = repo / rel
        if not (path.is_dir() if is_dir else path.is_file()):
            report.fail("2", f"missing {'folder' if is_dir else 'file'}: {rel}{'/' if is_dir else ''}")


def check_brief(repo: Path, lay: Layout, report: Report) -> None:
    text = read(repo / lay.brief)
    if text is None:
        return
    lines = strip_fences(text)
    missing = sorted(set(range(1, 10)) - numbered_headings(lines))
    if missing:
        report.fail("3", f"{lay.brief}: missing headings {', '.join(f'## {n}.' for n in missing)}")
    section = re.search(r"^## 6\.(.*?)(?=^## |\Z)", "\n".join(lines), flags=re.MULTILINE | re.DOTALL)
    named = re.search(r"Domain rules:\s*`([^`]+)`", section.group(1)) if section else None
    accepted = {lay.rules, lay.rules.removeprefix(f"{lay.root}/")}
    if not named:
        report.fail("3", f"{lay.brief}: §6 has no line `Domain rules: <path in backticks>`")
    elif named.group(1).strip().lstrip("./") not in accepted:
        report.fail("3", f"{lay.brief}: §6 names {named.group(1)!r}, not the domain rules file {lay.rules}")


def parse_rules(text: str) -> tuple[set[int], list[dict], list[tuple[int, str]]]:
    """(numbered headings, rules, legacy bullet rules as (heading, text))."""
    lines = strip_fences(text)
    heading, rule = None, None
    rules, bullets = [], []
    for number, line in enumerate(lines, 1):
        if line.startswith("## "):
            m = re.match(r"^## (\d+)\.", line)
            heading, rule = (int(m.group(1)) if m else None), None
        elif line.startswith("### ") and heading is not None:
            m = re.match(r"^### ([^:]+):\s*(.*)$", line)
            rule = {"id": (m.group(1) if m else line[4:]).strip(), "text": m.group(2) if m else "",
                    "line": number, "fields": {}, "heading": heading}
            rules.append(rule)
        elif re.match(r"^[-*] ", line) and heading is not None:
            content = line[2:].strip()
            m = re.match(r"^([A-Z][a-z]+):\s*(.*)$", content)
            if rule is not None:
                if m:
                    rule["fields"].setdefault(m.group(1), m.group(2).strip())
            elif not re.fullmatch(r"(?i)none( known)?\.?", content):
                bullets.append((heading, content))
    return numbered_headings(lines), rules, bullets


def check_rules(repo: Path, lay: Layout, report: Report) -> None:
    text = read(repo / lay.rules)
    if text is None:
        return
    headings, rules, bullets = parse_rules(text)
    missing = sorted(set(range(1, 9)) - headings)
    if missing:
        report.fail("4a", f"{lay.rules}: missing headings {', '.join(f'## {n}.' for n in missing)}")
    seen: set[str] = set()
    for rule in rules:
        where = f"{lay.rules}:{rule['line']}"
        rid, fields = rule["id"], rule["fields"]
        if not KEBAB.match(rid):
            report.fail("4a", f"{where}: rule ID {rid!r} is not kebab-case")
        if rid in seen:
            report.fail("4a", f"{where}: duplicate rule ID {rid}")
        seen.add(rid)
        absent = [f for f in RULE_FIELDS if not fields.get(f)]
        if absent:
            report.fail("4a", f"{where}: rule {rid} lacks {', '.join(absent)}")
        if fields.get("Scope") and fields["Scope"] not in ("decision-critical", "all"):
            report.fail("4a", f"{where}: rule {rid} Scope must be decision-critical or all")
        if fields.get("Added") and not DATE.match(fields["Added"]):
            report.fail("4a", f"{where}: rule {rid} Added must be YYYY-MM-DD")
        if "Host" in fields and lay.legacy:
            report.deprecated("4a", f"{where}: rule {rid} Host cannot be checked without a config; "
                                    f"write {CONFIG} with [project.consumer]")
        elif "Host" in fields and fields["Host"] != lay.consumer:
            expected = f"the configured consumer {lay.consumer!r}" if lay.consumer else "a configured [project.consumer]"
            report.fail("4a", f"{where}: rule {rid} Host {fields['Host']!r} is not {expected}")
    if bullets:
        under = sorted({h for h, _ in bullets})
        report.deprecated("4b", f"{lay.rules}: {len(bullets)} rule(s) written as bullets without an ID, "
                                f"under headings {', '.join(map(str, under))}; give each a ### rule ID "
                                "(fails from 0.7.0)")


def check_queue(repo: Path, lay: Layout, report: Report) -> None:
    text = read(repo / lay.queue)
    if text is None:
        return
    found = table_with(text, QUEUE_COLUMNS)
    if not found:
        report.fail("5", f"{lay.queue}: no table with the columns {', '.join(QUEUE_COLUMNS)}")
        return
    _, rows = found
    tasks = {row.get("Task", "").strip().lower() for row in rows}
    for row in rows:
        task = row.get("Task", "").strip()
        status = row.get("Status", "").strip()
        if status.lower() not in STATUSES:
            report.fail("5", f"{lay.queue}: task {task!r} has unknown status {status!r}")
        prompt = row.get("Prompt", "").strip()
        if not prompt or not (repo / lay.root / prompt).is_file():
            report.fail("5", f"{lay.queue}: task {task!r} prompt {prompt!r} not found under {lay.root}/")
        for prereq in row.get("Prerequisites", "").split(","):
            name = prereq.strip().lower()
            if name and name != "none" and name not in tasks:
                report.fail("5", f"{lay.queue}: task {task!r} prerequisite {prereq.strip()!r} names no task row")


def decision_headers(text: str) -> tuple[list[dict], list[str]]:
    """Each decision subsection's parsed header, and the errors met."""
    headers, errors = [], []
    section = re.search(r"^## Decisions[ \t]*$(.*?)(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    parts = re.split(r"^(?=### )", section.group(1) if section else "", flags=re.MULTILINE)
    for part in parts:
        heading = re.match(r"^### ([^:\n]+):", part)
        if not heading:
            continue
        name = heading.group(1).strip()
        body = re.split(r"^## ", part, maxsplit=1, flags=re.MULTILINE)[0]
        block = re.search(r"^```ya?ml\s*\n(.*?)^```", body, flags=re.MULTILINE | re.DOTALL)
        if not block:
            errors.append(f"decision {name} has no yaml header block")
            continue
        try:
            data = yaml.safe_load(block.group(1))
        except yaml.YAMLError as exc:
            errors.append(f"decision {name}: header does not parse ({str(exc).splitlines()[0]})")
            continue
        if not isinstance(data, dict):
            errors.append(f"decision {name}: header is not a mapping")
            continue
        absent = [k for k in DECISION_KEYS if k not in data]
        if absent:
            errors.append(f"decision {name}: header lacks {', '.join(absent)}")
        if data.get("name") != name:
            errors.append(f"decision {name}: header name {data.get('name')!r} differs from the heading")
        if data.get("status") not in DECISION_STATUSES:
            errors.append(f"decision {name}: status {data.get('status')!r} is not one of "
                          f"{', '.join(sorted(DECISION_STATUSES))}")
        headers.append(data)
    return headers, errors


def check_decisions(repo: Path, lay: Layout, report: Report) -> None:
    folder = repo / lay.decisions
    if not folder.is_dir():
        return
    found: dict[str, str] = {}
    for path in sorted(folder.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        headers, errors = decision_headers(read(path) or "")
        rel = f"{lay.decisions}/{path.name}"
        for error in errors:
            report.fail("6", f"{rel}: {error}")
        for data in headers:
            found[str(data.get("name"))] = str(data.get("status"))
    index_text = read(folder / "INDEX.md")
    if index_text is None:
        return
    table = table_with(index_text, ("Decision", "Status"))
    rows = {row["Decision"].strip(): row["Status"].strip() for row in (table[1] if table else [])}
    for name, status in found.items():
        if name not in rows:
            report.fail("6", f"{lay.decisions}/INDEX.md: no row for decision {name}")
        elif rows[name] != status:
            report.fail("6", f"{lay.decisions}/INDEX.md: {name} is {rows[name]!r}, its header says {status!r}")
    for name in rows:
        if name not in found:
            report.fail("6", f"{lay.decisions}/INDEX.md: row {name} has no decision header in {lay.decisions}/")


# ---------- check 7: the pointer ----------

def check_pointer(repo: Path, legacy: bool, report: Report) -> None:
    text = read(repo / "CLAUDE.md") or ""
    if CONFIG in text:
        return
    if legacy:
        report.deprecated("7", f'CLAUDE.md lists research paths in prose instead of pointing to {CONFIG} '
                               "(fails from 0.7.0)")
    else:
        report.fail("7", f"CLAUDE.md does not point to {CONFIG}")


# ---------- check 8: the consumer kit and lock ----------

def check_kit(repo: Path, requires: str | None, report: Report) -> None:
    for name in KIT_FILES:
        rel = f".research-agent/{name}"
        text = read(repo / rel)
        if text is None:
            report.fail("8", f"missing kit file: {rel}")
            continue
        first, rest = split_stamp(text)
        stamp = STAMP.search(first)
        if not stamp:
            report.fail("8", f"{rel}: first line has no research-agent stamp")
            continue
        version, digest = stamp.groups()
        if stamp_hash(rest) != digest:
            report.fail("8", f"{rel}: content differs from its stamp (edited locally?); copy it again from the plugin")
        if isinstance(requires, str):
            try:
                if not in_range(version, requires):
                    report.fail("8", f'{rel}: kit version {version} is outside requires = "{requires}"')
            except ValueError:
                pass  # check 1 reports a bad range
    text = read(repo / LOCK)
    if text is None:
        report.fail("8", f"missing lock: {LOCK}")
        return
    for columns, label in ((LOCK_DECISIONS, "Locked decisions"), (LOCK_RULES, "Pinned rules")):
        found = next((t for t in tables(text) if t[0] == columns), None)
        if found is None:
            report.fail("8", f"{LOCK}: no {label} table with the columns {' | '.join(columns)}")
            continue
        for cells in found[1:]:
            row = dict(zip(columns, cells, strict=False))
            key = row.get(columns[0], "")
            commit, digest = row.get("Research commit", ""), row.get("Content hash", "")
            if len(cells) != len(columns):
                report.fail("8", f"{LOCK}: {label} row {key!r} has {len(cells)} cells, not {len(columns)}")
            elif commit.lower().startswith("pending"):
                continue
            elif not re.fullmatch(r"[0-9a-f]{7,40}", commit) or not re.fullmatch(r"[0-9a-f]{12}", digest):
                report.fail("8", f"{LOCK}: {label} row {key!r} needs a commit and a 12-character hash, or 'pending <PR URL>'")


# ---------- checks 9 to 11: environment and .gitignore ----------

def identity_map(value: str) -> dict[str, str] | None:
    """FETCH_RAW_IDENTITY_HOSTS parsed as fetch_raw parses it; None when malformed."""
    pairs = {}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        suffix, sep, var = (x.strip() for x in item.partition("="))
        if not sep or not suffix or not var:
            return None
        pairs[suffix.lower().strip(".")] = var
    return pairs


def check_environment(project: dict, mode: str, report: Report) -> None:
    declared = {k.lower().strip("."): v for k, v in (project.get("fetch_identity") or {}).items()}
    actual_text = os.environ.get("FETCH_RAW_IDENTITY_HOSTS", "")
    level = report.fail if mode == "run" else report.warn
    if declared:
        actual = identity_map(actual_text)
        if actual is None:
            level("9", "FETCH_RAW_IDENTITY_HOSTS is not a list of host-suffix=ENVVAR pairs")
        elif actual != declared:
            want = ",".join(f"{k}={v}" for k, v in sorted(declared.items()))
            level("9", f"FETCH_RAW_IDENTITY_HOSTS does not equal [project.fetch_identity]; set it to {want}")
        for var in sorted(set(declared.values())):
            if not os.environ.get(var):
                level("9", f"{var} is not set ([project.fetch_identity] names it)")
    elif actual_text.strip():
        report.warn("9", "FETCH_RAW_IDENTITY_HOSTS is set, but research-agent.toml declares no "
                         "[project.fetch_identity]; declare the map so the project's identity hosts are on record")
    for var in project.get("env") or []:
        if var not in declared.values() and not os.environ.get(var):
            report.warn("10", f"{var} is not set (project.env names it)")


def check_gitignore(repo: Path, report: Report) -> None:
    lines = {line.strip() for line in (read(repo / ".gitignore") or "").split("\n")}
    if not lines & {"__pycache__/", "__pycache__", "**/__pycache__/"}:
        report.warn("11", ".gitignore lacks the line __pycache__/")
    if not lines & {"*.pyc", "*.py[cod]"}:
        report.warn("11", ".gitignore lacks the line *.pyc")


# ---------- check 12: the consumer context's age ----------

def check_context_age(repo: Path, consumes: dict, report: Report) -> None:
    research = consumes.get("research", "")
    if not isinstance(research, str) or research == "self" or "/" not in research:
        return
    tags = git(repo, "for-each-ref", "--sort=-creatordate", "--format=%(refname:short) %(creatordate:short)",
               "refs/tags/v*").stdout.split("\n")
    latest = next((t.split() for t in tags if t.strip()), None)
    if not latest:
        return
    tag, tag_date = latest
    clone = (repo / consumes.get("clone", f"../{research.split('/')[1]}")).resolve()
    if git(clone, "rev-parse", "--git-dir").returncode != 0:
        report.warn("12", f"cannot check the consumer context's age: no clone of {research} at {clone}")
        return
    shown = git(clone, "show", f"origin/main:{CONFIG}")
    try:
        config = tomllib.loads(shown.stdout) if shown.returncode == 0 else None
    except tomllib.TOMLDecodeError:
        config = None
    project = (config or {}).get("project", {})
    context = (project.get("consumer") or {}).get("context")
    if not context:
        report.warn("12", f"cannot check the consumer context's age: {research} on origin/main declares "
                          "no [project.consumer] context in research-agent.toml")
        return
    path = f"{project.get('root', 'docs/research').strip('/')}/{context}"
    text = git(clone, "show", f"origin/main:{path}").stdout
    as_of = re.search(r"As of:\s*(\d{4}-\d{2}-\d{2})", text)
    if not as_of:
        report.warn("12", f"{research}:{path} has no 'As of: YYYY-MM-DD' line")
    elif as_of.group(1) < tag_date:
        report.warn("12", f"{research}:{path} is as of {as_of.group(1)}, older than this repository's "
                          f"release {tag} ({tag_date}); update it")


# ---------- the run ----------

def diagnose(repo: Path, mode: str) -> tuple[Report, str]:
    """Run every check on the repository; returns the report and the config line."""
    report = Report(mode)
    version = installed_version()
    config_path = repo / CONFIG
    data: dict = {}
    if config_path.is_file():
        config_line = CONFIG
        try:
            data = tomllib.loads(read(config_path) or "")
        except tomllib.TOMLDecodeError as exc:
            report.fail("1", f"{CONFIG} does not parse: {exc}")
            return report, config_line
        check_config(data, version, report)
        project = data.get("project") if isinstance(data.get("project"), dict) else None
        consumes = data.get("consumes") if isinstance(data.get("consumes"), dict) else None
        layout = config_layout(project) if project is not None else None
    else:
        layout = legacy_layout(read(repo / "CLAUDE.md"))
        if layout is None:
            report.fail("1", f"no {CONFIG}, and CLAUDE.md has no \"Research\" section to read instead")
            return report, "none"
        config_line = LEGACY_LINE
        report.deprecated("1", f"no {CONFIG}: paths read from the CLAUDE.md \"Research\" section; "
                               "write the config (/new-research-project, adopt mode)")
        project, consumes = {}, None
    if layout is not None:
        check_paths(repo, layout, report)
        check_brief(repo, layout, report)
        check_rules(repo, layout, report)
        check_queue(repo, layout, report)
        check_decisions(repo, layout, report)
    check_pointer(repo, layout is not None and layout.legacy, report)
    if consumes is not None:
        check_kit(repo, data.get("requires"), report)
    if project:
        check_environment(project, mode, report)
    check_gitignore(repo, report)
    if consumes is not None:
        check_context_age(repo, consumes, report)
    return report, config_line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=__doc__.split("\n\n", 1)[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("run", "setup"), required=True,
                        help="run: /run-next-task step 0 (check 9 fails); setup: /new-research-project (check 9 warns)")
    parser.add_argument("--project", type=Path, default=Path("."), help="repository root (default: .)")
    args = parser.parse_args(argv)
    repo = args.project.resolve()
    try:
        if not repo.is_dir():
            raise CannotRun(f"no such folder: {repo}")
        report, config_line = diagnose(repo, args.mode)
        version = installed_version()
    except CannotRun as exc:
        print(f"doctor could not run: {exc}")
        return 2
    print(f"research-agent doctor {version} ({args.mode}): {repo}")
    print(f"config: {config_line}")
    for level, check, message in report.items:
        print(f"{level:<10} {check:<3} {message}")
    counts = {lvl: report.levels().count(lvl) for lvl in ("FAIL", "WARN", "DEPRECATED")}
    print(f"summary: {counts['FAIL']} FAIL, {counts['WARN']} WARN, {counts['DEPRECATED']} DEPRECATED")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
