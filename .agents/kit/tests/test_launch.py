"""The launch script's rules a live start cannot reach cheaply (contract C6), one row per failure it
catches. The real path, a builder started in a real background session, is agent-kit's live test
`tests/test_live_launch.py`.

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
"""

import contextlib
import io
import json
import re
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "bin"))
sys.path.insert(0, str(KIT / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import launch  # noqa: E402
from test_guard import Project, git  # noqa: E402  (its scratch project: schema, config, main, worktrees)


class Rules(unittest.TestCase):
    def test_autocompact_thirteen_points_above_handoff_and_never_below_the_flags_minimum(self):
        """Decision 115: the barrier reads one response behind (M77), automatic compaction fires 21,700-35,100
        tokens below the size (M83), and one response grew up to 8.9 points in real transcripts, so the net
        sits 13 points above the handoff: 13 - 3.5 > 8.9. The 100,000 floor (M58) holds for a small window."""
        self.assertEqual(launch.autocompact(55, 1_000_000), 680_000)
        self.assertEqual(launch.autocompact(45, 1_000_000), 580_000)
        self.assertEqual(launch.autocompact(2, 1_000_000), 150_000)
        self.assertEqual(launch.autocompact(2, 500_000), 100_000)

    def test_every_allowed_handoff_gives_a_valid_autocompact(self):
        """PR #64 review: with +10, a handoff the schema allowed (95) gave 1,050,000, above the flag's
        1,000,000 maximum (M58), so a valid config made every launch fail."""
        schema = launch.kitconfig.tomllib.loads((KIT / "config/schema.toml").read_text(encoding="utf-8"))
        window = schema["fixed"]["claude_context_window"]
        for role in ("orchestrator", "builder"):  # the roles the launch passes --autocompact to
            top = schema["key"][f"context.{role}.handoff"]["max"]
            with self.subTest(role=role, handoff=top):
                self.assertLessEqual(launch.autocompact(top, window), 1_000_000)

    def test_add_dir_cannot_swallow_the_prompt(self):
        """`--add-dir` takes several values: followed directly by the prompt, it would read the prompt as a
        directory and start the session with none."""
        cmd = launch.claude_command(name="p-t1", model="m", effort="low", compact=600000, settings="{}",
                                    coordination=Path("C:/c"), prompt="do it")
        i = cmd.index("--add-dir")
        self.assertTrue(cmd[i + 2].startswith("--"), cmd)
        self.assertEqual(cmd[-1], "do it")
        self.assertEqual(cmd[:2], ["claude", "--bg"])

    def test_secret_files_outside_the_project_are_refused(self):
        """C3 accepts absolute and `..` paths for `secret_files`; they have no place in a worktree."""
        launch.check_secret_entries([".env", "config/keys.env"])
        for entry in ("C:/keys/project.env", "../keys/project.env", "/etc/keys.env"):
            with self.subTest(entry=entry), self.assertRaises(launch.Refused):
                launch.check_secret_entries([entry])

    def test_effort_lowers_one_level_from_lower_effort_at(self):
        """Decision 53: max → xhigh → high → medium → low; low stays; under the level, or unknown, nothing."""
        values = {"usage.lower_effort_at": (80, "default")}
        self.assertEqual(launch.lowered("max", 80, values), ("xhigh", "max"))
        self.assertEqual(launch.lowered("medium", 94, values), ("low", "medium"))
        self.assertEqual(launch.lowered("low", 99, values), ("low", None))
        self.assertEqual(launch.lowered("xhigh", 79.9, values), ("xhigh", None))
        self.assertEqual(launch.lowered("xhigh", None, values), ("xhigh", None))

    def test_free_memory_is_read_here_and_unknown_elsewhere(self):
        """AC3: a reading on Windows and Linux; on any other system `memory unknown`, which passes."""
        if sys.platform in ("win32", "linux"):
            self.assertTrue(0 < launch.free_memory_gb() < 4096)
        if Path("/proc/meminfo").exists():
            return  # Linux: no "elsewhere" to imitate
        saved = launch.sys.platform
        launch.sys.platform = "darwin"
        try:
            self.assertIsNone(launch.free_memory_gb())
        finally:
            launch.sys.platform = saved


class WithRemote(Project):
    """The scratch project from test_guard (schema, config, a main checkout on main, worktrees) with a
    local remote."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.remote = cls.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(cls.remote)], check=True)
        git(cls.main, "remote", "add", "origin", str(cls.remote))
        git(cls.main, "push", "-q", "-u", "origin", "main")
        cls.coord = cls.main / ".coordination"

    rows = []  # what `claude agents --json` lists, for the rows that need sessions

    def setUp(self):
        """The scratch project has no guard entries, and these rows are not about the guard, the name or
        free memory: checks 2-4 refuse for real in tests/test_live_checks.py. Real free memory here sits
        near the 3.0 default floor, so reading it made these rows fail at random."""
        self.saved_checks = launch.selftest, launch.session_rows, launch.free_memory_gb
        launch.selftest, launch.session_rows = (lambda main: []), (lambda cwd: list(self.rows))
        launch.free_memory_gb = lambda: 8.0

    def tearDown(self):
        launch.selftest, launch.session_rows, launch.free_memory_gb = self.saved_checks
        self.rows = []

    def plant_usage(self, percent, minutes_old=0):
        observed = datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
        launch.workfiles.write_atomic(self.coord / "usage/claude.json", json.dumps(
            {"format": "usage", "version": 1, "id": "usage-claude", "observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "session_id": "x", "five_hour": {"used_percentage": percent}, "seven_day": None, "percent": percent}))
        self.addCleanup(lambda: (self.coord / "usage/claude.json").unlink(missing_ok=True))


class InAProject(WithRemote):
    def values(self):
        return launch.kitconfig.effective(self.main)

    def test_the_role_travels_in_settings(self):
        """A background session inherits the service's environment, not the launcher's (M53): the role must
        be in `--settings` env, with main's guard pinned."""
        settings = launch.session_settings(self.main, "builder", self.values())
        self.assertEqual(settings["env"]["KIT_ROLE"], "builder")
        self.assertEqual(settings["env"]["CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP"], "1")
        self.assertFalse(settings["disableAllHooks"])
        pre = settings["hooks"]["PreToolUse"][0]["hooks"][0]
        self.assertIn((self.main / ".agents/kit/hooks/guard.py").as_posix(), pre["args"])
        self.assertTrue(settings["autoMode"]["environment"])

    def test_only_the_orchestrator_turns_off_background_isolation(self):
        """A background successor writes the coordination folder in the main checkout; Claude Code refuses its
        Write and Edit there until this switch is off (M134, decision 124). A builder keeps the isolation."""
        orchestrator = launch.session_settings(self.main, "orchestrator", self.values())
        self.assertEqual(orchestrator.get("worktree"), {"bgIsolation": "none"})
        self.assertNotIn("worktree", launch.session_settings(self.main, "builder", self.values()))

    def test_the_orchestrator_keeps_its_auto_memory(self):
        """Issue #160 (the Orchestrator memory row): the orchestrator keeps Claude Code's auto memory, as
        before; only builders lose it. A key set for every role would end the orchestrator's memory."""
        orchestrator = launch.session_settings(self.main, "orchestrator", self.values())
        self.assertNotIn("autoMemoryEnabled", orchestrator)
        self.assertNotIn("CLAUDE_CODE_DISABLE_AUTO_MEMORY", orchestrator["env"])
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", orchestrator["env"])

    def test_a_builder_has_no_question_tool(self):
        """B2's green run 1018055952: an unattended builder asked AskUserQuestion and waited on it; a builder reaches
        you through the orchestrator (a blocked or escalate message, C9 section 4)."""
        builder = launch.session_settings(self.main, "builder", self.values())
        self.assertIn("AskUserQuestion", builder.get("permissions", {}).get("deny", []))
        orchestrator = launch.session_settings(self.main, "orchestrator", self.values())
        self.assertNotIn("AskUserQuestion", orchestrator.get("permissions", {}).get("deny", []))

    def record(self, ticket, session_id):
        path = self.coord / "launches" / f"launch-x-t{ticket}.json"
        launch.workfiles.write_atomic(path, json.dumps({"ticket": ticket, "session_id": session_id}))
        return path

    def test_an_existing_worktree_is_reused_only_when_no_session_worked_there(self):
        """A first start that failed (trust) leaves its worktree; a retry reuses it. A worktree a session
        worked in belongs to a successor."""
        first, _, _ = launch.make_worktree(self.main, self.coord, 7, None)
        self.assertTrue((first / ".git").exists())
        self.assertEqual(git_out(first, "branch", "--show-current"), "t7")
        self.record(7, None)  # a record with no session: nothing ran there
        again, _, _ = launch.make_worktree(self.main, self.coord, 7, None)
        self.assertEqual(again, first)
        self.record(7, "abc-session")
        with self.assertRaises(launch.Refused) as e:
            launch.make_worktree(self.main, self.coord, 7, None)
        self.assertIn("--successor", str(e.exception))

    def test_a_failure_after_the_start_stops_the_session_and_writes_no_record(self):
        """Once `claude` ran, a failure (here, the record cannot be written) must not leave a session working
        unrecorded, and must not claim nothing was started (C6 section 1)."""
        stopped = []
        saved = launch.start_background, launch.stop, launch.workfiles.write_atomic
        launch.start_background = lambda cmd, cwd, name: ("1234abcd", "1234abcd-full")
        launch.stop = lambda who, cwd: stopped.append(who) or True

        def no_write(path, text):
            raise OSError("disk full")
        launch.workfiles.write_atomic = no_write
        try:
            args = SimpleNamespace(ticket=8, base=None, effort=None, reason=None, prompt="x", check=False, successor=None)
            with self.assertRaises(SystemExit) as e:
                launch.builder(args, self.main)
        finally:
            launch.start_background, launch.stop, launch.workfiles.write_atomic = saved
        self.assertEqual(e.exception.code, 2)
        self.assertEqual(stopped, ["1234abcd"])
        self.assertEqual(list((self.coord / "launches").glob("*t8*")), [])
        self.assertTrue((self.main / ".claude/worktrees/t8").is_dir())


def write_brief(coordination, ticket, refresh):
    """`briefs/t<n>.md` from the kit's brief template, its `refresh:` line set: the field the launch reads."""
    template = (KIT / "templates/brief.md").read_text(encoding="utf-8")
    brief, count = re.subn(r"^refresh: <[^>\n]*>$", f"refresh: {refresh}", template, flags=re.M)
    assert count == 1, "the brief template has no `refresh: <...>` line"
    launch.workfiles.write_atomic(coordination / "briefs" / f"t{ticket}.md", brief)


class FakeClaude:
    """`claude` as a background start, `claude agents --json` and `claude stop` meet it; git runs for real.
    Only what the launch reads from Claude Code is faked, from what M48, M50 and M69 measured."""

    def __init__(self, start_exit=0, printed=None, rows=(), agents_error=False, stop_error=False):
        self.start_exit, self.printed, self.rows = start_exit, printed, list(rows)
        self.agents_error, self.stop_error, self.stopped = agents_error, stop_error, []
        self.real = subprocess.run

    def __call__(self, cmd, *a, **kw):
        cmd = [str(c) for c in cmd]
        if cmd[0] != "claude":
            return self.real(cmd, *a, **kw)
        if cmd[1:2] == ["--bg"]:
            self.started = cmd
            out = "Starting background service…\n" + (f"backgrounded · {self.printed} · x\n" if self.printed else "")
            return subprocess.CompletedProcess(cmd, self.start_exit, out, "")
        if cmd[1:3] == ["agents", "--json"]:
            if self.agents_error:
                raise OSError("claude agents failed")
            return subprocess.CompletedProcess(cmd, 0, json.dumps(self.rows), "")
        if cmd[1:2] == ["stop"]:
            if self.stop_error:
                raise OSError("claude stop failed")
            self.stopped.append(cmd[2])
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "2.1.301 (Claude Code)", "")


class AfterStart(WithRemote):
    """Review round 1 on PR #48: a start whose session cannot be identified must not report `Nothing was
    started` while a session may be working (C6 section 1)."""

    def launch(self, fake, ticket):
        saved_run, saved_wait = launch.subprocess.run, launch.ID_WAIT
        launch.subprocess.run, launch.ID_WAIT = fake, 1
        try:
            args = SimpleNamespace(ticket=ticket, base=None, effort=None, reason=None, prompt="x", check=False, successor=None)
            with self.assertRaises(SystemExit) as e:
                launch.builder(args, self.main)
            return e.exception.code
        finally:
            launch.subprocess.run, launch.ID_WAIT = saved_run, saved_wait

    def test_exit_1_with_no_id_is_a_failure_after_the_start(self):
        """M69: the start that starts the background service can exit 1, print no id, and run."""
        fake = FakeClaude(start_exit=1, rows=[{"id": "9999aaaa", "name": "sandbox-t11", "sessionId": None}])
        self.assertEqual(self.launch(fake, 11), 2)
        self.assertEqual(fake.stopped, ["9999aaaa"])
        self.assertEqual(list((self.coord / "launches").glob("*-t11-*")), [])

    def test_a_failing_lookup_still_stops_the_printed_session(self):
        fake = FakeClaude(printed="1234abcd", agents_error=True)
        self.assertEqual(self.launch(fake, 12), 2)
        self.assertEqual(fake.stopped, ["1234abcd"])

    def test_a_failing_stop_still_says_how_to_stop_it(self):
        fake = FakeClaude(printed="1234abcd", agents_error=True, stop_error=True)
        self.assertEqual(self.launch(fake, 13), 2)

    def test_the_record_fingerprints_the_settings_it_passed(self):
        """Review round 2: the record's `settings_sha256` must match the `--settings` the session got."""
        fake = FakeClaude(printed="5678abcd", rows=[{"id": "5678abcd", "name": "sandbox-t15", "sessionId": "full-id"}])
        saved = launch.subprocess.run
        launch.subprocess.run = fake
        try:
            launch.builder(SimpleNamespace(ticket=15, base=None, effort=None, reason=None, prompt="x", check=False, successor=None), self.main)
        finally:
            launch.subprocess.run = saved
        passed = fake.started[fake.started.index("--settings") + 1]
        record = json.loads(next((self.coord / "launches").glob("*-t15-*")).read_text(encoding="utf-8"))
        self.assertEqual(record["settings_sha256"], launch.sha256(passed))
        self.assertEqual(json.loads(passed)["env"]["KIT_ROLE"], "builder")

    def test_a_builder_keeps_no_auto_memory_and_a_refresh_builders_subagents_run_on_sonnet(self):
        """Issue #160 (the Builder memory and Refresh rows), read from the `--settings` the fake `claude`
        receives. Auto memory is per repository and shared by its worktrees, so a builder's note would load
        unreviewed into the orchestrator: both keys turn it off (Claude Code 2.1.319 reads the setting and the
        variable). A refresh ticket's builder (its brief's `refresh: yes`) runs the skill's refresh, whose
        investigation subagents would inherit the builder's model and effort: they run on Sonnet."""
        write_brief(self.coord, 41, "no")
        write_brief(self.coord, 42, "yes")
        for ticket, subagents in ((40, None), (41, None), (42, "sonnet")):  # t40 has no brief: an ordinary ticket
            with self.subTest(ticket=ticket):
                _, _, fake = self.start(ticket)
                settings = json.loads(fake.started[fake.started.index("--settings") + 1])
                self.assertIs(settings["autoMemoryEnabled"], False)
                self.assertEqual(settings["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
                self.assertEqual(settings["env"].get("CLAUDE_CODE_SUBAGENT_MODEL"), subagents)
                self.assertEqual(settings["env"]["KIT_ROLE"], "builder")

    def start(self, ticket, check=False):
        """(result, printed lines, fake) of one builder start with a session that is found at once."""
        fake = FakeClaude(printed="5678abcd", rows=[{"id": "5678abcd", "name": f"sandbox-t{ticket}", "sessionId": "full"}])
        saved, out = launch.subprocess.run, io.StringIO()
        launch.subprocess.run = fake
        try:
            with contextlib.redirect_stdout(out):
                args = SimpleNamespace(ticket=ticket, base=None, effort=None, reason=None, prompt="x", check=check, successor=None)
                return launch.builder(args, self.main), out.getvalue(), fake
        finally:
            launch.subprocess.run = saved

    def record_of(self, ticket):
        return json.loads(next((self.coord / "launches").glob(f"*-t{ticket}-*")).read_text(encoding="utf-8"))

    def files(self):
        return {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in self.tmp.rglob("*") if p.is_file()}

    def test_from_lower_effort_at_a_new_session_runs_one_level_lower(self):
        """AC2: at 82% (default level 80) the builder's xhigh becomes high, in the command and the record."""
        self.plant_usage(82, minutes_old=4)
        _, printed, fake = self.start(16)
        self.assertEqual(fake.started[fake.started.index("--effort") + 1], "high")
        record = self.record_of(16)
        self.assertEqual((record["effort"], record["effort_lowered_from"]), ("high", "xhigh"))
        self.assertEqual(record["usage"], {"percent": 82, "age_minutes": 4})
        self.assertIn("effort: high, lowered from xhigh", printed)

    def test_an_unknown_usage_starts_and_says_so(self):
        """AC2: a record older than 30 minutes, or one that does not parse, is `usage unknown`: the start
        goes on at full effort and the record keeps `usage: null`."""
        for ticket, plant in ((17, lambda: self.plant_usage(99, minutes_old=31)),
                              (18, lambda: launch.workfiles.write_atomic(self.coord / "usage/claude.json", "{"))):
            with self.subTest(ticket=ticket):
                plant()
                _, printed, _ = self.start(ticket)
                record = self.record_of(ticket)
                self.assertEqual((record["usage"], record["effort"], record["effort_lowered_from"]), (None, "xhigh", None))
                self.assertIn("usage: usage unknown", printed)

    def test_check_prints_every_line_and_writes_nothing(self):
        """AC4: `--check` at 82% prints checks 1-5 and the lowered effort; at 95% it reports the refusal and
        writes no notice. Neither fetches, makes a worktree or starts a session."""
        for percent in (82, 95):
            with self.subTest(percent=percent):
                self.plant_usage(percent)
                before = self.files()
                fake = None
                try:
                    result, printed, fake = self.start(19, check=True)
                    self.assertEqual(percent, 82, "95% must refuse")
                    self.assertIn("would pass checks 1-5", result)
                    self.assertIn("effort: high, lowered from xhigh", printed)
                except launch.Refused as e:
                    self.assertEqual(percent, 95, str(e))
                    self.assertTrue(str(e).startswith("REFUSED (usage): usage 95%"), str(e))
                self.assertEqual(self.files(), before)
                self.assertFalse(hasattr(fake, "started") if fake else False)

    def test_the_usage_stop_lifts_once_a_fresh_record_is_lower(self):
        """Issue #46: refused at 96%, then a fresh record at 50% starts the same launch. The stop is read
        from each launch's own reading, never held over from an earlier refusal or its notice (a hold that
        never released was munder-difflin's failure)."""
        self.plant_usage(96)
        with self.assertRaises(launch.Refused) as e:
            self.start(21)
        self.assertTrue(str(e.exception).startswith("REFUSED (usage): usage 96%"), str(e.exception))
        self.assertEqual(len(list((self.coord / "notices").glob("*-usage-stop-*.md"))), 1)
        self.assertFalse((self.main / ".claude/worktrees/t21").exists())
        self.plant_usage(50)
        result, printed, fake = self.start(21)
        self.assertIn("usage: 50%", printed)
        self.assertTrue(result.startswith("launched sandbox-t21 full "), result)
        self.assertEqual(fake.started[fake.started.index("--effort") + 1], "xhigh")
        self.assertEqual(self.record_of(21)["usage"], {"percent": 50, "age_minutes": 0})

    def test_a_successor_passes_the_usage_stop(self):
        """C6 section 4: from `usage.no_new_sessions_at` only a replacement starts."""
        self.plant_usage(97)
        with contextlib.redirect_stdout(io.StringIO()):
            found = launch.checks(self.main, lambda v, rows: "sandbox-orch-2", successor=True, check_only=False)
        self.assertEqual(found["percent"], 97)
        self.assertFalse((self.coord / "notices").exists())

    def test_the_default_base_is_the_remotes_not_the_current_branch(self):
        """Review round 2: with no `origin/HEAD` (a repository made with `git init` and `git remote add`) and
        the main checkout on a feature branch, the base must still be the remote's default."""
        subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/HEAD"], cwd=self.main, capture_output=True)
        git(self.main, "checkout", "-q", "-b", "feature")
        try:
            self.assertEqual(launch.default_branch(self.main), "main")
        finally:
            git(self.main, "checkout", "-q", "main")

    def test_a_failed_fetch_makes_no_worktree(self):
        """A stale origin/<default> would silently be the new branch's base (C6 section 5)."""
        git(self.main, "remote", "set-url", "origin", str(self.tmp / "no-such-remote.git"))
        try:
            with self.assertRaises(launch.Refused):
                launch.make_worktree(self.main, self.coord, 14, None)
        finally:
            git(self.main, "remote", "set-url", "origin", str(self.remote))
        self.assertFalse((self.main / ".claude/worktrees/t14").exists())


class Successors(WithRemote):
    """Issue #45 AC3, AC4: who may be replaced, and the successor's name. The real successors (a builder
    that pushes, a background orchestrator) are live cases in tests/test_live_launch.py."""

    def predecessor(self, launch_id, role="builder", session_id="old-session", ticket=21, worktree=".claude/worktrees/t21"):
        record = {"format": "launch", "version": 1, "id": launch_id, "role": role, "ticket": ticket,
                  "name": f"sandbox-t{ticket}" if role == "builder" else "sandbox-orch", "session_id": session_id,
                  "model": "claude-opus-5-5", "effort": "high", "worktree": worktree, "branch": f"t{ticket}",
                  "base": "origin/main", "base_commit": "abc1234"}
        launch.workfiles.write_atomic(self.coord / "launches" / f"{launch_id}.json", json.dumps(record))
        return record

    def test_a_missing_or_wrong_record_is_refused(self):
        self.predecessor("launch-x-t21-a")
        for launch_id, role, says in (("launch-none", "builder", "no launch record"),
                                      ("../launch-x-t21-a", "builder", "no launch record"),
                                      ("launch-x-t21-a", "orchestrator", "a builder's launch")):
            with self.subTest(launch_id=launch_id), self.assertRaises(launch.Refused) as e:
                launch.predecessor_of(self.coord, launch_id, role, [])
            self.assertIn(says, str(e.exception))

    def test_a_busy_predecessor_is_refused_unless_it_is_the_caller(self):
        """A predecessor still working must not get a second session in its worktree; a session launching
        its own successor in its last turn is busy too, and passes (M66)."""
        self.predecessor("launch-x-t22-a", session_id="s-22", ticket=22)
        busy = [{"sessionId": "s-22", "status": "busy"}]
        with self.assertRaises(launch.Refused) as e:
            launch.predecessor_of(self.coord, "launch-x-t22-a", "builder", busy)
        self.assertIn("is busy", str(e.exception))
        saved = launch.os.environ.get("CLAUDE_CODE_SESSION_ID")
        launch.os.environ["CLAUDE_CODE_SESSION_ID"] = "s-22"
        try:
            self.assertEqual(launch.predecessor_of(self.coord, "launch-x-t22-a", "builder", busy)["ticket"], 22)
        finally:
            launch.os.environ.pop("CLAUDE_CODE_SESSION_ID")
            if saved is not None:
                launch.os.environ["CLAUDE_CODE_SESSION_ID"] = saved
        for row in ([{"sessionId": "s-22", "status": "idle"}], []):  # idle, stopped or absent: replaceable
            self.assertEqual(launch.predecessor_of(self.coord, "launch-x-t22-a", "builder", row)["ticket"], 22)

    def test_the_successor_name_is_the_lowest_unused_number_from_2(self):
        self.assertEqual(launch.successor_name("p-t3", []), "p-t3-2")
        self.assertEqual(launch.successor_name("p-t3", [{"name": "p-t3-2"}, {"name": "p-t3-4"}]), "p-t3-3")
        self.assertEqual(launch.successor_name("p-orch", [{"name": "p-orch"}, {"name": "p-orch-2"}]), "p-orch-3")

    def start(self, args, role, rows):
        fake = FakeClaude(printed="7777abcd", rows=rows)
        saved, out = launch.subprocess.run, io.StringIO()
        launch.subprocess.run = fake
        try:
            with contextlib.redirect_stdout(out):
                result = (launch.builder(args, self.main) if role == "builder"
                          else launch.orchestrator(args, self.main))
            return result, out.getvalue(), fake
        finally:
            launch.subprocess.run = saved

    def test_a_builder_successor_keeps_its_predecessors_place_and_effort(self):
        """At 85% a new session runs one level lower; a replacement keeps its predecessor's effort (C6
        section 4), and takes its ticket, worktree and branch, with /startup and no remote control."""
        worktree, _, _ = launch.make_worktree(self.main, self.coord, 23, None)
        old = self.predecessor("launch-x-t23-a", ticket=23, worktree=".claude/worktrees/t23")
        self.plant_usage(85)
        rows = [{"id": "7777abcd", "name": "sandbox-t23-2", "sessionId": "new-23"}]
        args = SimpleNamespace(successor=old["id"], ticket=None, base=None, effort=None, reason=None, prompt=None, check=False)
        result, _, fake = self.start(args, "builder", rows)
        self.assertEqual(result.split()[:3], ["launched", "sandbox-t23-2", "new-23"])
        self.assertEqual(fake.started[fake.started.index("--effort") + 1], "high")
        self.assertEqual(fake.started[-1], "/startup")
        self.assertNotIn("--remote-control", fake.started)
        record = json.loads(next((self.coord / "launches").glob("launch-*-t23-*")).read_text(encoding="utf-8"))
        self.assertEqual((record["successor_of"], record["worktree"], record["branch"], record["effort_lowered_from"]),
                         (old["id"], ".claude/worktrees/t23", "t23", None))
        self.assertTrue(worktree.is_dir())

    def test_a_refresh_builders_successor_keeps_sonnet_subagents_and_no_auto_memory(self):
        """Issue #160: a refresh builder that hands off is replaced by a successor reading the same brief;
        a successor launched with the ordinary builder settings would run the rest of the refresh with
        Opus subagents, and one without the memory keys would write the repository's auto memory."""
        launch.make_worktree(self.main, self.coord, 43, None)
        old = self.predecessor("launch-x-t43-a", ticket=43, worktree=".claude/worktrees/t43")
        write_brief(self.coord, 43, "yes")
        rows = [{"id": "7777abcd", "name": "sandbox-t43-2", "sessionId": "new-43"}]
        args = SimpleNamespace(successor=old["id"], ticket=None, base=None, effort=None, reason=None, prompt=None, check=False)
        _, _, fake = self.start(args, "builder", rows)
        settings = json.loads(fake.started[fake.started.index("--settings") + 1])
        self.assertIs(settings["autoMemoryEnabled"], False)
        self.assertEqual(settings["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
        self.assertEqual(settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"], "sonnet")

    def test_the_start_command_writes_its_record_first_and_passes_on_the_exit_code(self):
        """AC2: the interactive start has no after-start step, so its record must exist before claude runs
        and name the id it passes; claude's exit code is the script's. A calling Claude session's markers
        are not passed on (M75)."""
        seen, other = {}, FakeClaude()  # made before the patch, so it holds the real subprocess.run

        def interactive(cmd, *a, **kw):
            cmd = [str(c) for c in cmd]
            if cmd[0] == "claude" and "--session-id" in cmd:
                seen["cmd"], seen["env"] = cmd, kw.get("env") or {}
                seen["records"] = [json.loads(p.read_text(encoding="utf-8")) for p in (self.coord / "launches").glob("*-none-*")]
                return subprocess.CompletedProcess(cmd, 3)
            return other(cmd, *a, **kw)

        saved_run, saved_child = launch.subprocess.run, launch.os.environ.get("CLAUDE_CODE_CHILD_SESSION")
        launch.subprocess.run = interactive
        launch.os.environ["CLAUDE_CODE_CHILD_SESSION"] = "1"
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = launch.orchestrator(SimpleNamespace(successor=None, prompt=None, check=False), self.main)
        finally:
            launch.subprocess.run = saved_run
            launch.os.environ.pop("CLAUDE_CODE_CHILD_SESSION")
            if saved_child is not None:
                launch.os.environ["CLAUDE_CODE_CHILD_SESSION"] = saved_child
        self.assertEqual(code, 3)
        session_id = seen["cmd"][seen["cmd"].index("--session-id") + 1]
        self.assertIn(session_id, [r["session_id"] for r in seen["records"]])  # other rows share the scratch folder
        self.assertEqual(seen["cmd"][seen["cmd"].index("--remote-control") + 1], "sandbox-orch")
        self.assertNotIn("--bg", seen["cmd"])
        self.assertNotIn("CLAUDE_CODE_CHILD_SESSION", seen["env"])
        self.assertIn(f"launched sandbox-orch {session_id}", out.getvalue())


class NeverABareResume(unittest.TestCase):
    def test_no_kit_script_resumes_a_session(self):
        """AC5: `claude --resume <id>` revives a session without any launch flag, so without main's guard
        (M56); only `claude respawn` keeps them (M57)."""
        hits = [f"{p.name}:{n}" for p in sorted((KIT).rglob("*.py")) if "tests" not in p.parts
                for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if "--resume" in line and "respawn" not in line]
        self.assertEqual(hits, [])


def git_out(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


if __name__ == "__main__":
    unittest.main()
