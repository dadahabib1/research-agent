"""The review script's isolation parse on a captured render (contract C7 section 12, the one unit row): cases
the end-to-end tests cannot reach cheaply, since planting a user skill named like a bundled one would shadow
that bundled skill in your own profile, and a plugin's skill is one no fake renders. The real path is
agent-kit's tests/test_review_e2e.py (fakes; also the AGENTS.md check, CRLF included) and
tests/test_live_review.py (the real `codex debug prompt-input`).

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "bin"))
sys.path.insert(0, str(KIT / "hooks"))

import review  # noqa: E402

HOME = Path("C:/kit/state/codex-reviewer-home") if sys.platform == "win32" else Path("/kit/state/codex-reviewer-home")
USER = Path("C:/Users/u/.agents/skills") if sys.platform == "win32" else Path("/home/u/.agents/skills")


def captured(co: Path) -> list:
    """`codex debug prompt-input`'s shape as rendered 2026-10-17 by Codex 0.162.1 (M96), cut to a few skills:
    the roots table and one line per skill ending `(file: rN/<dir>/SKILL.md)`."""
    skills = (
        "<skills_instructions>\n## Skills\nA skill is a set of local instructions to follow that is stored in a "
        "`SKILL.md` file. Below is the list of skills that can be used.\n### Skill roots\n"
        f"- `r0` = `{USER.as_posix()}`\n- `r1` = `{(HOME / 'skills/.system').as_posix()}`\n"
        f"- `r2` = `{(co / '.agents/skills').as_posix()}`\n"
        f"- `r3` = `{(HOME.parent / 'plugins/cache/work-pets/skills').as_posix()}`\n"
        "### Available skills\n"
        "- skill-creator: Create or update a Codex skill with appropriately scoped instructions. (file: r1/skill-creator/SKILL.md)\n"
        "- imagegen: Generate or edit raster images (photos: illustrations). (file: r1/imagegen/SKILL.md)\n"
        "- skill-creator: Create new skills, modify and improve existing skills. (file: r0/skill-creator/SKILL.md)\n"
        "- tdd: Test-driven development. Use when the user wants (file: x) integration tests. (file: r0/tdd/SKILL.md)\n"
        "- review: The project's review skill. (file: r2/review/SKILL.md)\n"
        "- work-pets:create-pet: Create a pet: any kind. (file: r3/create-pet/SKILL.md)\n"
        "</skills_instructions>")
    return [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": skills}]}]


class IsolationParse(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.co = self.tmp / "codex"
        (self.co / ".agents/skills").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_user_skill_named_like_a_bundled_one_and_a_plugin_skill_are_turned_off(self):
        """Allowed by name and source together: your skill-creator is not the bundled one. A plugin's skill
        keeps its colon (PR #82 review round 1: a name cut at the first colon was never seen at all)."""
        parsed = review.parse_render(captured(self.co))
        self.assertEqual(len(parsed["skills"]), 6, parsed)
        left = review.not_allowed(parsed["skills"], self.co, HOME, {("skill-creator", ".system"), ("imagegen", ".system")})
        self.assertEqual(sorted(n for n, _ in left), ["skill-creator", "tdd", "work-pets:create-pet"])


KINDS = KIT / "review" / "kinds.toml"
# One path per kind and shape, as design 2.1's table names them (agent-kit's) and as an installed project has them.
EXPECTED = {
    "docs/plans/2026-11-08-review-test-design.md": ["Other shared docs"],
    "docs/guide.md": ["Other shared docs"],
    "docs/reference/commands.md": ["Other shared docs", "Docs the two docs tests read"],
    "KIT-SHAPE.md": ["Docs the two docs tests read"],
    "tools/compare_runs.py": ["Pure logic in a script"],
    "tools/setup.py": ["Pure logic in a script", "A script driving git, Claude, Codex or files"],
    ".agents/kit/bin/tick.py": ["Pure logic in a script", "A script driving git, Claude, Codex or files"],
    "template/.agents/kit/bin/review.py": ["Pure logic in a script", "A script driving git, Claude, Codex or files",
                                           "The guard or a control path"],
    "template/.agents/skills/review/kit-standard.md": ["A step the model decides"],
    ".claude/skills/builder/SKILL.md": ["A step the model decides"],
    ".agents/kit/hooks/guard.py": ["The guard or a control path"],
    "tests/map.toml": ["The guard or a control path", "Tests only"],
    "tests/test_review_e2e.py": ["Tests only"],
    "template/.agents/kit/tests/test_review.py": ["Tests only"],
    "src/app.py": ["unclassified"],
}


class Kinds(unittest.TestCase):
    """The kind of each changed path, read from the path (design 2.1): pure logic, so a unit test. The real path,
    the list in the reviewer's prompt and the review record, is agent-kit's tests/test_review_map_e2e.py."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_shipped_file_gives_each_path_every_kind_its_globs_match(self):
        """A glob missing or mistyped in the shipped file hides a kind's checks from every review; a classifier
        keeping only the first match drops review.py's control-path row; an unmatched path must stay listed."""
        kinds = review.load_kinds(KINDS)
        self.assertEqual([k["n"] for k in kinds], list(range(1, 10)))
        got = {e["path"]: e["kinds"] for e in review.kinds_of(EXPECTED, kinds)}
        self.assertEqual(got, EXPECTED)

    def test_the_core_kind_takes_the_test_maps_core_list(self):
        """Design 2.4: the core list lives in the test map only; a copy here would drift from it."""
        kinds = review.load_kinds(KINDS)
        got = review.kinds_of(["conftest.py", "tests/conftest.py", "copier.yml"], kinds,
                              core=("conftest.py", "tests/conftest.py"))
        self.assertEqual([e["kinds"] for e in got], [["A core file"], ["unclassified"], ["A core file", "Tests only"]])

    def test_a_broken_kinds_file_is_refused_with_every_problem(self):
        """Fail closed: a file that half loads would classify nothing and the reviewer would never be told."""
        bad = self.tmp / "kinds.toml"
        bad.write_text('format = "review-kinds"\nversion = 2\nextra = 1\n\n[[kind]]\nn = 1\nname = "A"\n'
                       'paths = ["/abs/**", "docs\\\\x"]\nproject = "docs/**"\ncolour = "red"\n\n[[kind]]\nn = 1\n'
                       'name = ""\npaths = []\nproject = []\n', encoding="utf-8")
        with self.assertRaises(review.KindsProblem) as caught:
            review.load_kinds(bad)
        text = str(caught.exception)
        for part in ("version", "extra", "/abs/**", "docs\\x", "kind 1: project", "colour", "twice", "kind 2: name"):
            self.assertIn(part, text)


if __name__ == "__main__":
    unittest.main()
