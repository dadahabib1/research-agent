"""The loop's cheap first check (contract C9 section 16), one row per failure it catches. Each row runs
`tick.py`'s own entry on a real coordination folder in a scratch project; only `claude agents --json` is
faked, in the row shape test I and M81 measured. The real path, an orchestrator's timer turn in a live
session, is agent-kit's `tests/test_live_skills.py` (deferred with B2-B8).

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "bin"))
sys.path.insert(0, str(KIT / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import notices  # noqa: E402
import tick  # noqa: E402
from test_guard import Project  # noqa: E402  (its scratch project: schema, config, main, worktrees)

END = "<!-- end -->"


def message(complete=True):
    text = "---\nformat: message\nversion: 1\nkind: ready\nheadline: t37: lock waits\n---\nREADY t37 at abc\n"
    return text + (END + "\n" if complete else "")


class Tick(Project):
    def setUp(self):
        shutil.rmtree(self.coord, ignore_errors=True)
        self.inbox = self.coord / "messages/sandbox-orch"
        self.inbox.mkdir(parents=True)
        self.rows = []
        self.real_run = subprocess.run
        tick.subprocess.run = self.fake_run
        tick.main_checkout = lambda: self.main
        tick.PROJECTS = self.tmp / "claude-projects"  # where Claude Code keeps transcripts (C9 section 16)
        shutil.rmtree(tick.PROJECTS, ignore_errors=True)
        self.run_tick()  # the first run of a loop: saves the snapshot the rows compare against

    def tearDown(self):
        tick.subprocess.run = self.real_run

    def fake_run(self, cmd, *a, **kw):
        if list(cmd[:3]) == ["claude", "agents", "--json"]:
            if self.rows is None:
                return subprocess.CompletedProcess(cmd, 1, "", "daemon not running")
            return subprocess.CompletedProcess(cmd, 0, json.dumps(self.rows), "")
        return self.real_run(cmd, *a, **kw)

    def run_tick(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(tick.main([]), 0)
        return out.getvalue().splitlines()

    def row(self, sid, status, name="sandbox-t37", cwd=None, **extra):
        return {"id": sid, "name": name, "cwd": str(cwd or self.t1), "kind": "background", "status": status, **extra}

    def test_an_idle_timer_turn_ends_on_exactly_nothing_changed(self):
        """The skill ends a timer turn only on this exact line; any other output costs a full turn."""
        self.assertEqual(self.run_tick(), ["nothing changed"])

    def test_the_first_run_is_a_change(self):
        """A missing snapshot (a fresh orchestrator, a reinstall) must not read as nothing changed."""
        (self.coord / tick.SNAPSHOT).unlink()
        self.assertEqual(self.run_tick(), ["no earlier snapshot: a full turn reads everything"])

    def test_a_new_message_shows_once(self):
        """A READY that lands while the orchestrator is idle must start a turn, and only one."""
        (self.inbox / "20261017T102000Z-sandbox-t37.md").write_text(message(), encoding="utf-8")
        self.assertEqual(self.run_tick(), ["message 20261017T102000Z-sandbox-t37.md"])
        self.assertEqual(self.run_tick(), ["nothing changed"])

    def test_a_half_written_message_shows_again_when_finished(self):
        """C9 section 3: a message still being written is not acted on; when its end line lands, the next
        check must report it, or the READY waits until something else wakes the loop."""
        path = self.inbox / "20261017T102000Z-sandbox-t37.md"
        path.write_text(message(complete=False), encoding="utf-8")
        self.assertEqual(self.run_tick(), ["message 20261017T102000Z-sandbox-t37.md (incomplete)"])
        path.write_text(message(), encoding="utf-8")
        self.assertEqual(self.run_tick(), ["message 20261017T102000Z-sandbox-t37.md"])

    def test_a_message_whose_front_matter_does_not_parse_is_incomplete(self):
        """C9 section 3 (issue #98): the end line alone is not enough; the reader (`formats.complete`) also
        needs the front matter to parse. Counted complete here, a broken message never reached Needs you."""
        path = self.inbox / "20261017T102000Z-sandbox-t37.md"
        path.write_text(message().replace("kind: ready", "  kind: ready"), encoding="utf-8")
        self.assertEqual(self.run_tick(), ["message 20261017T102000Z-sandbox-t37.md (incomplete)"])

    def test_a_message_left_incomplete_shows_a_second_time_then_rests(self):
        """C9 section 3: two turns on, a broken message goes under Needs you. With no other activity the
        second look must still start a turn (review round 1 on PR #86), and later ones must not."""
        path = self.inbox / "20261017T102000Z-sandbox-t37.md"
        path.write_text(message(complete=False), encoding="utf-8")
        self.assertEqual(self.run_tick(), ["message 20261017T102000Z-sandbox-t37.md (incomplete)"])
        self.assertEqual(self.run_tick(), ["message 20261017T102000Z-sandbox-t37.md (still incomplete)"])
        self.assertEqual(self.run_tick(), ["nothing changed"])
        path.write_text(message(), encoding="utf-8")
        self.assertEqual(self.run_tick(), ["message 20261017T102000Z-sandbox-t37.md"])

    def test_a_stuck_read_through_does_not_wake_every_turn(self):
        """Issue #75's note from #68: `read_through` stays before a broken message, so `formats.py unread`
        lists the later ones again every turn. The check reports each file once, so a broken message
        does not cost a full turn every 15 minutes."""
        (self.inbox / "20261017T100000Z-sandbox-t36.md").write_text(message(complete=False), encoding="utf-8")
        (self.inbox / "20261017T102000Z-sandbox-t37.md").write_text(message(), encoding="utf-8")
        self.assertEqual(len(self.run_tick()), 2)
        self.assertEqual(self.run_tick(), ["message 20261017T100000Z-sandbox-t36.md (still incomplete)"])
        self.assertEqual(self.run_tick(), ["nothing changed"])

    def test_a_builder_that_dies_before_any_listing_is_noticed(self):
        """Review round 1 on PR #86: the loop takes its snapshot before it launches, so a builder that
        dies before the next check is in neither listing and never reads as gone; its launch record is
        the change that starts the turn whose TAKEOVER step finds it absent."""
        record = self.coord / "launches/launch-20261017T103000Z-t37-abc1234-1a2b.json"
        record.parent.mkdir(parents=True)
        record.write_text("{}", encoding="utf-8")
        self.assertEqual(self.run_tick(), [f"record launches/{record.name}"])

    def test_records_under_merges_and_verdicts(self):
        """A verdict, a merge record and a finished merge's marker going away are each a loop step."""
        marker = self.coord / "merges/in-progress-12.json"
        marker.parent.mkdir(parents=True)
        marker.write_text("{}", encoding="utf-8")
        verdict = self.coord / "verdicts/t37/round-1.json"
        verdict.parent.mkdir(parents=True)
        verdict.write_text("{}", encoding="utf-8")
        (self.coord / "merges/notes.md.tmp-99").write_text("half", encoding="utf-8")  # C4 rule 3's temp
        self.assertEqual(self.run_tick(), ["record merges/in-progress-12.json", "record verdicts/t37/round-1.json"])
        marker.unlink()
        (self.coord / "merges/merge-x.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.run_tick(), ["record merges/merge-x.json", "record removed merges/in-progress-12.json"])

    def test_a_pending_notice_shows_until_it_is_sent(self):
        """A notice is the user's only news while away; one left unsent must keep the loop turning."""
        name = notices.write(self.coord, "escalation", "t37 needs you").name
        self.assertEqual(self.run_tick(), [f"notice {name}"])
        self.assertEqual(self.run_tick(), [f"notice {name}"])
        notices.mark_sent(self.coord, name, "sent")
        self.assertEqual(self.run_tick(), ["nothing changed"])

    def test_sessions_waiting_and_gone(self):
        """A builder stuck on a prompt sends no message (test I 6b, 6c), and a crashed one sends nothing at
        all: only the listing shows them. Another project's sessions are not this loop's."""
        self.rows = [self.row("aaaa1111", "busy"), self.row("bbbb2222", "busy", "other-t1", cwd=self.tmp / "else")]
        self.assertEqual(self.run_tick(), ["nothing changed"])
        self.rows = [self.row("aaaa1111", "waiting", waitingFor="permission prompt")]
        self.assertEqual(self.run_tick(), ["session sandbox-t37 (aaaa1111) waiting: permission prompt"])
        self.assertEqual(self.run_tick(), ["nothing changed"])
        self.rows = [self.row("aaaa1111", "idle")]
        self.assertEqual(self.run_tick(), ["session sandbox-t37 (aaaa1111) no longer waiting"])
        self.rows = []
        self.assertEqual(self.run_tick(), ["session sandbox-t37 (aaaa1111) gone"])

    def test_a_failed_listing_is_a_change_and_not_a_crash(self):
        """A listing that fails cannot say nothing changed; and it must not report every session gone,
        or the loop would take over builders that are still working."""
        self.rows = [self.row("aaaa1111", "busy")]
        self.run_tick()
        self.rows = None
        lines = self.run_tick()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("sessions unknown: claude agents --json exited 1"), lines)
        self.rows = [self.row("aaaa1111", "busy")]
        self.assertEqual(self.run_tick(), ["nothing changed"])

    def escalated(self, hours_ago, ticket=37, answer=None):
        """An escalation record written `hours_ago`, as escalate.py writes it; with `answer`, its answer too."""
        eid = f"escalation-20261017T100000Z-t{ticket}-abc1234-{ticket:04x}"
        merges = self.coord / "merges"
        merges.mkdir(parents=True, exist_ok=True)
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - hours_ago * 3600))
        (merges / f"{eid}.md").write_text(f"---\nformat: escalation\nversion: 1\nid: {eid}\nticket: {ticket}\n"
                                          f"trigger: approach\nwritten_at: {at}\n---\n", encoding="utf-8")
        if answer:
            (merges / f"answer-{eid}.md").write_text(f"---\nescalation: {eid}\nanswer: {answer}\n---\n",
                                                     encoding="utf-8")

    def transcript(self, sid, minutes_ago):
        """The session's transcript, last written `minutes_ago` (its last turn)."""
        path = self.tmp / "claude-projects" / "C--proj-t37" / f"{sid}-full.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        stamp = time.time() - minutes_ago * 60
        os.utime(path, (stamp, stamp))

    def escalation_lines(self):
        return [line for line in self.run_tick() if line.startswith("escalated ")]

    def test_an_escalated_idle_builder_gets_a_keepalive_before_its_cache_expires(self):
        """Decision 123: an escalated builder waits idle with its context; its prompt cache lasts an hour
        (C9 section 16), and a quiet timer turn ends on `nothing changed`, so only this line starts the
        turn that sends the keepalive. Once the keepalive's turn writes the transcript, it rests."""
        self.escalated(hours_ago=1)
        self.rows = [self.row("aaaa1111", "idle", sessionId="aaaa1111-full")]
        self.assertEqual(self.escalation_lines(), ["escalated sandbox-t37 (aaaa1111) idle unknown: keepalive"])
        self.transcript("aaaa1111", minutes_ago=50)
        self.assertEqual(self.escalation_lines(), ["escalated sandbox-t37 (aaaa1111) idle 50 min: keepalive"])
        self.transcript("aaaa1111", minutes_ago=0)  # the keepalive's one-line turn
        self.assertEqual(self.run_tick(), ["nothing changed"])
        self.transcript("aaaa1111", minutes_ago=35)
        self.assertEqual(self.run_tick(), ["nothing changed"])
        self.transcript("aaaa1111", minutes_ago=41)  # past 40: a 15-minute clock still nudges by minute 55
        self.assertEqual(self.escalation_lines(), ["escalated sandbox-t37 (aaaa1111) idle 41 min: keepalive"])

    def test_a_builder_that_waited_past_the_cap_hands_off(self):
        """Decision 123: past `sessions.escalation_wait_hours` the builder hands off, idle or not recently
        nudged; 0 means at once. A successor (`-2`) is the same ticket's builder; t371 is not t37's."""
        self.transcript("aaaa1111", minutes_ago=1)
        self.escalated(hours_ago=9)
        self.rows = [self.row("aaaa1111", "idle", name="sandbox-t37-2", sessionId="aaaa1111-full"),
                     self.row("cccc3333", "idle", name="sandbox-t371", sessionId="cccc3333-full")]
        self.assertEqual(self.escalation_lines(), ["escalated sandbox-t37-2 (aaaa1111) waited 9.0 h: hand off"])
        config = self.main / "agent-kit.toml"
        saved = config.read_text(encoding="utf-8")
        self.assertIn("escalation_wait_hours = 8.0", saved)
        config.write_text(saved.replace("escalation_wait_hours = 8.0", "escalation_wait_hours = 0"), encoding="utf-8")
        try:
            shutil.rmtree(self.coord / "merges")
            self.escalated(hours_ago=0)
            self.assertEqual(self.escalation_lines(), ["escalated sandbox-t37-2 (aaaa1111) waited 0.0 h: hand off"])
        finally:
            config.write_text(saved, encoding="utf-8")

    def test_an_answered_escalation_or_a_busy_builder_is_not_escalated(self):
        """The answer wakes the builder (decision 123 rule 4): a keepalive after it, or to a builder at
        work, would cost a turn for nothing."""
        self.transcript("aaaa1111", minutes_ago=50)
        self.escalated(hours_ago=9, answer="fix")
        self.rows = [self.row("aaaa1111", "idle", sessionId="aaaa1111-full")]
        self.assertEqual(self.escalation_lines(), [])
        shutil.rmtree(self.coord / "merges")
        self.escalated(hours_ago=1)
        self.rows = [self.row("aaaa1111", "busy", sessionId="aaaa1111-full")]
        self.assertEqual(self.escalation_lines(), [])

    def test_an_error_is_a_change(self):
        """A broken config must not end every timer turn on `nothing changed`."""
        config = self.main / "agent-kit.toml"
        saved = config.read_text(encoding="utf-8")
        config.write_text(saved + "\nnot toml [\n", encoding="utf-8")
        try:
            lines = self.run_tick()
        finally:
            config.write_text(saved, encoding="utf-8")
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("check failed: "), lines)


if __name__ == "__main__":
    unittest.main()
