"""The config validator's rules, one test per mistake a person or session makes in the config (C3).

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
The real path (install, the command line, encodings, Windows paths) is agent-kit's end-to-end test
(decision 105); these cover the rules that test does not reach.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent  # .agents/kit
ROOT = KIT.parent.parent  # template/ in agent-kit, the project root in a project
sys.path.insert(0, str(KIT / "bin"))  # C1 section 2: imports by __file__ under -I

import kitconfig  # noqa: E402


class Project(unittest.TestCase):
    """A scratch project: schema, the kit's .gitignore block, a git repo, both files rendered."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.p = self.tmp / "proj"
        (self.p / ".agents/kit/config").mkdir(parents=True)
        shutil.copy(KIT / "config/schema.toml", self.p / ".agents/kit/config/schema.toml")
        shutil.copy(ROOT / ".gitignore", self.p / ".gitignore")
        subprocess.run(["git", "init", "-q", str(self.p)], check=True)
        self.write("agent-kit.toml", self.render("project", "project.name='sandbox'"))
        self.write("agent-kit.local.toml", self.render("local", "reviewer_home='C:/kit/state/codex-reviewer-home'"))

    def render(self, which, *sets):
        text, problems = kitconfig.render(self.p, which, list(sets))
        self.assertEqual(problems, [])
        return text

    def write(self, name, text):
        (self.p / name).write_text(text, encoding="utf-8")

    def edit(self, name, old, new):
        path = self.p / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def problems(self):
        return [str(p) for p in kitconfig.check(self.p)]

    def assertReported(self, *fragments):
        found = self.problems()
        for fragment in fragments:
            self.assertTrue(any(fragment in p for p in found), f"{fragment!r} not in {found}")


class TestRender(Project):
    def test_render_parses_for_any_key_order(self):
        """Issue #57: a project key with no dot, and a key whose section appears earlier in the schema, made
        `render` write TOML that does not parse (` = 1`, and a second `[project]` table). A kit release that
        adds such a key would hand every install a broken file."""
        schema = self.p / ".agents/kit/config/schema.toml"
        schema.write_text(schema.read_text(encoding="utf-8") + '''
[key."standalone"]
file = "project"
type = "integer"
default = 1
labels = ["judgment"]
doc = "A project setting with no section."
added_in = "v0.1.0"

[key."project.late"]
file = "project"
type = "integer"
default = 2
labels = ["judgment"]
doc = "A project setting listed after other sections."
added_in = "v0.1.0"
''', encoding="utf-8")
        # The real command, as an install or a person runs it; its output saved, then read back from disk.
        cli = [sys.executable, "-I", str(KIT / "bin/kitconfig.py")]
        r = subprocess.run(cli + ["render", "project", "--project", str(self.p), "--set", "project.name='sandbox'"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.write("agent-kit.toml", r.stdout)
        with open(self.p / "agent-kit.toml", "rb") as f:
            data = kitconfig.tomllib.load(f)
        self.assertEqual((data["standalone"], data["project"]["late"], data["project"]["name"]), (1, 2, "sandbox"))
        r = subprocess.run(cli + ["check", "--project", str(self.p)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestRules(Project):
    def test_unknown_or_misplaced_keys(self):  # V2
        self.edit("agent-kit.toml", 'builder.effort = "xhigh"', 'builder.efort = "xhigh"')
        self.edit("agent-kit.toml", "[tickets]", "[tickets.typo]\n[tickets]")
        self.edit("agent-kit.local.toml", "memory_floor_gb", "[tickets]\nstacking = false\nmemory_floor_gb")
        self.assertReported(
            "agent-kit.toml: sessions.builder.efort: unknown setting; valid: sessions.builder.effort",
            "agent-kit.toml: tickets.typo: unknown setting",
            "agent-kit.local.toml: tickets.stacking: belongs in agent-kit.toml")

    def test_wrong_types_and_values_are_all_reported(self):  # V3, V4, every problem not only the first
        self.edit("agent-kit.toml", "auto_merge = false", "auto_merge = {}")
        self.edit("agent-kit.toml", "max_builders = 1", "max_builders = 0")
        self.edit("agent-kit.toml", 'orchestrator.effort = "high"', 'orchestrator.effort = "extreme"')
        self.edit("agent-kit.toml", '"docs/spec/**"', '"C:/outside/**"')
        self.assertReported("tickets.auto_merge:", "sessions.max_builders:", "sessions.orchestrator.effort:",
                            "tickets.your_paths:")

    def test_rules_across_keys(self):  # V5, V6, V7, V10
        self.edit("agent-kit.toml", 'engine = "codex"', 'engine = "claude"')
        self.edit("agent-kit.toml", "builder.warn = 50", "builder.warn = 55")
        self.edit("agent-kit.toml", "lower_effort_at = 80", "lower_effort_at = 96")
        self.edit("agent-kit.toml", "enabled = []", 'enabled = ["research"]')
        self.assertReported("reviewer.model:", "context.builder.warn:", "usage.lower_effort_at:", "modules.enabled:")

    def test_reviewer_checkouts_are_two_distinct_places(self):  # V8, as Windows compares them
        base = (self.p / "agent-kit.local.toml").read_text(encoding="utf-8")
        outside = (self.tmp / "checkouts").as_posix()  # outside the project, so V9 has nothing to say
        for same in ("/CODEX", "/codex."):  # Windows ignores case and a trailing dot
            with self.subTest(same=same):
                self.write("agent-kit.local.toml", base)
                self.edit("agent-kit.local.toml", '["codex", "codex-b"]', f'["{outside}/codex", "{outside}{same}"]')
                self.assertReported("reviewer_checkouts: ", "is not two distinct checkouts")

    def test_folders_inside_the_project_are_ignored_and_secrets_untracked(self):  # V9
        self.edit("agent-kit.local.toml", 'coordination = ".coordination"', 'coordination = "coord"')
        (self.p / ".env").write_text("KEY=1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.p), "add", "-f", ".env"], check=True)
        self.assertReported("coordination: coord is inside the project but git does not ignore it",
                            "secret_files: .env is tracked by git")

    def test_a_non_ascii_folder_that_git_ignores_passes(self):  # V9 reads git's output NUL-separated
        with open(self.p / ".gitignore", "a", encoding="utf-8") as f:
            f.write("/koordinasyon-ş/\n")
        self.edit("agent-kit.local.toml", 'coordination = ".coordination"', 'coordination = "koordinasyon-ş"')
        self.assertEqual(self.problems(), [])

    def test_required_settings(self):  # V11
        self.edit("agent-kit.toml", 'name = "sandbox"', "")
        self.assertReported("agent-kit.toml: project.name: required setting is not set")

    def test_dotted_inline_and_table_forms_are_the_same_key(self):
        for form in ('sessions.builder.effort = "medium"', '[sessions]\nbuilder = { effort = "medium" }',
                     '[sessions.builder]\neffort = "medium"'):
            with self.subTest(form=form):
                self.write("agent-kit.toml", 'project.name = "sandbox"\n' + form + "\n")
                values = kitconfig.effective(self.p)
                self.assertEqual(values["sessions.builder.effort"], ("medium", "agent-kit.toml"))

    def test_effective_refuses_a_bad_config(self):  # the launch script starts no session on this (C3 section 4)
        self.edit("agent-kit.toml", "max_builders = 1", "max_builders = 0")
        with self.assertRaises(kitconfig.ConfigError) as caught:
            kitconfig.effective(self.p)
        self.assertTrue(any(p.key == "sessions.max_builders" for p in caught.exception.problems))

    def test_set_refuses_bare_words_unknown_keys_and_repeats(self):
        for sets, fragment in ((["project.name=sandbox"], "is not one TOML value"),
                               (["no.such=1"], "not a setting of agent-kit.toml"),
                               (["project.name='a'", "project.name='b'"], "set twice")):
            with self.subTest(sets=sets):
                _, problems = kitconfig.render(self.p, "project", sets)
                self.assertTrue(any(fragment in str(p) for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
