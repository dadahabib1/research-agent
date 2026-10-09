"""The drift tool: UTF-8 hashes of equity's real decision records and the app's one re-pin, rule pins,
research = "self", the legacy fallback, every report code, exit codes, the stamp and --help."""

import hashlib
import json
import re
import shutil
from pathlib import Path

from conftest import KIT, commit, drift, git, init, lock, make_host, write

EQUITY = KIT.parents[2] / "test-fixtures" / "equity"  # outside the shipped plugin folder
APP_CONSUMES = '[consumes]\nresearch = "dadahabib1/equity_research"\n'
REQUIRES = 'requires = ">=0.6.0, <0.7.0"\n'


def lock_hashes(text: str) -> list[tuple[str, str, str]]:
    """(decision, record, hash) for each row of the app's lock, read independently of the kit."""
    rows = []
    for line in text.splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and re.fullmatch(r"[0-9a-f]{12}", cells[3] if len(cells) > 3 else ""):
            rows.append((cells[0], cells[1], cells[3]))
    return rows


# ---------- equity's decisions and equity_analyst_v2's lock ----------

def equity_clone(tmp: Path) -> Path:
    research = init(tmp / "equity_research")
    files = {f"docs/research/decisions/{p.name}": p.read_text(encoding="utf-8").replace("\r\n", "\n")
             for p in (EQUITY / "decisions").glob("*.md")}
    commit(research, files, "equity decisions at 2712374")
    return research


def utf8_hash(record: str, name: str) -> str:
    """The contract's hash, computed here independently of the kit: the decision's subsection of the
    record read as UTF-8, lines right-stripped, joined with \\n, sha256, first 12 hex characters."""
    text = (EQUITY / "decisions" / Path(record).name).read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith(f"### {name}:"))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(("### ", "## "))), len(lines))
    body = "\n".join(line.rstrip() for line in lines[start:end]).strip("\n")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def test_hashes_equity_decisions_as_utf8(tmp):
    research = equity_clone(tmp)
    app_lock = (EQUITY / "research-lock.md").read_text(encoding="utf-8")
    rows = lock_hashes(app_lock)
    assert len(rows) == 12
    host = make_host(tmp / "equity_analyst_v2", REQUIRES + APP_CONSUMES, app_lock)
    for name, record, _ in rows:
        out = drift(host, "--no-fetch", "--hash", "decision", record, name)
        assert out.returncode == 0, out.stdout + out.stderr
        assert out.stdout.strip() == utf8_hash(record, name), name


def test_the_apps_12_rows_need_one_re_pin_on_the_legacy_fallback(tmp):
    """Migration §13, step 2: the app's script hashed git output decoded as cp1252 (Python's default on
    Windows), so its 12 rows report CHANGED once; re-pinned with --hash, they report no drift."""
    equity_clone(tmp)
    app_lock = (EQUITY / "research-lock.md").read_text(encoding="utf-8")
    host = make_host(tmp / "equity_analyst_v2", REQUIRES + APP_CONSUMES, app_lock)
    out = drift(host, "--no-fetch")
    assert out.returncode == 1, out.stdout + out.stderr
    assert sum(line.startswith("CHANGED") for line in out.stdout.splitlines()) == 12
    for name, record, old in lock_hashes(app_lock):
        app_lock = app_lock.replace(old, hash_of(host, "decision", record, name), 1)
    write(host, {"docs/research-lock.md": app_lock})
    out = drift(host, "--no-fetch")
    assert out.returncode == 0, out.stdout + out.stderr
    lines = out.stdout.strip().splitlines()
    assert lines[0].startswith("DEPRECATED ") and "has no research-agent.toml" in lines[0]
    assert lines[1].startswith("No drift: every pinned decision and rule matches")
    assert len(lines) == 2


def test_the_hash_is_the_apps_function():
    """Lines right-stripped, joined with \\n, sha256, first 12 hex characters."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("drift", KIT / "research_drift.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text = "### a-b: title  \n\n- x \t\n"
    assert mod.content_hash(text) == hashlib.sha256("### a-b: title\n\n- x".encode()).hexdigest()[:12]
    doc = "## Decisions\n\n### a-b: one\n\nbody\n\n### c-d: two\n\nmore\n## Rejected\n"
    assert mod.section(doc, "a-b") == "### a-b: one\n\nbody"
    assert mod.section(doc, "c-d") == "### c-d: two\n\nmore"
    assert mod.section(doc, "a") is None


# ---------- a research repository with a config ----------

CONFIG = '''requires = ">=0.6.0, <0.7.0"
[project]
root = "research"
decider = "requester"
[project.consumer]
name = "app"
context = "app-context.md"
'''


def record(*decisions: tuple[str, str, str]) -> str:
    """A decision record with (name, status, supersedes) subsections."""
    parts = ["# Decision record", "", "## Decisions", ""]
    for name, status, supersedes in decisions:
        parts += [f"### {name}: decide {name}", "", "```yaml", f"name: {name}", f"status: {status}",
                  "decided: 2026-10-01", "decided_by: requester", "depends_on: []",
                  f"supersedes: {supersedes}", "parameters: []", "```", "", f"- **Decision:** {name} must hold.", ""]
    return "\n".join(parts + ["## Rejected and deferred decisions", "", "- none", ""])


def rules(*items: tuple[str, str, str | None, bool]) -> str:
    """A domain rules file with (id, text, host, retired) rules under heading 1."""
    parts = ["# Domain rules", "", "## 1. When information counts as known", ""]
    for rid, text, host, retired in items:
        parts += [f"### {rid}: {text}", "- Check: it holds.", "- Scope: all", "- Source: requester, 2026-10-01",
                  "- Added: 2026-10-01"]
        if host:
            parts.append(f"- Host: {host}")
        if retired:
            parts.append("- Retired: 2026-10-05; replaced")
        parts.append("")
    return "\n".join(parts + ["## 2. What settles each claim type here", "", "none known", ""])


def research_repo(tmp: Path, rule_items=None, record_text=None, config=CONFIG) -> Path:
    research = init(tmp / "research-repo")
    files = {"research/domain-rules.md": rules(*(rule_items or [])),
             "research/decisions/topic-2026-10-01.md": record_text or record(("d-one", "accepted", "[]"))}
    if config:
        files["research-agent.toml"] = config
    commit(research, files, "research")
    return research


def host_for(tmp: Path, research: Path, decisions=(), rule_rows=(), requires=REQUIRES) -> Path:
    config = requires + f'[consumes]\nresearch = "owner/research-repo"\nclone = "../{research.name}"\n'
    return make_host(tmp / "host", config, lock(list(decisions), list(rule_rows)))


def hash_of(host: Path, *item: str) -> str:
    out = drift(host, "--no-fetch", "--hash", *item)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout.strip()


def pin_all(tmp, research, decision_names=(), rule_ids=()) -> Path:
    host = host_for(tmp, research)
    head = git(research, "rev-parse", "--short", "HEAD").strip()
    path = "research/decisions/topic-2026-10-01.md"
    decisions = [(d, path, head, hash_of(host, "decision", path, d)) for d in decision_names]
    rule_rows = [(r, head, hash_of(host, "rule", r)) for r in rule_ids]
    write(host, {"docs/research-lock.md": lock(decisions, rule_rows)})
    return host


def reports(out) -> list[str]:
    return [line for line in out.stdout.splitlines() if line.strip()]


def test_hashes_non_ascii_text_as_utf8_on_every_platform(tmp):
    """A pin made on one machine must match on another, whatever its default encoding."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("drift", KIT / "research_drift.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    research = research_repo(tmp, [("unit-rule", "Readings at or above 15 µg/m³ in Łódź count.", "app", False)])
    doc = (research / "research/domain-rules.md").read_text(encoding="utf-8")
    assert hash_of(host_for(tmp, research), "rule", "unit-rule") == mod.content_hash(mod.section(doc, "unit-rule"))


# ---------- rule pins ----------

def test_rule_pins(tmp):
    research = research_repo(tmp, [("pinned-rule", "It holds.", "app", False),
                                   ("plain-rule", "No host.", None, False),
                                   ("old-host-rule", "Retired.", "app", True),
                                   ("other-host-rule", "Another consumer.", "other", False)])
    host = pin_all(tmp, research, ["d-one"], ["pinned-rule"])
    out = drift(host, "--no-fetch")
    assert out.returncode == 0, out.stdout
    assert reports(out) == [f"No drift: every pinned decision and rule matches {git(research, 'rev-parse', '--short', 'HEAD').strip()}."]

    commit(research, {"research/domain-rules.md": rules(("pinned-rule", "It holds, edited.", "app", False),
                                                       ("new-host-rule", "New.", "app", False))})
    out = drift(host, "--no-fetch")
    assert out.returncode == 1
    lines = reports(out)
    assert any(l.startswith("CHANGED  rule pinned-rule: since ") for l in lines), lines
    assert any(l.startswith("NEW      rule new-host-rule: Host app") for l in lines), lines
    assert len(lines) == 2


def test_retiring_a_pinned_rule_reports_changed(tmp):
    research = research_repo(tmp, [("pinned-rule", "It holds.", "app", False)])
    host = pin_all(tmp, research, ["d-one"], ["pinned-rule"])
    commit(research, {"research/domain-rules.md": rules(("pinned-rule", "It holds.", "app", True))})
    lines = reports(drift(host, "--no-fetch"))
    assert len(lines) == 1 and lines[0].startswith("CHANGED  rule pinned-rule")


def test_a_deleted_rule_reports_missing_and_a_pending_rule_pending(tmp):
    research = research_repo(tmp, [("pinned-rule", "It holds.", "app", False)])
    host = pin_all(tmp, research, ["d-one"], ["pinned-rule"])
    text = (host / "docs/research-lock.md").read_text(encoding="utf-8")
    text = text.replace("| src/x.py |", "| src/x.py |", 1) + "| later-rule | pending https://example.invalid/pull/2 |  | src/y.py | 2026-10-09 |\n"
    write(host, {"docs/research-lock.md": text})
    commit(research, {"research/domain-rules.md": rules()})
    lines = reports(drift(host, "--no-fetch"))
    assert any(l.startswith("MISSING  rule pinned-rule: not in research/domain-rules.md") for l in lines), lines
    assert "PENDING  rule later-rule: pending https://example.invalid/pull/2" in lines


# ---------- decision reports ----------

def test_every_decision_report(tmp):
    research = research_repo(tmp, record_text=record(("d-one", "accepted", "[]"), ("d-two", "accepted", "[]")))
    host = pin_all(tmp, research, ["d-one", "d-two"])
    text = (host / "docs/research-lock.md").read_text(encoding="utf-8")
    pending = "| d-three | `research/decisions/later.md` | pending https://example.invalid/pull/1 |  | ticket | 2026-10-09 |\n"
    write(host, {"docs/research-lock.md": text.replace("\n## Pinned rules", pending + "\n## Pinned rules")})
    assert reports(drift(host, "--no-fetch")) == ["PENDING  d-three: pending https://example.invalid/pull/1"]

    commit(research, {"research/decisions/topic-2026-10-01.md": record(
        ("d-one", "accepted", "[]"), ("d-two", "deferred", "[]"), ("d-four", "accepted", "[d-one]"))})
    lines = reports(drift(host, "--no-fetch"))
    assert any(l.startswith("CHANGED  d-two: since ") for l in lines), lines
    assert any(l.startswith("STATUS   d-two: deferred on ") for l in lines), lines
    assert any(l.startswith("SUPERSEDED d-one: by d-four") for l in lines), lines
    assert any(l.startswith("NEW      d-four: accepted on ") for l in lines), lines

    commit(research, {"research/decisions/topic-2026-10-01.md": None})
    lines = reports(drift(host, "--no-fetch"))
    assert any(l.startswith("MISSING  d-one: not in research/decisions/topic-2026-10-01.md") for l in lines), lines
    out = drift(host, "--no-fetch")
    assert out.returncode == 1


def test_every_report_code_is_covered():
    source = Path(__file__).read_text(encoding="utf-8")
    for code in ("PENDING ", "CHANGED ", "SUPERSEDED ", "STATUS ", "MISSING ", "NEW ", "DEPRECATED "):
        assert f'"{code}' in source or f"'{code}" in source, code


# ---------- research = "self" ----------

def test_self(tmp):
    repo = init(tmp / "generalist")
    config = CONFIG.replace('name = "app"', 'name = "generalist"') + '[consumes]\nresearch = "self"\n'
    commit(repo, {"research-agent.toml": config,
                  "research/domain-rules.md": rules(("cli-rule", "The CLI holds.", "generalist", False)),
                  "research/decisions/topic-2026-10-01.md": record(("d-one", "accepted", "[]"))})
    (repo / ".research-agent").mkdir()
    shutil.copy(KIT / "research_drift.py", repo / ".research-agent" / "research_drift.py")
    head = git(repo, "rev-parse", "--short", "HEAD").strip()
    path = "research/decisions/topic-2026-10-01.md"
    write(repo, {"docs/research-lock.md": lock([("d-one", path, head, hash_of(repo, "decision", path, "d-one"))],
                                               [("cli-rule", head, hash_of(repo, "rule", "cli-rule"))])})
    out = drift(repo, "--no-fetch", cwd=repo / "research")  # found by walking up
    assert out.returncode == 0, out.stdout + out.stderr
    commit(repo, {"research/decisions/topic-2026-10-01.md": record(("d-one", "accepted", "[d-zero]"))})
    lines = reports(drift(repo, "--no-fetch"))
    assert len(lines) == 1 and lines[0].startswith("CHANGED  d-one")


# ---------- the legacy fallback ----------

def test_legacy_fallback_reads_docs_research(tmp):
    research = init(tmp / "legacy")
    commit(research, {"docs/research/decisions/r.md": record(("d-one", "accepted", "[]")),
                      "docs/research/domain-rules.md": rules(("a-rule", "Holds.", "app", False))})
    host = host_for(tmp, research)
    head = git(research, "rev-parse", "--short", "HEAD").strip()
    write(host, {"docs/research-lock.md": lock(
        [("d-one", "docs/research/decisions/r.md", head, hash_of(host, "decision", "docs/research/decisions/r.md", "d-one"))],
        [("a-rule", head, hash_of(host, "rule", "a-rule"))])})
    lines = reports(drift(host, "--no-fetch"))
    assert lines[0].startswith("DEPRECATED ") and "reading docs/research/" in lines[0]
    assert lines[1].startswith("No drift")  # no consumer name on legacy, so no NEW rule reports


# ---------- fetching ----------

def test_fetches_the_clone_by_default(tmp):
    upstream = tmp / "upstream.git"
    git(tmp, "init", "-q", "--bare", "-b", "main", str(upstream))
    work = init(tmp / "work")
    commit(work, {"research-agent.toml": CONFIG, "research/domain-rules.md": rules(),
                  "research/decisions/topic-2026-10-01.md": record(("d-one", "accepted", "[]"))}, origin=False)
    git(work, "remote", "add", "origin", str(upstream))
    git(work, "push", "-q", "origin", "main")
    clone = tmp / "research-repo"
    git(tmp, "clone", "-q", str(upstream), str(clone))
    host = pin_all(tmp, clone, ["d-one"])
    assert drift(host).returncode == 0
    commit(work, {"research/decisions/topic-2026-10-01.md": record(("d-one", "deferred", "[]"))}, origin=False)
    git(work, "push", "-q", "origin", "main")
    assert drift(host, "--no-fetch").returncode == 0  # not fetched: still the old main
    lines = reports(drift(host))
    assert any(l.startswith("STATUS   d-one: deferred") for l in lines), lines


# ---------- exit code 2 ----------

def test_setup_errors(tmp):
    research = research_repo(tmp)
    lone = tmp / "lone"
    lone.mkdir()
    shutil.copytree(KIT, lone / ".research-agent", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    assert drift(lone).returncode == 2  # no config anywhere above (tmp has none)

    host = host_for(tmp, research)
    write(host, {"research-agent.toml": REQUIRES + '[project]\nroot = "x"\ndecider = "r"\n'})
    assert "no [consumes]" in drift(host, "--no-fetch").stdout

    host = host_for(tmp, research)
    write(host, {"research-agent.toml": REQUIRES + '[consumes]\nresearch = "owner/nowhere"\n'})
    out = drift(host, "--no-fetch")
    assert out.returncode == 2 and "No clone of owner/nowhere" in out.stdout

    host = host_for(tmp, research)
    out = drift(host, "--no-fetch", "--ref", "origin/nope")
    assert out.returncode == 2
    out = drift(host)  # the test clone has no origin remote to fetch
    assert out.returncode == 2 and "--no-fetch" in out.stdout
    out = drift(host, "--no-fetch", "--hash", "decision", "x.md")
    assert out.returncode == 2
    (host / "docs/research-lock.md").unlink()
    assert drift(host, "--no-fetch").returncode == 2


# ---------- the stamp and --help ----------

def test_kit_files_carry_a_valid_stamp_for_this_version():
    version = json.loads((KIT.parent / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    files = sorted(p for p in KIT.glob("*.*") if p.suffix in (".py", ".md"))
    assert {p.name for p in files} >= {"research_drift.py"}
    for path in files:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        first, rest = text.split("\n", 1)
        match = re.search(r"research-agent (\d+\.\d+\.\d+) sha256:([0-9a-f]{64})", first)
        assert match, f"{path.name}: no stamp; run python tools/stamp_kit.py"
        assert match.group(1) == version, f"{path.name}: stamp {match.group(1)}, plugin {version}; run python tools/stamp_kit.py"
        assert match.group(2) == hashlib.sha256(rest.encode("utf-8")).hexdigest(), \
            f"{path.name}: hash differs from its content; run python tools/stamp_kit.py"


def test_warns_when_its_stamp_is_outside_requires(tmp):
    research = research_repo(tmp)
    host = pin_all(tmp, research, ["d-one"])
    write(host, {"research-agent.toml": (host / "research-agent.toml").read_text(encoding="utf-8")
                 .replace(REQUIRES, 'requires = ">=0.7.0"\n')})
    out = drift(host, "--no-fetch")
    lines = reports(out)
    assert lines[0].startswith("WARN ") and "outside requires" in lines[0]
    assert lines[1].startswith("No drift")
    assert out.returncode == 0


def test_help_explains_every_report_and_its_action(tmp):
    host = make_host(tmp / "h", REQUIRES + APP_CONSUMES)
    out = drift(host, "--help")
    assert out.returncode == 0
    for code in ("No drift", "PENDING", "CHANGED", "SUPERSEDED", "STATUS", "MISSING", "NEW", "DEPRECATED", "WARN"):
        assert f"\n  {code}" in out.stdout, code
    assert out.stdout.count("Action:") >= 7
    for usage in ("--hash decision <record path> <decision-name>", "--hash rule <rule-id>", "--no-fetch", "--ref"):
        assert usage in out.stdout


def test_malformed_research_config_is_a_setup_error(tmp):
    research = research_repo(tmp)
    host = pin_all(tmp, research, ["d-one"])
    commit(research, {"research-agent.toml": "requires = [\n"})
    for args in (("--no-fetch",), ("--no-fetch", "--hash", "decision", "research/decisions/topic-2026-10-01.md", "d-one")):
        out = drift(host, *args)
        assert out.returncode == 2, out.stdout + out.stderr
        assert "research-agent.toml on origin/main does not parse" in out.stdout
        assert "Traceback" not in out.stderr
