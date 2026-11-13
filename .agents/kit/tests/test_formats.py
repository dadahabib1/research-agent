"""The role formats (contract C9 sections 1-8) and their check, `formats.py`.

The real path: `formats.py check` run as a command on a folder of files written from the shipped
templates, and on the same files with one planted break each, read back from its output and exit code.
No row restates a format (C9 section 13): the templates and `formats.py` are the format, and these rows
only show the check passes what the templates produce and names each break. C9 section 13's real-output
row (`formats.py check <coordination>` on the folders live runs leave) comes with those runs.

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
"""

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
TEMPLATES = KIT / "templates"
sys.path.insert(0, str(KIT / "bin"))

import formats  # noqa: E402

# Where each template's file lands in the coordination folder (C4's keys), and the values a session
# would write in place of the template's <placeholders>.
PLACES = {
    "brief.md": "briefs/t37.md",
    "message.md": "messages/proj-t37/20261017T102500Z-proj-orch.md",
    "ready.md": "messages/proj-orch/20261017T102000Z-proj-t37.md",
    "blocked.md": "messages/proj-orch/20261017T103000Z-proj-t38.md",
    "escalation.md": "merges/escalation-20261017T110000Z-t37-9f31c2d-0a1b.md",
    "answer.md": "merges/answer-escalation-20261017T110000Z-t37-9f31c2d-0a1b.md",
    "handoff.md": "handoffs/proj-t37-20261017T120000Z.md",
    "state-builder.md": "state/builder-proj-t37.md",
    "state-orchestrator.md": "state/orchestrator.md",
    "tasks.md": "tasks.md",
    "probe.md": "probes/t37-20261017T130000Z.md",
    "steer.md": "steer/proj-t37.md",
}
NOT_FORMATS = {"prose-pr.md"}  # C8 section 11: a PR body's shape (gh pr create --body-file), no coordination file
VALUES = {
    "from": "proj-t37", "to": "proj-orch", "kind": "answer", "ticket": "37", "issue": "37",
    "headline": "t37: a second merge waits on the lock instead of failing",
    "reply_to": "none", "head": "9f31c2d", "branch": "t37", "base_commit": "b1df0ee", "round": "0",
    "effort": "medium", "spec": "docs/specs/merge.md#the-lock @ b1df0ee", "decisions": "45, 67",
    "files": "src/merge.py, tests/test_merge.py", "base": "origin/main", "stacked_on": "none",
    "lower_base_commit": "none", "effort_reason": "the builder default", "trigger": "round-cap",
    "by": "review.py", "review": "review-20261017T105000Z-t37-9f31c2d-3c4d", "verdict": "verdicts/t37/round-4.json",
    "holds": "37, 38", "escalation": "escalation-20261017T110000Z-t37-9f31c2d-0a1b", "answer": "fix",
    "quote": "yes, try the clock fixture once more", "session": "proj-t37", "launch_id":
    "launch-20261017T090000Z-t37-b1df0ee-5e6f", "role": "builder", "reason": "context", "context_percent": "71",
    "stage": "fixing", "waiting_on": "none", "read_through": "20261017T102210Z-proj-orch.md",
    "handoff_read": "none", "steer_ack": "none", "merges_since_start": "2", "usage": "62% (4 minutes old)",
    "sample": "none", "asked_by": "proj-orch", "action": "nudge",
    "lessons": "docs/solutions/logic-errors/merge-lock-held-through-post-run.md", "refresh": "no",
}
TIME = "2026-10-17T10:20:00Z"


def written_from(template: str, coordination: Path) -> Path:
    """The file a session writes from `template`: each <placeholder> value in the front matter filled."""
    path = coordination / PLACES[template]
    lines = (TEMPLATES / template).read_text(encoding="utf-8").splitlines(keepends=True)
    closing = lines.index("---\n", 1)
    for i in range(1, closing):
        key, value = lines[i].rstrip("\n").split(": ", 1)
        if "<" in value:
            value = path.stem if key == "id" else TIME if key.endswith("_at") else VALUES[key]
            lines[i] = f"{key}: {value}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")
    return path


def check(*paths) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(KIT / "bin/formats.py"), "check", *map(str, paths)],
                          capture_output=True, text=True, encoding="utf-8")


def planted(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"{path.name} has no {old!r} to plant a break in")
    path.write_text(text.replace(old, new, count), encoding="utf-8")


class Templates(unittest.TestCase):
    def setUp(self):
        self.coord = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.coord, ignore_errors=True)

    def test_every_format_has_a_template(self):
        """C9 section 1 rule 5: a format with no template is one sessions write from memory. Each format
        the check knows, and each message kind or role with its own fields or sections, has a template that
        names it; and each shipped template has its place here, so the next row writes it."""
        named = set()
        for template in sorted(TEMPLATES.glob("*.md")):
            if template.name in NOT_FORMATS:
                continue
            fields = formats.front_matter(template.read_text(encoding="utf-8"))[0]
            named.add((fields["format"], fields.get(formats.FORMATS[fields["format"]].get("by", ""), "")))
            self.assertIn(template.name, PLACES, f"{template.name} is shipped but no row writes it")
        for name, spec in formats.FORMATS.items():
            if spec.get("c9"):
                self.assertIn(name, {f for f, _ in named}, f"format {name} has no template")
            for value, extra in spec.get("values", {}).items():
                if extra:
                    self.assertIn((name, value), named, f"{name} {spec['by']}: {value} has no template")

    def test_files_written_from_every_template_pass(self):
        """AC1's green half: the check passes what the templates produce, so a session that writes from a
        template is never refused (and the templates match the check)."""
        for template in PLACES:
            written_from(template, self.coord)
        r = check(self.coord)
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        self.assertEqual(r.stdout.strip(), f"{len(PLACES)} files checked, no problems")

    def test_the_review_scripts_raw_files_are_not_checked(self):
        """C7: `reviews/<review id>/` holds a review's raw files (the rendered prompt, the canary's output, the
        triager's input), not C9 formats, so a coordination folder after a review passes (issue #107: every B
        run's report listed them as problems). A broken message beside them still fails."""
        for template in PLACES:
            written_from(template, self.coord)
        raw = self.coord / "reviews" / "review-20261018T063947Z-t37-dc4cf15-b497"
        raw.mkdir(parents=True)
        (raw / "prompt-1.md").write_text("# Review t37\n\nThe rendered prompt.\n", encoding="utf-8")
        (raw / "canary-last.md").write_text("The canary's last output.\n", encoding="utf-8")
        r = check(self.coord)
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        self.assertEqual(r.stdout.strip(), f"{len(PLACES)} files checked, no problems")
        planted(self.coord / PLACES["ready.md"], "<!-- end -->\n", "")
        self.assertEqual(check(self.coord).returncode, 1)
        self.assertEqual(check(self.coord / "reviews").returncode, 0)  # the review folder alone: raw files only
        # A project named review-...: its inboxes are messages, never skipped (PR #108 review r1).
        inbox = self.coord / "messages" / "review-demo-orch"
        inbox.mkdir(parents=True)
        (inbox / "20261018T100000Z-review-demo-t37.md").write_text("---\nformat: message\n---\nbroken\n",
                                                                encoding="utf-8")
        r = check(self.coord / "messages")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("review-demo-orch/20261018T100000Z-review-demo-t37.md: ", r.stdout)

    def test_each_planted_break_is_named_with_exit_1(self):
        """AC1: a file a successor cannot parse is found by the check, one line per problem, each naming
        the file and the problem, so the writer can fix it; a good file beside them is not reported."""
        swap = [("## Prior art", "## Cuts-swap"), ("## Cuts\n", "## Prior art\n"), ("## Cuts-swap", "## Cuts")]
        breaks = {  # name: (template, the (old, new) edits, the problem the line names)
            "nested": ("ready.md", [("effort: medium\n", "effort:\n  asked: medium\n")], "front-matter"),
            "headline": ("ready.md", [(f"headline: {VALUES['headline']}", "headline: " + "x" * 120)], "headline"),
            "missing-section": ("ready.md", [("## Evidence\n", "")], "missing-section"),
            "out-of-order": ("ready.md", swap, "section-order"),
            "no-end-line": ("ready.md", [("<!-- end -->\n", "")], "end-line"),
            "missing-field": ("ready.md", [("head: 9f31c2d\n", "")], "missing-field"),
            "bad-kind": ("ready.md", [("kind: ready\n", "kind: READY\n")], "bad-value"),
            "version-2": ("handoff.md", [("version: 1\n", "version: 2\n")], "bad-value"),
            "id-not-name": ("handoff.md", [("id: proj-t37-20261017T120000Z\n", "id: proj-t37\n")], "id"),
            # the answer record has no body, so every line would read as a field without the closing check
            "unclosed": ("answer.md", [("Z\n---\n", "Z\n")], "front-matter"),
            "no-front-matter": ("brief.md", [("---\nformat: brief\n", "format: brief\n")], "front-matter"),
            "flow-list": ("escalation.md", [("holds: 37, 38\n", "holds: [37, 38]\n")], "front-matter"),
            # C9 section 2: a stacked builder's only pointer to the lower branch's diff (review round 1)
            "stacked-no-section": ("brief.md", [("stacked_on: none\n", "stacked_on: 36\n"), ("## Stacking\n", "")],
                                   "missing-section"),
        }
        # Not problems (review round 1): a `~~~` line inside a backtick evidence block, and an issue quoted
        # in a brief that has its own `## Prior art` heading.
        goods = {
            "good": ("ready.md", []),
            "good-tilde": ("ready.md", [("## Red first\n", "```text\n$ cat out.txt\n~~~\n```\n\n## Red first\n")]),
            "good-quoted-heading": ("brief.md", [("## Spec\n", "## Prior art\n\nthe issue's own heading\n\n## Spec\n")]),
            # review round 2: an unstacked brief (its Stacking section deleted) quoting an issue about stacking
            "good-quoted-stacking": ("brief.md", [("## Stacking\n", ""), ("## Spec\n", "## Stacking\n\nquoted\n\n## Spec\n")]),
        }
        for name, (template, edits, *_) in {**breaks, **goods}.items():
            path = written_from(template, self.coord / name)
            for old, new in edits:
                planted(path, old, new)
        r = check(self.coord)
        self.assertEqual(r.returncode, 1, r.stdout)
        lines = r.stdout.splitlines()
        self.assertFalse([line for line in lines if line.split("/")[0] in goods], r.stdout)
        for name, (template, _, problem) in breaks.items():
            with self.subTest(name):
                where = f"{name}/{PLACES[template]}: {problem}: "
                self.assertTrue([line for line in lines if line.startswith(where)], f"no {where!r} in:\n{r.stdout}")

    def test_one_line_per_problem(self):
        """C9 rule 5: two problems in one file are two lines, so fixing one does not hide the other."""
        path = written_from("ready.md", self.coord)
        planted(path, "head: 9f31c2d\n", "")
        planted(path, "branch: t37\n", "")
        r = check(path)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(sorted(re.findall(r"missing-field: (\w+)", r.stdout)), ["branch", "head"], r.stdout)


class Escalations(unittest.TestCase):
    """AC3: `escalate.py` (a later ticket) checks the record it writes with the same command."""

    def setUp(self):
        self.coord = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.coord, ignore_errors=True)

    def test_the_escalation_and_answer_records_are_checked(self):
        escalation = written_from("escalation.md", self.coord)
        answer = written_from("answer.md", self.coord)
        self.assertEqual(check(escalation).returncode, 0, check(escalation).stdout)
        self.assertEqual(check(answer).returncode, 0, check(answer).stdout)
        planted(escalation, "holds: 37, 38\n", "")
        planted(escalation, "## Options", "## Recommendation-swap")
        planted(escalation, "## Recommendation\n", "## Options\n")
        planted(escalation, "## Recommendation-swap", "## Recommendation")
        planted(answer, "quote: yes, try the clock fixture once more\n", "")
        r = check(self.coord / "merges")
        self.assertEqual(r.returncode, 1, r.stdout)
        for line in (f"{escalation.name}: missing-field: holds", f"{escalation.name}: section-order: ",
                     f"{answer.name}: missing-field: quote"):
            self.assertIn(line, r.stdout)


class MessageReader(unittest.TestCase):
    """AC2, a unit row: the race (a reader listing the inbox while a sender's Write is mid-file) cannot be
    produced on demand live (C9 section 13)."""

    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.inbox, self.scratch = root / "messages/proj-orch", root / "scratch"
        self.inbox.mkdir(parents=True)

    def message(self, name: str, done: bool = True) -> None:
        path = self.inbox / name
        shutil.copy(written_from("ready.md", self.scratch), path)
        if not done:
            planted(path, "<!-- end -->\n", "")

    def test_a_message_still_being_written_is_skipped_and_read_through_stops_before_it(self):
        """The orchestrator must not act on half a READY, and must not lose it: one that sorts earlier
        but finished later is read next turn, not skipped for good."""
        self.message("20261017T100000Z-proj-t36.md")
        self.message("20261017T100100Z-proj-t37.md", done=False)
        self.message("20261017T100200Z-proj-t38.md")
        (self.inbox / "20261017T100300Z-proj-t39.md.tmp-123").write_text("---\n", encoding="utf-8")
        self.assertEqual(formats.readable(self.inbox, "none"),
                         (["20261017T100000Z-proj-t36.md", "20261017T100200Z-proj-t38.md"],
                          "20261017T100000Z-proj-t36.md"))
        self.message("20261017T100100Z-proj-t37.md")  # the sender's write finishes
        self.assertEqual(formats.readable(self.inbox, "20261017T100000Z-proj-t36.md"),
                         (["20261017T100100Z-proj-t37.md", "20261017T100200Z-proj-t38.md"],
                          "20261017T100200Z-proj-t38.md"))
        self.assertEqual(formats.readable(self.inbox, "20261017T100200Z-proj-t38.md"),
                         ([], "20261017T100200Z-proj-t38.md"))

    def test_the_command_prints_the_same(self):
        """Sessions run the reader rule as a command; its output is the function's."""
        self.message("20261017T100000Z-proj-t36.md", done=False)
        self.message("20261017T100100Z-proj-t37.md")
        r = subprocess.run([sys.executable, "-I", str(KIT / "bin/formats.py"), "unread", str(self.inbox), "none"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual((r.returncode, r.stdout), (0, "20261017T100100Z-proj-t37.md\nread_through: none\n"), r.stderr)


if __name__ == "__main__":
    unittest.main()
