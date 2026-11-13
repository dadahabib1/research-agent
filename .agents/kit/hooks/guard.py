"""The guard (contract C5): every check for one hook event, in one process.

    python -I .agents/kit/hooks/guard.py pre|prompt|stop|post   (the harness's JSON payload on stdin)

Claude Code runs `pre` (PreToolUse), `prompt` (UserPromptSubmit) and `stop` (Stop); Codex runs `pre` and
`post` (PostToolUse). It stops mistakes and overeager actions, not a session set on getting around it
(decision 107). Standard library only. It never returns allow: a refusal, or nothing.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))  # C1 section 2: imports by __file__ under -I

import kitconfig  # noqa: E402

EVENTS = ("pre", "prompt", "stop", "post")
ROLES = ("orchestrator", "builder", "reviewer", "triager")  # the triager: C7 section 7, C5 section 1
SHELLS = ("Bash", "PowerShell")  # Codex reports its shell as Bash (M28)
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
RUNTIME_RECORDS = ("reviews/**", "verdicts/**", "merges/**", "locks/merge.lock")  # C4; written by the kit's scripts
USER_SETTINGS = (".claude/settings.json", ".claude/settings.local.json")
GH_MCP = ("merge_pull_request", "branch_protection", "ruleset", "delete_repo")
NOTHING_RUN = "nothing was run"
CONTROL_CHANGE = "control changes go through a control/<topic> worktree and a PR the user merges (decision 104)"


class Refusal(Exception):
    def __init__(self, check: str, failed: str, valid: str, done: str = NOTHING_RUN):
        super().__init__(failed)
        self.check, self.failed, self.valid, self.done = check, failed, valid, done


def refusal_text(check: str, role: str, failed: str, valid: str, done: str = NOTHING_RUN) -> str:
    return f"BLOCKED ({check}, role {role}): {failed}. Valid: {valid}. Done: {done}."


HOOK_EVENTS = {"pre": "PreToolUse", "prompt": "UserPromptSubmit", "post": "PostToolUse", "stop": "Stop"}


def output(event: str, reason: str | None, warning: str | None = None, halt: str | None = None) -> dict:
    """The one output function (M12): a halt, a block, a warning (M6, M7, M26), or nothing; never allow.
    A halt is `continue: false`, which ends the turn (M90); on a tool call it also denies the call, since
    `continue: false` alone lets that call run first (M90)."""
    if halt is not None and event in ("pre", "prompt"):
        out = {"continue": False, "stopReason": halt}
        if event == "pre":
            out["hookSpecificOutput"] = {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                         "permissionDecisionReason": reason or halt}
        return out
    if reason is not None:
        if event == "pre":
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": reason}}
        return {"decision": "block", "reason": reason}
    if warning is not None and event != "stop":
        return {"hookSpecificOutput": {"hookEventName": HOOK_EVENTS[event], "additionalContext": warning}}
    return {}


def git(cwd, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def git_out(cwd, *args) -> str:
    r = git(cwd, *args)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd}: {r.stderr.strip()}")
    return r.stdout.strip()


def folded(path: str) -> str:
    """A relative path for comparison: forward slashes, case-folded where the file system is."""
    path = path.replace("\\", "/")
    return path.lower() if os.name == "nt" else path


def matches(rel: str, patterns) -> bool:
    rel = folded(rel)
    for pattern in map(folded, patterns):
        if pattern.endswith("/**"):
            if rel == pattern[:-3] or rel.startswith(pattern[:-2]):
                return True
        elif rel == pattern:
            return True
    return False


def inside(loc: str, root: str) -> str | None:
    """`loc` relative to `root` (both from kitconfig.location), or None when it is not inside."""
    try:
        rel = os.path.relpath(loc, root)
    except ValueError:  # another drive
        return None
    return None if rel == ".." or rel.startswith(".." + os.sep) else rel


# ---------------------------------------------------------------- the session's places (C5 section 1)


class Context:
    def __init__(self, payload: dict, env):
        self.cwd = Path(payload["cwd"])
        self.env = env
        self.role = self.find_role()
        self.payload = payload

    @cached_property
    def transcript(self) -> str:
        return self.payload["transcript_path"]  # M31, M37; a missing field is an error

    @cached_property
    def percent(self) -> float:
        return context_percent(self)

    @cached_property
    def values(self) -> dict:
        """The main checkout's settings and their sources, so an older branch cannot bring older rules."""
        return kitconfig.effective(self.main)

    @cached_property
    def main(self) -> Path:
        """The main checkout: the parent of the shared git folder, so every worktree finds the same one."""
        return Path(git_out(self.cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent

    def find_role(self) -> str:
        role = self.env.get("KIT_ROLE")
        if role is not None:
            if role not in ROLES:
                raise ValueError(f"KIT_ROLE is {role!r}; valid: {', '.join(ROLES)}")
            return role
        project_dir = self.env.get("CLAUDE_PROJECT_DIR")
        if project_dir is None:
            return "reviewer"  # Codex sets no CLAUDE_PROJECT_DIR
        return "orchestrator" if self.same(project_dir, self.main) else "builder"

    def loc(self, path) -> str:
        return kitconfig.location(self.cwd, os.path.expanduser(str(path)))

    def same(self, a, b) -> bool:
        return self.loc(a) == self.loc(b)

    @cached_property
    def schema(self) -> dict:
        return kitconfig.load_schema(self.main)

    @cached_property
    def coordination(self) -> str:
        """The coordination folder, from the main checkout's config, so an older branch cannot move it."""
        return kitconfig.location(self.main, str(self.values["coordination"][0]))

    @cached_property
    def worktrees(self) -> list[tuple[str, str]]:
        """(location, branch) for every checkout git knows, the longest path first."""
        rows, path = [], None
        for line in git_out(self.main, "worktree", "list", "--porcelain").splitlines():
            if line.startswith("worktree "):
                path = line[len("worktree "):]
                rows.append([kitconfig.location(self.main, path), ""])
            elif line.startswith("branch ") and rows:
                rows[-1][1] = line[len("branch "):].removeprefix("refs/heads/")
        return sorted(map(tuple, rows), key=lambda r: len(r[0]), reverse=True)

    @cached_property
    def default_branch(self) -> str:
        r = git(self.main, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
        if r.returncode == 0 and "/" in r.stdout:
            return r.stdout.strip().split("/", 1)[1]
        return git_out(self.main, "branch", "--show-current") or "main"

    @cached_property
    def branch(self) -> str:
        """The branch of the checkout the session started in (CLAUDE_PROJECT_DIR stays it after a cd, M15-M17),
        or of `cwd` when that is not set; '' on a detached head or outside a repository."""
        r = git(self.env.get("CLAUDE_PROJECT_DIR") or self.cwd, "branch", "--show-current")
        return r.stdout.strip() if r.returncode == 0 else ""

    @cached_property
    def ticket(self) -> int | None:
        """A builder's ticket, from its worktree's branch `t<n>` (C6 section 3); None on any other branch."""
        found = re.fullmatch(r"t(\d+)", self.branch) if self.role == "builder" else None
        return int(found.group(1)) if found else None

    @cached_property
    def base_name(self) -> str | None:
        """The role slot's name without C6's `-<k>` suffix (C9 section 1, rule 4), which keys steer and state
        files; None for the reviewer and for a builder that is not on a ticket branch."""
        project = self.values["project.name"][0]
        if self.role == "orchestrator":
            return f"{project}-orch"
        return f"{project}-t{self.ticket}" if self.ticket is not None else None

    def state_file(self) -> Path:
        name = "orchestrator.md" if self.role == "orchestrator" else f"builder-{self.base_name}.md"
        return Path(self.coordination) / "state" / name


# ---------------------------------------------------------------- reading commands as written


TOKEN = re.compile(r'"([^"]*)"|\'([^\']*)\'|([^\s"\']+)')
WRAPPERS = {"sudo", "env", "command", "nohup", "time", "exec"}
INLINE = {"python", "python3", "py", "node", "bash", "sh", "zsh", "powershell", "pwsh", "cmd", "perl", "ruby"}
INLINE_FLAGS = {"-c", "-e", "-command", "/c"}
CD_NAMES = {"cd", "chdir", "pushd", "push-location", "set-location", "sl"}


def outer(text: str, names: dict) -> str:
    """Text as the outer shell hands it to a child shell: the variables the command set substituted, `$PWD`
    the folder before the child's own cd (`$(pwd)`, unplaceable, when the guard does not know it)."""
    return re.sub(r"\$\{?(\w+)\}?", lambda m: names.get(m.group(1), "$(pwd)" if m.group(1) == "PWD"
                                                        else m.group(0)), text)


def words(text: str, names: dict | None = None) -> list[str]:
    """Shell words, quotes removed; pieces with no space between them are one word (G="C:/a b"). With
    `names`, pieces outside single quotes are expanded as the outer shell does (outer())."""
    out, end = [], None
    for m in TOKEN.finditer(text):
        piece = "".join(m.groups(""))
        if names is not None and m.group(2) is None:
            piece = outer(piece, names)
        if out and m.start() == end:
            out[-1] += piece
        else:
            out.append(piece)
        end = m.end()
    return out


def cd_target(ws: list[str]) -> str:
    """A cd's folder as written: its first operand, a lone `-` (the folder before, which the guard does not
    know) included; `~` when there is none."""
    return next((a for a in ws[1:] if a == "-" or not a.startswith("-")), "~")


def name(word: str) -> str:
    """A command word as run: no folder, no .exe, lower case."""
    return re.split(r"[\\/]", word)[-1].lower().removesuffix(".exe")


SHELL_LIKE = {"bash", "sh", "zsh", "powershell", "pwsh", "cmd"}


SHELL_FOLDER = re.compile(r"\$(?:env:)?\{?(?:PWD|OLDPWD)\}?(?!\w)|%CD%", re.I)


def native(path: str, names: dict | None = None) -> str:
    """A path as Windows opens it: Git Bash's /c/Users/... is C:/Users/...; variables expanded, first the
    ones the command set itself (`G="C:/x"; git -C "$G" ...`), then the environment's. `$PWD` is the folder
    the command is in (units() sets it); the shell's other folders ($OLDPWD, %CD%, $env:PWD) are not the hook
    process's, so they stay unexpanded, and unplaceable (decision 107)."""
    names = names or {}
    path = SHELL_FOLDER.sub(lambda m: names.get("PWD", m.group(0)) if re.fullmatch(r"\$\{?PWD\}?", m.group(0))
                            else m.group(0), path)
    if SHELL_FOLDER.search(path):
        return path
    if names:
        path = re.sub(r"\$(?:env:)?\{?(\w+)\}?", lambda m: names.get(m.group(1), m.group(0)), path)
        if SHELL_FOLDER.search(path):  # one a variable of the command's holds: `G="$OLDPWD"; cd "$G"`
            return path
    path = os.path.expanduser(os.path.expandvars(path))
    if os.name == "nt":
        path = re.sub(r"^/([A-Za-z])(?=/|$)", lambda m: m.group(1).upper() + ":", path)
    return path


def placeable(path: str) -> bool:
    """False for a path the guard cannot know: a variable left unexpanded, or a substitution."""
    return not re.search(r"[$%`]", path)


def heredocs(command: str) -> list[tuple[str, str]]:
    """The command's lines without heredoc bodies, each with the body it opens ('' for none). A body is
    text fed to a command, not commands to run, unless that command is an interpreter (see units)."""
    out, ends = [], []
    for line in command.split("\n"):
        if ends:
            if line.strip() == ends[0]:
                ends.pop(0)
            else:
                out[-1] = (out[-1][0], out[-1][1] + line + "\n")
            continue
        out.append((line, ""))
        for m in re.finditer(r"<<-?\s*", masked(line)):  # the operator outside quotes, the word as written
            word = re.match(r"['\"]?([A-Za-z_]\w*)", line[m.end():])
            if word:
                ends.append(word.group(1))
    return out


@dataclass
class Unit:
    words: list[str]  # past `sudo`, `env` and NAME=value
    segment: str  # as written, for redirections
    here: Path | None  # the folder it runs in; None after a cd the guard cannot follow
    code: str | None  # code it runs: `bash -c`, `python -c`, or a heredoc fed to an interpreter
    names: dict  # variables the command set before it


def units(command: str, here: Path | None, depth: int = 0, names: dict | None = None) -> list[Unit]:
    """Each command that runs, in order, with the folder it runs in. A `cd <path>` moves the ones after it
    (sessions start most commands with one: 8,284 of 13,639 in equity_analyst). Quoted text that is only
    an argument (a commit message, a search pattern) and a heredoc fed to `cat` are not commands."""
    out, names = [], {} if names is None else names
    if here is not None:
        names["PWD"] = str(here)
    for line, body in heredocs(command):
        for segment in segments(line):
            ws = words(unredirected(segment)) or words(segment)  # `> file` alone is still read by its writes
            assigned = re.fullmatch(r"\$(\w+)=(.+)", "".join(ws)) if len(ws) <= 3 else None
            if assigned and (len(ws) == 1 or ws[1] == "="):  # PowerShell: $wt = 'C:/x' or $d="C:\x"
                names[assigned.group(1)] = native(assigned.group(2), names)
                continue
            while ws and (name(ws[0]) in WRAPPERS or re.match(r"^\w+=", ws[0])):
                if re.match(r"^\w+=", ws[0]) and len(ws) == 1:  # NAME=value alone sets it for what follows
                    key, value = ws[0].split("=", 1)
                    names[key] = native(value, names)
                ws = ws[1:]
            if not ws:  # a wrapper or NAME=value with only a redirection after it: its write is still checked
                ws = words(segment)
                while ws and (name(ws[0]) in WRAPPERS or re.match(r"^\w+=", ws[0])):
                    ws = ws[1:]
            if not ws:
                continue
            code = None
            if name(ws[0]) in INLINE:
                # a child shell's body as the outer shell passes it: expanded before the child's own cd, unless
                # in single quotes or a quoted heredoc word (PR #119's review, round 1)
                child = name(ws[0]) in SHELL_LIKE
                at = words(unredirected(segment), names)[-len(ws):] if child else ws
                given = [at[i + 1] for i in range(1, len(at) - 1) if at[i].lower() in INLINE_FLAGS]
                fed = outer(body, names) if child and not re.search(r"<<-?\s*['\"\\]", segment) else body
                code = "\n".join(given + ([fed] if body and "<<" in segment else [])) or None
            out.append(Unit(ws, segment, here, code, dict(names)))
            if code and name(ws[0]) in SHELL_LIKE and depth < 3:
                out += units(code, here, depth + 1, dict(names))
            if name(ws[0]) in CD_NAMES:
                target = native(cd_target(ws), names)
                if target == "-" or not placeable(target):
                    here = None
                elif os.path.isabs(target):
                    here = Path(target)
                else:
                    here = here / target if here is not None else None
                if here is None:
                    names.pop("PWD", None)
                else:
                    names["PWD"] = str(here)
    return out


# a descriptor's digits only at a word's start: in `main2>log` the 2 is the argument's (PR #114 review round 1)
REDIRECTION = re.compile(r"(?:(?<!\S)\d+)?(?<![<>&])(?:&>>?|>>?|<(?!<))(&(?:\d+|-))?")


def unredirected(segment: str) -> str:
    """The segment without its redirections (`2>&1`, `>file`, `2> /dev/null`, `&>log`, `<in`), found outside
    quotes, so they are not read as arguments (issue #103, M135). A heredoc's `<<` stays; `write_targets` reads the
    targets from the segment as written."""
    m, out, at = masked(segment), [], 0
    for r in REDIRECTION.finditer(m):
        if r.start() < at:
            continue
        end = r.end()
        if not r.group(1):  # not a descriptor copy: the target word follows, maybe after spaces
            target = re.match(r"\s*\S+", m[end:])
            end += target.end() if target else 0
        out.append(segment[at:r.start()] + " ")
        at = end
    return "".join(out) + segment[at:]


def segments(command: str) -> list[str]:
    """The command split at ; && || | line breaks and brackets, outside quotes."""
    out, cur, quote, i = [], [], None, 0
    while i < len(command):
        ch = command[i]
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "&" and (command[i - 1:i] in ("<", ">") or command[i + 1:i + 2] == ">"):
            pass  # 2>&1, <&3, &>file: a redirection, not the & that ends a command (issue #103)
        elif ch in ";|\n(){}`&":
            out.append("".join(cur))
            cur = []
            i += 2 if command[i:i + 2] in ("&&", "||") else 1
            continue
        cur.append(ch)
        i += 1
    out.append("".join(cur))
    return [s.strip() for s in out if s.strip()]


# ---------------------------------------------------------------- git (C5 section 3)


def split_git(args: list[str]) -> tuple[str | None, str, list[str]]:
    """(the -C path, the subcommand, its arguments), past git's global options."""
    at, i = None, 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(args):
            at = args[i + 1] if args[i] == "-C" else at
            i += 2
        else:
            i += 1
    return at, (args[i] if i < len(args) else ""), args[i + 1:]


def short_flag(args, letter) -> bool:
    return any(a.startswith("-") and not a.startswith("--") and letter in a[1:] for a in args)


def positional(args, takes_value=()) -> list[str]:
    takes, out, skip = {t.lower() for t in takes_value}, [], False
    for a in args:
        if skip:
            skip = False
        elif a.startswith("-"):
            skip = a.lower() in takes
        else:
            out.append(a)
    return out


def git_folder(here: Path | None, at: str | None, names: dict | None = None) -> Path | None:
    """The folder a git command runs in (its -C after the session's folder), or None when unknown."""
    if at is None:
        return here
    at = native(at, names)
    if not placeable(at):
        return None
    if os.path.isabs(at):
        return Path(at)
    return here / at if here is not None else None


def check_git(ctx: Context, command: str):
    for unit in units(command, ctx.cwd):
        if name(unit.words[0]) != "git":
            continue
        at, sub, rest = split_git(unit.words[1:])
        folder = git_folder(unit.here, at, unit.names)
        if folder is None:
            checkout = ctx.main  # C5: when the guard cannot tell, the main checkout
        else:
            top = git(folder, "rev-parse", "--show-toplevel")
            if top.returncode != 0:
                continue  # not a repository, or no such folder: git fails on its own
            checkout = Path(top.stdout.strip())
        in_main = ctx.same(checkout, ctx.main)
        if sub == "push":
            check_push(ctx, checkout, rest)
        elif sub == "branch" and ("--delete" in rest or short_flag(rest, "d") or short_flag(rest, "D")):
            raise Refusal("git", "deleting a branch", "branches are kept; leave it")
        elif sub == "reset" and "--hard" in rest:
            raise Refusal("git", "git reset --hard discards work", "commit your work, or ask the user to discard it")
        elif sub == "clean" and ("--force" in rest or short_flag(rest, "f")):
            raise Refusal("git", "git clean -f deletes untracked files", "remove files one at a time by name, or ask the user")
        elif sub in ("checkout", "restore") and "." in rest:
            raise Refusal("git", f"git {sub} . discards every change", f"git {sub} <file> for one named file")
        elif sub == "rebase":
            raise Refusal("git", "git rebase rewrites history", "merge main into your branch: git merge origin/<default branch>")
        elif sub == "worktree" and rest[:1] == ["remove"]:
            raise Refusal("git", "removing a worktree", "the guarded merge removes merged worktrees")
        elif sub == "stash" and rest[:1] not in (["list"], ["show"]):
            raise Refusal("git", "git stash hides work outside any branch", "commit your work on your branch; git stash list and git stash show are allowed")
        elif in_main:
            check_main_checkout(ctx, sub, rest)


def check_push(ctx: Context, checkout: Path, args: list[str]):
    if any(a in ("--force", "--force-if-includes") or a.startswith("--force-with-lease") for a in args) \
            or short_flag(args, "f"):
        raise Refusal("git", "a force push", "push without force: git push origin <your branch>")
    if "--delete" in args or short_flag(args, "d"):
        raise Refusal("git", "deleting a remote branch", "branches are kept; leave it")
    if "--all" in args or "--mirror" in args:
        raise Refusal("git", "pushing every branch, main included", "push your branch: git push origin <your branch>")
    named = positional(args, ("-o", "--push-option", "--repo", "--receive-pack", "--exec"))
    repo_option = any(a == "--repo" or a.startswith("--repo=") for a in args)
    refspecs = named if repo_option else named[1:]  # the repository is an option or the first word
    current = git_out(checkout, "branch", "--show-current")
    targets = []
    for spec in refspecs:
        if spec.startswith("+"):
            raise Refusal("git", "a force push (a + refspec)", "push without force: git push origin <your branch>")
        if spec.startswith(":"):
            raise Refusal("git", "deleting a remote branch", "branches are kept; leave it")
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        targets.append(current if dst == "HEAD" else dst.removeprefix("refs/heads/"))
    if not refspecs:
        targets.append(current)
    if ctx.default_branch in targets:
        raise Refusal("git", f"a push to {ctx.default_branch}",
                      f"push your branch; {ctx.default_branch} changes only by merged PRs")


MAIN_CHANGES = ("checkout", "switch", "reset", "restore", "merge", "cherry-pick", "revert", "am", "apply", "pull")


def check_main_checkout(ctx: Context, sub: str, args: list[str]):
    default = ctx.default_branch
    rest = positional(args)
    if sub == "pull" and "--ff-only" in args and rest in ([], ["origin", default]):
        return
    if sub == "merge" and "--ff-only" in args and rest == [f"origin/{default}"]:
        return
    if sub in MAIN_CHANGES or (sub == "stash" and args[:1] in (["pop"], ["apply"])):
        raise Refusal("git", f"git {sub} changes the main checkout's files",
                      "main changes only by merged PRs; update it with git pull --ff-only")


# ---------------------------------------------------------------- GitHub (C5 section 3)


def check_github(command: str):
    for args in (u.words[1:] for u in units(command, None) if name(u.words[0]) == "gh"):
        if "--admin" in args:
            raise Refusal("github", "an --admin override", "no admin overrides; the user decides")
        sub = args[:2]
        if sub == ["pr", "merge"]:
            raise Refusal("github", "gh pr merge", YOURS_VALID)
        if sub == ["repo", "sync"] and ("--force" in args or short_flag(args[2:], "f")):
            raise Refusal("github", "gh repo sync --force resets a branch", "git pull --ff-only")
        if sub[:1] == ["repo"] and (sub[1:] in (["delete"], ["archive"], ["rename"]) or (
                sub[1:] == ["edit"] and any(a.startswith(("--visibility", "--default-branch")) for a in args))):
            raise Refusal("github", f"gh repo {sub[1]} changes the repository", "repository settings are the user's")
        if sub[:1] == ["api"]:
            check_gh_api(args[1:])


def check_gh_api(args: list[str]):
    method = None
    for i, a in enumerate(args):
        if a in ("-X", "--method") and i + 1 < len(args):
            method = args[i + 1]
        elif a.startswith("--method="):
            method = a.split("=", 1)[1]
        elif a.startswith("-X") and len(a) > 2:
            method = a[2:]
    if method is None:
        sends = any(a in ("-f", "-F", "--field", "--raw-field", "--input") or re.match(r"^-[fF].", a)
                    or a.startswith(("--field=", "--raw-field=", "--input=")) for a in args)
        method = "POST" if sends else "GET"
    paths = positional(args, ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input", "-H", "--header",
                              "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview"))
    path = paths[0] if paths else ""
    if method.upper() != "GET" and re.search(r"/protection\b|rulesets|/pulls/\d+/merge\b|/merges\b", path):
        raise Refusal("github", f"gh api {method.upper()} {path}", "branch protection, rulesets and merges are the user's or the guarded merge's")


# ---------------------------------------------------------------- the session block (C5 section 3, C8 section 15)


RUNNERS = {"python", "python3", "py", "pythonw", "uv", "run"}  # what may run merge.py or kit.py before its name
YOURS_VALID = "the user runs `! python -I .agents/kit/bin/merge.py yours <N> --head <sha>` (kit merge <N> from step 7)"
# settings-entries.json's allow rule, spelled as written: no quotes, no other path or interpreter (M203)
BARE_AUTO = re.compile(r"python -I \.agents/kit/bin/merge\.py auto(?: [\w.=:/-]+)*")


def merge_call(words: list[str]) -> str | None:
    """`merge.py <sub>`'s subcommand, or "kit merge", when this command runs one: merge.py, kit or kit.py run
    directly or by an interpreter with only options before it; None otherwise."""
    for i, word in enumerate(words):
        script = name(word)
        if script not in ("merge.py", "kit", "kit.py"):
            continue
        if not all(name(w) in RUNNERS or w.startswith("-") for w in words[:i]):
            return None
        sub = next((w for w in words[i + 1:] if not w.startswith("-")), None)
        if script == "merge.py":
            return sub
        return "kit merge" if sub == "merge" else None
    return None


def check_session_block(ctx: Context, command: str):
    """Your mode and lifting a stop are yours, so no session runs them; automatic mode is the
    orchestrator's (decision 99). You run them with `!`, which meets no hook (M110). `auto` runs bare, the whole
    command spelled as its allow rule. That does not keep it from Claude Code's auto-mode classifier, which refused
    chained `auto` calls (B9's PRs 25 and 42, M203) and, on 2026-10-20, a bare one (B4's PR 26, M219); the
    orchestrator then hands the PR to you. `status`, `check` and `reconcile` may chain: 210 chained, none refused."""
    for unit in units(command, ctx.cwd):
        sub = merge_call(unit.words)
        if sub in ("yours", "kit merge"):
            raise Refusal("merge", f"{'kit merge' if sub == 'kit merge' else 'merge.py yours'} is your mode, which "
                          "only the user runs", YOURS_VALID + "; merge.py check <N> shows what it would find")
        if sub == "resume":
            raise Refusal("merge", "merge.py resume lifts a stop, which is the user's (decision 112)",
                          "tell the user; they run `! python -I .agents/kit/bin/merge.py resume --reason <text>`")
        if sub == "auto" and ctx.role != "orchestrator":
            raise Refusal("merge", "merge.py auto is the orchestrator's",
                          "send READY; the orchestrator merges earned ticket PRs and the user the rest")
        if sub == "auto" and not BARE_AUTO.fullmatch(command.strip()):
            raise Refusal("merge", "merge.py auto not run bare, so its allow rule may not settle it and Claude "
                          "Code's auto-mode classifier may refuse it",
                          "run `python -I .agents/kit/bin/merge.py auto <args>` alone, from the project folder: "
                          "no cd, pipe or other command with it, that exact interpreter and path")


# ---------------------------------------------------------------- control files (C5 sections 2, 3)


def protection(ctx: Context, path: str) -> str | None:
    """Why `path` is protected for this role, or None."""
    loc = ctx.loc(path)
    home = os.path.expanduser("~")
    if any(loc == kitconfig.location(home, s) for s in USER_SETTINGS):
        return "your user settings, which no session may write"
    rel = inside(loc, ctx.coordination)
    if rel is not None and matches(rel, RUNTIME_RECORDS):
        return "a runtime record, which only the kit's scripts write"
    control = ctx.schema["fixed"]["control_paths"]
    for root, branch in ctx.worktrees:
        rel = inside(loc, root)
        if rel is None:
            continue
        if root == kitconfig.location(ctx.main, "."):
            if matches(rel, [*control, kitconfig.FILES["local"]]):
                return "a control file in the main checkout, which no session may write"
        elif matches(rel, control) and not (ctx.role == "orchestrator" and branch.startswith("control/")):
            return f"a control file in the worktree on {branch or 'a detached head'}"
        return None
    return None


def refuse_protected(ctx: Context, path: str):
    why = protection(ctx, path)
    if why:
        valid = "ask the user to change their settings" if "user settings" in why else \
            "the kit's scripts write runtime records" if "runtime" in why else CONTROL_CHANGE
        raise Refusal("control file", f"{path} is {why}", valid)


WRITERS = {"rm", "del", "erase", "rd", "rmdir", "mv", "move", "touch", "tee", "tee-object", "set-content", "sc",
           "add-content", "ac", "clear-content", "clc", "out-file", "new-item", "ni", "remove-item", "ri",
           "move-item", "mi", "rename-item", "rni", "ren", "truncate"}
COPIERS = {"cp", "copy", "copy-item", "cpi", "xcopy"}
PS_VALUES = ("-value", "-encoding", "-itemtype", "-erroraction", "-stream", "-delimiter", "-inputobject", "-width")
REDIRECT = re.compile(r"(?<![<>&])(?:&|\d)?>>?(?!&)\s*")  # &> and &>> too (issue #103)


def masked(segment: str) -> str:
    """Quoted text blanked out, same length, so a > inside quotes is not a redirection."""
    return re.sub(r'"[^"]*"|\'[^\']*\'', lambda m: m.group(0)[0] + "_" * (len(m.group(0)) - 2) + m.group(0)[-1], segment)


def write_targets(unit: Unit) -> list[tuple[str, Path | None, bool]]:
    """(target, the folder it is relative to, whether it is a word of code rather than a path) for
    everything the command writes: redirections, writing commands, git checkout/restore/rm/mv, and the
    words of code it runs (shell code is read as commands by units() instead)."""
    segment, here = unit.segment, unit.here
    out = [(w[0], here, False) for m in REDIRECT.finditer(masked(segment)) if (w := words(segment[m.end():]))]
    cmd, args = name(unit.words[0]), unit.words[1:]
    if unit.code is not None:
        if cmd not in SHELL_LIKE:
            out += [(w, here, True) for w in re.findall(r"[\w.~:\\/-]+", unit.code) if re.search(r"\w", w)]
    elif cmd in COPIERS:
        dest = [args[i + 1] for i, a in enumerate(args[:-1]) if a.lower() == "-destination"]
        out += [(t, here, False) for t in dest or positional(args)[-1:]]
    elif cmd == "sed":
        if short_flag(args, "i") or any(a.startswith("--in-place") for a in args):
            scripted = any(a in ("-e", "-f") or a.startswith(("--expression", "--file")) for a in args)
            out += [(t, here, False) for t in positional(args, ("-e", "-f"))[0 if scripted else 1:]]
    elif cmd in WRITERS:
        out += [(t, here, False) for t in positional(args, PS_VALUES)]
    elif cmd == "git":
        at, sub, rest = split_git(args)
        if sub in ("checkout", "restore", "rm", "mv"):
            out += [(t, git_folder(here, at, unit.names), False) for t in positional(rest)]
    return out


UNKNOWN = object()  # a target after a cd the guard cannot follow


def resolved(target: str, base: Path | None, names: dict):
    """A write target as a path; None for a variable the guard cannot expand (it cannot know the file,
    decision 107); UNKNOWN for a relative target after a cd it cannot follow."""
    path = native(target, names)
    if not placeable(path):
        return None
    if os.path.isabs(path) or kitconfig.is_absolute(path):
        return path
    return str(base / path) if base is not None else UNKNOWN


def shell_writes(ctx: Context, command: str):
    """(target as written, its path or None or UNKNOWN, whether a word of code) for each write."""
    for unit in units(command, ctx.cwd):
        for target, base, code in write_targets(unit):
            yield target, resolved(target, base, unit.names), code


def check_shell_files(ctx: Context, command: str):
    for target, path, code in shell_writes(ctx, command):
        if path is UNKNOWN:
            if not code:
                raise Refusal("control file", f"{target} is written after a cd the guard cannot follow",
                              "cd to a written path, or write to an absolute path")
        elif path is not None:
            refuse_protected(ctx, path)


# ---------------------------------------------------------------- a builder stays in its worktree (C5 section 3)


WORKTREE_TOOLS = ("EnterWorktree", "ExitWorktree")
STAY_HOME = "write coordination files by absolute path; stay in your worktree"
DRIVE = re.compile(r"[A-Za-z]:")  # PowerShell: a drive name alone changes to that drive


def check_stays_home(ctx: Context, tool: str, tool_input: dict):
    """M128: Claude Code keeps a shell cd across calls, so a builder that cd'd out of its worktree moved its
    session, and Claude Code's own guard then refused its writes. The launch script makes a builder's
    worktree, so EnterWorktree and ExitWorktree are refused too."""
    if tool in WORKTREE_TOOLS:
        raise Refusal("worktree", f"{tool}: a builder's worktree is the one the launch script made for it", STAY_HOME)
    if tool not in SHELLS:
        return
    found = units(tool_input["command"], ctx.cwd)
    if not found:
        return
    # the checkout the session started in (CLAUDE_PROJECT_DIR stays it after a cd, M15-M17)
    home = kitconfig.location(ctx.cwd, git_out(ctx.env.get("CLAUDE_PROJECT_DIR") or ctx.cwd,
                                               "rev-parse", "--show-toplevel"))
    if inside(ctx.loc(ctx.cwd), home) is None:
        # Already out: the harness's own cwd says so, whatever cd got it there (a conditional one, one after a
        # failed cd: 7 of 20,764 real commands, PR #95's probe). Only the way back runs, alone: the next call's
        # cwd shows whether it worked (a cd into a missing folder fails and leaves the session where it was).
        first, target = found[0], next((a for a in found[0].words[1:] if not a.startswith("-")), "")
        path = resolved(target, None, first.names) if os.path.isabs(native(target, first.names)) else None
        if (len(found) > 1 or name(first.words[0]) not in CD_NAMES or not isinstance(path, str)
                or inside(ctx.loc(path), home) is None):
            raise Refusal("worktree", f"the session is in {ctx.cwd}, outside your worktree {home}",
                          f'cd "{home}" alone first; {STAY_HOME}')
    for unit in found:
        if len(unit.words) == 1 and DRIVE.fullmatch(unit.words[0]):
            if os.path.splitdrive(home)[0].lower() != unit.words[0].lower():
                raise Refusal("worktree", f"{unit.words[0]} changes to another drive, out of your worktree {home}",
                              STAY_HOME)
            continue
        if name(unit.words[0]) not in CD_NAMES:
            continue
        target = cd_target(unit.words)
        path = None if target == "-" else resolved(target, unit.here, unit.names)
        if not isinstance(path, str):
            raise Refusal("worktree", f"{' '.join(unit.words)} goes to a folder the guard cannot place", STAY_HOME)
        if inside(ctx.loc(path), home) is None:
            raise Refusal("worktree", f"{' '.join(unit.words)} leaves your worktree {home}", STAY_HOME)


# ---------------------------------------------------------------- recursive deletes (C5 section 3)


DELETERS = {"rm", "remove-item", "ri", "del", "erase", "rd", "rmdir"}
CMD_SWITCHES = {"/s", "/q"}  # rd /s /q
UNSET = re.compile(r"\$(?:env:)?\{?\w+\}?|%\w+%")
# PowerShell's $env:USERPROFILE, $HOME; never the shell's folders, which are not the hook's (native())
HOME_NAMES = re.compile(r"\$(?:env:(?!(?:OLD)?PWD\b)(\w+)|HOME\b)", re.I)


def recursive(args: list[str]) -> bool:
    """rm's -r, -R or --recursive (alone or in a cluster: -rf, -fr), PowerShell's -Recurse or a prefix of
    it (-rec), cmd's /s."""
    return any(a == "--recursive" or a.lower() == "/s" or re.fullmatch(r"-[dfiIvrR]*[rR][dfiIvrR]*", a)
               or (len(a) > 2 and "-recurse".startswith(a.lower())) for a in args)


def root_kind(ctx: Context, path: str) -> str | None:
    loc = ctx.loc(path)
    if os.path.dirname(loc) == loc:
        return "a drive or filesystem root"
    if loc == ctx.loc(Path.home()):
        return "your home folder"
    if any(loc == root for root, _ in ctx.worktrees):
        return "a checkout root"
    return None


def check_recursive_delete(ctx: Context, command: str):
    """A recursive delete of a drive root, the home folder or a checkout root, also one that a variable
    left empty would make: `rm -rf "$BUILD/"` with BUILD unset is `rm -rf /`. An empty target alone
    deletes nothing in either shell, so it passes."""
    for unit in units(command, ctx.cwd):
        cmd, args = name(unit.words[0]), unit.words[1:]
        if cmd not in DELETERS or not recursive(args):
            continue
        for target in positional(args, PS_VALUES):
            if target.lower() in CMD_SWITCHES:
                continue
            path, empty = native(target, unit.names), ""
            path = HOME_NAMES.sub(lambda m: os.environ.get(m.group(1), m.group(0)) if m.group(1)
                                  else str(Path.home()), path)
            if not placeable(path):
                path, empty = UNSET.sub("", path), " if its variable is empty"
                if not placeable(path):
                    continue  # a substitution the guard cannot know (decision 107)
            if not path:
                continue  # an empty target deletes nothing in either shell
            path = re.sub(r"(^|[\\/])\*$", r"\1", path) or "."  # dir/* empties dir
            path += "/" if re.fullmatch(r"[A-Za-z]:", path) else ""  # Git Bash's /c
            if os.path.isabs(path) or kitconfig.is_absolute(path):
                kind = root_kind(ctx, path)
            elif unit.here is not None:
                kind = root_kind(ctx, str(unit.here / path))
            else:  # after a cd the guard cannot follow, which may have gone home (`cd $EMPTY`)
                kind = "the folder an unknown cd went to" if path.rstrip("/\\") in (".", "..") else None
            if kind:
                raise Refusal("recursive delete", f"{' '.join(unit.words)} deletes {kind}{empty}",
                              "delete a named folder inside it (rm -rf build/); the user deletes roots")


# ---------------------------------------------------------------- the context barrier (C5 section 3)


HANDOFF_TOOLS = {"TaskStop", "PushNotification", "SendMessage", "ToolSearch", "Skill"}
READ_TOOLS = {"Read": "file_path", "Grep": "path", "Glob": "path", "NotebookRead": "notebook_path"}
HANDOFF_FOLDERS = ("handoffs/**", "state/**", "messages/**")
READ_ONLY_GIT = {"status", "log", "diff", "show", "rev-parse", "ls-files", "ls-tree", "blame", "describe",
                 "shortlog", "cat-file", "merge-base", "rev-list", "grep"}


def records(path: str, newest_first: bool):
    """A transcript's JSON records. A last line with no line break is still being written and is skipped;
    any other line that does not parse is an error, so a changed format blocks instead of reading 0%."""
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return
    lines = data.split(b"\n")[:-1]  # the part after the last line break is unfinished (or empty)
    for number in (range(len(lines) - 1, -1, -1) if newest_first else range(len(lines))):
        if lines[number].strip():
            try:
                yield json.loads(lines[number])
            except ValueError as e:
                raise ValueError(f"{path}: line {number + 1} cannot be read ({e})") from None


def claude_tokens(record: dict) -> int:
    usage = record["message"]["usage"]  # M34; a missing field is an error
    return (usage["input_tokens"] + usage["cache_creation_input_tokens"] + usage["cache_read_input_tokens"]
            + usage["output_tokens"])


def is_context_record(record: dict) -> bool:
    return record.get("type") == "assistant" and not record.get("isSidechain")


def context_percent(ctx: Context) -> float:
    """Claude: the newest non-sidechain assistant record over Claude's window (M34). Codex: the newest
    token_count record (M36). 0% only when there is none."""
    if ctx.role == "reviewer":
        for r in records(ctx.transcript, newest_first=True):
            info = (r.get("payload") or {}).get("info") if (r.get("payload") or {}).get("type") == "token_count" else None
            if info:
                return 100 * info["last_token_usage"]["total_tokens"] / info["model_context_window"]
        return 0.0
    window = ctx.schema["fixed"]["claude_context_window"]
    for r in records(ctx.transcript, newest_first=True):
        if is_context_record(r):
            return 100 * claude_tokens(r) / window
    return 0.0


def in_coordination(ctx: Context, path: str, patterns=("**",)) -> bool:
    rel = inside(ctx.loc(path), ctx.coordination)
    return rel is not None and (patterns == ("**",) or matches(rel, patterns))


def in_skills(ctx: Context, path: str) -> bool:
    loc = folded(ctx.loc(path))
    return any(f"/{d}/skills/" in loc + "/" for d in (".claude", ".agents"))


def read_only_git(words: list[str]) -> bool:
    _, sub, rest = split_git(words[1:])
    if sub in READ_ONLY_GIT:
        return True
    if sub == "branch":
        return not positional(rest)  # listing; a name would create a branch
    return (sub, rest[:1]) in (("worktree", ["list"]), ("stash", ["list"]), ("stash", ["show"])) or \
        (sub == "remote" and rest in ([], ["-v"]))


READERS = {"cat", "head", "tail", "less", "more", "ls", "dir", "get-content", "gc", "type", "wc", "stat",
           "grep", "rg", "findstr", "select-string", "sls"}
SEARCHERS = {"grep", "rg", "findstr", "select-string", "sls"}  # their first word is a pattern, not a file
FILTERS = {"head", "tail", "wc", "grep", "rg", "findstr", "select-string", "sls"}  # read what is piped in


def handoff_read(ctx: Context, unit: Unit) -> bool:
    """A simple read whose every file is under the coordination or skills folders (C5's handoff reads)."""
    cmd = name(unit.words[0])
    if cmd not in READERS or unit.code is not None:
        return False
    # No option parsing (review rounds 2-3: per-command value options kept going wrong): every word that is
    # not an option or a number must be a file in the allowed folders, except a search's first word, its pattern.
    words = [w for w in unit.words[1:] if not w.startswith("-") and not w.isdigit()]
    if not words:
        return cmd in FILTERS  # reads what is piped in
    outside = [w for w in words if not (isinstance(p := resolved(w, unit.here, unit.names), str)
                                        and (in_coordination(ctx, p) or in_skills(ctx, p)))]
    return not outside or (cmd in SEARCHERS and outside == words[:1])


def handoff_shell(ctx: Context, command: str) -> bool:
    """Every command is a cd, read-only git, a read under the coordination or skills folders, the launch
    script (these three not for the reviewer), or a write whose every target is allowed at handoff."""
    for unit in units(command, ctx.cwd):
        writes = [resolved(t, base, unit.names) for t, base, _ in write_targets(unit)]
        cmd = name(unit.words[0])
        if writes:
            if not all(isinstance(p, str) and handoff_writable(ctx, p) for p in writes):
                return False
        elif not (cmd in CD_NAMES or (cmd == "git" and read_only_git(unit.words)) or
                  (ctx.role != "reviewer" and (handoff_read(ctx, unit) or
                                               any(name(w) == "launch.py" for w in unit.words)))):
            return False
    return True


def handoff_writable(ctx: Context, path: str) -> bool:
    if ctx.role == "reviewer":
        out = ctx.env.get("KIT_REVIEW_OUT")
        return out is not None and ctx.same(path, out)
    return in_coordination(ctx, path, HANDOFF_FOLDERS)


def patch_files(patch: str) -> list[str]:
    """The files a Codex apply_patch call names (M35)."""
    return re.findall(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+?)\s*$", patch, re.MULTILINE)


def handoff_step(ctx: Context, tool: str, tool_input: dict) -> bool:
    """C5's handoff steps: what a session past its handoff level may still do."""
    if tool in SHELLS:
        return handoff_shell(ctx, tool_input["command"])
    if ctx.role == "reviewer":
        files = patch_files(tool_input.get("command", "")) if tool == "apply_patch" else []
        return bool(files) and all(handoff_writable(ctx, f) for f in files)
    if tool in HANDOFF_TOOLS:
        return True
    if tool in READ_TOOLS:
        path = tool_input.get(READ_TOOLS[tool])
        return isinstance(path, str) and (in_coordination(ctx, path) or in_skills(ctx, path))
    if tool in FILE_TOOLS:
        return handoff_writable(ctx, tool_input[FILE_TOOLS[tool]])
    return False


def warning_text(ctx: Context, percent: float, handoff: int) -> str:
    if ctx.role == "reviewer":
        out = ctx.env.get("KIT_REVIEW_OUT", "the file KIT_REVIEW_OUT names")
        return (f"CONTEXT (reviewer): {percent:.0f}% of the context window is used; handoff at {handoff}%. Finish "
                f"the review in progress through writing its findings. At {handoff}%, write the findings so far and "
                f"what remains to {out}; after that, only that file and read-only git can be used.")
    if ctx.role == "triager":  # one-shot, with Read, Grep and Glob only: it has no handoff to write
        return (f"CONTEXT (triager): {percent:.0f}% of the context window is used; the limit is {handoff}%. Give "
                "your verdicts now from what you have read.")
    handoffs = Path(ctx.coordination) / "handoffs"
    if percent >= handoff:
        return (f"CONTEXT ({ctx.role}): {percent:.0f}% of the context window is used, past the handoff level "
                f"({handoff}%). Only handoff steps run now: write your handoff to {handoffs}, your state file, "
                "messages; read-only git; the launch script for a successor.")
    return (f"CONTEXT ({ctx.role}): {percent:.0f}% of the context window is used; handoff at {handoff}%. Finish "
            f"the current step, then write your handoff to {handoffs}.")


def levels(role: str) -> str:
    """The config's context levels a role reads: the triager reads the reviewer's (C7 section 13)."""
    return "reviewer" if role == "triager" else role


def barrier(ctx: Context, event: str, payload: dict) -> str | None:
    """The warning to add, or None; past handoff, a tool call that is not a handoff step is refused."""
    percent = ctx.percent
    warn, handoff = (ctx.values[f"context.{levels(ctx.role)}.{level}"][0] for level in ("warn", "handoff"))
    if percent < warn:
        return None
    if event == "pre" and percent >= handoff and not handoff_step(ctx, payload["tool_name"], payload["tool_input"]):
        raise Refusal("context", f"the session is at {percent:.0f}% of its context window, past its handoff level "
                      f"({handoff}%)", "only handoff steps: " + ("findings to KIT_REVIEW_OUT and read-only git"
                      if ctx.role == "reviewer" else "your handoff, state file and messages; read-only git; "
                      "the launch script for a successor"))
    return warning_text(ctx, percent, handoff)


def writes_handoff(ctx: Context, block: dict) -> bool:
    if not isinstance(block, dict) or block.get("type") != "tool_use":
        return False
    tool, tool_input = block.get("name"), block.get("input") or {}
    if tool in FILE_TOOLS:
        return in_coordination(ctx, str(tool_input.get(FILE_TOOLS[tool], "")), ("handoffs/**",))
    if tool in SHELLS:
        return any(isinstance(p, str) and in_coordination(ctx, p, ("handoffs/**",))
                   for _, p, _ in shell_writes(ctx, str(tool_input.get("command", ""))))
    return False


def missed_handoff(ctx: Context) -> str | None:
    """Stop: past handoff with no handoff written since crossing it, the session is sent back. Not the
    reviewer (the review script continues it) nor the triager, which cannot write one."""
    if ctx.role in ("reviewer", "triager"):
        return None
    handoff = ctx.values[f"context.{ctx.role}.handoff"][0]
    percent = ctx.percent
    if percent < handoff:
        return None
    window, crossed, attempts = ctx.schema["fixed"]["claude_context_window"], False, set()
    for r in records(ctx.transcript, newest_first=False):
        content = (r.get("message") or {}).get("content")
        if r.get("type") == "user" and isinstance(content, list):  # a handoff counts once its write succeeded
            if any(b.get("type") == "tool_result" and b.get("tool_use_id") in attempts and not b.get("is_error")
                   for b in content if isinstance(b, dict)):
                return None
        if not is_context_record(r):
            continue
        crossed = crossed or 100 * claude_tokens(r) / window >= handoff
        if crossed:
            attempts |= {b.get("id") for b in content or [] if writes_handoff(ctx, b)}
    return refusal_text("missed handoff", ctx.role, f"the session is at {percent:.0f}%, past its handoff level "
                        f"({handoff}%), and has written no handoff since crossing it",
                        f"write your handoff to {Path(ctx.coordination) / 'handoffs'} before stopping",
                        "the session continues; nothing was lost")


# ---------------------------------------------------------------- the READY check (C5 section 3)


COMMAND_LINE = re.compile(r"^(\$|>|PS>) \S")
BAD_SUMMARY = re.compile(r"\b[1-9]\d* (?:failed|errors?)\b|\bno tests ran\b|\bRan 0 tests\b|\bFAILED\b|"
                         r"(?<![\d,.])\b0 (?:passed|tests?)\b|\bcollected 0 items\b")


def ready_claim(text: str) -> bool:
    """A line whose first word, after Markdown marks are removed, is READY (C5 section 3)."""
    return any(re.match(r"READY\b", re.sub(r"^[\s#>*_`~-]+", "", line)) for line in text.splitlines())


def ready_problem(text: str) -> str | None:
    """Why a READY claim in `text` is refused, or None (no claim, or a claim with evidence)."""
    if not ready_claim(text):
        return None
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    if any(BAD_SUMMARY.search(b) for b in blocks):
        return "the READY evidence shows a failure, an error or zero tests"
    for block in blocks:
        lines = block.splitlines()
        first = next((i for i, line in enumerate(lines) if COMMAND_LINE.match(line)), None)
        if first is not None and any(line.strip() and not COMMAND_LINE.match(line) for line in lines[first + 1:]):
            return None
    return "READY without evidence: no fenced block with a command line and its output"


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def after_edit(ctx: Context, tool: str, tool_input: dict) -> str:
    """The file as it would be after a Write, Edit or MultiEdit."""
    if tool == "Write":
        return tool_input.get("content", "")
    path = Path(native(tool_input["file_path"]))
    path = path if path.is_absolute() else ctx.cwd / path
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    for edit in tool_input.get("edits", []) if tool == "MultiEdit" else [tool_input]:
        old, new = edit.get("old_string", ""), edit.get("new_string", "")
        text = text.replace(old, new, -1 if edit.get("replace_all") else 1) if old else text
    return text


def check_ready(ctx: Context, tool: str, tool_input: dict):
    """A builder's READY is a message, so it is checked where it is sent (C5 section 3)."""
    valid = "a fenced block with the command you ran ($ ...) and its output, showing tests that ran and passed"
    if tool == "SendMessage":  # the summary is a preview line, not the READY: the READY file is checked when written
        texts = list(strings({k: v for k, v in tool_input.items() if k != "summary"}))
    elif tool in ("Write", "Edit", "MultiEdit") and in_coordination(ctx, tool_input["file_path"], ("messages/**",)):
        texts = [after_edit(ctx, tool, tool_input)]
    elif tool in SHELLS:
        for target, path, _ in shell_writes(ctx, tool_input["command"]):
            if isinstance(path, str) and in_coordination(ctx, path, ("messages/**",)):
                raise Refusal("READY", f"a shell write into messages/ ({target})", "write messages with the Write tool")
        return
    else:
        return
    for text in texts:
        problem = ready_problem(text)
        if problem:
            raise Refusal("READY", problem, valid)
    if any(ready_claim(text) for text in texts):
        check_stacked(ctx)


def read_front(path: Path) -> tuple[dict, str] | None:
    """A format file's flat front matter and body (C9 section 1), or None when there is no file. Raises
    ValueError when it cannot be read as one."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} has no front matter (a first line ---)")
    fields = {}
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return fields, "\n".join(lines[i + 1:]).strip()
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            raise ValueError(f"{path}: line {i + 1} is not key: value")
        fields[key.strip()] = value.strip()
    raise ValueError(f"{path}: the front matter has no closing ---")


def merged(ctx: Context, ticket: int) -> bool:
    """A merge record with `result: merged` names the ticket (C8 section 8); a not-merged attempt does not count."""
    for path in sorted((Path(ctx.coordination) / "merges").glob("merge-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Refusal("READY", f"the merge record {path.name} cannot be read ({e})", "stop and tell the user",
                          "nothing was sent") from None
        if isinstance(record, dict) and record.get("result") == "merged" and str(record.get("ticket")) == str(ticket):
            return True
    return False


def check_stacked(ctx: Context):
    """C9 section 3: no READY from a ticket stacked on one that has not merged. The brief is found by the
    worktree's branch t<n>; a missing or unreadable brief blocks. These are refusals, not errors, because
    an error lets handoff steps through (C5 section 1), and SendMessage and messages/ are handoff steps."""
    stop = "stop and tell the user: the READY check reads the ticket's brief"
    if ctx.ticket is None:
        raise Refusal("READY", f"the branch {ctx.branch or '(detached)'} is not a ticket branch t<n>, so the brief "
                      "cannot be found", stop, "nothing was sent")
    brief = Path(ctx.coordination) / "briefs" / f"t{ctx.ticket}.md"
    try:
        found = read_front(brief)
    except (OSError, ValueError) as e:
        raise Refusal("READY", f"the brief cannot be read ({e})", stop, "nothing was sent") from None
    if found is None:
        raise Refusal("READY", f"there is no brief {brief}", stop, "nothing was sent")
    stacked = found[0].get("stacked_on")
    lower = re.fullmatch(r"t?(\d+)", stacked or "")
    if stacked == "none":
        return
    if lower is None:
        raise Refusal("READY", f"the brief {brief} has stacked_on: {stacked or '(missing)'}; valid: a ticket "
                      "number or none", stop, "nothing was sent")
    m = int(lower.group(1))
    if not merged(ctx, m):
        raise Refusal("READY", f"t{ctx.ticket} is stacked on t{m}, which has not merged",
                      f"send READY after t{m} merges; merge its fix rounds upward meanwhile", "nothing was sent")


# ---------------------------------------------------------------- steering (C9 section 9)


STEER_ACTIONS = ("nudge", "halt", "none")


def steer(ctx: Context) -> tuple[str, str] | None:
    """The orchestrator's standing steer for this session: ("halt", text) or ("nudge", text), or None. A
    steer file that cannot be read is an error, so a half-written halt blocks rather than passes."""
    folder = Path(ctx.coordination) / "steer"
    if ctx.role == "reviewer" or not folder.is_dir() or ctx.base_name is None:  # the folder first: no git call
        return None
    path = folder / f"{ctx.base_name}.md"
    found = read_front(path)
    if found is None:
        return None
    fields, body = found
    action, steer_id = fields.get("action"), fields.get("id")
    if action not in STEER_ACTIONS:
        raise ValueError(f"{path}: action is {action!r}; valid: {', '.join(STEER_ACTIONS)}")
    if action == "none":
        return None
    if not steer_id:
        raise ValueError(f"{path} has no id")
    body = " ".join(body.split())
    if action == "halt":
        return "halt", f"HALT {steer_id} from the orchestrator: {body}"
    if acknowledged(ctx) == steer_id:
        return None
    return "nudge", (f"STEER {steer_id} from the orchestrator: {body} Record steer_ack: {steer_id} in your state "
                     f"file, {ctx.state_file()}.")


def acknowledged(ctx: Context) -> str | None:
    """The state file's steer_ack. A state file that cannot be read counts as no acknowledgement, so the
    nudge keeps showing: the safe side, and it does not block the session's work."""
    try:
        found = read_front(ctx.state_file())
    except (OSError, ValueError):
        return None
    return found[0].get("steer_ack") if found else None


# ---------------------------------------------------------------- the events


CANARY = re.compile(r"KIT-HOOK-CANARY-[0-9a-f]+")


def check_pre(ctx: Context, tool: str, tool_input: dict):
    if tool in SHELLS:
        command = tool_input["command"]
        canary = CANARY.search(command)
        if canary:  # every role: the review script's proof that hooks fire (C7 section 5)
            raise Refusal("canary", f"{canary.group()} is the review script's hook canary",
                          "nothing to do: this refusal is the proof the review script looks for")
        check_git(ctx, command)
        check_github(command)
        check_session_block(ctx, command)
        check_recursive_delete(ctx, command)
        if ctx.role != "reviewer":  # Codex writes only in its own checkout (C5 section 1)
            check_shell_files(ctx, command)
    elif tool in FILE_TOOLS and ctx.role != "reviewer":
        refuse_protected(ctx, tool_input[FILE_TOOLS[tool]])
    elif tool.startswith("mcp__"):
        if any(name in tool.lower() for name in GH_MCP):
            raise Refusal("github", f"the MCP tool {tool}", "the user merges and changes repository settings")
        if ctx.role != "reviewer":
            for key, value in tool_input.items():
                if "path" in key.lower() and isinstance(value, str):
                    refuse_protected(ctx, value)
    if ctx.role == "builder":
        check_ready(ctx, tool, tool_input)
        check_stays_home(ctx, tool, tool_input)


def decide(event: str, payload, env) -> dict:
    """The output for one hook call. Raises on any error; main() turns that into a block."""
    if not isinstance(payload, dict):
        raise TypeError("the payload is not a JSON object")
    ctx = Context(payload, env)
    try:
        if event == "stop":
            return output(event, missed_handoff(ctx))
        standing, broken = None, None
        try:
            standing = steer(ctx) if event in ("pre", "prompt") else None
        except Exception as e:  # raised after the checks, so a broken steer file cannot skip them (review round 1)
            broken = e
        if standing and standing[0] == "halt":  # before every check: a halt stops handoff steps too
            return output(event, refusal_text("halt", ctx.role, f"the orchestrator halted this session ({standing[1]})",
                                              "stop; the orchestrator lifts the halt and wakes this session"),
                          halt=standing[1])
        if event == "pre":
            check_pre(ctx, payload["tool_name"], payload["tool_input"])
        if broken is not None and not (event == "pre" and handoff_step(ctx, payload["tool_name"], payload["tool_input"])):
            raise broken  # an error blocks; a handoff step that passed every check still goes (C5 section 1)
        notes = [n for n in (barrier(ctx, event, payload), standing and standing[1]) if n]
        return output(event, None, "\n\n".join(notes) or None)
    except Refusal as r:
        return output(event, refusal_text(r.check, ctx.role, r.failed, r.valid, r.done))


def lets_through(event: str, payload, env) -> bool:
    """C5: an error blocks, but the context barrier still lets handoff steps through."""
    try:
        return event == "pre" and handoff_step(Context(payload, env), payload["tool_name"], payload["tool_input"])
    except Exception:
        return False


# ---------------------------------------------------------------- launching and the selftest (C5 section 1)


MAIN = Path(__file__).resolve().parents[3]  # this script's checkout: main's, when a launch pins main's guard
ROLE_EVENTS = (("PreToolUse", "pre"), ("UserPromptSubmit", "prompt"), ("Stop", "stop"))
CLAUDE_FLOOR = (2, 1, 295)  # the version that added onFailure (documented)


def launch_settings(main: Path, role: str) -> dict:
    """The `--settings` every launched session gets: main's guard by absolute path, so an older branch
    cannot bring an older guard (M15, M22); hooks on whatever the local file says (M19, M20); and for a
    builder the control paths denied to its file tools, anchored at its worktree (C5 section 4)."""
    guard = (Path(main) / ".agents/kit/hooks/guard.py").as_posix()
    hooks = {}
    for event, arg in ROLE_EVENTS:
        hook = {"type": "command", "command": "python", "args": ["-I", guard, arg], "timeout": 30}
        if arg == "pre":
            hook["onFailure"] = "block"
        hooks[event] = [{"matcher": "*", "hooks": [hook]} if arg == "pre" else {"hooks": [hook]}]
    settings = {"disableAllHooks": False, "hooks": hooks}
    if role in ("builder", "triager"):  # the triager has a builder's rules (C7 section 13)
        control = kitconfig.load_schema(Path(main))["fixed"]["control_paths"]
        auto = "python -I .agents/kit/bin/merge.py auto"  # the orchestrator's (C8 section 15)
        settings["permissions"] = {"deny": [f"Edit(./{p})" for p in control] +
                                   [f"{tool}({auto}{rest})" for tool in ("Bash", "PowerShell") for rest in ("", " *")]}
    return settings


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)  # C2 section 4


def entry_problems(main: Path) -> list[str]:
    """Every shipped entry is in its file, at its pointer, equal to the shipped value (C2 section 4)."""
    doc = json.loads((main / ".agents/kit/settings-entries.json").read_text(encoding="utf-8"))
    problems, files = [], {}
    for entry in doc["entries"]:
        if entry["path"] not in files:
            try:
                files[entry["path"]] = json.loads((main / entry["path"]).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                files[entry["path"]] = e
        data = node = files[entry["path"]]
        if isinstance(data, Exception):
            problems.append(f"{entry['name']}: {entry['path']} cannot be read ({data})")
            continue
        for key in entry["pointer"].strip("/").split("/"):
            node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, list) or canonical(entry["value"]) not in map(canonical, node):
            problems.append(f"{entry['name']}: not in {entry['path']} at {entry['pointer']} as shipped")
    return problems


def canned(main: Path, command: str) -> dict:
    """Main's guard, run as a hook is run, on one builder Bash call."""
    payload = {"cwd": str(main), "tool_name": "Bash", "tool_input": {"command": command},
               "transcript_path": str(main / "selftest-no-transcript.jsonl")}
    r = subprocess.run([sys.executable, "-I", str(main / ".agents/kit/hooks/guard.py"), "pre"], capture_output=True,
                       input=json.dumps(payload).encode("utf-8"), env={**os.environ, "KIT_ROLE": "builder"})
    return json.loads(r.stdout.decode("utf-8") or "null") if r.returncode == 0 else {"exit": r.returncode}


def selftest(main: Path, claude_version: str | None = None) -> list[str]:
    """C5 section 1: the entries are present and as shipped, the script blocks one canned payload and passes
    another, and Claude Code is new enough. A launch starts nothing unless this returns no problem."""
    problems = entry_problems(Path(main))
    blocked = canned(Path(main), "git push --force origin HEAD")
    if not (blocked or {}).get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
        problems.append(f"the guard did not refuse a force push: {blocked}")
    passed = canned(Path(main), "echo selftest")  # not a handoff step, so an error in the guard shows
    if passed != {}:
        problems.append(f"the guard did not pass echo selftest: {passed}")
    if claude_version is None:
        r = subprocess.run("claude --version", capture_output=True, text=True, shell=True)
        claude_version = r.stdout.strip() if r.returncode == 0 else ""
    found = re.match(r"(\d+)\.(\d+)\.(\d+)", claude_version)
    if not found or tuple(map(int, found.groups())) < CLAUDE_FLOOR:
        problems.append(f"Claude Code {claude_version or 'not found'}: 2.1.295 or later is needed (onFailure)")
    return problems


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["selftest"]:
        problems = selftest(MAIN)
        print("\n".join(f"FAILED: {p}" for p in problems) or "selftest: ok")
        return 1 if problems else 0
    if argv[:1] == ["settings"] and len(argv) == 2 and argv[1] in ROLES:
        print(json.dumps(launch_settings(MAIN, argv[1])))
        return 0
    if len(argv) != 1 or argv[0] not in EVENTS:
        print(f"usage: guard.py {'|'.join(EVENTS)}  (payload on stdin) | selftest | settings <role>", file=sys.stderr)
        return 2
    event, payload = argv[0], None
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        result = decide(event, payload, os.environ)
    except Exception as e:  # C5: any error blocks; a missing field is an error
        role = os.environ.get("KIT_ROLE", "unknown")
        result = {} if lets_through(event, payload, os.environ) else output(
            event, refusal_text("error", role, f"the guard failed: {type(e).__name__}: {e}", "stop and tell the user"))
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
