# research-agent 0.6.2 sha256:c8ca4817bc28e99851b21d86329d1b7866e62bc0726bb00ccd0bf45b38eecd15
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Research drift check: compare each decision and rule pinned in docs/research-lock.md with the
research repository's main branch, and list what changed since this repository read it.

Part of the research-agent consumer kit, copied into .research-agent/ by /new-research-project.
The first line is its stamp (plugin version and the sha256 of the rest of the file); do not edit
this copy, or the doctor reports it.

Usage, from anywhere inside the host repository:
    python .research-agent/research_drift.py                 # fetch, then check
    python .research-agent/research_drift.py --no-fetch      # check the clone's REF as it is
    python .research-agent/research_drift.py --hash decision <record path> <decision-name>
    python .research-agent/research_drift.py --hash rule <rule-id>
Options: --research <path to the research clone> (default: [consumes] clone in research-agent.toml,
else ../<repo name>; this repository when research = "self"); --ref <git ref> (default origin/main;
another ref only to hash an item before its merge).
Exit code: 0 no drift, 1 drift or pending rows, 2 setup error.
"""

import argparse
import hashlib
import re
import subprocess
import sys
import tomllib
from pathlib import Path

CONFIG = "research-agent.toml"
LOCK_PATH = "docs/research-lock.md"
LEGACY_ROOT = "docs/research"
REF = "origin/main"
LOCK = Path(LOCK_PATH)
DECISIONS = f"{LEGACY_ROOT}/decisions"
RULES = f"{LEGACY_ROOT}/domain-rules.md"

REPORTS = """reports, and what to do about each:

  No drift    every pinned decision and rule matches REF.
              Action: none.
  PENDING     the row waits for a research pull request to merge.
              Action: once it is merged, replace "pending <PR URL>" with the merge commit; rerun
              --hash to check that the hash did not change in review.
  CHANGED     the pinned decision's or rule's text hashes differently on REF (a retired rule
              gains a Retired: line, so it shows here too).
              Action: read the diff the report names, then consume the item again: update the
              specs and code that rely on it, and the row (new commit, hash and date), in one
              pull request.
  SUPERSEDED  an accepted decision on REF supersedes a pinned one (its supersedes list names
              the pinned decision alone; a quoted part of a decision is not reported here).
              Action: consume the new decision; list every spec, ticket and test that uses the
              old one, and retire the old row, in the same pull request.
  STATUS      a pinned decision is no longer accepted.
              Action: escalate to your decider; you build on something withdrawn.
  MISSING     the record, decision or rule is gone from REF.
              Action: escalate to your decider.
  NEW         an accepted decision, or a rule whose Host: names this consumer, that the lock does
              not hold.
              Action: decide whether your work needs it now; pin it when your work starts
              relying on it (--hash gives the hash).
  DEPRECATED  the research repository has no research-agent.toml on REF, so its research is read
              from docs/research (removed in 0.7.0).
  WARN        this kit's stamp names a version outside your requires range: copy the kit again
              (/new-research-project), or change requires.

Only accepted decision records on the research repository's main branch are requirements;
branches, open pull requests and drafts are context."""


def git(research: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(research), *args], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def show(research: Path, path: str) -> str | None:
    try:
        return git(research, "show", f"{REF}:{path}").replace("\r\n", "\n")
    except subprocess.CalledProcessError:
        return None


def section(text: str, name: str) -> str | None:
    """The decision's subsection, from its `### <name>:` heading to the next heading."""
    match = re.search(
        rf"^### {re.escape(name)}:.*?(?=^### |^## |\Z)", text, flags=re.MULTILINE | re.DOTALL
    )
    return match.group(0).strip() if match else None


def content_hash(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().split("\n")]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:12]


def field(block: str, key: str) -> str:
    """A top-level key's raw value in a decision's yaml block, continuation lines included."""
    match = re.search(rf"^{key}:(.*?)(?=^\w+:|\Z)", block, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def blocks(research: Path) -> list[tuple[str, str]]:
    """(record path, yaml block) for every decision on main."""
    out = []
    for path in git(research, "ls-tree", "-r", "--name-only", REF, DECISIONS).split():
        if path.endswith(".md") and not path.endswith("INDEX.md"):
            text = show(research, path) or ""
            out += [(path, b) for b in re.findall(r"```yaml\n(.*?)```", text, flags=re.DOTALL)]
    return out


def lock_rows() -> dict[str, list[dict[str, str]]]:
    """The lock's rows by table: "Decision" (Locked decisions) and "Rule" (Pinned rules)."""
    tables: dict[str, list[dict[str, str]]] = {"Decision": [], "Rule": []}
    header = None
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if header is None:
            if cells[0] in tables:
                header = cells
        elif not set(cells[0]) <= set("-: "):
            tables[header[0]].append(dict(zip(header, cells, strict=False)))
    return tables


def supersedes(text: str, name: str) -> bool:
    """Whether a supersedes list names the whole decision: an item that is the name alone,
    bare or quoted. A quoted part of a decision ("<name> rule 2, detection only") is not."""
    items = re.findall(r'"([^"]*)"|\'([^\']*)\'|([^,\[\]\s"\'][^,\[\]]*)', text)
    return any("".join(item).strip() == name for item in items)


def host_rules(text: str, consumer: str) -> list[str]:
    """IDs of the rules whose Host: names the consumer and that are not retired."""
    out = []
    for match in re.finditer(r"^### ([^:\n]+):", text, flags=re.MULTILINE):
        sec = section(text, match.group(1)) or ""
        host = re.search(r"^[-*] Host:\s*(.+?)\s*$", sec, flags=re.MULTILINE)
        retired = re.search(r"^[-*] Retired:", sec, flags=re.MULTILINE)
        if host and host.group(1) == consumer and not retired:
            out.append(match.group(1).strip())
    return out


def check(research: Path, consumer: str | None) -> list[str]:
    head = git(research, "rev-parse", "--short", REF).strip()
    tables = lock_rows()
    rows = tables["Decision"]
    locked = {row["Decision"] for row in rows}
    found = blocks(research)
    report = []
    for row in rows:
        name, path, commit = row["Decision"], row["Record"], row["Research commit"]
        if commit.lower().startswith("pending"):
            report.append(f"PENDING  {name}: {commit}")
            continue
        text = show(research, path)
        sec = section(text, name) if text else None
        if sec is None:
            report.append(f"MISSING  {name}: not in {path} on {head}")
            continue
        if content_hash(sec) != row["Content hash"]:
            report.append(
                f"CHANGED  {name}: since {commit}; see git -C {research} diff {commit} {REF} -- {path}"
            )
        status = re.search(r"^status:\s*(\S+)", sec, flags=re.MULTILINE)
        if not status or status.group(1) != "accepted":
            report.append(f"STATUS   {name}: {status.group(1) if status else 'none'} on {head}")
    for path, block in found:
        name = field(block, "name")
        if field(block, "status") != "accepted":
            continue
        for old in sorted(locked - {name}):
            if supersedes(field(block, "supersedes"), old):
                report.append(f"SUPERSEDED {old}: by {name} ({path})")
        if name not in locked:
            report.append(f"NEW      {name}: accepted on {head} ({path}), not in the lock")
    rules_text = show(research, RULES)
    pinned = set()
    for row in tables["Rule"]:
        rule, commit = row["Rule"], row["Research commit"]
        pinned.add(rule)
        if commit.lower().startswith("pending"):
            report.append(f"PENDING  rule {rule}: {commit}")
            continue
        sec = section(rules_text, rule) if rules_text else None
        if sec is None:
            report.append(f"MISSING  rule {rule}: not in {RULES} on {head}")
        elif content_hash(sec) != row["Content hash"]:
            report.append(
                f"CHANGED  rule {rule}: since {commit}; see git -C {research} diff {commit} {REF} -- {RULES}"
            )
    if consumer and rules_text:
        for rule in host_rules(rules_text, consumer):
            if rule not in pinned:
                report.append(f"NEW      rule {rule}: Host {consumer} on {head} ({RULES}), not in the lock")
    return report


# ---------- configuration ----------

def find_host(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / CONFIG).is_file():
            return folder
    return None


def in_range(version: str, spec: str) -> bool:
    """Whether version satisfies spec: comparators >=, >, <=, <, == joined by commas ("and")."""
    def parse(text: str) -> tuple[int, ...]:
        return tuple(int(x) for x in text.strip().split("."))
    v = parse(version)
    ops = {">=": v.__ge__, ">": v.__gt__, "<=": v.__le__, "<": v.__lt__, "==": v.__eq__}
    for part in spec.split(","):
        match = re.fullmatch(r"\s*(>=|<=|==|>|<)\s*(\d+\.\d+\.\d+)\s*", part)
        if not match or not ops[match.group(1)](parse(match.group(2))):
            return False
    return True


def own_version() -> str | None:
    first = Path(__file__).read_text(encoding="utf-8").split("\n", 1)[0]
    match = re.search(r"research-agent (\d+\.\d+\.\d+) sha256:", first)
    return match.group(1) if match else None


class SetupError(Exception):
    """A setup problem: exit code 2."""


def research_layout(research: Path) -> tuple[str | None, list[str]]:
    """Set DECISIONS and RULES from the research repository's config on REF.
    Returns the consumer name it declares and any notices."""
    global DECISIONS, RULES
    text = show(research, CONFIG)
    if text is None:
        DECISIONS, RULES = f"{LEGACY_ROOT}/decisions", f"{LEGACY_ROOT}/domain-rules.md"
        return None, [f"DEPRECATED {research} has no {CONFIG} on {REF}; reading {LEGACY_ROOT}/ "
                      "(removed in 0.7.0)"]
    try:
        project = tomllib.loads(text).get("project", {})
    except tomllib.TOMLDecodeError:
        raise SetupError(f"{research}: {CONFIG} on {REF} does not parse") from None
    root = project.get("root", LEGACY_ROOT).strip("/")
    DECISIONS, RULES = f"{root}/decisions", f"{root}/domain-rules.md"
    return (project.get("consumer") or {}).get("name"), []


def main() -> int:
    global REF, LOCK
    parser = argparse.ArgumentParser(
        description=__doc__, epilog=REPORTS,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--research", type=Path, help="path to the research repository's clone")
    parser.add_argument("--no-fetch", action="store_true", help="do not fetch the clone first")
    parser.add_argument("--hash", nargs="+", metavar="ITEM",
                        help="print the hash for a new lock row: decision <record path> <decision-name>, "
                             "or rule <rule-id>")
    parser.add_argument("--ref", default=REF, help="git ref to compare with (default origin/main)")
    args = parser.parse_args()
    REF = args.ref
    host = find_host(Path.cwd())
    if host is None:
        print(f"No {CONFIG} here or in any parent folder: run this inside the host repository.")
        return 2
    try:
        config = tomllib.loads((host / CONFIG).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        print(f"{host / CONFIG} does not parse: {exc}")
        return 2
    consumes = config.get("consumes")
    if not isinstance(consumes, dict) or not consumes.get("research"):
        print(f"{host / CONFIG} has no [consumes] table with research = \"owner/repo\" or \"self\".")
        return 2
    repo = consumes["research"]
    if args.research:
        research = args.research
    elif repo == "self":
        research = host
    else:
        research = host / consumes.get("clone", f"../{repo.split('/')[-1]}")
    research = research.resolve()
    LOCK = host / LOCK_PATH
    if not (research / ".git").exists():
        print(f"No clone of {repo} at {research}: clone it there, set [consumes] clone, or pass --research.")
        return 2
    if not LOCK.is_file() and not args.hash:
        print(f"No lock at {LOCK}: create it from the plugin's templates/research-lock.md.")
        return 2
    try:
        if not args.no_fetch:
            git(research, "fetch", "-q", "origin")
        head = git(research, "rev-parse", "--short", REF).strip()
    except subprocess.CalledProcessError as exc:
        print(f"git failed in {research}: {exc.stderr.strip()} (pass --no-fetch, or --ref)")
        return 2
    try:
        consumer, notices = research_layout(research)
    except SetupError as exc:
        print(exc)
        return 2
    version, requires = own_version(), config.get("requires")
    if version and isinstance(requires, str) and not in_range(version, requires):
        notices.append(f'WARN     this kit is research-agent {version}, outside requires = "{requires}"; '
                       "copy the kit again (/new-research-project)")
    if args.hash:
        kind, rest = args.hash[0], args.hash[1:]
        if kind == "decision" and len(rest) == 2:
            text, name = show(research, rest[0]), rest[1]
        elif kind == "rule" and len(rest) == 1:
            text, name = show(research, RULES), rest[0]
        else:
            print("--hash takes: decision <record path> <decision-name>, or rule <rule-id>")
            return 2
        sec = section(text, name) if text else None
        if sec is None:
            print(f"{kind} {name} not found on {REF}")
            return 2
        print(content_hash(sec))
        return 0
    report = check(research, consumer)
    for line in notices + report:
        print(line)
    if not report:
        print(f"No drift: every pinned decision and rule matches {head}.")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
