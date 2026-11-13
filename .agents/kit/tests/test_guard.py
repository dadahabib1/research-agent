"""The guard's git, GitHub and control-file checks, one row per command or path a session might use
(contract C5 sections 2, 3 and 5).

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
The real path (real Claude Code and Codex sessions, settings, roles) is agent-kit's live test
`tests/test_live_guards.py`; these rows cover what a live test cannot reach cheaply: every command
form in Bash and PowerShell, quoting, path forms, a write to your user settings, and errors.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent  # .agents/kit
ROOT = KIT.parent.parent  # template/ in agent-kit, the project root in a project
sys.path.insert(0, str(KIT / "hooks"))  # C1 section 2: imports by __file__ under -I
sys.path.insert(0, str(KIT / "bin"))

import guard  # noqa: E402
import kitconfig  # noqa: E402

BLOCK, PASS = "block", "pass"


def msys(path):
    """Git Bash's form of a Windows path: C:\\a\\b is /c/a/b."""
    text = str(path).replace("\\", "/")
    return "/" + text[0].lower() + text[2:] if os.name == "nt" and text[1:2] == ":" else text


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


class Project(unittest.TestCase):
    """A scratch project: the kit's schema and config, a main checkout on main, a builder worktree
    `.claude/worktrees/t1` and an orchestrator worktree `.claude/worktrees/cx` on `control/x`."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.main = main = cls.tmp / "proj"
        (main / ".agents/kit/config").mkdir(parents=True)
        shutil.copy(KIT / "config/schema.toml", main / ".agents/kit/config/schema.toml")
        shutil.copy(ROOT / ".gitignore", main / ".gitignore")
        subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
        for which, value in (("project", "project.name='sandbox'"), ("local", "reviewer_home='C:/kit/state/r'")):
            text, problems = kitconfig.render(main, which, [value])
            assert problems == [], problems
            (main / kitconfig.FILES[which]).write_text(text, encoding="utf-8")
        (main / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
        git(main, "add", "-A")
        git(main, "commit", "-qm", "install")
        cls.t1 = main / ".claude/worktrees/t1"
        cls.cx = main / ".claude/worktrees/cx"
        git(main, "worktree", "add", "-q", "-b", "t1", str(cls.t1))
        git(main, "worktree", "add", "-q", "-b", "control/x", str(cls.cx))
        cls.coord = main / ".coordination"
        cls.home = Path(os.path.expanduser("~"))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["git", "worktree", "prune"], cwd=cls.main, capture_output=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def decide(self, role, cwd, tool, tool_input, event="pre"):
        env = {} if role is None else {"KIT_ROLE": role}
        payload = {"hook_event_name": "PreToolUse", "cwd": str(cwd), "tool_name": tool, "tool_input": tool_input,
                   "transcript_path": "t.jsonl"}
        return guard.decide(event, payload, env)

    def expect(self, rows, role, cwd, tool="Bash", key="command"):
        for value, want in rows:
            with self.subTest(role=role, tool=tool, value=value):
                out = self.decide(role, cwd, tool, {key: value})
                reason = out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
                if want == BLOCK:
                    self.assertTrue(reason.startswith("BLOCKED ("), f"not blocked: {value}")
                    self.assertIn(f"role {role}", reason)
                    self.assertIn(". Valid: ", reason)
                else:
                    self.assertEqual(out, {}, f"blocked: {value}: {reason}")

    def run_guard(self, event, stdin, env=None):
        r = subprocess.run([sys.executable, "-I", str(KIT / "hooks/guard.py"), event], input=stdin.encode("utf-8"),
                           capture_output=True, env={**os.environ, **(env or {})}, cwd=self.main)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.decode("utf-8"))  # every output parses as JSON (M12)


class Guard(Project):
    """The git, GitHub and control-file checks."""

    # ------------------------------------------------------------------ git (C5 section 3)

    def test_git_in_a_worktree(self):
        rows = [
            ("git status", PASS), ("git push origin t1", PASS), ("git push -u origin t1", PASS), ("git push", PASS),
            ("git push origin HEAD", PASS), ("git commit -m 'push --force later'", PASS), ("git fetch", PASS),
            ("git stash list", PASS), ("git stash show", PASS), ("git checkout t1", PASS), ("git log --all", PASS),
            ("cat .git/config", PASS), ("git add AGENTS.md", PASS), ("git merge origin/main", PASS),
            ("git push --force origin t1", BLOCK), ("git push -f origin t1", BLOCK), ("git push -uf origin t1", BLOCK),
            ("git push --force-with-lease", BLOCK), ("git push --force-with-lease=t1:abc origin t1", BLOCK),
            ("git push --force-if-includes origin t1", BLOCK), ("git push origin +t1", BLOCK),
            ("git push origin t1:main", BLOCK), ("git push origin HEAD:refs/heads/main", BLOCK),
            ("git push origin main", BLOCK), ("git push --all", BLOCK), ("git push --mirror origin", BLOCK),
            ("git push origin --delete t1", BLOCK), ("git push origin -d t1", BLOCK), ("git push origin :t1", BLOCK),
            ("git branch -D t1", BLOCK), ("git branch -d t1", BLOCK), ("git branch --delete t1", BLOCK),
            ("git reset --hard", BLOCK), ("git reset --hard HEAD~1", BLOCK), ("git clean -fd", BLOCK),
            ("git clean -xfd", BLOCK), ("git checkout .", BLOCK), ("git checkout -- .", BLOCK), ("git restore .", BLOCK),
            ("git rebase main", BLOCK), ("git worktree remove x", BLOCK), ("git stash", BLOCK),
            ("git stash pop", BLOCK), ("git stash drop", BLOCK),
            # read as written: inside bash -c, after other commands, with a path or .exe, -C on main
            ('bash -c "git push --force origin t1"', BLOCK), ("git status; git push --force", BLOCK),
            ("echo hi && git push -f", BLOCK), ("/usr/bin/git push --force origin t1", BLOCK),
            ("git.exe push --force origin t1", BLOCK), ("git push origin 't1:main'", BLOCK),
            (f'git -C "{self.main}" checkout t1', BLOCK), ("git -c core.x=y push --force", BLOCK),
            ("git push --repo origin HEAD:main", BLOCK), ("git push --repo=origin HEAD:main", BLOCK),
            ("powershell -Command \"git push --force\"", BLOCK), ("FOO=1 git push --force", BLOCK),
            # a cd is followed (most real commands start with one); one it cannot follow means the main checkout
            (f'cd "{self.main}" && git checkout t1', BLOCK), (f"cd '{msys(self.main)}' && git switch t1", BLOCK),
            (f'cd "{self.main}" && git pull --ff-only', BLOCK), (f'cd "{self.t1}" && git checkout t1', PASS),
            ("cd $SOMEWHERE && git checkout x", BLOCK), ("cd /no/such/folder && git checkout x", BLOCK),  # M128
            # variables the command sets itself are followed (sessions do this before git -C and cd)
            (f'G="{self.main}"; git -C "$G" switch t1', BLOCK), (f'G="{self.t1}"; git -C "$G" switch t1', PASS),
            (f"$wt = '{self.main}'; git -C $wt switch t1", BLOCK), (f'$d="{self.main}"; git -C $d switch t1', BLOCK),
            (f'$d="{self.t1}"; git -C $d switch t1', PASS),
            ("cat > notes.md <<'EOF'\ngit push --force\ngit branch -D t1\nEOF", PASS),
            ("bash <<'EOF'\ngit push --force\nEOF", BLOCK),
            # a command after a quoted heredoc is still read (review round 3)
            ("git commit -F - <<'EOF'\nmessage\nEOF\ngit push --force origin HEAD", BLOCK),
            ('git commit -F - <<"EOF"\nmessage\nEOF\ngit push origin t1', PASS),
            # quoted text that is not run is not a command (review round 1, note 4)
            ('git commit -m "Block git push --force"', PASS), ('rg "git reset --hard" README.md', PASS),
            ('grep -r "gh pr merge" .', PASS), ('git commit -m "cd into it" && git push origin t1', PASS),
        ]
        self.expect(rows, "builder", self.t1)
        self.expect([(c, w) for c, w in rows if "bash -c" not in c and "/usr/bin" not in c], "builder", self.t1,
                    tool="PowerShell")

    def test_git_in_the_main_checkout(self):
        rows = [
            ("git status", PASS), ("git log", PASS), ("git fetch", PASS), ("git pull --ff-only", PASS),
            ("git pull --ff-only origin main", PASS), ("git merge --ff-only origin/main", PASS),
            ("git worktree list", PASS), ("git worktree add .claude/worktrees/t2 -b t2", PASS),
            ("git push", BLOCK), ("git push origin HEAD", BLOCK), ("git checkout t1", BLOCK), ("git switch t1", BLOCK),
            ("git checkout -b new", BLOCK), ("git reset HEAD~1", BLOCK), ("git restore AGENTS.md", BLOCK),
            ("git merge t1", BLOCK), ("git merge --ff-only t1", BLOCK), ("git cherry-pick abc", BLOCK),
            ("git revert abc", BLOCK), ("git am x.patch", BLOCK), ("git apply x.patch", BLOCK),
            ("git stash pop", BLOCK), ("git stash apply", BLOCK), ("git pull", BLOCK), ("git pull origin t1", BLOCK),
            ("git pull --ff-only origin t1", BLOCK),
            # a redirection is not an argument (issue #103, M135: refused in PR #91's T2 run)
            ("git pull --ff-only 2>&1 | tail -2", PASS), ("git pull --ff-only 2>/dev/null", PASS),
            ("git pull --ff-only > pull.log 2>&1", PASS), ("git pull --ff-only &> pull.log", PASS),
            ("git pull 2>&1 | tail -2", BLOCK), ("git pull --ff-only origin t1 2>&1", BLOCK),
            ("git merge t1 2>&1", BLOCK), ('git pull --ff-only ">x"', BLOCK),
            # a digit touching the redirection is the argument's (PR #114 review round 1)
            ("git pull --ff-only origin main2>pull.log", BLOCK), ("git merge --ff-only origin/main2>merge.log", BLOCK),
            ("git pull --ff-only origin main 2>pull.log", PASS),
        ]
        self.expect(rows, "orchestrator", self.main)
        # a cd into the main checkout is followed (a builder's is refused first, M128)
        self.expect([(f'cd "{self.main}" && git pull --ff-only', PASS), (f'cd "{self.main}" && git switch t1', BLOCK),
                     ("cd /no/such/folder && git checkout x", PASS)], "orchestrator", self.cx)

    # ------------------------------------------------------------------ GitHub (C5 section 3)

    def test_github(self):
        rows = [
            ("gh pr view 1", PASS), ("gh pr list", PASS), ("gh pr create --title x --body y", PASS),
            ("gh repo view", PASS), ("gh repo edit --description x", PASS), ("gh api repos/o/r/pulls/1", PASS),
            ("gh api repos/o/r/branches/main/protection", PASS), ("gh api repos/o/r/rulesets", PASS),
            ("gh pr merge 1", BLOCK), ("gh pr merge 1 --squash", BLOCK), ("gh pr review 1 --admin", BLOCK),
            ("gh repo sync --force", BLOCK), ("gh repo delete o/r --yes", BLOCK), ("gh repo archive o/r", BLOCK),
            ("gh repo rename x", BLOCK), ("gh repo edit --visibility public", BLOCK),
            ("gh repo edit --default-branch dev", BLOCK),
            ("gh api -X PUT repos/o/r/branches/main/protection", BLOCK),
            ("gh api --method DELETE repos/o/r/rulesets/1", BLOCK), ("gh api -XPOST repos/o/r/rulesets", BLOCK),
            ("gh api -X PUT repos/o/r/pulls/1/merge", BLOCK), ("gh api repos/o/r/merges -f base=main -f head=x", BLOCK),
            ('bash -c "gh pr merge 1"', BLOCK), ("gh.exe pr merge 1", BLOCK),
            ("gh api repos/o/r/merges --input=merge.json", BLOCK), ("gh api repos/o/r/merges -fbase=main", BLOCK),
            ("gh api repos/o/r/merges -Fbase=main", BLOCK),
        ]
        self.expect(rows, "builder", self.t1)
        self.expect(rows, "orchestrator", self.main, tool="PowerShell")

    def test_the_session_block(self):
        """C8 section 15 (decision 99): your mode and resume are yours, so every session is refused them, in
        the forms the deny rules miss too; automatic mode is the orchestrator's. The rest of merge.py passes."""
        mp = ".agents/kit/bin/merge.py"
        rows = [
            (f"python -I {mp} yours 5", BLOCK), (f"python -I {mp} yours 5 --head 3f2a9c1e0b7d", BLOCK),
            (f"python -I {mp} resume --reason fixed", BLOCK), ("python .agents\\kit\\bin\\merge.py yours 5", BLOCK),
            ("py -3 merge.py yours 5", BLOCK), ("cd .agents/kit/bin && python -I merge.py yours 5", BLOCK),
            (f"git status && python -I {mp} yours 5", BLOCK), (f"python -I {mp} -h yours 5", BLOCK),
            (f"python3 {mp} resume", BLOCK), ("kit merge 5", BLOCK), ("kit merge 5 --head 3f2a9c1e0b7d", BLOCK),
            ("kit.py merge 5", BLOCK), ("python -I kit.py merge 5", BLOCK), ("kit.exe merge 5", BLOCK),
            (f"python -I {mp} check 5", PASS), (f"python -I {mp} status", PASS), (f"python -I {mp} reconcile", PASS),
            (f"python -I {mp} --help", PASS), (f"git add {mp}", PASS), (f"cat {mp}", PASS),
            ('git commit -m "merge.py yours is yours"', PASS), ('rg "kit merge" docs', PASS), ("kit status", PASS),
            (f"grep -n yours {mp}", PASS),
        ]
        auto = f"python -I {mp} auto 5"
        for role, cwd in (("builder", self.t1), ("reviewer", self.t1), ("triager", self.t1),
                          ("orchestrator", self.main)):
            own = rows + [(auto, PASS if role == "orchestrator" else BLOCK)]
            self.expect(own + [(f'bash -c "python -I {mp} yours 5"', BLOCK)], role, cwd)
            self.expect(own + [(f"& python -I {mp} yours 5", BLOCK), (f"& python -I {mp} check 5", PASS)], role, cwd,
                        tool="PowerShell")
        out = self.decide("builder", self.t1, "Bash", {"command": f"python -I {mp} yours 5"})
        self.assertIn("! python -I .agents/kit/bin/merge.py yours",
                      out["hookSpecificOutput"]["permissionDecisionReason"])  # the valid form: you, with !

    def test_merge_runs_bare(self):
        """M203: `merge.py auto` runs only as its allow rule spells it; the auto-mode classifier refused 2 of 48 chained
        calls in the saved runs (B9's `cd <project>; python -I .agents/kit/bin/merge.py auto 42`, 2026-10-19) and none
        of 13 bare ones. Refused with the bare form. The read-only subcommands still chain (210 chained, none refused)."""
        mp = ".agents/kit/bin/merge.py"
        rows = [
            (f"cd {msys(self.main)}; python -I {mp} auto 5", BLOCK), (f"cd {self.main} && python -I {mp} auto 5", BLOCK),
            (f"python -I {mp} auto 5", PASS), (f"python -I {mp} auto 5 --wait", PASS),
            (f"python -I {mp} auto 5 | tail -5", BLOCK), (f"git status; python -I {mp} auto 5", BLOCK),
            (f"python -I {msys(self.main)}/{mp} auto 5", BLOCK), (f"python {mp} auto 5", BLOCK),
            (f"python3 -I {mp} auto 5", BLOCK), ("python -I .agents\\kit\\bin\\merge.py auto 5", BLOCK),
            (f'bash -c "python -I {mp} auto 5"', BLOCK), (f'python -I "{mp}" auto 5', BLOCK),
            (f"python -I '{mp}' auto 5", BLOCK), (f"python  -I {mp} auto 5", BLOCK),
            (f"python -I {mp} auto 5 --head 3f2a9c1e0b7d", PASS),
            (f"cd {msys(self.main)}; python -I {mp} status", PASS), (f"python -I {mp} status; git status", PASS),
            (f"python3 {mp} check 5", PASS), (f"cd {self.main} && python -I {mp} reconcile", PASS),
        ]
        self.expect(rows, "orchestrator", self.main)
        self.expect(rows[:2], "orchestrator", self.main, tool="PowerShell")
        out = self.decide("orchestrator", self.main, "Bash", {"command": f"cd {msys(self.main)}; python -I {mp} auto 5"})
        self.assertIn(f"`python -I {mp} auto <args>` alone", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_github_mcp_tools(self):
        for tool, want in (("mcp__github__get_pull_request", PASS), ("mcp__github__merge_pull_request", BLOCK),
                           ("mcp__gh__update_branch_protection", BLOCK), ("mcp__gh__create_ruleset", BLOCK),
                           ("mcp__gh__delete_repo", BLOCK)):
            with self.subTest(tool=tool):
                out = self.decide("orchestrator", self.main, tool, {"owner": "o", "repo": "r"})
                self.assertEqual(bool(out), want == BLOCK, tool)

    # ------------------------------------------------------------------ control files (C5 sections 2, 3)

    def file_rows(self):
        m, t1, cx, c, h = self.main, self.t1, self.cx, self.coord, self.home
        return [  # (path, builder, orchestrator)
            (t1 / "src/app.py", PASS, PASS), (m / "README.md", PASS, PASS), (c / "messages/m.md", PASS, PASS),
            (c / "handoffs/h.md", PASS, PASS), (c / "state/builder.md", PASS, PASS),
            (t1 / ".claude/settings.json", BLOCK, BLOCK), (t1 / "AGENTS.md", BLOCK, BLOCK),
            (t1 / ".agents/kit/bin/kitconfig.py", BLOCK, BLOCK), (t1 / "agent-kit.toml", BLOCK, BLOCK),
            (m / "AGENTS.md", BLOCK, BLOCK), (m / ".claude/settings.json", BLOCK, BLOCK),
            (m / "agent-kit.local.toml", BLOCK, BLOCK), (m / "kit.lock", BLOCK, BLOCK), (m / ".codex/hooks.json", BLOCK, BLOCK),
            (cx / ".claude/settings.json", BLOCK, PASS), (cx / "AGENTS.md", BLOCK, PASS), (cx / "src/x.py", PASS, PASS),
            (c / "merges/m.json", BLOCK, BLOCK), (c / "reviews/r1.json", BLOCK, BLOCK),
            (c / "verdicts/v.json", BLOCK, BLOCK), (c / "locks/merge.lock", BLOCK, BLOCK),
            (h / ".claude/settings.json", BLOCK, BLOCK), (h / ".claude/settings.local.json", BLOCK, BLOCK),
            # path forms: case, backslashes, a trailing dot Windows drops
            (Path(str(t1 / ".claude/settings.json").upper()), BLOCK, BLOCK),
            (str(m / "AGENTS.md").replace("/", "\\"), BLOCK, BLOCK), (str(m / "AGENTS.md") + ".", BLOCK, BLOCK),
        ]

    def test_file_tools(self):
        for path, builder, orchestrator in self.file_rows():
            for tool, key in (("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"),
                              ("NotebookEdit", "notebook_path"), ("mcp__fs__write_file", "path")):
                self.expect([(str(path), builder)], "builder", self.t1, tool=tool, key=key)
                self.expect([(str(path), orchestrator)], "orchestrator", self.main, tool=tool, key=key)

    def test_git_files_from_a_subfolder(self):
        """git -C .. restore from a worktree's subfolder names the worktree's AGENTS.md (round 2, finding 2)."""
        sub = self.t1 / "src"
        sub.mkdir(exist_ok=True)
        self.expect([("git -C .. restore AGENTS.md", BLOCK), ("git restore notes.txt", PASS)], "builder", sub)

    def test_reads_pass(self):
        for tool, key in (("Read", "file_path"), ("Grep", "path"), ("Glob", "path")):
            self.expect([(str(self.main / "AGENTS.md"), PASS)], "builder", self.t1, tool=tool, key=key)

    def test_a_builder_stays_in_its_worktree(self):
        """M128: a builder that cd'd to the coordination folder moved its session into the main checkout, and
        Claude Code's own guard then refused every write; a cd out of the worktree, or EnterWorktree, is refused."""
        m, t1, c = self.main, self.t1, self.coord
        (t1 / "src").mkdir(exist_ok=True)
        for tool in ("EnterWorktree", "ExitWorktree"):
            self.expect([("t9", BLOCK)], "builder", t1, tool=tool, key="name")
            self.expect([("t9", PASS)], "orchestrator", m, tool=tool, key="name")
        bash = [
            (f'cd "{m}"', BLOCK), (f"cd '{msys(m)}' && ls", BLOCK), (f'cd "{c}" && ls', BLOCK), ("cd ../..", BLOCK),
            ("cd src && cd ../..", BLOCK), (f'pushd "{m}"', BLOCK), ("cd ~", BLOCK), ("cd", BLOCK), ("cd $HOME", BLOCK),
            ("cd $SOMEWHERE", BLOCK), ("cd -", BLOCK), ("cd ../cx", BLOCK), (f'C="{c}"; cd "$C"', BLOCK),
            ("ls; cd D:/", BLOCK), (f'bash -c "cd {msys(m)}"', BLOCK),
            ("cd src", PASS), ("cd src && cd ..", PASS), (f'cd "{t1}" && git status', PASS), ("pushd src", PASS),
            (f"cd '{msys(t1 / 'src')}'", PASS), (f"cd src/.. && ls '{c}'", PASS),
            (f"cat '{c / 'state/x.md'}'", PASS), ('git commit -m "cd .. later"', PASS),
            ("if [ -d missing-m128 ]; then cd missing-m128; fi; git reset --hard HEAD", BLOCK),  # PR #95 round 2
        ]
        self.expect(bash, "builder", t1)
        powershell = [
            (f"Set-Location '{m}'", BLOCK), (f"sl -Path '{c}'", BLOCK), ("Set-Location ..\\..", BLOCK),
            ("chdir D:", BLOCK), (f"Push-Location '{m}'; pushd '{m}'", BLOCK),
            ("Set-Location src", PASS), (f"Set-Location -LiteralPath '{t1}'", PASS),
            ("D:" if t1.drive.upper() != "D:" else "E:", BLOCK), (t1.drive, PASS),  # review round 1 on PR #95
        ]
        self.expect(powershell, "builder", t1, tool="PowerShell")
        self.expect([(f'cd "{m}"', PASS), (f'cd "{c}" && ls', PASS)], "orchestrator", m)
        # a session already moved out (M128's state) may come home by absolute path, and only that
        # PR #95 rounds 1-2: a cd the static check cannot foresee (behind `then`, after a failed cd) is caught on
        # the next call by the harness's cwd: only a cd home by absolute path runs, alone (round 3: a cd into a
        # missing folder fails, and what follows it would run outside)
        for command, want in ((f'cd "{t1}"', PASS), ("cd src", BLOCK), (f'cd "{t1}" && git status', BLOCK),
                              ("echo x > notes.txt", BLOCK), ("git status", BLOCK), (f"cat '{c / 'state/x.md'}'", BLOCK),
                              (f'cd "{c}"', BLOCK), (f'cd "{msys(t1)}"; ls', BLOCK),
                              (f'cd "{t1 / "missing"}"; echo x > notes.txt', BLOCK), (f'cd "{t1 / "src"}"', PASS)):
            payload = {"cwd": str(m), "tool_name": "Bash", "tool_input": {"command": command},
                       "transcript_path": "t.jsonl"}
            out = guard.decide("pre", payload, {"KIT_ROLE": "builder", "CLAUDE_PROJECT_DIR": str(t1)})
            self.assertEqual(out != {}, want == BLOCK, f"{command}: {out}")
        out = self.decide("builder", t1, "Bash", {"command": f'cd "{c}"'})
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("write coordination files by absolute path; stay in your worktree", reason)

    def test_pwd_is_the_session_folder(self):
        """`$PWD` is the folder the session's shell is in at that point of the command, never the hook process's
        PWD (2026-10-19's final pass: `cd "$PWD" && git status` was refused as leaving the worktree). $OLDPWD, %CD%
        and $env:PWD are never read from the hook's environment either; they stay unplaceable (decision 107)."""
        t1, elsewhere = self.t1, self.tmp / "elsewhere"
        (t1 / "src").mkdir(exist_ok=True)
        hook_env = {"PWD": str(elsewhere), "OLDPWD": str(t1), "CD": str(t1)}
        bash = [
            ('cd "$PWD" && git status', PASS), ("cd $PWD", PASS), ('cd "${PWD}"', PASS),
            ('cd src && cd "$PWD"', PASS), ('cd src && cd "$PWD/.."', PASS),  # $PWD is src after the cd
            ('cd $SOMEWHERE && cd "$PWD"', BLOCK), ('cd "$PWD/.."', BLOCK),
            ('cd "$OLDPWD"', BLOCK), ("cd %CD%", BLOCK), ("cd $pwd", BLOCK), ('bash -c "cd $PWD"', PASS),
            ('echo x > "$PWD/notes.txt"', PASS), ('echo x > "$PWD/.claude/settings.json"', BLOCK),
            ('echo x > "${PWD}/AGENTS.md"', BLOCK), ('cd src && echo x > "$PWD/../AGENTS.md"', BLOCK),
            ('G="$PWD/AGENTS.md"; echo x > "$G"', BLOCK),
        ]
        powershell = [
            ("Set-Location $PWD", PASS), ("cd $PWD; git status", PASS), ("Set-Location $env:PWD", BLOCK),
            ("Set-Content -Path $PWD/AGENTS.md -Value x", BLOCK),
        ]
        with unittest.mock.patch.dict(os.environ, hook_env):
            self.expect(bash, "builder", t1)
            self.expect(powershell, "builder", t1, tool="PowerShell")
            out = self.decide("builder", t1, "Bash", {"command": 'echo x > "$PWD/.claude/settings.json"'})
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(f"{t1}/.claude/settings.json is a control file in the worktree on t1", reason)

    def test_pwd_in_nested_shells_and_aliases(self):
        """PR #119's review, round 1. A shell body in double quotes (or none) is expanded by the outer shell before
        the child runs, so its `$PWD` is the folder before the child's own cd; in single quotes the child expands it
        after. A variable the command set to `$OLDPWD`, `%CD%` or `$env:PWD` stays unplaceable, as the spelling
        itself does (decision 107), never read from the hook's environment."""
        t1, elsewhere = self.t1, self.tmp / "elsewhere"
        (t1 / "src").mkdir(exist_ok=True)
        hook_env = {"PWD": str(elsewhere), "OLDPWD": str(t1), "CD": str(t1)}
        bash = [
            ('bash -c "cd src; echo x > $PWD/AGENTS.md"', BLOCK), ("bash -c 'cd src; echo x > $PWD/AGENTS.md'", PASS),
            ('sh -c "cd src && echo x > ${PWD}/AGENTS.md"', BLOCK), ("sh -c 'cd src && echo x > $PWD/AGENTS.md'", PASS),
            ("sh -c 'cd src && echo x > $PWD/../AGENTS.md'", BLOCK),
            ('pwsh -Command "cd src; Set-Content -Path $PWD/AGENTS.md -Value x"', BLOCK),
            ("pwsh -Command 'cd src; Set-Content -Path $PWD/AGENTS.md -Value x'", PASS),
            ("bash <<EOF\ncd src\necho x > $PWD/AGENTS.md\nEOF", BLOCK),  # an unquoted heredoc word: outer
            ("bash <<'EOF'\ncd src\necho x > $PWD/AGENTS.md\nEOF", PASS),
            ('G="$OLDPWD"; cd "$G"', BLOCK), ('G="%CD%"; cd "$G"', BLOCK), ('G="$OLDPWD"; H="$G"; cd "$H"', BLOCK),
            ('G="$env:PWD"; cd "$G"', BLOCK),
        ]
        powershell = [
            ('bash -c "cd src; echo x > $PWD/AGENTS.md"', BLOCK), ('$G = "$env:PWD"; Set-Location $G', BLOCK),
            ('$G = "%CD%"; Set-Location $G', BLOCK),
        ]
        with unittest.mock.patch.dict(os.environ, hook_env):
            self.expect(bash, "builder", t1)
            self.expect(powershell, "builder", t1, tool="PowerShell")
        # after a cd the guard cannot follow, an outer `$PWD` stays unplaceable, whatever the child's cd
        found = guard.units(f'cd $SOMEWHERE && bash -c "cd {t1}; echo x > $PWD/AGENTS.md"', t1)
        self.assertEqual([guard.resolved(t, base, u.names) for u in found for t, base, _ in guard.write_targets(u)],
                         [None])

    def test_pwd_after_cd_back_and_in_recursive_deletes(self):
        """PR #119's review, round 2. `cd -` goes to the folder before, which the guard does not know: `$PWD` is
        unknown after it (C5), never the home folder a bare `cd` goes to. A recursive delete never reads `$env:PWD`
        or `$env:OLDPWD` (or a variable holding them) from the hook's environment: they are unknown variables, and
        an empty one would make `/`."""
        m, t1, elsewhere = self.main, self.t1, self.tmp / "elsewhere"
        (t1 / "src").mkdir(exist_ok=True)
        build = t1 / "build"
        with unittest.mock.patch.dict(os.environ, {"HOME": str(elsewhere), "USERPROFILE": str(elsewhere)}):
            self.expect([('cd template && cd - && git -C "$PWD" reset --hard', BLOCK),
                         ('cd src; cd -; git -C "${PWD}" reset --hard', BLOCK)], "orchestrator", m)
            out = self.decide("builder", t1, "Bash", {"command": 'cd src && cd - && echo x > "$PWD/AGENTS.md"'})
            found = guard.units('cd src && cd - && echo x > "$PWD/AGENTS.md"', t1)
        powershell = [
            ('Remove-Item -Recurse "$env:PWD/"', BLOCK), ('Remove-Item -Recurse "$env:OLDPWD/"', BLOCK),
            ("Remove-Item -Recurse -Force $env:pwd/", BLOCK), ('$X = "$env:PWD"; Remove-Item -Recurse "$X/"', BLOCK),
            ('$X = "$env:OLDPWD"; Remove-Item -Recurse "$X/"', BLOCK), ('Remove-Item -Recurse "$env:PWD/build"', PASS),
        ]
        with unittest.mock.patch.dict(os.environ, {"PWD": str(build), "OLDPWD": str(build)}):
            for role, cwd in (("builder", t1), ("orchestrator", m)):
                self.expect(powershell, role, cwd, tool="PowerShell")
                self.expect([('X="$env:PWD"; rm -rf "$X/"', BLOCK)], role, cwd)
        self.assertIn("cd - goes to a folder the guard cannot place", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual([guard.resolved(t, base, u.names) for u in found for t, base, _ in guard.write_targets(u)],
                         [None])

    def test_shell_writes(self):
        m, c = self.main, self.coord
        rows = [
            ("cat AGENTS.md", PASS), ("grep x .claude/settings.json", PASS), ("ls .claude", PASS),
            ("echo x > notes.txt", PASS), ('echo "a > AGENTS.md" > notes.txt', PASS), ("sed s/a/b/ AGENTS.md", PASS),
            ("cp AGENTS.md notes.txt", PASS), ('python -c "print(1)"', PASS), ("echo x 2>&1", PASS),
            ("git add .claude/settings.json", PASS), (f"cd src && echo x > '{m / 'notes.txt'}'", PASS),
            ("echo x > .claude/settings.json", BLOCK), ("echo x >> AGENTS.md", BLOCK),
            ("echo x > \".claude/settings.json\"", BLOCK), ("echo x 2> AGENTS.md", BLOCK),
            ("echo x &> AGENTS.md", BLOCK), ("echo x &>> AGENTS.md", BLOCK), ("echo x > AGENTS.md 2>&1", BLOCK),
            ("> AGENTS.md", BLOCK), ("2> AGENTS.md", BLOCK), ("&> AGENTS.md", BLOCK), (">> AGENTS.md", BLOCK),
            ("exec > AGENTS.md", BLOCK), ("env > AGENTS.md", BLOCK), ("FOO=bar > AGENTS.md", BLOCK),
            ("exec 2>&1", PASS),
            ("echo x | tee .claude/settings.json", BLOCK), ("cat a | tee -a AGENTS.md", BLOCK),
            ("rm AGENTS.md", BLOCK), ("mv AGENTS.md old.md", BLOCK), ("cp notes.txt .claude/settings.json", BLOCK),
            ("touch .agents/kit/new.py", BLOCK), ("sed -i s/a/b/ AGENTS.md", BLOCK),
            ("git checkout AGENTS.md", BLOCK), ("git restore AGENTS.md", BLOCK), ("git rm AGENTS.md", BLOCK),
            ("git mv AGENTS.md x.md", BLOCK), ("python -c \"open('AGENTS.md','w').write('x')\"", BLOCK),
            ('bash -c "echo x > AGENTS.md"', BLOCK), (f"echo x > '{m / 'AGENTS.md'}'", BLOCK),
            ("echo x > ~/.claude/settings.json", BLOCK), (f"echo x > '{c / 'merges/m.json'}'", BLOCK),
            ("cd src && echo x > out.txt", PASS), ("cd .claude && echo x > settings.json", BLOCK),
            (f'cd "{m}" && echo x > AGENTS.md', BLOCK), (f"cd '{msys(m)}' && echo x >> AGENTS.md", BLOCK),
            ("cd $SOMEWHERE && echo x > out.txt", BLOCK),  # a cd the guard cannot follow
            ("echo x > $NOT_SET_ANYWHERE/AGENTS.md", PASS), ("echo x > $HOME/.claude/settings.json", BLOCK),
            ("cat > notes.md <<'EOF'\nrm AGENTS.md\necho x > AGENTS.md\nEOF", PASS),
            ("cat > AGENTS.md <<'EOF'\nx\nEOF", BLOCK), ("python - <<'EOF'\nopen('AGENTS.md', 'w')\nEOF", BLOCK),
            ("rm .claude/*.json", BLOCK), (f'C="{m}"; cd "$C" && echo x > AGENTS.md', BLOCK),
            (f'C="{self.t1}"; cd "$C" && echo x > notes.txt', PASS), ("python - <<'EOF'\nprint('...')\nEOF", PASS),
            ("echo x>AGENTS.md", BLOCK), (f"echo x>'{c / 'merges/m.json'}'", BLOCK),
            ("sed --in-place=.bak s/a/b/ AGENTS.md", BLOCK), ("sed -Ei s/a/b/ AGENTS.md", BLOCK),
            ("sed -i -e s/a/b/ AGENTS.md", BLOCK), ("cd $SOMEWHERE && sed -i 's/AGENTS.md/x/' /tmp/notes.txt", BLOCK),  # M128
        ]
        self.expect(rows, "builder", self.t1)
        self.expect([("cd $SOMEWHERE && sed -i 's/AGENTS.md/x/' /tmp/notes.txt", PASS),
                     (f'C="{m}"; cd "$C" && echo x > notes.txt', PASS)], "orchestrator", self.cx)
        powershell = [
            ("Get-Content AGENTS.md", PASS), ("Set-Content -Path notes.txt -Value x", PASS),
            ("Set-Content -Path AGENTS.md -Value x", BLOCK), ("'x' | Out-File AGENTS.md", BLOCK),
            ("Add-Content AGENTS.md x", BLOCK), ("New-Item .claude/x.json", BLOCK), ("Remove-Item AGENTS.md", BLOCK),
            ("Copy-Item notes.txt -Destination AGENTS.md", BLOCK), ("Move-Item AGENTS.md old.md", BLOCK),
            ("sc AGENTS.md x", BLOCK), ("del AGENTS.md", BLOCK), ("echo x > AGENTS.md", BLOCK),
            ('powershell -Command "Set-Content AGENTS.md x"', BLOCK),
        ]
        self.expect(powershell, "builder", self.t1, tool="PowerShell")

    def test_recursive_deletes(self):
        """A recursive delete of a drive root, the home folder or a checkout root, or of one a variable
        left empty would make (the empty-variable mistake), is refused for every role (issue #37)."""
        m, t1, cx, h, drive = self.main, self.t1, self.cx, self.home, Path(self.tmp).anchor.replace("\\", "/")
        bash = [
            ("rm -rf /", BLOCK), ('rm -rf "/"', BLOCK), ("rm -fr /*", BLOCK), ("rm -r -f /", BLOCK),
            ("rm --recursive /", BLOCK), (f"rm -Rf {drive}", BLOCK), ("rm -rf ~", BLOCK), (f"rm -rf '{h}'", BLOCK),
            (f"rm -rf '{m}'", BLOCK), (f"rm -rf '{msys(m)}'", BLOCK), (f"rm -rf '{t1}'", BLOCK), (f"rm -rf '{cx}'", BLOCK),
            ("rm -rf .", BLOCK), ("rm -rf ./", BLOCK), ("rm -rf *", BLOCK), ("rm -rf ../t1", BLOCK),
            (f'cd "{m}" && rm -rf .', BLOCK), ("sudo rm -rf /", BLOCK), ('bash -c "rm -rf /"', BLOCK),
            *([("rm -rf /c", BLOCK)] if os.name == "nt" else []),  # Git Bash's C:
            # the empty-variable mistake: a variable the guard cannot expand is read as empty; an empty
            # target alone deletes nothing in either shell (measured), so it passes
            ('rm -rf "$NOT_SET_ANYWHERE/"', BLOCK), ('rm -rf "${NOT_SET_ANYWHERE}"/*', BLOCK),
            ("cd $SOMEWHERE && rm -rf .", BLOCK), ('rm -rf "$NOT_SET_ANYWHERE"', PASS),
            # deletes inside a checkout, scratch folders and deletes that are not recursive pass
            ("rm -rf build/", PASS), ("rm -rf node_modules", PASS), (f"rm -rf '{t1 / 'build'}'", PASS),
            ('rm -rf "$NOT_SET_ANYWHERE/build"', PASS), (f"rm -rf '{self.tmp / 'scratch'}'", PASS),
            ('T=$(mktemp -d); rm -rf "$T"', PASS), ("rm -f notes.txt", PASS), ("rm -rf src/*", PASS),
            ('rm -rf ""', PASS), ('BUILD=""; rm -rf "$BUILD"', PASS),  # review round 1, finding 4
        ]
        powershell = [
            (f"Remove-Item -Recurse -Force {drive}", BLOCK), ('Remove-Item -Recurse "$NOT_SET_ANYWHERE\\"', BLOCK),
            ("Remove-Item -Recurse $NOT_SET_ANYWHERE", PASS),
            ("rm -Recurse ~", BLOCK), (f"ri -r '{m}'", BLOCK), (f"del -Recurse '{t1}'", BLOCK),
            (f"Remove-Item -Path '{h}' -Recurse", BLOCK), ("Remove-Item -rec .", BLOCK),
            (f"rd /s /q {drive}", BLOCK), (f"rmdir /s '{m}'", BLOCK), (f'cmd /c "rd /s /q {drive}"', BLOCK),
            ("Remove-Item -Recurse build", PASS), ("Remove-Item -Force notes.txt", PASS), ("rd /s /q build", PASS),
            ("Remove-Item -Recurse -Force $env:TEMP/kit-scratch", PASS),
            # PowerShell's names for the home folder (review round 1, finding 1)
            ("Remove-Item -Recurse $HOME", BLOCK), ("Remove-Item -Recurse $HOME/build", PASS),
            *([("Remove-Item -Recurse $env:USERPROFILE", BLOCK)] if os.name == "nt" else []),
        ]
        for role, cwd in (("builder", t1), ("reviewer", t1), ("orchestrator", m)):
            self.expect([r for r in bash if cwd == t1 or "../t1" not in r[0]], role, cwd)
            self.expect(powershell, role, cwd, tool="PowerShell")

    def test_roles(self):
        cx_settings = str(self.cx / ".claude/settings.json")
        # No KIT_ROLE: a Claude session started in the main checkout is the orchestrator, in a worktree a builder.
        for project_dir, want in ((self.main, {}), (self.t1, "blocked")):
            payload = {"cwd": str(self.main), "tool_name": "Write", "tool_input": {"file_path": cx_settings},
                       "transcript_path": "t.jsonl"}
            out = guard.decide("pre", payload, {"CLAUDE_PROJECT_DIR": str(project_dir)})
            self.assertEqual(out if want == {} else bool(out) and "blocked", want, project_dir)
        # No KIT_ROLE and no CLAUDE_PROJECT_DIR: Codex, the reviewer; git still refused, files not checked.
        self.expect([("git push --force origin t1", BLOCK), ("echo x > AGENTS.md", PASS)], "reviewer", self.t1)
        out = guard.decide("pre", {"cwd": str(self.t1), "tool_name": "Bash", "transcript_path": "t.jsonl",
                                   "tool_input": {"command": "git push --force"}}, {})
        self.assertIn("role reviewer", out["hookSpecificOutput"]["permissionDecisionReason"])

    # ------------------------------------------------------------------ errors and output (C5 section 1)

    def test_errors_block_on_every_event(self):
        for event in ("pre", "prompt", "stop", "post"):
            with self.subTest(event=event):
                out = self.run_guard(event, "{not json")
                text = json.dumps(out)
                self.assertIn("BLOCKED (error", text)
                self.assertIn("stop and tell the user", text)
        missing = self.run_guard("pre", json.dumps({"cwd": str(self.main), "tool_name": "Bash"}))
        self.assertIn("tool_input", missing["hookSpecificOutput"]["permissionDecisionReason"])
        bad_role = self.run_guard("pre", json.dumps({"cwd": str(self.main), "tool_name": "Bash",
                                                     "tool_input": {"command": "git status"}}), {"KIT_ROLE": "admin"})
        self.assertIn("BLOCKED (error", bad_role["hookSpecificOutput"]["permissionDecisionReason"])

    def test_output_through_the_script(self):
        blocked = self.run_guard("pre", json.dumps({"cwd": str(self.t1), "tool_name": "Bash", "transcript_path": "t.jsonl",
                                                    "tool_input": {"command": "git push --force"}}),
                                 {"KIT_ROLE": "builder"})
        self.assertEqual(blocked["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(blocked["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(self.run_guard("pre", json.dumps({"cwd": str(self.t1), "tool_name": "Bash", "transcript_path": "t.jsonl",
                                                           "tool_input": {"command": "git status"}}),
                                        {"KIT_ROLE": "builder"}), {})
        self.assertEqual(self.run_guard("prompt", json.dumps({"cwd": str(self.main), "prompt": "hi",
                                                              "transcript_path": "t.jsonl"}), {"KIT_ROLE": "builder"}), {})


class Barrier(Project):
    """The context barrier, the READY check and the missed-handoff check (C5 section 3), on transcripts
    written as Claude Code and Codex write them (M34, M36). Default levels: builder 50/55, reviewer 55/70."""

    def transcript(self, *records, raw=""):
        path = self.tmp / f"t{len(list(self.tmp.glob('t*.jsonl')))}.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in records) + raw, encoding="utf-8")
        return str(path)

    @staticmethod
    def claude(tokens, sidechain=False, content=()):
        usage = {"input_tokens": 2, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": tokens - 1100,
                 "output_tokens": 98}
        return {"type": "assistant", "isSidechain": sidechain,
                "message": {"role": "assistant", "usage": usage, "content": list(content)}}

    @staticmethod
    def codex(tokens):
        return {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"total_tokens": tokens}, "model_context_window": 258400}}}

    def call(self, event, transcript, tool=None, tool_input=None, role="builder", cwd=None, extra_env=None):
        payload = {"cwd": str(cwd or self.t1), "transcript_path": transcript}
        if tool:
            payload.update(tool_name=tool, tool_input=tool_input)
        return guard.decide(event, payload, {"KIT_ROLE": role, **(extra_env or {})})

    def refused(self, out):
        return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny" or out.get("decision") == "block"

    def warned(self, out):
        return "additionalContext" in out.get("hookSpecificOutput", {})

    def test_levels_on_claude_transcripts(self):
        below = self.transcript(self.claude(400_000))
        warn = self.transcript(self.claude(100_000), self.claude(520_000))
        over = self.transcript(self.claude(600_000), self.claude(900_000, sidechain=True))
        empty = self.transcript()
        bash = ("Bash", {"command": "ls"})
        self.assertEqual(self.call("pre", below, *bash), {})
        self.assertEqual(self.call("pre", empty, *bash), {})  # 0% only when there is no assistant record
        self.assertEqual(self.call("pre", str(self.tmp / "none.jsonl"), *bash), {})
        out = self.call("pre", warn, *bash)
        self.assertTrue(self.warned(out) and not self.refused(out), out)
        self.assertIn("52%", out["hookSpecificOutput"]["additionalContext"])
        self.assertTrue(self.refused(self.call("pre", over, *bash)))
        # a sidechain (subagent) record is not the session's context
        side = self.transcript(self.claude(100_000), self.claude(900_000, sidechain=True))
        self.assertEqual(self.call("pre", side, *bash), {})
        # a refusal from another check wins over the warning
        self.assertTrue(self.refused(self.call("pre", warn, "Bash", {"command": "git push --force"})))
        # every prompt you send is warned too
        prompt = self.call("prompt", warn)
        self.assertEqual(prompt["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertTrue(self.warned(prompt))
        self.assertEqual(self.call("prompt", below), {})
        self.assertTrue(self.warned(self.call("prompt", over)))  # a prompt is never refused

    def test_an_unreadable_transcript_blocks(self):
        broken = self.transcript(self.claude(100_000), raw='{"type": "assistant", "message": \n')
        with self.assertRaises(Exception):
            self.call("pre", broken, "Bash", {"command": "ls"})
        no_usage = self.transcript({"type": "assistant", "isSidechain": False, "message": {"content": []}})
        with self.assertRaises(Exception):
            self.call("pre", no_usage, "Bash", {"command": "ls"})
        # a last line still being written (no line break yet) is skipped, not an error
        writing = self.transcript(self.claude(100_000), raw='{"type": "assist')
        self.assertEqual(self.call("pre", writing, "Bash", {"command": "ls"}), {})

    def test_handoff_steps_pass_at_handoff(self):
        over = self.transcript(self.claude(600_000))
        c, t1 = self.coord, self.t1
        rows = [
            ("Bash", {"command": "git status"}, PASS), ("Bash", {"command": "git log --oneline -3"}, PASS),
            ("Bash", {"command": f'cd "{t1}" && git diff --stat'}, PASS),
            ("Bash", {"command": "python -I .agents/kit/bin/launch.py builder 28"}, PASS),
            ("Bash", {"command": "git commit -m x"}, BLOCK), ("Bash", {"command": "ls"}, BLOCK),
            ("Bash", {"command": "git status && rm notes.txt"}, BLOCK),
            ("Write", {"file_path": str(c / "handoffs/builder.md"), "content": "x"}, PASS),
            ("Write", {"file_path": str(c / "state/builder.md"), "content": "x"}, PASS),
            ("Write", {"file_path": str(c / "messages/m.md"), "content": "Handing off."}, PASS),
            ("Write", {"file_path": str(t1 / "src/x.py"), "content": "x"}, BLOCK),
            ("Write", {"file_path": str(c / "merges/m.json"), "content": "x"}, BLOCK),
            ("Read", {"file_path": str(c / "messages/m.md")}, PASS),
            ("Read", {"file_path": str(t1 / ".claude/skills/plan/SKILL.md")}, PASS),
            ("Read", {"file_path": str(t1 / "src/x.py")}, BLOCK), ("Grep", {"pattern": "x", "path": str(t1)}, BLOCK),
            # simple shell reads of the same folders (review round 1: 195 real commands read this way)
            ("Bash", {"command": "cat .claude/skills/signoff/SKILL.md"}, PASS),
            ("Bash", {"command": f"cat '{c / 'messages/m.md'}' | head -5"}, PASS),
            ("Bash", {"command": f"ls '{c / 'messages'}'"}, PASS),
            ("Bash", {"command": f"grep -n READY '{c / 'messages/m.md'}'"}, PASS),
            ("Bash", {"command": "cat src/x.py"}, BLOCK), ("Bash", {"command": f"cat '{c / 'messages/m.md'}' src/x.py"}, BLOCK),
            ("Bash", {"command": "grep -rn x ."}, BLOCK),
            # each reader's own value options (review round 2: grep -n takes none, head -n takes one)
            ("Bash", {"command": 'grep -n "^#" docs/agents/automation.md'}, BLOCK),
            ("Bash", {"command": "grep -e x src/x.py"}, BLOCK), ("Bash", {"command": "head -n 5 src/x.py"}, BLOCK),
            ("Bash", {"command": f"head -n 5 '{c / 'messages/m.md'}'"}, PASS),
            ("Bash", {"command": f"grep -e READY -n '{c / 'messages/m.md'}'"}, PASS),
            # round 3: -c and -C are different options; neither may hide a file outside the folders
            ("Bash", {"command": 'grep -c "^|" docs/research-lock.md'}, BLOCK),
            ("Bash", {"command": "grep -C 3 x src/x.py"}, BLOCK),
            ("Bash", {"command": f"grep -c READY '{c / 'messages/m.md'}'"}, PASS),
            ("Bash", {"command": f"grep -C 3 READY '{c / 'messages/m.md'}'"}, PASS),
            ("SendMessage", {"to": "orchestrator", "message": "Handing off."}, PASS),
            ("TaskStop", {"task_id": "1"}, PASS), ("PushNotification", {"message": "x"}, PASS),
            ("ToolSearch", {"query": "x"}, PASS), ("Skill", {"skill": "x"}, PASS),
            ("Agent", {"prompt": "x"}, BLOCK), ("WebSearch", {"query": "x"}, BLOCK),
        ]
        for tool, tool_input, want in rows:
            with self.subTest(tool=tool, tool_input=tool_input):
                out = self.call("pre", over, tool, tool_input)
                self.assertEqual(self.refused(out), want == BLOCK, out)
                if want == BLOCK and "merges" not in json.dumps(tool_input):  # a runtime record is refused first
                    self.assertIn("BLOCKED (context", out["hookSpecificOutput"]["permissionDecisionReason"])
                if want == PASS:
                    self.assertTrue(self.warned(out), out)  # a handoff step still carries the warning

    def test_errors_still_let_handoff_steps_through(self):
        broken = self.transcript(raw='{"not": json}\n')
        for tool_input, want in (({"file_path": str(self.coord / "handoffs/builder.md"), "content": "x"}, PASS),
                                 ({"file_path": str(self.t1 / "src/x.py"), "content": "x"}, BLOCK)):
            with self.subTest(tool_input=tool_input):
                out = self.run_guard("pre", json.dumps({"cwd": str(self.t1), "tool_name": "Write",
                                                        "tool_input": tool_input, "transcript_path": broken}),
                                     {"KIT_ROLE": "builder"})
                self.assertEqual(bool(out), want == BLOCK, out)

    def test_the_reviewer_on_codex_transcripts(self):
        out_file = self.t1 / "review-out.md"
        env = {"KIT_REVIEW_OUT": str(out_file)}
        below, warn, over = (self.transcript(self.codex(n)) for n in (100_000, 150_000, 200_000))
        self.assertEqual(self.call("pre", below, "Bash", {"command": "ls"}, "reviewer", extra_env=env), {})
        warned = self.call("pre", warn, "Bash", {"command": "ls"}, "reviewer", extra_env=env)
        self.assertTrue(self.warned(warned))
        self.assertIn(str(out_file), warned["hookSpecificOutput"]["additionalContext"])
        post = self.call("post", warn, "Bash", {"command": "ls"}, "reviewer", extra_env=env)
        self.assertEqual(post["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        rows = [
            ({"command": "git diff main...HEAD"}, PASS),
            ({"command": f"Set-Content -Path '{out_file}' -Value 'findings so far'"}, PASS),
            ({"command": f"echo findings > '{out_file}'"}, PASS),
            ({"command": "New-Item -ItemType File scratch.txt"}, BLOCK), ({"command": "python -m pytest"}, BLOCK),
            ({"command": f"echo x > '{self.t1 / 'other.md'}'"}, BLOCK),
            ({"command": f"cat '{self.coord / 'messages/m.md'}'"}, BLOCK),  # the reviewer's steps are narrower
        ]
        for tool_input, want in rows:
            with self.subTest(tool_input=tool_input):
                out = self.call("pre", over, "Bash", tool_input, "reviewer", extra_env=env)
                self.assertEqual(self.refused(out), want == BLOCK, out)
        patch = "*** Begin Patch\n*** Add File: {}\n+x\n*** End Patch"
        self.assertFalse(self.refused(self.call("pre", over, "apply_patch", {"command": patch.format(out_file)},
                                                "reviewer", extra_env=env)))
        self.assertTrue(self.refused(self.call("pre", over, "apply_patch", {"command": patch.format(self.t1 / "x.py")},
                                               "reviewer", extra_env=env)))

    @staticmethod
    def result(tool_use_id, error=False):
        block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": "x"}
        return {"type": "user", "message": {"role": "user", "content": [{**block, "is_error": True} if error else block]}}

    def test_missed_handoff_at_stop(self):
        handoff = self.coord / "handoffs/builder.md"
        write = {"type": "tool_use", "id": "w1", "name": "Write", "input": {"file_path": str(handoff), "content": "x"}}
        no_handoff = self.transcript(self.claude(300_000), self.claude(600_000))
        before = self.transcript(self.claude(300_000, content=[write]), self.result("w1"), self.claude(600_000))
        after = self.transcript(self.claude(300_000), self.claude(600_000, content=[write]), self.result("w1"),
                                self.claude(610_000))
        failed = self.transcript(self.claude(600_000, content=[write]), self.result("w1", error=True),
                                 self.claude(610_000))  # review round 1: a refused write is no handoff
        unanswered = self.transcript(self.claude(600_000, content=[write]), self.claude(610_000))
        shell = self.transcript(self.claude(600_000, content=[{"type": "tool_use", "id": "b1", "name": "Bash",
                                                              "input": {"command": f"echo x > '{handoff}'"}}]),
                                self.result("b1"))
        out = self.call("stop", no_handoff)
        self.assertEqual(out["decision"], "block")
        self.assertTrue(out["reason"].startswith("BLOCKED (missed handoff"), out)
        self.assertEqual(self.call("stop", before)["decision"], "block")  # written before crossing: not this one
        self.assertEqual(self.call("stop", after), {})
        self.assertEqual(self.call("stop", failed)["decision"], "block")
        self.assertEqual(self.call("stop", unanswered)["decision"], "block")
        self.assertEqual(self.call("stop", shell), {})
        self.assertEqual(self.call("stop", self.transcript(self.claude(300_000))), {})  # below handoff

    def test_the_triager(self):
        """C7 section 13: the review script's triager (KIT_ROLE=triager, a one-shot Claude process) gets a
        builder's control-file rules and the reviewer's context levels (55/70) on its Claude transcript.
        Without the role every call of it was refused as an unknown role (PR #83 ran it as a builder)."""
        at_60, at_72 = self.transcript(self.claude(600_000)), self.transcript(self.claude(720_000))
        read = ("Read", {"file_path": str(self.t1 / "src/app.py")})
        out = self.call("pre", at_60, *read, role="triager")
        self.assertTrue(self.warned(out) and not self.refused(out), out)  # past a builder's 55, below 70
        self.assertTrue(self.refused(self.call("pre", at_60, *read, role="builder")))
        self.assertTrue(self.refused(self.call("pre", at_72, *read, role="triager")))
        for path, want in ((self.t1 / "AGENTS.md", True), (self.cx / "AGENTS.md", True),
                           (self.coord / "verdicts/t1/round-1.json", True), (self.t1 / "src/x.py", False)):
            with self.subTest(path=path):
                out = self.call("pre", self.transcript(), "Write", {"file_path": str(path)}, role="triager")
                self.assertEqual(self.refused(out), want, out)
        # it cannot write a handoff (Read, Grep and Glob only), so a stop past its level is not sent back
        self.assertEqual(self.call("stop", at_72, role="triager"), {})

    def steer_file(self, base, action, steer_id="steer-20261017T102000Z-ab12", body="t36 merged; READY may go."):
        path = self.coord / f"steer/{base}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nformat: steer\nversion: 1\nid: {steer_id}\naction: {action}\nheadline: x\n"
                        f"written_at: 2026-10-17T10:20:00Z\n---\n{body}\n", encoding="utf-8")
        return path

    def test_steering(self):
        """C9 section 9, the cases the live nudge and halt cannot vary: an acknowledgement of another id,
        `none`, the prompt event, a warning beside the nudge, a broken steer file, the orchestrator's key."""
        state = self.coord / "state/builder-sandbox-t1.md"
        state.parent.mkdir(parents=True, exist_ok=True)
        below, warn = self.transcript(self.claude(100_000)), self.transcript(self.claude(520_000))
        bash = ("Bash", {"command": "git status"})
        steer = self.steer_file("sandbox-t1", "nudge")
        try:
            for ack, shown in ((None, True), ("steer-20261017T090000Z-0000", True), ("steer-20261017T102000Z-ab12", False)):
                state.write_text(f"---\nrole: builder\nsteer_ack: {ack}\n---\n" if ack else "---\nrole: builder\n---\n",
                                 encoding="utf-8")
                for event in ("pre", "prompt"):
                    with self.subTest(ack=ack, event=event):
                        out = self.call(event, below, *(bash if event == "pre" else ()))
                        self.assertFalse(self.refused(out), out)
                        text = out.get("hookSpecificOutput", {}).get("additionalContext", "")
                        self.assertEqual(text.startswith("STEER steer-20261017T102000Z-ab12 from the orchestrator: t36 "
                                                         "merged; READY may go. Record steer_ack: "
                                                         "steer-20261017T102000Z-ab12 in your state file, "), shown, out)
                        if shown:  # the state file's path, so a session without the builder skill finds it
                            self.assertTrue(guard.folded(text).endswith(guard.folded(f"{state}.")), text)
            state.write_text("---\nrole: builder\n---\n", encoding="utf-8")
            both = self.call("pre", warn, *bash)["hookSpecificOutput"]["additionalContext"]
            self.assertTrue(both.startswith("CONTEXT (builder)") and "STEER steer-" in both, both)
            self.steer_file("sandbox-t1", "none")
            self.assertEqual(self.call("pre", below, *bash), {})
            self.steer_file("sandbox-t1", "halt", body="Ticket cancelled.")
            handoff = ("Write", {"file_path": str(self.coord / "handoffs/h.md"), "content": "x"})
            for event, args in (("pre", bash), ("pre", handoff), ("prompt", ())):
                with self.subTest(halt=event, args=args):
                    out = self.call(event, below, *args)
                    self.assertIs(out["continue"], False)
                    self.assertEqual(out["stopReason"], "HALT steer-20261017T102000Z-ab12 from the orchestrator: "
                                                        "Ticket cancelled.")
                    # continue: false alone lets the tool call run (M90), so a tool call is also denied
                    self.assertEqual(self.refused(out), event == "pre", out)
            # a broken steer file blocks a call that is not a handoff step (errors let those through, C5 section 1)
            steer.write_text("---\nid: steer-x\naction: stop\n---\nx\n", encoding="utf-8")
            out = self.run_guard("pre", json.dumps({"cwd": str(self.t1), "tool_name": "Bash", "transcript_path": below,
                                                    "tool_input": {"command": "echo x"}}), {"KIT_ROLE": "builder"})
            self.assertIn("BLOCKED (error", out["hookSpecificOutput"]["permissionDecisionReason"])
            # ... but it never skips the other checks: a READY sent while the steer file is broken is still
            # checked, though SendMessage is a handoff step (review round 1, blocker 1); other handoff steps go
            self.brief("36")
            for message, want in ((self.EVIDENCE, "t1 is stacked on t36, which has not merged"),
                                  ("READY t1", "READY without evidence"), ("Handing off.", None)):
                with self.subTest(broken_steer=message):
                    out = self.run_guard("pre", json.dumps({
                        "cwd": str(self.t1), "tool_name": "SendMessage", "transcript_path": below,
                        "tool_input": {"to": "sandbox-orch", "message": message}}), {"KIT_ROLE": "builder"})
                    reason = out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
                    self.assertIn(want, reason) if want else self.assertNotIn("BLOCKED", reason)
            self.brief("none")
            # the orchestrator's steer file is keyed by <project.name>-orch, not by the builder's
            self.assertEqual(self.call("pre", below, *bash, role="orchestrator", cwd=self.main), {})
            self.steer_file("sandbox-orch", "halt")
            self.assertIs(self.call("pre", below, *bash, role="orchestrator", cwd=self.main)["continue"], False)
        finally:
            for path in (self.coord / "steer").glob("*.md"):
                path.unlink()
            state.unlink(missing_ok=True)

    EVIDENCE = "READY t1 at abc1234\n\n```\n$ python -I -m pytest -q\n3 passed in 0.12s\n```\n"

    def brief(self, stacked_on="none", text=None):
        path = self.coord / "briefs/t1.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text is not None else
                        f"---\nformat: brief\nversion: 1\nticket: 1\nstacked_on: {stacked_on}\n---\n## Issue\nx\n",
                        encoding="utf-8")
        return path

    def merge_record(self, ticket, result):
        path = self.coord / f"merges/merge-20261017T101502Z-t{ticket}-3f2a9c1-{result[:4]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"format": "merge", "version": 1, "result": result, "ticket": ticket}),
                        encoding="utf-8")
        return path

    def test_stacked_ready(self):
        """C9 section 3: a builder whose brief has stacked_on: <m> may not send READY until a merge record
        with result: merged names ticket m; a missing or unreadable brief blocks. Through the script, since
        an error there would let SendMessage and messages/ writes through as handoff steps."""
        unmerged = ("BLOCKED (READY, role builder): t1 is stacked on t36, which has not merged. Valid: send READY "
                    "after t36 merges; merge its fix rounds upward meanwhile. Done: nothing was sent.")
        rows = [  # (what is on disk, the expected refusal text or part of it, or PASS)
            (lambda: self.brief("36"), unmerged),
            (lambda: (self.brief("36"), self.merge_record(36, "not-merged")), unmerged),
            (lambda: (self.brief("36"), self.merge_record(35, "merged")), unmerged),
            (lambda: (self.brief("36"), self.merge_record(36, "merged")), PASS),
            (lambda: (self.brief("t36"), self.merge_record(36, "merged")), PASS),
            (lambda: self.brief("none"), PASS),
            (lambda: None, "there is no brief"),
            (lambda: self.brief(text="ticket: 1\nstacked_on: none\n"), "the brief cannot be read"),
            (lambda: self.brief(text="---\nticket: 1\n---\n"), "stacked_on: (missing)"),
            (lambda: (self.brief("36"), (self.coord / "merges/merge-x.json").write_text("{", encoding="utf-8")),
             "cannot be read"),
        ]
        msg = self.coord / "messages/r.md"
        msg.parent.mkdir(parents=True, exist_ok=True)
        for i, (plant, want) in enumerate(rows):
            for path in [self.coord / "briefs/t1.md", *(self.coord / "merges").glob("merge-*.json")]:
                path.unlink(missing_ok=True)
            plant()
            for tool, tool_input in (("SendMessage", {"to": "sandbox-orch", "message": self.EVIDENCE}),
                                     ("Write", {"file_path": str(msg), "content": self.EVIDENCE})):
                with self.subTest(row=i, tool=tool):
                    out = self.run_guard("pre", json.dumps({"cwd": str(self.t1), "tool_name": tool,
                                                            "tool_input": tool_input, "transcript_path": "t.jsonl"}),
                                         {"KIT_ROLE": "builder"})
                    reason = out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
                    if want == PASS:
                        self.assertEqual(out, {}, reason)
                    else:
                        self.assertIn(want, reason)
                        self.assertTrue(reason.startswith("BLOCKED (READY, role builder)"), reason)
        for path in (self.coord / "merges").glob("merge-*.json"):  # the class's project is shared
            path.unlink()
        self.brief("none")
        # only a READY claim reads the brief; any other message does not need one
        (self.coord / "briefs/t1.md").unlink()
        self.assertEqual(self.call("pre", self.transcript(), "SendMessage", {"message": "Handing off."}), {})
        self.brief("none")

    def test_ready_check(self):
        self.brief("none")
        evidence = "READY: issue #1 is done.\n\n```\n$ python -I -m pytest -q\n3 passed in 0.12s\n```\n"
        rows = [
            ("READY: issue #1 is done.", BLOCK), ("## READY\nAll done.", BLOCK), ("**READY** done", BLOCK),
            (evidence, PASS), ("Not READY yet; still testing.", PASS), ("Handing off.", PASS),
            (evidence.replace("3 passed", "2 passed, 1 failed"), BLOCK),
            (evidence.replace("3 passed in 0.12s", "no tests ran in 0.01s"), BLOCK),
            ("READY\n\n```\n> python -m unittest\nRan 0 tests in 0.000s\n\nOK\n```", BLOCK),
            ("READY\n\n```\nPS> python -m unittest\nRan 4 tests in 0.1s\n\nOK\n```", PASS),
            ("READY\n\n```\n$ python -m pytest\n```", BLOCK),  # a command with no output
            ("READY\n\n```\n3 passed\n```", BLOCK),  # output with no command line
            ("READY\n\n```\n$ pytest\n5 passed, 1 error in 2s\n```", BLOCK),
        ]
        msg = self.coord / "messages/r.md"
        msg.parent.mkdir(parents=True, exist_ok=True)
        for text, want in rows:
            with self.subTest(text=text):
                sent = self.call("pre", self.transcript(), "SendMessage", {"to": "orchestrator", "message": text})
                self.assertEqual(self.refused(sent), want == BLOCK, sent)
                written = self.call("pre", self.transcript(), "Write", {"file_path": str(msg), "content": text})
                self.assertEqual(self.refused(written), want == BLOCK, written)
                if want == BLOCK:
                    self.assertIn("BLOCKED (READY", sent["hookSpecificOutput"]["permissionDecisionReason"])
        # an Edit is checked as the file will be after it
        msg.write_text(evidence, encoding="utf-8")
        strip = {"file_path": str(msg), "old_string": "3 passed in 0.12s\n", "new_string": ""}
        self.assertTrue(self.refused(self.call("pre", self.transcript(), "Edit", strip)))
        keep = {"file_path": str(msg), "old_string": "is done", "new_string": "is finished"}
        self.assertEqual(self.call("pre", self.transcript(), "Edit", keep), {})
        # a shell write into messages/ is refused; the orchestrator is not checked
        self.assertTrue(self.refused(self.call("pre", self.transcript(), "Bash", {"command": f"echo READY > '{msg}'"})))
        self.assertTrue(self.refused(self.call("pre", self.transcript(), "Bash", {"command": f"echo hi >> '{msg}'"})))
        self.assertEqual(self.call("pre", self.transcript(), "SendMessage", {"message": "READY"}, "orchestrator",
                                   cwd=self.main), {})
        # the builder skill's pointer to a READY file is not the READY: its summary line is no claim (M125: every
        # builder's first pointer, summary "READY t120 to orchestrator", was refused for want of evidence); the
        # file was checked where it was written
        pointer = {"to": "sandbox-orch", "message": "New message: 20261017T160200Z-sandbox-t1.md",
                   "summary": "READY t1 to orchestrator"}
        self.assertEqual(self.call("pre", self.transcript(), "SendMessage", pointer), {})
        # a READY claim in the message itself is still checked
        self.assertTrue(self.refused(self.call("pre", self.transcript(), "SendMessage",
                                               {**pointer, "message": "READY: issue #1 is done."})))


def apply_entries(project):
    """What the install does with settings-entries.json (C2 section 4): append each value at its pointer."""
    doc = json.loads((KIT / "settings-entries.json").read_text(encoding="utf-8"))
    for entry in doc["entries"]:
        path = project / entry["path"]
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        *parents, last = entry["pointer"].strip("/").split("/")
        node = data
        for key in parents:
            node = node.setdefault(key, {})
        node.setdefault(last, []).append(entry["value"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")


class Entries(Project):
    """The kit's settings entries, the --settings a launch passes, and the selftest (C5 sections 1, 4)."""

    FORMS = ["git push --force", "git push -f", "git push --force-with-lease", "git reset --hard", "git branch -D",
             "git branch -d", "git branch --delete", "git rebase", "gh pr merge", "gh repo delete",
             "python -I .agents/kit/bin/merge.py yours", "python -I .agents/kit/bin/merge.py resume", "kit merge"]
    ALLOWED = ["python -I .agents/kit/bin/merge.py " + sub for sub in ("auto", "check", "status", "reconcile")]
    AUTO = "python -I .agents/kit/bin/merge.py auto"  # denied in a builder's and the triager's --settings

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for rel in ("hooks/guard.py", "bin/kitconfig.py", "settings-entries.json"):  # the main checkout's machinery
            (cls.main / ".agents/kit" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(KIT / rel, cls.main / ".agents/kit" / rel)
        apply_entries(cls.main)

    def entries(self):
        return json.loads((KIT / "settings-entries.json").read_text(encoding="utf-8"))

    def test_the_shipped_entries(self):
        doc = self.entries()
        self.assertEqual((doc["format"], doc["version"]), ("settings-entries", 1))
        names = [e["name"] for e in doc["entries"]]
        self.assertEqual(len(names), len(set(names)))
        hooks = {"guard-pre": (".claude/settings.json", "/hooks/PreToolUse", "pre"),
                 "guard-prompt": (".claude/settings.json", "/hooks/UserPromptSubmit", "prompt"),
                 "guard-stop": (".claude/settings.json", "/hooks/Stop", "stop"),
                 "codex-guard-pre": (".codex/hooks.json", "/hooks/PreToolUse", "pre"),
                 "codex-guard-post": (".codex/hooks.json", "/hooks/PostToolUse", "post")}
        by_name = {e["name"]: e for e in doc["entries"]}
        for name, (path, pointer, event) in hooks.items():
            with self.subTest(entry=name):
                e = by_name[name]
                self.assertEqual((e["path"], e["pointer"]), (path, pointer))
                (hook,) = e["value"]["hooks"]
                text = " ".join(hook.get("args", [])) if "args" in hook else hook["command"]
                self.assertRegex(text, r"(^|\s|/)\.agents/kit/hooks/guard\.py " + event + "$")
                self.assertEqual(hook["timeout"], 30)  # above the 7.5 s a Python start took under load (M14)
                self.assertEqual(hook.get("onFailure"), "block" if name == "guard-pre" else None)
        rules = {e["value"] for e in doc["entries"] if e["pointer"] == "/permissions/deny"}
        allowed = {e["value"] for e in doc["entries"] if e["pointer"] == "/permissions/allow"}
        for tool in ("Bash", "PowerShell"):
            for form in self.FORMS:
                self.assertLessEqual({f"{tool}({form})", f"{tool}({form} *)"}, rules)
            for form in self.ALLOWED:  # C8 section 15: the narrow allow entries, nothing wider
                self.assertLessEqual({f"{tool}({form})", f"{tool}({form} *)"}, allowed)
        self.assertEqual(len(allowed), 4 * 2 * 2, allowed)
        self.assertFalse(any("yours" in a or "resume" in a for a in allowed), allowed)
        for e in doc["entries"]:  # every entry is a hook object in hooks.<Event> or a rule string (C2 section 4)
            hook_entry = e["pointer"].startswith("/hooks/")
            self.assertIn(e["path"], (".claude/settings.json", ".codex/hooks.json"), e["name"])
            self.assertTrue(isinstance(e["value"], dict) if hook_entry else
                            e["pointer"] in ("/permissions/deny", "/permissions/allow") and isinstance(e["value"], str),
                            e["name"])

    def test_launch_settings(self):
        guard_path = (self.main / ".agents/kit/hooks/guard.py").as_posix()
        builder = guard.launch_settings(self.main, "builder")
        self.assertIs(builder["disableAllHooks"], False)  # overrides the local file's switch (M19, M20)
        for event, arg in (("PreToolUse", "pre"), ("UserPromptSubmit", "prompt"), ("Stop", "stop")):
            (group,) = builder["hooks"][event]
            (hook,) = group["hooks"]
            self.assertEqual(hook["args"], ["-I", guard_path, arg])  # main's guard, by absolute path (M22)
        self.assertEqual(builder["hooks"]["PreToolUse"][0]["hooks"][0]["onFailure"], "block")
        control = kitconfig.load_schema(self.main)["fixed"]["control_paths"]
        auto = [f"{tool}({self.AUTO}{rest})" for tool in ("Bash", "PowerShell") for rest in ("", " *")]
        self.assertEqual(builder["permissions"]["deny"], [f"Edit(./{p})" for p in control] + auto)
        self.assertNotIn("permissions", guard.launch_settings(self.main, "orchestrator"))
        printed = subprocess.run([sys.executable, "-I", guard_path, "settings", "builder"], capture_output=True,
                                 text=True)
        self.assertEqual(json.loads(printed.stdout), builder)
        # the triager (C7 section 13): a builder's settings, printed by `guard.py settings triager`
        printed = subprocess.run([sys.executable, "-I", guard_path, "settings", "triager"], capture_output=True,
                                 text=True)
        self.assertEqual(printed.returncode, 0, printed.stderr)
        self.assertEqual(json.loads(printed.stdout), builder)

    def test_selftest(self):
        self.assertEqual(guard.selftest(self.main, claude_version="2.1.301"), [])
        self.assertTrue(any("2.1.295" in p for p in guard.selftest(self.main, claude_version="2.1.200")))
        # a config the guard cannot read fails the selftest, not only the session's later calls (review round 1)
        config = self.main / "agent-kit.toml"
        good = config.read_text(encoding="utf-8")
        try:
            config.write_text(good + "\n[reviewer]\nefort = 'high'\n", encoding="utf-8")
            self.assertTrue(any("did not pass" in p for p in guard.selftest(self.main, claude_version="2.1.301")))
        finally:
            config.write_text(good, encoding="utf-8")
        settings = self.main / ".claude/settings.json"
        original = settings.read_text(encoding="utf-8")
        try:
            settings.write_text(original.replace('"timeout": 30', '"timeout": 5', 1), encoding="utf-8")
            self.assertTrue(any("guard-pre" in p for p in guard.selftest(self.main, claude_version="2.1.301")))
            settings.unlink()
            problems = guard.selftest(self.main, claude_version="2.1.301")
            self.assertTrue(any("guard-prompt" in p for p in problems), problems)
        finally:
            settings.write_text(original, encoding="utf-8")
        # the command: exit 0 when it passes, 1 with the reasons when it fails (C5 section 1)
        script = str(self.main / ".agents/kit/hooks/guard.py")
        r = subprocess.run([sys.executable, "-I", script, "selftest"], capture_output=True, text=True)
        if shutil.which("claude"):
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        codex = self.main / ".codex/hooks.json"
        saved = codex.read_text(encoding="utf-8")
        codex.unlink()
        try:
            r = subprocess.run([sys.executable, "-I", script, "selftest"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("codex-guard-pre", r.stdout)
        finally:
            codex.write_text(saved, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
