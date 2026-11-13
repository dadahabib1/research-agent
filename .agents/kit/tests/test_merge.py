"""The guarded merge's rules a live merge cannot reach cheaply (contract C8 section 14), one row per failure
each catches in real use. The real path, merges through GitHub, is agent-kit's live test
`tests/test_live_merge.py`. These rows use real temporary git repositories and no `gh`:
- head binding's history shapes (section 4): approval reused for unreviewed code, or a clean update refused;
- the earning walk (section 8): self-merge earned or kept wrongly;
- eligibility (section 2): an always-yours PR, or an unreviewed one, merged automatically;
- main's copy (section 1), the clean-run runner (section 7) and escalate.py's records (section 8), end to end
  on a local project;
- the merged ticket's worktree removal (section 10): unmerged work deleted, or a busy session's folder.

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

KIT = Path(__file__).resolve().parent.parent
ROOT = KIT.parent.parent  # template/ in agent-kit, the project root in a project
sys.path.insert(0, str(KIT / "bin"))
sys.path.insert(0, str(KIT / "hooks"))

import kitconfig  # noqa: E402
import merge  # noqa: E402


def git(cwd, *args) -> str:
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args],
                       cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def scratch(test: unittest.TestCase) -> Path:
    tmp = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


def commit(repo: Path, files: dict, message: str) -> str:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


# ---------------------------------------------------------------- head binding (section 4)


class HeadBinding(unittest.TestCase):
    """R is the approved head on branch t1; main moves on after it."""

    def setUp(self):
        self.repo = repo = scratch(self)
        git(repo, "init", "-q", "-b", "main")
        commit(repo, {"app.py": "one\ntwo\nthree\n", "README.md": "readme\n"}, "base")
        git(repo, "switch", "-q", "-c", "t1")
        self.R = commit(repo, {"feature.py": "feature\n"}, "the ticket")
        git(repo, "switch", "-q", "main")
        commit(repo, {"other.py": "main moved\n"}, "main 1")
        git(repo, "switch", "-q", "t1")

    def chain(self, head):
        return merge.update_chain(self.repo, self.R, head, "main")

    def update(self, message="update from main"):
        git(self.repo, "merge", "-q", "--no-edit", "-m", message, "main")
        return git(self.repo, "rev-parse", "HEAD")

    def test_the_approved_head_and_one_or_two_clean_updates_from_main_are_bound(self):
        """AU3, AU5: the refresh (or GitHub's update button) merges main in; the approval still holds."""
        self.assertEqual(self.chain(self.R), [])
        first = self.update()
        self.assertEqual(self.chain(first), [first])
        git(self.repo, "switch", "-q", "main")
        commit(self.repo, {"other.py": "main moved twice\n"}, "main 2")
        git(self.repo, "switch", "-q", "t1")
        second = self.update()
        self.assertEqual(self.chain(second), [first, second])

    def test_a_rebase_is_not_bound(self):
        git(self.repo, "rebase", "-q", "main")
        self.assertIn("not an ancestor", self.chain(git(self.repo, "rev-parse", "HEAD")))

    def test_a_commit_after_approval_is_not_bound(self):
        head = commit(self.repo, {"feature.py": "feature, changed after approval\n"}, "after approval")
        self.assertIn("not a merge from main", self.chain(head))
        later = self.update()  # a clean update on top does not launder it
        self.assertIsInstance(self.chain(later), str)

    def test_a_hand_resolved_conflict_is_not_bound(self):
        git(self.repo, "switch", "-q", "main")
        commit(self.repo, {"feature.py": "main's own feature\n"}, "main conflicts")
        git(self.repo, "switch", "-q", "t1")
        r = subprocess.run(["git", "merge", "-q", "--no-edit", "main"], cwd=self.repo, capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        head = commit(self.repo, {"feature.py": "resolved by hand\n"}, "resolve")
        self.assertIn("conflict by hand", self.chain(head))

    def test_code_added_inside_an_update_merge_is_not_bound(self):
        """A merge commit amended with a change of its own: two parents, both fine, but its tree is not the
        clean merge of them."""
        self.update()
        (self.repo / "feature.py").write_text("slipped in\n", encoding="utf-8")
        git(self.repo, "commit", "-q", "-a", "--amend", "--no-edit")
        self.assertIn("not the clean merge", self.chain(git(self.repo, "rev-parse", "HEAD")))

    def test_a_merge_of_something_not_on_main_is_not_bound(self):
        git(self.repo, "switch", "-q", "-c", "side", "main")
        commit(self.repo, {"side.py": "never on main\n"}, "side")
        git(self.repo, "switch", "-q", "t1")
        git(self.repo, "merge", "-q", "--no-edit", "side")
        self.assertIn("not on main", self.chain(git(self.repo, "rev-parse", "HEAD")))


# ---------------------------------------------------------------- the pure revert (sections 2, 9; decision 117)


class PureRevert(unittest.TestCase):
    """PR t1 lands as merge commit M with two commits (code and a binary file); main moves on; the revert
    branch is `git revert -m 1 M` from main, as open_revert() makes it. The live case (red main on a code
    PR) covers the record lookup and the merge; these rows are the history shapes."""

    def setUp(self):
        self.repo = repo = scratch(self)
        git(repo, "init", "-q", "-b", "main")
        (repo / "logo.bin").write_bytes(b"\x00\x01binary one\xff")
        commit(repo, {"tool.py": "one\ntwo\nthree\n"}, "base")
        git(repo, "switch", "-q", "-c", "t1")
        commit(repo, {"tool.py": "one\nTWO\nthree\n"}, "first")
        (repo / "logo.bin").write_bytes(b"\x00\x01binary two\xff")
        commit(repo, {"new.py": "added\n"}, "second")
        git(repo, "switch", "-q", "main")
        git(repo, "merge", "-q", "--no-ff", "--no-edit", "t1")
        self.M = git(repo, "rev-parse", "HEAD")
        commit(repo, {"other.md": "main moved\n"}, "main 1")
        git(repo, "switch", "-q", "-c", "revert/m", "main")
        git(repo, "revert", "--no-edit", "-m", "1", self.M)
        self.R = git(repo, "rev-parse", "HEAD")

    def pure(self, head):
        return merge.pure_revert(self.repo, self.M, "main", head)

    def test_the_revert_of_a_merge_of_several_commits_is_pure_and_stays_pure_after_a_clean_update(self):
        self.assertIsNone(self.pure(self.R))
        git(self.repo, "switch", "-q", "main")
        commit(self.repo, {"other.md": "main moved twice\n"}, "main 2")
        git(self.repo, "switch", "-q", "revert/m")
        git(self.repo, "merge", "-q", "--no-edit", "main")  # the refresh
        self.assertIsNone(self.pure(git(self.repo, "rev-parse", "HEAD")))

    def test_an_edited_revert_is_not_pure(self):
        """An extra line amended in, an extra commit, and a binary file left at another content: its diff says
        only `Binary files differ`, and this row measures that patch-id still tells the contents apart (it
        hashes the `index` line's blob ids)."""
        (self.repo / "tool.py").write_text("one\ntwo\nthree\nslipped in\n", encoding="utf-8")
        git(self.repo, "commit", "-q", "-a", "--amend", "--no-edit")
        self.assertIn("patch id differs", self.pure(git(self.repo, "rev-parse", "HEAD")))
        git(self.repo, "reset", "-q", "--hard", self.R)
        extra = commit(self.repo, {"tool.py": "one\ntwo\nthree\nslipped in\n"}, "an extra commit")
        self.assertIn("2 commits of its own", self.pure(extra))
        git(self.repo, "reset", "-q", "--hard", self.R)
        (self.repo / "logo.bin").write_bytes(b"\x00\x01binary three\xff")
        git(self.repo, "commit", "-q", "-a", "--amend", "--no-edit")
        self.assertIn("patch id differs", self.pure(git(self.repo, "rev-parse", "HEAD")))

    def test_a_revert_of_another_commit_or_of_a_merge_not_on_main_is_not_pure(self):
        self.assertIn("patch id differs", merge.pure_revert(self.repo, git(self.repo, "rev-parse", "main"), "main",
                                                            self.R))
        git(self.repo, "switch", "-q", "-c", "side", f"{self.M}^1")
        side = commit(self.repo, {"side.py": "never on main\n"}, "side")
        self.assertIn("not on main", merge.pure_revert(self.repo, side, "main", self.R))

    # issue #181: `kit rollback`'s branch (tools/rollback.py: `kit-rollback-<old tag>`, one `git revert --no-edit`)
    # is pure against the commit its one commit's message names, read with no record; tests/test_update.py's case 12
    # runs it on a real rollback branch

    ROLLBACK = "kit-rollback-v0.1.0"

    def of_record(self, branch, head):
        project = SimpleNamespace(main=self.repo, merges=self.repo / ".coordination/merges")
        return merge.revert_of_record(project, branch, "main", head)

    def message(self, text):
        git(self.repo, "commit", "-q", "--amend", "-m", text)
        return git(self.repo, "rev-parse", "HEAD")

    def test_a_rollback_branch_is_pure_against_the_commit_its_message_names_with_no_record(self):
        self.assertIn(f"This reverts commit {self.M}, reversing", git(self.repo, "log", "-1", "--format=%B"))
        self.assertIsNone(self.of_record(self.ROLLBACK, self.R))
        self.assertFalse((self.repo / ".coordination").exists())

    def test_a_rollback_branch_that_is_not_one_pure_revert_of_a_commit_on_main_says_why(self):
        git(self.repo, "switch", "-q", "-c", "side", f"{self.M}^1")
        side = commit(self.repo, {"side.py": "never on main\n"}, "side")
        git(self.repo, "switch", "-q", "revert/m")
        rows = {"no such line": (lambda: self.message('Revert "the update"'), "names no reverted commit"),
                "a commit not on main": (lambda: self.message(f"Revert\n\nThis reverts commit {side}."),
                                         f"{side[:12]} is not on main"),
                "an edited revert": (lambda: self.edited(), f"is not the revert of {self.M[:12]} (its patch id "
                                                            "differs: edited)"),
                "two own commits": (lambda: commit(self.repo, {"extra.py": "x\n"}, "an extra commit"),
                                    "it has 2 commits of its own, not one")}
        for name, (make, why) in rows.items():
            with self.subTest(name):
                git(self.repo, "reset", "-q", "--hard", self.R)
                self.assertIn(why, self.of_record(self.ROLLBACK, make()) or "pure")

    def edited(self):
        (self.repo / "tool.py").write_text("one\ntwo\nthree, edited\n", encoding="utf-8")
        git(self.repo, "commit", "-q", "-a", "--amend", "--no-edit")
        return git(self.repo, "rev-parse", "HEAD")

    def test_the_scripts_revert_branch_still_reads_its_record_and_githubs_revert_button_branch_is_never_pure(self):
        """The record, not the message: the merge commit `merges/<merge id>.json` names, with the message's line
        gone; GitHub's `revert-<N>-<branch>` stays a revert that no record makes pure."""
        head = self.message("Revert PR #1: red main")
        rid = "merge-20261017T101502Z-t1-3f2a9c1-7b1e"
        merges = self.repo / ".coordination/merges"
        merges.mkdir(parents=True)
        (merges / f"{rid}.json").write_text(json.dumps({"result": "merged", "merge_commit": self.M}), encoding="utf-8")
        self.assertIsNone(self.of_record(f"revert/{rid}", head))
        self.assertIn("not a revert branch this script opened", self.of_record("revert-41-t1", self.R))


# ---------------------------------------------------------------- the earning walk (section 8)


class EarningWalk(unittest.TestCase):
    """Event files in a real `merges/` folder, walked in time order: merge records by `recorded_at`, the
    others by their ids' UTC part."""

    def setUp(self):
        self.merges = scratch(self) / "merges"
        self.merges.mkdir()
        self.k = 0

    def at(self, minute: int) -> str:
        self.k += 1
        return f"20261017T10{minute:02d}00Z-t{self.k}-abcdef0-{self.k:04x}"

    def merge_record(self, minute, counts=False, kind="ticket", entry="auto", post="green", result="merged",
                     recorded=None):
        name = f"merge-{self.at(minute)}"
        post_run = None if post is None else {"result": post}
        (self.merges / f"{name}.json").write_text(json.dumps(
            {"format": "merge", "id": name, "result": result, "entry": entry, "kind": kind, "post_run": post_run,
             "counts_toward_earning": counts,
             "recorded_at": f"2026-10-17T10:{recorded if recorded is not None else minute:02d}:30Z"}),
            encoding="utf-8")

    def event(self, kind, minute, data=None):
        name = f"{kind}-{self.at(minute)}"
        if kind == "escalation":
            (self.merges / f"{name}.md").write_text(f"---\nformat: escalation\nversion: 1\nid: {name}\n"
                                                    "trigger: round-cap\n---\n## The choice\n", encoding="utf-8")
        else:
            (self.merges / f"{name}.json").write_text(json.dumps({"id": name, **(data or {})}), encoding="utf-8")

    def state(self):
        return merge.earning(merge.events(self.merges), earn_after=3, hand_back_after=3)

    def test_three_consecutive_clean_merges_earn_and_a_merge_that_does_not_count_breaks_nothing(self):
        for minute in (1, 2):
            self.merge_record(minute, counts=True)
        self.assertFalse(self.state()["earned"])
        self.merge_record(3, counts=False, kind="known-limitation", entry="yours")
        self.merge_record(4, result="not-merged", post=None)
        self.merge_record(5, counts=True)
        self.assertEqual(self.state(), {"clean_streak": 3, "escalation_streak": 0, "earned": True, "stopped": False})

    def test_three_escalations_in_a_row_hand_back_and_a_clean_merge_breaks_the_row(self):
        for minute in (1, 2, 3):
            self.merge_record(minute, counts=True)
        self.event("escalation", 4)
        self.event("escalation", 5)
        self.merge_record(6, counts=True)  # the row is broken: escalations restart from 0
        self.event("escalation", 7)
        self.event("escalation", 8)
        self.assertEqual(self.state(), {"clean_streak": 4, "escalation_streak": 2, "earned": True, "stopped": False})
        self.event("escalation", 9)
        self.assertEqual(self.state(), {"clean_streak": 0, "escalation_streak": 0, "earned": False, "stopped": False})

    def test_a_merged_revert_hands_back(self):
        for minute in (1, 2, 3):
            self.merge_record(minute, counts=True)
        self.merge_record(4, kind="revert", entry="yours")
        self.assertEqual(self.state()["clean_streak"], 0)

    def test_a_red_main_stops_until_you_resume_and_the_streak_starts_again(self):
        for minute in (1, 2, 3):
            self.merge_record(minute, counts=True)
        self.merge_record(4, post="red")
        self.event("stop", 5, {"reason": "red main", "merge": "merge-x"})
        self.assertEqual(self.state(), {"clean_streak": 0, "escalation_streak": 0, "earned": False, "stopped": True})
        self.event("resume", 6, {"reason": "fixed"})
        for minute in (7, 8):
            self.merge_record(minute, counts=True)
        self.assertEqual(self.state(), {"clean_streak": 2, "escalation_streak": 0, "earned": False, "stopped": False})

    def test_an_outside_write_neither_counts_nor_resets_unless_its_run_is_red(self):
        for minute in (1, 2, 3):
            self.merge_record(minute, counts=True)
        self.merge_record(4, kind="outside", entry="outside")
        self.assertEqual(self.state()["clean_streak"], 3)
        self.merge_record(5, kind="outside", entry="outside", post="timeout")
        self.assertEqual(self.state()["clean_streak"], 0)

    def test_a_late_red_paid_suite_resets_after_the_merges_before_it_ended(self):
        """Ordered by the paid run's end (its id), not by the merge it ran for: merges B and C landed while A's
        paid suite ran, so its red resets them too."""
        self.merge_record(0, counts=True)  # A
        self.merge_record(10, counts=True)  # B
        self.merge_record(20, counts=True)  # C: earned
        self.assertTrue(self.state()["earned"])
        self.event("paid", 30, {"merge": "merge-A", "run": {"result": "red"}})  # A's paid suite ends red
        self.merge_record(40, counts=True)
        self.assertEqual(self.state()["clean_streak"], 1)

    def test_a_slow_attempt_that_lands_red_after_later_merges_resets_them(self):
        """Review round 1: an attempt's id carries its start; one that waited behind three later merges and
        then went red counts at its record, after them, so the streak is 0, not 3."""
        self.merge_record(0, post="red", recorded=30)  # started first, merged and recorded last
        for minute in (10, 15, 20):
            self.merge_record(minute, counts=True)
        self.assertEqual(self.state()["clean_streak"], 0)

    def test_an_unreadable_event_file_stops_the_walk(self):
        """A corrupt file skipped would leave a hand-back uncounted."""
        self.merge_record(1, counts=True)
        (self.merges / f"stop-{self.at(2)}.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(merge.Failed):
            self.state()


# ---------------------------------------------------------------- eligibility (section 2)


class Eligibility(unittest.TestCase):
    CONTROL = ["AGENTS.md", "CLAUDE.md", ".claude/**", ".agents/**", ".codex/**", "kit.lock", "agent-kit.toml"]
    YOURS = ["docs/spec/**", "docs/adr/**", "docs/agents/**"]
    EARNED = {"clean_streak": 3, "escalation_streak": 0, "earned": True, "stopped": False}

    PROSE = ("Kit change: customization\n## Instructions changed\n- `AGENTS.md`: a builder names its base branch\n"
             "## Behaviour that should change\nA builder says in READY which branch it started from.\n"
             "## Before and after\nBefore: READY: issue #4 is done.\nAfter: READY: issue #4 is done, on t4 from main.\n")

    def decide(self, paths, entry, approved=True, branch="t7", earning=None, auto_merge=True, body=""):
        cls = merge.classify(paths, branch, self.CONTROL, self.YOURS, body)
        return merge.eligibility(entry, cls, approved, earning or self.EARNED, auto_merge, 3, 41)

    def refused(self, item, *args, **kw):
        with self.assertRaises(merge.Refused) as caught:
            self.decide(*args, **kw)
        self.assertEqual(caught.exception.item, item, str(caught.exception))
        return str(caught.exception)

    def test_automatic_mode_merges_only_an_approved_earned_ticket_pr_with_auto_merge_on(self):
        self.assertEqual(self.decide(["src/app.py", "tests/test_app.py"], "auto"), ("ticket", "verdict"))
        unearned = {**self.EARNED, "clean_streak": 2, "earned": False}
        self.assertIn("not earned: 2 of 3", self.refused("earned", ["src/app.py"], "auto", earning=unearned))
        self.refused("stopped", ["src/app.py"], "auto", earning={**self.EARNED, "stopped": True})
        self.refused("auto merge", ["src/app.py"], "auto", auto_merge=False)

    def test_automatic_mode_refuses_every_always_yours_pr(self):
        for paths, branch in ((["src/app.py", ".agents/kit/bin/merge.py"], "t7"),  # control code
                              (["AGENTS.md"], "t7"),  # instruction text
                              (["docs/spec/feed.md"], "t7"),  # your paths
                              (["src/app.py"], "revert/merge-20261017T101502Z-t37-3f2a9c1-7b1e"),
                              (["src/app.py"], "revert-41-t37")):  # GitHub's Revert button
            with self.subTest(paths=paths, branch=branch):
                self.refused("class", paths, "auto", branch=branch)

    def test_automatic_mode_refuses_a_known_limitation_your_mode_takes_your_command(self):
        self.refused("clearance", ["src/app.py"], "auto", approved=False)
        self.assertEqual(self.decide(["src/app.py"], "yours", approved=False), ("known-limitation", "your command"))
        self.assertEqual(self.decide(["src/app.py"], "yours"), ("ticket", "verdict"))

    def test_your_mode_needs_a_codex_approval_for_control_code(self):
        for path in ("scripts/release.ps1", ".claude/settings.json", ".codex/hooks.json", "agent-kit.toml",
                     ".agents/kit/config/schema.toml", ".agents/kit/hooks/guard.py"):
            with self.subTest(path=path):
                self.refused("Codex approval", ["docs/spec/x.md", path], "yours", approved=False)
                self.assertEqual(self.decide(["docs/spec/x.md", path], "yours"), ("control", "verdict"))

    def test_a_kit_rollback_branch_is_a_revert_as_the_revert_branches_are(self):
        """Issue #181: by its branch alone, `kit rollback`'s PR is always yours and merges as a revert, a hand-back
        (section 8)."""
        for branch, revert in (("kit-rollback-v0.1.0", True), ("revert/merge-20261017T101502Z-t37-3f2a9c1-7b1e", True),
                               ("revert-41-t37", True), ("t7", False)):
            with self.subTest(branch=branch):
                cls = merge.classify(["src/app.py"], branch, self.CONTROL, self.YOURS)
                self.assertEqual((cls["class"], cls["revert"]), ("yours" if revert else "ticket", revert))
        self.assertEqual(self.decide(["README.md"], "yours", approved=False, branch="kit-rollback-v0.1.0"),
                         ("revert", "your command"))

    def test_your_mode_specs_and_reverts_need_nothing_more(self):
        self.assertEqual(self.decide(["docs/spec/feed.md"], "yours", approved=False), ("spec", "your command"))
        self.assertEqual(self.decide(["README.md"], "yours", approved=False, branch="revert-41-t37"),
                         ("revert", "your command"))
        # review round 1: a revert of code, cleared by a Codex approval, is still a revert, so it hands back
        self.assertEqual(self.decide(["src/app.py"], "yours", branch="revert-41-t37"), ("revert", "verdict"))

    def test_instruction_text_needs_a_codex_approval_unless_it_is_a_customization_in_the_prose_shape(self):
        """C8 section 11 (decisions 100, 114): an instruction change merged unexplained, or a workflow unit
        merged without Codex, is the failure; a missing `Kit change:` line reads as a workflow unit."""
        text = [".agents/skills/review/standard.md"]
        self.refused("Codex approval", text, "yours", approved=False)  # no line: a workflow unit
        self.refused("Codex approval", ["AGENTS.md"], "yours", approved=False,
                     body=self.PROSE.replace("customization", "workflow unit"))
        self.refused("Codex approval", ["AGENTS.md"], "yours", approved=False, body=self.PROSE.split("\n", 1)[1])
        self.assertEqual(self.decide(["AGENTS.md"], "yours", body="Kit change: workflow unit\n"), ("control", "verdict"))
        self.assertEqual(self.decide(["AGENTS.md"], "yours", approved=False, body=self.PROSE), ("prose", "your command"))
        self.assertEqual(self.decide(["AGENTS.md"], "yours", approved=False, body=self.PROSE.replace("\n", "\r\n")),
                         ("prose", "your command"))  # a body written on GitHub's page
        # control code needs the approval whatever the body says; automatic mode refuses either way
        self.refused("Codex approval", ["AGENTS.md", ".agents/kit/bin/merge.py"], "yours", approved=False,
                     body=self.PROSE)
        self.refused("class", ["AGENTS.md"], "auto", body=self.PROSE)

    def test_the_prose_shape_refuses_a_missing_part_and_an_unnamed_path(self):
        p = self.PROSE
        cases = {
            "## Instructions changed": p.replace("## Instructions changed\n", ""),
            "## Behaviour that should change": p.replace("## Behaviour that should change\n", ""),
            "## Before and after": p.replace("## Before and after\n", ""),
            "## Behaviour that should change (empty)": p.replace("A builder says in READY which branch it started "
                                                                 "from.\n", ""),
            "## Before and after (empty)": p.split("## Before and after")[0] + "## Before and after\n\n",
            # review round 1: a section ends at the next heading, so a footer after it does not fill it
            "## Before and after (a footer)": p.split("## Before and after")[0] + "## Before and after\n"
                                              "Before: <x>\nAfter: <y>\n## Validation\n7 tests passed.\n",
            "the headings in order": p.replace("## Behaviour that should change", "## Tmp").replace(
                "## Before and after", "## Behaviour that should change").replace("## Tmp", "## Before and after"),
        }
        for part, body in cases.items():
            with self.subTest(part=part):
                self.assertIn(part.split(" (")[0], self.refused("prose shape", ["AGENTS.md"], "yours",
                                                                approved=False, body=body))
        named = self.refused("prose shape", ["AGENTS.md", ".claude/skills/build/SKILL.md"], "yours", approved=False,
                             body=self.PROSE)
        self.assertIn(".claude/skills/build/SKILL.md", named)
        # the shipped template, copied but not filled in, is not the shape
        template = (KIT / "templates/prose-pr.md").read_text(encoding="utf-8")
        self.assertTrue(template.startswith("Kit change: customization\n"), template)
        self.refused("prose shape", ["AGENTS.md"], "yours", approved=False, body=template)

    def test_a_pure_revert_of_control_code_needs_no_codex_approval_an_impure_one_does(self):
        """Decision 117. Automatic mode still refuses it: a revert is always yours."""
        branch = "revert/merge-20261017T101502Z-t37-3f2a9c1-7b1e"
        cls = merge.classify([".agents/kit/bin/merge.py", "AGENTS.md"], branch, self.CONTROL, self.YOURS)
        pure = {**cls, "pure_revert": True, "impure_because": None}
        self.assertEqual(merge.eligibility("yours", pure, False, self.EARNED, True, 3, 41), ("revert", "your command"))
        self.assertFalse(merge.needs_codex(pure))
        with self.assertRaises(merge.Refused) as caught:
            merge.eligibility("auto", pure, True, self.EARNED, True, 3, 41)
        self.assertEqual(caught.exception.item, "class")
        impure = {**cls, "pure_revert": False, "impure_because": "it has 2 commits of its own, not one"}
        with self.assertRaises(merge.Refused) as caught:
            merge.eligibility("yours", impure, False, self.EARNED, True, 3, 41)
        self.assertEqual(caught.exception.item, "Codex approval")
        self.assertIn("not a pure revert: it has 2 commits", str(caught.exception))
        self.assertTrue(merge.needs_codex(impure))

    def test_item_11_does_not_bind_a_verdict_a_pure_revert_was_not_cleared_by(self):
        """Review round 1: a reviewed revert whose message was then amended is still pure and cleared by your
        command; when main moves during its run, item 11 must not refuse it for the old verdict's head."""
        from unittest import mock
        ready = merge.Ready()
        ready.pr, ready.shown, ready.clearance = {"headRefName": "revert/x"}, None, {"by": "your command"}
        ready.cls = {"class": "yours", "yours_because": [], "revert": True, "code": ["a.py"], "text": [],
                     "pure_revert": True, "impure_because": None}
        ready.reference = {"verdict": {"head": "a" * 40}}
        rec = {"head": "b" * 40, "main_before": "c" * 40, "pre_run": {"reruns": 0}}
        p = SimpleNamespace(main=Path("."), default="main", repo="me/proj",
                            value=lambda key: {"tickets.auto_merge": True, "tickets.earn_after": 3}[key])
        moved = f"{'d' * 40}\trefs/heads/main\n{'b' * 40}\trefs/heads/revert/x"
        pr = {"state": "OPEN", "isDraft": False, "baseRefName": "main", "headRefName": "revert/x",
              "headRefOid": "b" * 40, "headRepositoryOwner": {"login": "me"}, "isCrossRepository": False}

        class Reached(Exception):
            pass

        def bind(cwd, ref, head, main_ref, what, valid):
            if what == "approval":
                raise merge.Refused("head", f"approval is for {ref}", valid)
            return []

        with mock.patch.multiple(merge, reconcile_pass=lambda *a: 0, earning_now=lambda p: self.EARNED,
                                 pr_view=lambda p, n: pr, check_comments=lambda p, n: None,
                                 fetch_head=lambda *a: None, bind=bind,
                                 is_ancestor=lambda *a: True, reclassify=mock.Mock(side_effect=Reached),
                                 git=lambda cwd, *args: moved if args[0] == "ls-remote" else ""):
            with self.assertRaises(Reached):  # on to the rerun, not refused for the verdict's head
                merge.item_11(p, 41, "yours", ready, rec, "merge-x", None)

    def test_item_11_refuses_a_pr_retargeted_during_the_clean_run(self):
        """Issue #102: the PR's base changed while head and main stayed put; the merge would go into a base
        nobody tested, so item 11 refuses as item 3 does."""
        from unittest import mock
        ready = merge.Ready()
        ready.pr, ready.cls, ready.reference = {"headRefName": "t7"}, {"class": "routine"}, None
        rec = {"head": "b" * 40, "main_before": "c" * 40, "pre_run": {"reruns": 0}}
        p = SimpleNamespace(main=Path("."), default="main", repo="me/proj",
                            value=lambda key: {"tickets.auto_merge": True, "tickets.earn_after": 3}[key])
        pr = {"state": "OPEN", "isDraft": False, "baseRefName": "release", "headRefName": "t7",
              "headRefOid": "b" * 40, "headRepositoryOwner": {"login": "me"}, "isCrossRepository": False}
        unchanged = f"{'c' * 40}\trefs/heads/main\n{'b' * 40}\trefs/heads/t7"
        with mock.patch.multiple(merge, reconcile_pass=lambda *a: 0, earning_now=lambda p: self.EARNED,
                                 eligibility=lambda *a: None, pr_view=lambda p, n: pr,
                                 check_comments=lambda p, n: None,
                                 git=lambda cwd, *args: unchanged if args[0] == "ls-remote" else ""):
            with self.assertRaises(merge.Refused) as caught:
                merge.item_11(p, 7, "auto", ready, rec, "merge-x", None)
        self.assertEqual(caught.exception.item, "PR")
        self.assertIn("based on release, not main", str(caught.exception))

    def test_both_sides_of_a_rename_and_a_deleted_path_are_classed(self):
        """A file moved out of a your-path, or a deleted guard, still makes the PR yours."""
        repo = scratch(self)
        git(repo, "init", "-q", "-b", "main")
        commit(repo, {"docs/spec/feed.md": "a spec\n" * 20, ".agents/kit/hooks/guard.py": "guard\n"}, "base")
        git(repo, "switch", "-q", "-c", "t7")
        (repo / "notes").mkdir()
        git(repo, "mv", "docs/spec/feed.md", "notes/feed.md")
        git(repo, "rm", "-q", ".agents/kit/hooks/guard.py")
        commit(repo, {}, "move and delete")
        paths = merge.changed_paths(repo, "main", "t7")
        self.assertEqual(sorted(paths), [".agents/kit/hooks/guard.py", "docs/spec/feed.md", "notes/feed.md"])
        self.refused("class", paths, "auto")


# ---------------------------------------------------------------- end to end on a local project (sections 1, 7)


def git_only_path() -> str:
    """PATH without the folders that hold gh: a gh call fails at once, so a refusal shows it came first."""
    return os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep)
                           if d and not shutil.which("gh", path=d))


class LocalProject(unittest.TestCase):
    """The kit's bin, hooks and config in a main checkout with a bare local remote, a worktree t1."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.main = main = cls.tmp / "proj"
        for part in ("bin", "hooks", "config"):
            shutil.copytree(KIT / part, main / ".agents/kit" / part, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / ".gitignore", main / ".gitignore")
        git(cls.tmp, "init", "-q", "-b", "main", str(main))
        for which, values in (("project", ["project.name='e2e'", "merge.clean_run=['python','-I','suite.py']"]),
                              ("local", ["reviewer_home='C:/kit/state/r'"])):
            text, problems = kitconfig.render(main, which, values)
            assert problems == [], problems
            (main / kitconfig.FILES[which]).write_text(text, encoding="utf-8")
        (main / "suite.py").write_text(SUITE, encoding="utf-8")
        (main / ".env").write_text("E2E_KEY=not-a-real-key\n", encoding="utf-8")
        git(main, "add", "-A")
        git(main, "commit", "-qm", "install")
        git(cls.tmp, "init", "-q", "--bare", "-b", "main", str(cls.tmp / "remote.git"))
        git(main, "remote", "add", "origin", str(cls.tmp / "remote.git"))
        git(main, "push", "-q", "-u", "origin", "main")
        git(main, "remote", "set-head", "origin", "main")
        cls.t1 = main / ".claude/worktrees/t1"
        git(main, "worktree", "add", "-q", "-b", "t1", str(cls.t1))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["git", "worktree", "prune"], cwd=cls.main, capture_output=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def merge_py(self, checkout, *args, env=None):
        return subprocess.run([sys.executable, "-I", str(checkout / ".agents/kit/bin/merge.py"), *args],
                              cwd=checkout, capture_output=True, text=True, env={**os.environ, "PATH": git_only_path(),
                                                                                 **(env or {})})

    def test_main_s_copy_refuses_a_changed_script_or_a_worktree_s_copy_before_any_gh_call(self):
        """Decision 93: only main's copy, equal to origin/main's, ever merges."""
        passed = self.merge_py(self.main, "check", "1")  # item 1 passes; item 3 then finds no GitHub origin
        self.assertIn("ok main's copy", passed.stdout, passed.stdout + passed.stderr)
        self.assertIn("REFUSED (repository)", passed.stderr)
        script = self.main / ".agents/kit/bin/merge.py"
        original = script.read_bytes()
        self.addCleanup(script.write_bytes, original)
        script.write_bytes(original + b"\n# a local change\n")
        r = self.merge_py(self.main, "auto", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUSED (main's copy): .agents/kit/bin/merge.py differs from origin/main", r.stderr)
        script.write_bytes(original)
        r = self.merge_py(self.t1, "yours", "1", "--head", "0123456789ab")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUSED (main's copy): merge.py ran from", r.stderr)

    def project(self, minutes=1.0):
        values = {"merge.clean_run": ["python", "-I", "suite.py"], "merge.run_timeout_minutes": minutes,
                  "secret_files": [".env"], "tickets.your_paths": ["docs/spec/**"], "tickets.auto_merge": True,
                  "tickets.earn_after": 3, "tickets.hand_back_after_escalations": 3}
        return SimpleNamespace(main=self.main, coordination=self.main / ".coordination", default="main",
                               merges=self.main / ".coordination/merges", value=lambda key: values[key])

    def test_an_update_from_main_that_moves_the_ticket_s_file_into_your_paths_makes_it_yours(self):
        """Review round 2: main moved notes.md into docs/spec/ while the ticket edited it; git merges the edit
        into docs/spec/notes.md, so after the refresh the head changes a your-path and automatic mode must
        refuse it, though the PR was a ticket PR before."""
        wt, other = self.tmp / "class-t", self.tmp / "class-main"
        git(self.main, "fetch", "-q", "origin")
        git(self.main, "worktree", "add", "-q", "--detach", str(other), "origin/main")
        commit(other, {"notes.md": "one\ntwo\nthree\nfour\nfive\n"}, "notes")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(self.main, "fetch", "-q", "origin")
        git(self.main, "worktree", "add", "-q", "-b", "t-class", str(wt), "origin/main")
        commit(wt, {"notes.md": "one\ntwo\nthree, the ticket's edit\nfour\nfive\n"}, "ticket edit")
        (other / "docs/spec").mkdir(parents=True)
        git(other, "mv", "notes.md", "docs/spec/notes.md")
        moved = commit(other, {}, "main moves notes into docs/spec")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(self.main, "fetch", "-q", "origin")
        before, cls = merge.classify_head(self.project(), "t-class", moved, git(wt, "rev-parse", "HEAD"))
        self.assertEqual((before, cls["class"]), (["notes.md"], "ticket"))
        git(wt, "merge", "-q", "--no-edit", moved)
        self.assertIn("the ticket's edit", (wt / "docs/spec/notes.md").read_text(encoding="utf-8"))
        with self.assertRaises(merge.Refused) as caught:
            merge.reclassify(self.project(), 41, "auto", "t-class", moved, git(wt, "rev-parse", "HEAD"), True,
                             "verdict")
        self.assertEqual(caught.exception.item, "class", str(caught.exception))

    def test_the_refresh_merges_the_main_this_run_read_not_a_newer_one(self):
        """Review round 1: origin/main is one ref every run in the checkout shares, so a concurrent run's fetch
        can move it after this run read it. The refresh merges the commit this run read, which it tested and
        records, not whatever the ref says by then."""
        wt, other = self.tmp / "refresh-t", self.tmp / "refresh-main"
        git(self.main, "fetch", "-q", "origin")
        git(self.main, "worktree", "add", "-q", "-b", "t-refresh", str(wt), "origin/main")
        head = commit(wt, {"ticket.txt": "the ticket\n"}, "ticket")
        git(wt, "push", "-q", "origin", "t-refresh")
        git(self.main, "worktree", "add", "-q", "--detach", str(other), "origin/main")
        read = commit(other, {"main-1.txt": "main moved\n"}, "main 1")
        git(other, "push", "-q", "origin", "HEAD:main")
        newer = commit(other, {"main-2.txt": "main moved again\n"}, "main 2")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(git(self.main, "rev-parse", "origin/main"), newer)
        new = merge.refresh(self.project(), "t-refresh", head, read)
        self.assertEqual(merge.parents(self.main, new), [head, read])
        self.assertEqual(git(self.main, "ls-remote", "origin", "refs/heads/t-refresh").split()[0], new)

    def clean_run(self, stage, plant=None, minutes=1.0, changed=None):
        head = git(self.main, "rev-parse", "HEAD")
        if plant:
            git(self.main, "switch", "-q", "-c", f"plant-{plant}-{stage}")
            self.addCleanup(git, self.main, "switch", "-q", "main")
            head = commit(self.main, {f"plant-{plant}": "planted\n"}, f"plant {plant}")
        env = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "s-1", "KIT_CHANGED_PATHS_FILE": "C:/stale.txt"}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            out = merge.clean_run(self.project(minutes), f"merge-e2e-{stage}-{plant}", stage, head, changed, False)
        finally:
            for k, v in saved.items():
                os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
        return out, (self.main / ".coordination" / out["log"]).read_text(encoding="utf-8")

    def test_a_green_run_sees_its_commit_the_secret_file_and_no_session_markers(self):
        out, log = self.clean_run("pre", changed=["src/app.py", "docs/a b.md"])
        self.assertEqual((out["result"], out["exit"]), ("green", 0), log)
        self.assertIn("KIT_RUN=merge-pre", log)
        self.assertIn("secret: E2E_KEY=not-a-real-key", log)
        self.assertIn("markers: none", log)
        self.assertIn("changed: ['src/app.py', 'docs/a b.md']", log)
        post, log = self.clean_run("post")
        self.assertEqual(post["result"], "green", log)
        self.assertIn("changed: unset", log)  # the whole live suite runs after the merge (decision 66)
        self.assertEqual(list((self.main / ".claude/worktrees").glob("merge-*")), [])  # removed after each run

    def test_a_failing_suite_is_red(self):
        out, log = self.clean_run("pre", plant="red")
        self.assertEqual((out["result"], out["exit"]), ("red", 1), log)

    def test_a_run_past_the_timeout_is_red_and_its_process_tree_is_killed(self):
        out, log = self.clean_run("pre", plant="slow", minutes=0.1)
        self.assertEqual((out["result"], out["exit"]), ("timeout", None), log)
        self.assertLess(out["seconds"], 60)
        child = int(log.split("grandchild ")[1].split()[0])
        alive = subprocess.run(["tasklist", "/FI", f"PID eq {child}", "/NH"], capture_output=True, text=True).stdout \
            if sys.platform == "win32" else ("x" if Path(f"/proc/{child}").exists() else "")
        self.assertNotIn(str(child), alive, "the suite's own child outlived the timeout")


    def test_escalate_writes_the_record_the_earning_walk_reads_and_one_answer_from_its_list(self):
        """C8 section 8, C9 section 4: escalate.py's records, end to end through the command. A record in
        the wrong shape, or a second answer, would leave the earning walk or the review script misled."""
        def esc(*args):
            return subprocess.run([sys.executable, "-I", str(self.main / ".agents/kit/bin/escalate.py"), *args],
                                  cwd=self.main, capture_output=True, text=True)
        body = self.tmp / "esc-body.md"
        body.write_text("---\nheadline: t7 needs you: which feed wins\nanswers: fix, defer\n---\n## The choice\n"
                        "Two feeds disagree.\n## Findings\nNone.\n## Options\nfix: pick one.\n", encoding="utf-8")
        r = esc("--ticket", "7", "--trigger", "needs-decision", "--body-file", str(body))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no ## Recommendation", r.stderr)
        body.write_text(body.read_text(encoding="utf-8") + "## Recommendation\nfix: the newer feed.\n",
                        encoding="utf-8")
        r = esc("--ticket", "7", "--trigger", "needs-decision", "--body-file", str(body))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        merges = self.main / ".coordination" / "merges"
        [path] = list(merges.glob("escalation-*-t7-*.md"))
        fields = merge.front_matter(path.read_text(encoding="utf-8"))
        self.assertEqual((fields["id"], fields["by"], fields["trigger"], fields["holds"], fields["answers"]),
                         (path.stem, "escalate.py", "needs-decision", "7", "fix, defer"))
        self.assertEqual(merge.earning(merge.events(merges), 3, 3)["escalation_streak"], 1)
        self.assertIn("is not one this escalation offers",
                      esc("answer", "--escalation", path.stem, "--answer", "cancel", "--quote", "stop it").stderr)
        self.assertIn("more than one line", esc("answer", "--escalation", path.stem, "--answer", "fix",
                                                "--quote", "use the\nnewer feed").stderr)
        r = esc("answer", "--escalation", path.stem, "--answer", "fix", "--quote", "use the newer feed:  `a  b`")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        answer = merge.front_matter((merges / f"answer-{path.stem}.md").read_text(encoding="utf-8"))
        self.assertEqual((answer["answer"], answer["quote"]), ("fix", "use the newer feed:  `a  b`"))  # verbatim
        again = esc("answer", "--escalation", path.stem, "--answer", "defer", "--quote", "later")
        self.assertIn("answered once", again.stderr)
        self.assertEqual(merge.earning(merge.events(merges), 3, 3)["escalation_streak"], 1)  # the answer is no event

    def test_escalate_refuses_a_record_the_format_check_rejects(self):
        """C8 section 8 (issue #98): the writer checks with `formats.problems`, the readers' check. A nested
        `holds: [37, 38]` passed escalate.py's own shape check, and formats.py then dropped `holds`."""
        body = self.tmp / "esc-nested.md"
        body.write_text("---\nheadline: t7 needs you: which feed wins\nanswers: fix, defer\nholds: [7, 8]\n---\n"
                        "## The choice\nTwo feeds disagree.\n## Findings\nNone.\n## Options\nfix: pick one.\n"
                        "## Recommendation\nfix: the newer feed.\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", str(self.main / ".agents/kit/bin/escalate.py"), "--ticket", "7",
                            "--trigger", "needs-decision", "--body-file", str(body)],
                           cwd=self.main, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("holds", r.stderr)
        self.assertEqual(list((self.main / ".coordination" / "merges").glob("escalation-*-t7-*.md")), [])


class OutsideNeeds(unittest.TestCase):
    def test_an_outside_commit_of_kit_code_gets_the_machinery_tests_and_one_of_paid_paths_its_paid_suite(self):
        """Review round 1: a merge made on GitHub's page that changed kit code ran only merge.clean_run, and
        one that changed paid inputs never got its paid suite."""
        repo = scratch(self)
        git(repo, "init", "-q", "-b", "main")
        commit(repo, {"app.py": "app\n"}, "base")
        kit = commit(repo, {".agents/kit/bin/extra.py": "x = 1\n", "README.md": "readme\n"}, "kit code")
        data = commit(repo, {"data/feed.csv": "a,b\n"}, "paid input")
        values = {"merge.paid_suite": ["python", "paid.py"], "merge.paid_paths": ["data/**"]}
        p = SimpleNamespace(main=repo, value=lambda key: values[key])
        self.assertEqual(merge.outside_needs(p, [{"commit": kit}, {"commit": data}]),
                         (True, {kit: "not due", data: "due"}))
        self.assertEqual(merge.outside_needs(p, [{"commit": data}]), (False, {data: "due"}))


class OutsidePR(unittest.TestCase):
    """M218: 7 s after a merge through GitHub's API, `commits/<sha>/pulls` still named no PR, so T17's outside
    record had `pr` null and its notice named the commit. Here GitHub is a fake `gh` that answers `[]` there;
    the PR is still found by the number in the commit's subject, kept only when GitHub names the commit as
    that PR's merge commit."""

    def setUp(self):
        self.repo = scratch(self)
        git(self.repo, "init", "-q", "-b", "main")
        commit(self.repo, {"app.py": "app\n"}, "base")
        self.pulls = {}  # number -> what `gh api repos/o/r/pulls/<n>` answers
        self.calls = []

    def gh(self, cwd, *args, check=True):
        self.calls.append(args)
        if args[0] == "api" and args[1].endswith("/pulls") and "/commits/" in args[1]:
            return subprocess.CompletedProcess(args, 0, "[]", "")  # the lagging commit-to-PR index
        if args[0] == "api" and args[1].startswith("repos/o/r/pulls/"):
            pr = self.pulls.get(int(args[1].rsplit("/", 1)[1]))
            if pr is None:
                if check:
                    raise merge.Failed(f"gh {' '.join(args)}: HTTP 404")
                return subprocess.CompletedProcess(args, 1, "", "HTTP 404: Not Found")
            return subprocess.CompletedProcess(args, 0, json.dumps(pr), "")
        raise AssertionError(f"unexpected gh call {args}")

    def pr_of(self, sha):
        from unittest import mock
        with mock.patch.object(merge, "gh", self.gh):
            return merge.pr_of_commit(SimpleNamespace(main=self.repo, repo="o/r"), sha)

    def test_a_fresh_api_merge_gets_its_pr_from_the_subject_and_a_wrong_or_missing_number_gets_none(self):
        merged = commit(self.repo, {"a.txt": "a\n"}, "Merge pull request #153 from o/test-api\n\nbody")
        squashed = commit(self.repo, {"b.txt": "b\n"}, "Add b (#154)")
        claimed = commit(self.repo, {"c.txt": "c\n"}, "Merge pull request #155 from o/other")
        pushed = commit(self.repo, {"d.txt": "d\n"}, "a direct push")
        self.pulls = {153: {"number": 153, "merge_commit_sha": merged, "title": "API", "head": {"ref": "test-api"}},
                      154: {"number": 154, "merge_commit_sha": squashed, "title": "B", "head": {"ref": "t4"}},
                      155: {"number": 155, "merge_commit_sha": "0" * 40, "title": "C", "head": {"ref": "x"}}}
        self.assertEqual((self.pr_of(merged) or {}).get("number"), 153)
        self.assertEqual((self.pr_of(squashed) or {}).get("number"), 154)
        self.assertIsNone(self.pr_of(claimed))  # the subject names a PR GitHub merged as another commit
        self.calls.clear()
        self.assertIsNone(self.pr_of(pushed))
        self.assertEqual(len(self.calls), 1, self.calls)  # no PR named: only the index is asked
        gone = commit(self.repo, {"e.txt": "e\n"}, "Merge pull request #999 from o/gone")
        self.assertIsNone(self.pr_of(gone))  # an unreadable PR is no PR, not a crash


# ---------------------------------------------------------------- the merged ticket's worktree (section 10)


class WorktreeRemoval(unittest.TestCase):
    """A main checkout with a bare remote and the ticket's worktree `.claude/worktrees/t5` on branch t5,
    pushed; then GitHub's side is played by hand: a merge commit, a squash, main moving on."""

    def setUp(self):
        tmp = scratch(self)
        git(tmp, "init", "-q", "--bare", "-b", "main", str(tmp / "remote.git"))
        self.main = main = tmp / "proj"
        git(tmp, "init", "-q", "-b", "main", str(main))
        (main / ".gitignore").write_text(".coordination/\n.claude/worktrees/\n.env\n", encoding="utf-8")
        commit(main, {"app.py": "app\n"}, "base")
        git(main, "remote", "add", "origin", str(tmp / "remote.git"))
        git(main, "push", "-q", "-u", "origin", "main")
        self.wt = main / ".claude/worktrees/t5"
        git(main, "worktree", "add", "-q", "-b", "t5", str(self.wt), "origin/main")
        self.head = commit(self.wt, {"feature.py": "feature\n"}, "the ticket")
        (self.wt / ".env").write_text("KEY=copied secret, ignored\n", encoding="utf-8")
        git(self.wt, "push", "-q", "origin", "t5")
        self.p = SimpleNamespace(main=main, coordination=main / ".coordination", default="main",
                                 merges=main / ".coordination/merges")
        self.sessions, self.stopped = [], []
        for name, fake in (("list_sessions", lambda cwd: self.sessions), ("stop_session", self.stop)):
            original = getattr(merge, name)
            setattr(merge, name, fake)
            self.addCleanup(setattr, merge, name, original)

    def stop(self, who, cwd):
        self.stopped.append((who, self.wt.exists()))
        return who != "stuck"

    def land(self, how):
        """Merge t5 into main the way GitHub would, push, fetch; the PR's merge commit."""
        if how == "merge":
            git(self.main, "merge", "-q", "--no-ff", "-m", "Merge PR #5", "t5")
        else:
            git(self.main, "merge", "-q", "--squash", "t5")
            git(self.main, "commit", "-qm", "Squash PR #5")
        sha = git(self.main, "rev-parse", "HEAD")
        git(self.main, "push", "-q", "origin", "main")
        git(self.main, "fetch", "-q", "origin")
        return sha

    def remove(self, commit_):
        return merge.remove_worktree(self.p, "t5", commit_)

    def kept(self, out, why):
        self.assertFalse(out["removed"], out)
        self.assertIn(why, out["kept_because"])
        self.assertTrue(self.wt.exists())
        self.assertTrue(list((self.p.coordination / "notices").glob("*-worktree-kept-*.md")))

    def removed(self, out):
        self.assertEqual((out["removed"], out["kept_because"], out["path"]), (True, None, ".claude/worktrees/t5"), out)
        self.assertFalse(self.wt.exists())
        self.assertEqual(git(self.main, "rev-parse", "t5"), self.head)  # the branch is kept

    def test_a_merge_commit_removes_it(self):
        self.removed(self.remove(self.land("merge")))

    def test_a_squash_removes_it_even_after_main_moved_on(self):
        """GitHub's squash button: the worktree's HEAD is not on main, but its tree is the squash's. Compared
        with main's tip instead, it would be kept once main moves on."""
        squash = self.land("squash")
        commit(self.main, {"later.py": "main moved on\n"}, "a later merge")
        git(self.main, "push", "-q", "origin", "main")
        git(self.main, "fetch", "-q", "origin")
        self.removed(self.remove(squash))

    def test_a_dirty_worktree_or_an_extra_commit_is_kept(self):
        merged = self.land("merge")
        (self.wt / "notes.txt").write_text("not committed\n", encoding="utf-8")
        self.kept(self.remove(merged), "uncommitted or untracked")
        (self.wt / "notes.txt").unlink()
        commit(self.wt, {"feature.py": "more work after the PR\n"}, "extra")
        self.kept(self.remove(merged), "not on origin/main")

    def test_a_locked_worktree_is_kept(self):
        merged = self.land("merge")
        git(self.main, "worktree", "lock", str(self.wt))
        self.kept(self.remove(merged), "git worktree remove")

    def test_a_session_still_in_it_is_stopped_first_and_one_that_will_not_stop_keeps_it(self):
        """M70: a folder a session works in cannot be deleted, and a session ends when its ticket merges."""
        merged = self.land("merge")
        self.sessions = [{"id": "8d1cf54b", "name": "proj-t5", "cwd": str(self.wt / "src")},
                         {"id": "aaaabbbb", "name": "proj-orchestrator", "cwd": str(self.main)}]
        out = self.remove(merged)
        self.removed(out)
        self.assertEqual((self.stopped, out["sessions_stopped"]), ([("8d1cf54b", True)], ["proj-t5"]))
        git(self.main, "worktree", "add", "-q", str(self.wt), "t5")
        self.sessions = [{"id": "stuck", "name": "proj-t5", "cwd": str(self.wt)}]
        self.kept(self.remove(merged), "could not be stopped")


def alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    return Path(f"/proc/{pid}").exists()


class LockedCalls(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "the job object is Windows only (C7 section 3)")
    def test_a_git_or_gh_call_under_the_lock_ends_when_merge_py_crashes(self):
        """Review round 1: a refresh push or the merge call itself, still running after merge.py died and its
        lock was freed, would change GitHub behind the next run's back."""
        tmp = scratch(self)
        pidfile = tmp / "child.pid"
        child = (f"import os, pathlib, time; pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); "
                 "time.sleep(600)")
        holder = "\n".join([
            "import os, sys, threading", "from pathlib import Path", "from types import SimpleNamespace",
            f"sys.path.insert(0, {str(KIT / 'bin')!r})", "import merge",
            f"merge.take_lock(SimpleNamespace(coordination=Path({str(tmp)!r})), "
            "{'format': 'merge-lock', 'version': 1, 'id': 'merge-test', 'pr': 1})",
            "threading.Timer(8, os._exit, (9,)).start()",
            f"merge.run([sys.executable, '-c', {child!r}], Path('.'), timeout=600)"])
        r = subprocess.run([sys.executable, "-I", "-c", holder], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 9, r.stderr)
        pid = int(pidfile.read_text())
        self.addCleanup(subprocess.run, ["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        deadline = time.time() + 10
        while alive(pid) and time.time() < deadline:
            time.sleep(0.5)
        self.assertFalse(alive(pid), "a call merge.py made under the lock outlived it")


SUITE = r'''"""The local project's clean run: prints what it sees, fails or hangs on a planted file."""
import os, pathlib, subprocess, sys, time
print("KIT_RUN=" + os.environ.get("KIT_RUN", ""))
env_file = pathlib.Path(".env")
print("secret: " + (env_file.read_text().strip() if env_file.exists() else "missing"))
markers = [k for k in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID") if k in os.environ]
print("markers: " + (", ".join(markers) or "none"))
listed = os.environ.get("KIT_CHANGED_PATHS_FILE")
print("changed: " + (str(pathlib.Path(listed).read_text().splitlines()) if listed else "unset"), flush=True)
if pathlib.Path("plant-red").exists():
    sys.exit(1)
if pathlib.Path("plant-slow").exists():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    print(f"grandchild {child.pid}", flush=True)
    time.sleep(600)
'''


if __name__ == "__main__":
    unittest.main()
