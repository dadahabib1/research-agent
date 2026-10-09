"""The doctor: one fixture project per FAIL item, a valid project, the legacy fallback (§3 per-check
table), an equity-shaped project after adoption, and the command line."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import doctor
from conftest import git, stamped, write_kit

DOCTOR = Path(doctor.__file__)


def diagnose(repo: Path, mode: str = "run"):
    report, config_line = doctor.diagnose(repo, mode)
    return report, config_line


def by_check(report) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for level, check, _ in report.items:
        out.setdefault(check, set()).add(level)
    return out


def edit(repo: Path, rel: str, old: str, new: str) -> None:
    path = repo / rel
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert old in text, f"{old!r} not in {rel}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def append(repo: Path, rel: str, text: str) -> None:
    with open(repo / rel, "a", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ---------- the valid project ----------

def test_valid_project_has_no_items(valid):
    report, config_line = diagnose(valid, "run")
    assert report.items == []
    assert config_line == "research-agent.toml"


def test_valid_project_passes_in_setup_mode(valid):
    report, _ = diagnose(valid, "setup")
    assert report.items == []


# ---------- one fixture project per FAIL item ----------

R = "docs/research"
RULES = f"{R}/domain-rules.md"
QUEUE = f"{R}/research-queue.md"
BRIEF = f"{R}/research-brief.md"
RECORD = f"{R}/decisions/first-topic-2026-10-02.md"
INDEX = f"{R}/decisions/INDEX.md"
CONFIG = "research-agent.toml"

FAIL_CASES = {
    # check 1: the config
    "config-does-not-parse": ("1", lambda r: append(r, CONFIG, "\n[project\n")),
    "config-unknown-key": ("1", lambda r: edit(r, CONFIG, 'decider = "requester"', 'decider = "requester"\nhandover = "pr"')),
    "config-unknown-nested-key": ("1", lambda r: edit(r, CONFIG, 'name = "demo-app"', 'name = "demo-app"\nurl = "x"')),
    "config-missing-key": ("1", lambda r: edit(r, CONFIG, 'decider = "requester"\n', "")),
    "config-wrong-type": ("1", lambda r: edit(r, CONFIG, 'env = ["DEMO_API_KEY"]', 'env = "DEMO_API_KEY"')),
    "config-requires-excludes-installed": ("1", lambda r: edit(r, CONFIG, '">=0.6.0, <0.7.0"', '"<0.6.0"')),
    "config-requires-malformed": ("1", lambda r: edit(r, CONFIG, '">=0.6.0, <0.7.0"', '"~0.6"')),
    "config-no-tables": ("1", lambda r: (r / CONFIG).write_text('requires = ">=0.6.0"\n', encoding="utf-8")),
    "config-self-without-project": ("1", lambda r: (r / CONFIG).write_text(
        'requires = ">=0.6.0"\n[consumes]\nresearch = "self"\n', encoding="utf-8")),
    "config-research-not-owner-repo": ("1", lambda r: edit(r, CONFIG, 'research = "self"', 'research = "equity"')),
    "no-config-no-prose": ("1", lambda r: ((r / CONFIG).unlink(), (r / "CLAUDE.md").write_text("# x\n", encoding="utf-8"))),
    # check 2: paths
    "missing-root": ("2", lambda r: edit(r, CONFIG, 'root = "docs/research"', 'root = "docs/other"')),
    "missing-brief": ("2", lambda r: (r / BRIEF).unlink()),
    "missing-domain-rules": ("2", lambda r: (r / RULES).unlink()),
    "missing-queue": ("2", lambda r: (r / QUEUE).unlink()),
    "missing-prompts": ("2", lambda r: shutil.rmtree(r / R / "prompts")),
    "missing-logs": ("2", lambda r: shutil.rmtree(r / R / "logs")),
    "missing-index": ("2", lambda r: (r / INDEX).unlink()),
    "missing-consumer-context": ("2", lambda r: (r / R / "consumer-context.md").unlink()),
    "configured-brief-missing": ("2", lambda r: edit(r, CONFIG, 'root = "docs/research"', 'root = "docs/research"\nbrief = "other.md"')),
    # check 3: the brief
    "brief-missing-heading": ("3", lambda r: edit(r, BRIEF, "## 7. Deliverable format", "## Deliverable format")),
    "brief-no-domain-rules-line": ("3", lambda r: edit(r, BRIEF, "Domain rules: `docs/research/domain-rules.md`", "See the rules.")),
    "brief-wrong-domain-rules-path": ("3", lambda r: edit(r, BRIEF, "`docs/research/domain-rules.md`", "`docs/research/rules.md`")),
    # check 4a: domain rules
    "rules-missing-heading": ("4a", lambda r: edit(r, RULES, "## 5. Feasibility", "## Feasibility")),
    "rule-lacks-check": ("4a", lambda r: edit(r, RULES, "- Check: every input names its publication time.\n", "")),
    "rule-lacks-added": ("4a", lambda r: edit(r, RULES, "- Added: 2026-10-01\n- Host", "- Host")),
    "rule-bad-scope": ("4a", lambda r: edit(r, RULES, "- Scope: decision-critical", "- Scope: critical")),
    "rule-bad-added-date": ("4a", lambda r: edit(r, RULES, "- Added: 2026-10-01\n- Host", "- Added: October 2026\n- Host")),
    "rule-id-not-kebab": ("4a", lambda r: edit(r, RULES, "### known-at-publication:", "### Known At Publication:")),
    "rule-duplicate-id": ("4a", lambda r: edit(r, RULES, "### measurements-name-their-sample:", "### known-at-publication:")),
    "rule-host-not-consumer": ("4a", lambda r: edit(r, RULES, "- Host: demo-app", "- Host: other-app")),
    # check 5: the queue
    "queue-missing-column": ("5", lambda r: edit(r, QUEUE, "| Task | Prompt | Deliverable | Prerequisites |", "| Task | Prompt | Deliverable | Needs |")),
    "queue-unknown-status": ("5", lambda r: edit(r, QUEUE, "| requester | todo |", "| requester | started |")),
    "queue-prompt-missing": ("5", lambda r: (r / R / "prompts" / "02-second.md").unlink()),
    "queue-prerequisite-unknown": ("5", lambda r: edit(r, QUEUE, "| first topic |", "| first topics |")),
    # check 6: decision headers and the index
    "decision-header-does-not-parse": ("6", lambda r: edit(r, RECORD, "depends_on: []\nsupersedes: [older-choice]", "depends_on: [\nsupersedes: [older-choice]")),
    "decision-header-lacks-key": ("6", lambda r: edit(r, RECORD, "decided_by: requester\ndepends_on: []\nsupersedes: [older-choice]", "depends_on: []\nsupersedes: [older-choice]")),
    "decision-header-bad-status": ("6", lambda r: edit(r, RECORD, "status: accepted", "status: approved")),
    "decision-name-differs-from-heading": ("6", lambda r: edit(r, RECORD, "name: first-choice", "name: first-choise")),
    "decision-without-header": ("6", lambda r: (r / R / "decisions" / "second-2026-10-03.md").write_text(
        "# Decision record\n\n## Decisions\n\n### lone-choice: no header\n\n- **Status:** accepted\n", encoding="utf-8")),
    "index-status-mismatch": ("6", lambda r: edit(r, INDEX, "| first-choice | accepted |", "| first-choice | deferred |")),
    "index-row-without-decision": ("6", lambda r: append(r, INDEX, "| ghost-choice | accepted | 2026-10-02 | x.md | none |\n")),
    "decision-without-index-row": ("6", lambda r: edit(r, INDEX, "| older-choice | superseded | 2026-09-01 | first-topic-2026-10-02.md | none |\n", "")),
    # check 7: the CLAUDE.md pointer
    "claude-md-no-pointer": ("7", lambda r: (r / "CLAUDE.md").write_text("# Demo\n", encoding="utf-8")),
    # check 8: the kit and the lock
    "kit-file-missing": ("8", lambda r: (r / ".research-agent" / "research_drift.py").unlink()),
    "kit-file-edited": ("8", lambda r: append(r, ".research-agent/INTEGRATION.md", "a local edit\n")),
    "kit-file-unstamped": ("8", lambda r: (r / ".research-agent" / "INTEGRATION.md").write_text("no stamp\n", encoding="utf-8")),
    "kit-version-outside-requires": ("8", lambda r: (r / ".research-agent" / "INTEGRATION.md").write_text(
        stamped("old kit\n", "0.5.0"), encoding="utf-8", newline="\n")),
    "lock-missing": ("8", lambda r: (r / "docs" / "research-lock.md").unlink()),
    "lock-missing-rules-table": ("8", lambda r: edit(r, "docs/research-lock.md", "| Rule | Research commit |", "| Pinned | Research commit |")),
    "lock-bad-hash": ("8", lambda r: edit(r, "docs/research-lock.md", "0123456789ab", "0123")),
    "lock-short-row": ("8", lambda r: append(r, "docs/research-lock.md", "| extra-rule | abc1234 |\n")),
    # check 9: the identity map, at /run-next-task step 0
    "identity-map-differs": ("9", lambda r: edit(r, CONFIG, '"example.gov" = "DEMO_IDENTITY"', '"example.org" = "DEMO_IDENTITY"')),
    "identity-variable-unset": ("9", lambda r: edit(r, CONFIG, '"example.gov" = "DEMO_IDENTITY"', '"example.gov" = "DEMO_IDENTITY_2"\n"example.net" = "DEMO_IDENTITY"')),
}


@pytest.mark.parametrize("case", sorted(FAIL_CASES))
def test_each_fail_item(valid, case):
    check, mutate = FAIL_CASES[case]
    mutate(valid)
    report, _ = diagnose(valid, "run")
    assert "FAIL" in by_check(report).get(check, set()), report.items
    others = {c for lvl, c, _ in report.items if lvl == "FAIL"} - {check}
    # a missing file may also be reported by the check that reads it; a range that excludes the
    # installed version also excludes the kit's stamp; nothing else may fail
    allowed = {"missing-index": {"6"}, "missing-prompts": {"5"},
               "config-requires-excludes-installed": {"8"}}.get(case, set())
    assert others <= allowed, report.items


def test_fail_items_cover_every_fail_check():
    assert {check for check, _ in FAIL_CASES.values()} == {"1", "2", "3", "4a", "5", "6", "7", "8", "9"}


# ---------- WARN and DEPRECATED items ----------

def test_identity_check_warns_in_setup_mode(valid, monkeypatch):
    monkeypatch.delenv("DEMO_IDENTITY")
    monkeypatch.setenv("FETCH_RAW_IDENTITY_HOSTS", "sec.gov=EDGAR_IDENTITY")
    report, _ = diagnose(valid, "setup")
    assert by_check(report) == {"9": {"WARN"}}
    run, _ = diagnose(valid, "run")
    assert by_check(run) == {"9": {"FAIL"}}


def test_identity_map_matches_whatever_the_case_and_order(valid, monkeypatch):
    edit(valid, CONFIG, '"example.gov" = "DEMO_IDENTITY"', '"Example.gov." = "DEMO_IDENTITY"\n"b.org" = "DEMO_API_KEY"')
    monkeypatch.setenv("FETCH_RAW_IDENTITY_HOSTS", " b.org=DEMO_API_KEY , example.gov=DEMO_IDENTITY")
    report, _ = diagnose(valid, "run")
    assert report.items == []


def test_undeclared_identity_map_warns(valid):
    edit(valid, CONFIG, '[project.fetch_identity]\n"example.gov" = "DEMO_IDENTITY"\n', "")
    report, _ = diagnose(valid, "run")
    assert by_check(report) == {"9": {"WARN"}}


def test_env_name_unset_warns_and_names_no_value(valid, monkeypatch):
    monkeypatch.delenv("DEMO_API_KEY")
    report, _ = diagnose(valid, "run")
    assert by_check(report) == {"10": {"WARN"}}
    assert "DEMO_API_KEY" in report.items[0][2]


def test_output_never_prints_environment_values(valid, monkeypatch, capsys):
    monkeypatch.setenv("FETCH_RAW_IDENTITY_HOSTS", "example.gov=SECRET_HOLDER")
    monkeypatch.setenv("SECRET_HOLDER", "value-that-must-not-print")
    monkeypatch.setenv("DEMO_IDENTITY", "another-value-that-must-not-print")
    code = doctor.main(["--mode", "run", "--project", str(valid)])
    out = capsys.readouterr().out
    assert code == 1
    assert "must-not-print" not in out


def test_gitignore_lines_warn(valid):
    (valid / ".gitignore").unlink()
    report, _ = diagnose(valid, "run")
    assert by_check(report) == {"11": {"WARN"}}
    assert len(report.items) == 2


def test_bullet_rules_are_deprecated_with_config(valid):
    edit(valid, RULES, "## 3. Standard methods to reuse\n\nnone known", "## 3. Standard methods to reuse\n\n- Use the standard method. Check: it is cited.")
    report, _ = diagnose(valid, "run")
    assert by_check(report) == {"4b": {"DEPRECATED"}}


def test_fenced_and_quoted_examples_are_not_rules(valid):
    edit(valid, RULES, "## 4. Units, denominators and bases\n\nnone known",
         "## 4. Units, denominators and bases\n\n> ILLUSTRATIVE:\n>\n> ### Bad Id: example\n> - Check: x\n\n"
         "```markdown\n### also-bad: no fields\n- an example bullet\n```\n\nnone known")
    report, _ = diagnose(valid, "run")
    assert report.items == []


def test_consumer_context_older_than_release_tag_warns(tmp_path, monkeypatch):
    research = tmp_path / "research"
    research.mkdir()
    (research / "research-agent.toml").write_text(
        'requires = ">=0.6.0"\n[project]\nroot = "docs/research"\ndecider = "requester"\n'
        '[project.consumer]\nname = "app"\ncontext = "app-context.md"\n', encoding="utf-8")
    (research / "docs" / "research").mkdir(parents=True)
    (research / "docs" / "research" / "app-context.md").write_text("- As of: 2026-01-15, app commit x\n", encoding="utf-8")
    git(research, "init", "-q", "-b", "main")
    git(research, "add", "-A")
    git(research, "commit", "-q", "-m", "research")
    git(research, "update-ref", "refs/remotes/origin/main", "HEAD")

    host = tmp_path / "app"
    host.mkdir()
    (host / "research-agent.toml").write_text(
        f'requires = ">=0.6.0, <0.7.0"\n[consumes]\nresearch = "owner/research"\n', encoding="utf-8")
    (host / "CLAUDE.md").write_text("Research: `research-agent.toml`\n", encoding="utf-8")
    (host / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    (host / "docs").mkdir()
    shutil.copy(Path(__file__).parent / "fixtures" / "valid" / "docs" / "research-lock.md", host / "docs")
    write_kit(host, doctor.installed_version())
    dated = {"GIT_COMMITTER_DATE": "2026-03-01T12:00:00Z", "GIT_AUTHOR_DATE": "2026-03-01T12:00:00Z"}
    git(host, "init", "-q", "-b", "main")
    git(host, "add", "-A")
    git(host, "commit", "-q", "-m", "app", env=dated)
    git(host, "tag", "v1.0.0", env=dated)

    report, _ = diagnose(host, "run")
    assert by_check(report) == {"12": {"WARN"}}, report.items
    assert "2026-01-15" in report.items[0][2] and "v1.0.0" in report.items[0][2]

    (research / "docs" / "research" / "app-context.md").write_text("- As of: 2026-03-02\n", encoding="utf-8")
    git(research, "commit", "-q", "-am", "context")
    git(research, "update-ref", "refs/remotes/origin/main", "HEAD")
    report, _ = diagnose(host, "run")
    assert report.items == []


def test_consumer_without_clone_warns(tmp_path):
    host = tmp_path / "app"
    host.mkdir()
    (host / "research-agent.toml").write_text('requires = ">=0.6.0, <0.7.0"\n[consumes]\nresearch = "owner/nowhere"\n', encoding="utf-8")
    (host / "CLAUDE.md").write_text("`research-agent.toml`\n", encoding="utf-8")
    (host / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    (host / "docs").mkdir()
    shutil.copy(Path(__file__).parent / "fixtures" / "valid" / "docs" / "research-lock.md", host / "docs")
    write_kit(host, doctor.installed_version())
    git(host, "init", "-q", "-b", "main")
    git(host, "add", "-A")
    git(host, "commit", "-q", "-m", "app")
    git(host, "tag", "v1.0.0")
    report, _ = diagnose(host, "run")
    assert by_check(report) == {"12": {"WARN"}}


# ---------- legacy fallback: equity_research at 2712374 (§3 per-check table) ----------

def test_equity_2712374_passes_on_legacy_fallback(equity, monkeypatch):
    monkeypatch.setenv("FETCH_RAW_IDENTITY_HOSTS", "sec.gov=WRONG")  # n/a on legacy: no map to compare
    report, config_line = diagnose(equity, "run")
    assert config_line == doctor.LEGACY_LINE
    assert by_check(report) == {"1": {"DEPRECATED"}, "4b": {"DEPRECATED"}, "7": {"DEPRECATED"}, "11": {"WARN"}}


def test_equity_legacy_reads_the_prose_paths(equity):
    layout = doctor.legacy_layout((equity / "CLAUDE.md").read_text(encoding="utf-8"))
    assert layout.brief == "docs/research/strategy-research-brief.md"
    assert layout.rules == "docs/research/domain-rules.md"
    assert layout.queue == "docs/research/research-queue.md"
    assert layout.decisions == "docs/research/decisions"
    assert layout.prompts == "docs/research/prompts"
    assert layout.logs == "docs/research/logs"
    assert layout.context == "docs/research/app-context.md"
    assert layout.root == "docs/research"


E = "docs/research"
LEGACY_FAIL_CASES = {
    "2-prose-path-missing": ("2", lambda r: (r / E / "app-context.md").unlink()),
    "3-brief-heading": ("3", lambda r: edit(r, f"{E}/strategy-research-brief.md", "## 8. Open inputs", "## Open inputs")),
    "4a-bad-rule": ("4a", lambda r: append(r, f"{E}/domain-rules.md", "\n### Bad Rule: no fields\n")),
    "5-queue-prerequisite": ("5", lambda r: edit(r, f"{E}/research-queue.md", "| validation ladder |", "| validation ladders |")),
    "6-index-status": ("6", lambda r: edit(r, f"{E}/decisions/INDEX.md", "| known-from-rule | accepted |", "| known-from-rule | deferred |")),
}


@pytest.mark.parametrize("case", sorted(LEGACY_FAIL_CASES))
def test_legacy_checks_2_to_6_still_fail(equity, case):
    check, mutate = LEGACY_FAIL_CASES[case]
    mutate(equity)
    report, _ = diagnose(equity, "run")
    assert "FAIL" in by_check(report).get(check, set()), report.items


def test_legacy_has_no_kit_identity_or_context_checks(equity, monkeypatch):
    monkeypatch.setenv("FETCH_RAW_IDENTITY_HOSTS", "sec.gov=EDGAR_IDENTITY")
    report, _ = diagnose(equity, "setup")
    assert not {"8", "9", "10", "12"} & set(by_check(report))


# ---------- equity after adoption (§2 config): passes with DEPRECATED bullet rules ----------

EQUITY_CONFIG = '''requires = ">=0.6.0, <0.7.0"

[project]
root = "docs/research"
brief = "strategy-research-brief.md"
decider = "requester"
env = ["EDGAR_IDENTITY", "FRED_API_KEY"]

[project.consumer]
name = "equity_analyst_v2"
context = "app-context.md"

[project.fetch_identity]
"sec.gov" = "EDGAR_IDENTITY"

[project.run_defaults]
effort = "xhigh"
'''


@pytest.fixture
def adopted(equity):
    (equity / "research-agent.toml").write_text(EQUITY_CONFIG, encoding="utf-8")
    edit(equity, "CLAUDE.md", "## Research\n", "## Research\n\nResearch config: `research-agent.toml`.\n")
    (equity / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    return equity


def test_equity_adopted_passes_with_deprecated_bullet_rules(adopted, monkeypatch):
    monkeypatch.setenv("FETCH_RAW_IDENTITY_HOSTS", "sec.gov=EDGAR_IDENTITY")
    monkeypatch.setenv("EDGAR_IDENTITY", "name contact")
    monkeypatch.setenv("FRED_API_KEY", "k")
    report, config_line = diagnose(adopted, "run")
    assert config_line == "research-agent.toml"
    assert by_check(report) == {"4b": {"DEPRECATED"}}


def test_equity_adopted_setup_on_a_machine_without_the_secret(adopted):
    report, _ = diagnose(adopted, "setup")
    assert by_check(report) == {"4b": {"DEPRECATED"}, "9": {"WARN"}, "10": {"WARN"}}
    run, _ = diagnose(adopted, "run")
    assert by_check(run) == {"4b": {"DEPRECATED"}, "9": {"FAIL"}, "10": {"WARN"}}


def test_equity_adopted_with_rule_ids_and_host_line(adopted, monkeypatch):
    monkeypatch.setenv("FETCH_RAW_IDENTITY_HOSTS", "sec.gov=EDGAR_IDENTITY")
    monkeypatch.setenv("EDGAR_IDENTITY", "name contact")
    monkeypatch.setenv("FRED_API_KEY", "k")
    rules = adopted / E / "domain-rules.md"
    lines = rules.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    out, n, heading = [], 0, None
    for line in lines:
        if line.startswith("## "):
            heading = line
        if heading and line.startswith("- ") and heading[3].isdigit():
            n += 1
            rule, _, check = line[2:].partition(" Check: ")
            out += [f"### rule-{n}: {rule}", f"- Check: {check or 'n/a'}", "- Scope: decision-critical",
                    "- Source: requester, 2026-10-07", "- Added: 2026-10-07"]
            if "trust tier" in rule:
                out.append("- Host: equity_analyst_v2")
        else:
            out.append(line)
    rules.write_text("\n".join(out), encoding="utf-8")
    report, _ = diagnose(adopted, "run")
    assert report.items == []


# ---------- the command line ----------

def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(DOCTOR), *args], capture_output=True, text=True)


def test_cli_exit_codes(valid, equity, tmp_path):
    assert run_cli("--mode", "setup", "--project", str(equity)).returncode == 0
    (valid / "CLAUDE.md").write_text("# Demo\n", encoding="utf-8")
    failed = run_cli("--mode", "setup", "--project", str(valid))
    assert failed.returncode == 1
    assert "FAIL       7" in failed.stdout
    assert run_cli("--mode", "run", "--project", str(tmp_path / "nowhere")).returncode == 2


def test_cli_requires_a_mode():
    assert run_cli().returncode == 2


def test_help_lists_every_check():
    out = run_cli("--help").stdout
    for check in ("1 ", "2 ", "3 ", "4a", "4b", "5 ", "6 ", "7 ", "8 ", "9 ", "10", "11", "12"):
        assert f"\n  {check}" in out


def test_version_ranges():
    assert doctor.in_range("0.6.0", ">=0.6.0, <0.7.0")
    assert doctor.in_range("0.6.3", ">=0.6.0,<0.7.0")
    assert not doctor.in_range("0.7.0", ">=0.6.0, <0.7.0")
    assert not doctor.in_range("0.6.0", "<0.6.0")
    assert doctor.in_range("0.6.0", "==0.6.0")
    assert doctor.in_range("1.10.0", ">1.9.9")
    with pytest.raises(ValueError):
        doctor.in_range("0.6.0", "^0.6")


def test_the_plugins_own_kit_passes_check_8(valid):
    kit = Path(doctor.__file__).resolve().parents[1] / "kit"
    for name in doctor.KIT_FILES:
        shutil.copy(kit / name, valid / ".research-agent" / name)
    report, _ = diagnose(valid, "run")
    assert report.items == []


def test_a_project_written_from_the_templates_passes(tmp_path):
    """New mode's files, with only the placeholders setup fills, give no FAIL."""
    templates = Path(doctor.__file__).resolve().parents[1] / "skills" / "new-research-project" / "templates"
    repo, root = tmp_path / "fresh", tmp_path / "fresh" / "docs" / "research"
    for folder in ("prompts", "logs", "decisions", "templates"):
        (root / folder).mkdir(parents=True)

    def place(name: str, dest: Path, **values: str) -> None:
        text = (templates / name).read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace(key, value)
        dest.write_text(text, encoding="utf-8")

    config = (templates / "research-agent.toml").read_text(encoding="utf-8")
    config = config.split("[consumes]")[0].replace("<who accepts, rejects or defers decisions, for example requester>", "requester")
    config = config.replace('name = "<consumer name>"', 'name = "demo"')
    (repo / "research-agent.toml").write_text(config, encoding="utf-8")
    place("brief.md", root / "research-brief.md", **{"<root>": "docs/research"})
    place("domain-rules.md", root / "domain-rules.md")
    place("queue.md", root / "research-queue.md")
    place("decision-index.md", root / "decisions" / "INDEX.md")
    place("consumer-context.md", root / "consumer-context.md")
    place("prompt.md", root / "templates" / "prompt.md")
    (repo / "CLAUDE.md").write_text("## Research\n\nResearch config: `research-agent.toml`.\n", encoding="utf-8")
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    report, _ = diagnose(repo, "setup")
    assert report.items == [], report.items
