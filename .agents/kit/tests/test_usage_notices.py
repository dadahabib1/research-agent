"""The usage record and the notice files (contract C6 sections 4 and 7), one row per failure each catches.
The real path, a background session whose status line keeps the record, is agent-kit's live test
`tests/test_live_launch.py`.

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "bin"))

import notices  # noqa: E402
import usage  # noqa: E402

STATUS = {"session_id": "s1", "rate_limits": {"five_hour": {"used_percentage": 8, "resets_at": 100},
                                              "seven_day": {"used_percentage": 62, "resets_at": 200}},
          "context_window": {"used_percentage": 4}}


class Usage(unittest.TestCase):
    def setUp(self):
        self.coord = Path(tempfile.mkdtemp())

    def test_the_record_takes_the_larger_window(self):
        """The 95% stop must apply when either window is near its limit (C6 section 4)."""
        line = usage.statusline(self.coord, json.dumps(STATUS))
        data = json.loads((self.coord / "usage/claude.json").read_text(encoding="utf-8"))
        self.assertEqual(data["percent"], 62)
        self.assertEqual((data["format"], data["id"], data["session_id"]), ("usage", "usage-claude", "s1"))
        self.assertEqual(line, "usage 62% · context 4%")

    def test_an_input_without_rate_limits_keeps_the_last_reading(self):
        """The status line runs before the first response too (context `null`, test I 4b); that call must
        not wipe the reading the launch relies on."""
        usage.statusline(self.coord, json.dumps(STATUS))
        before = (self.coord / "usage/claude.json").read_text(encoding="utf-8")
        self.assertEqual(usage.statusline(self.coord, json.dumps({"session_id": "s1"})), "usage -")
        self.assertEqual((self.coord / "usage/claude.json").read_text(encoding="utf-8"), before)

    def test_a_bad_input_never_fails_the_status_line(self):
        """A status line that errors shows nothing useful and can repeat on every refresh: input that is
        not JSON, and JSON of an unexpected shape."""
        for text in ("{not json", '{"rate_limits": "unexpected"}'):
            with self.subTest(text=text):
                r = subprocess.run([sys.executable, "-I", str(KIT / "bin/usage.py"), "statusline", str(self.coord)],
                                   input=text, capture_output=True, text=True)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, "usage ?"))

    def test_a_missing_or_stale_reading_is_unknown(self):
        """A reading the orchestrator stopped refreshing must not keep blocking or allowing launches."""
        self.assertEqual(usage.read(self.coord), (None, None))
        usage.statusline(self.coord, json.dumps(STATUS))
        now = datetime.now(timezone.utc)
        self.assertEqual(usage.read(self.coord, now)[0], 62)
        self.assertEqual(usage.read(self.coord, now + timedelta(minutes=29, seconds=59))[0], 62)
        self.assertEqual(usage.read(self.coord, now + timedelta(minutes=30, seconds=30)), (None, None))
        (self.coord / "usage/claude.json").write_text("{half", encoding="utf-8")
        self.assertEqual(usage.read(self.coord), (None, None))

    def test_the_warning_is_written_once_per_window_reset(self):
        """Issue #45 AC6: the status line refreshes every few seconds; at 80% you get one notice per window
        reset, not one per refresh, and a new reset warns again. A real 80% cannot be planted live."""
        def status(five, resets):
            return json.dumps({"session_id": "s1", "rate_limits": {"five_hour": {"used_percentage": five, "resets_at": resets},
                                                                   "seven_day": {"used_percentage": 40, "resets_at": 200}}})
        warned = lambda: sorted((self.coord / "notices").glob("*-usage-warn-*.md"))
        self.assertEqual(usage.statusline(self.coord, status(79, 1_800_000_000), warn_at=80), "usage 79%")
        self.assertEqual(warned(), [])
        self.assertIn("usage notice written", usage.statusline(self.coord, status(80, 1_800_000_000), warn_at=80))
        for _ in range(3):
            self.assertNotIn("notice", usage.statusline(self.coord, status(91, 1_800_000_000), warn_at=80))
        self.assertEqual(len(warned()), 1)
        line = warned()[0].read_text(encoding="utf-8").splitlines()[-1]
        self.assertIn("80% of your plan's 5-hour limit", line)
        self.assertIn("2027-01-15 08:00 UTC", line)  # 1,800,000,000 s
        usage.statusline(self.coord, status(85, 1_800_018_000), warn_at=80)  # the next window
        self.assertEqual(len(warned()), 2)
        r = subprocess.run([sys.executable, "-I", str(KIT / "bin/usage.py"), "statusline", str(self.coord), "--warn-at", "80"],
                           input=status(99, 1_800_036_000), capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "usage 99% · usage notice written"))
        self.assertEqual(len(warned()), 3)


class Notices(unittest.TestCase):
    def setUp(self):
        self.coord = Path(tempfile.mkdtemp())

    def test_written_once_sent_once(self):
        """One writer per file (C4 rules 4, 5): the producer's notice is never rewritten; sending is the
        orchestrator's own file, and a notice is sent once."""
        path = notices.write(self.coord, "usage-stop", "95% used: no new sessions start")
        text = path.read_text(encoding="utf-8")
        self.assertIn("kind: usage-stop", text)
        self.assertEqual(notices.pending(self.coord), [path.name])
        notices.mark_sent(self.coord, path.name, "sent")
        self.assertEqual(notices.pending(self.coord), [])
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        with self.assertRaises(FileExistsError):
            notices.mark_sent(self.coord, path.name, "sent")

    def test_two_notices_in_one_second_are_both_kept(self):
        """A notice must never overwrite another (a usage stop refused twice in one second), also when two
        producers write at the same moment (PR #49 review: checking for a free name, then writing, races)."""
        a = notices.write(self.coord, "usage-stop", "first")
        b = notices.write(self.coord, "usage-stop", "second")
        self.assertNotEqual(a, b)
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(lambda i: notices.write(self.coord, "usage-stop", f"refused start {i}"), range(32)))
        self.assertEqual(len(notices.pending(self.coord)), 34)

    def test_the_command_prints_the_notice(self):
        """C6 section 7: the producer writes the notice and prints it, so whoever ran the command sees the
        news, not only a file name (PR #49 review round 2)."""
        r = subprocess.run([sys.executable, "-I", str(KIT / "bin/notices.py"), "write", str(self.coord), "usage-stop",
                            "95% used: no new sessions start"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("95% used: no new sessions start", r.stdout)
        self.assertRegex(r.stdout, r"usage-stop-[0-9a-f]{8}\.md")

    def test_a_notice_is_one_short_line(self):
        """Phones cut long notices (the tool's 200-character rule); a kind names the file."""
        with self.assertRaises(ValueError):
            notices.write(self.coord, "merge", "x" * 200)
        with self.assertRaises(ValueError):
            notices.write(self.coord, "Bad Kind", "x")
        self.assertTrue(notices.write(self.coord, "merge", "line one\nline two").read_text(encoding="utf-8")
                        .endswith("line one line two\n"))


if __name__ == "__main__":
    unittest.main()
