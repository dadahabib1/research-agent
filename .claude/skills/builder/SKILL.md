---
name: builder
description: The kit builder's method, from the brief to the PR. Use when KIT_ROLE is builder, or when you work a ticket from a brief under briefs/.
freedom: judgment
---

# Builder

You build one ticket in your own worktree, from its brief (`<coordination>/briefs/t<n>.md`). The brief is
the whole task: nothing in it points at the chat. Formats have one copy each, under
`.agents/kit/templates/` (C9 rule 5): fill the template, keep every field and heading, and write
coordination files with the Write tool, by absolute path: never `cd` out of your worktree, and never call
`EnterWorktree` (the guard refuses both, M128). `<orch>` below is `<project.name>-orch`; your base name is
`<project.name>-t<n>`.

## Start

1. Read the brief, then each lesson file its `lessons:` line names. Run `git merge-base --is-ancestor
   <base_commit> HEAD`; if it fails, send `BLOCKED` (below) and stop.
2. Stacked (`stacked_on` is a ticket): your first command is `git diff <lower_base_commit>...t<m>`, since
   you lack the lower session's memory.
3. Write `<coordination>/state/builder-<base name>.md` from `state-builder.md`. Rewrite it whole at each
   stage change, after reading messages, and before a handoff.
4. Prior art: before building a parser, a data source or an integration, check what the project's
   libraries and well-known maintained ones already do, and build only what they do not.

## The test rule

<!-- KIT-SHAPE 10.3, quoted unchanged (decision 106) -->
**The test rule (decisions 105, 106).** Every builder, every reviewer and agent-kit's own build follow
it; it is the kit's test-driven development. A test exists to catch a named failure in real use.
1. **Prove the real path first.** A ticket starts with an end-to-end test of what it claims, in real
   use: the real command on real files, and a real session for anything a session meets. It reads the
   result from disk, logs or the transcript, never from the code's own report.
2. **Red first.** Every new test, and every fix, is seen failing on the broken code or a planted break
   before it passes. A test never seen failing proves nothing: it may pass for the wrong reason.
3. **Unit tests only where they earn it:** a case the end-to-end test cannot reach cheaply, each naming
   the real failure it catches. No test that restates the contract or repeats an end-to-end test.
4. **Cut nothing blind.** Before removing or moving a test or a check, list what it catches; for each,
   name the test that still catches it, or why that failure cannot happen in real use. Move code
   unchanged rather than rewriting it from memory.
5. **Measure the harness.** A claim about how Claude Code or Codex behaves cites a measurement, or says
   it is documented and not measured.
<!-- end of the quote -->

Keep each red run (commit, command, failing line): READY lists them.

**Before each push**, where the project keeps a test map (`tests/map.toml`): commit, then run the kit's test
command on what your branch changes, `python -I .agents/kit/bin/testmap.py --diff <base>` (the brief's base
branch). It runs the tests the map names for the changed files, or the full offline suite when a changed file
is core or has no entry; uncommitted work is not in the set. Paste the command and pytest's summary line in
READY and the PR. Without a map, run the offline suite as the brief says.

## Commits

- The subject states the behaviour now true. Stage files by name.
- One commit per review round, naming the reviewer, the round and the severities it fixes.
- A fix that adds a mechanism carries the impact probe's four answers in its message (below).

## The impact probe (KIT-SHAPE 10.5)

Run the read-only probe after a review, before a large fix, before any fix that adds a mechanism rather
than a line, when two rounds in a row find the same kind of finding, before the user decides to merge
with a blocking finding left open as a known limitation, and when asked. Write its text
unchanged as `<coordination>/probes/t<n>-<UTC>.md` from `probe.md`. Two rounds of the same kind of
finding mean: question the approach before patching again.

## The lesson step

After the brief's acceptance criteria pass and before READY, run the `ce-compound` skill as
`/ce-compound mode:non-interactive depth:lightweight <one line: the problem this ticket solved, and how>`.
It asks nothing and starts no subagent. It writes at most one lesson file under `docs/solutions/` (or one
test or lint rule in its place), or nothing when no lesson clears its bar, and its report ends on
`Documentation complete` or `Documentation skipped`. Commit what it wrote, by name (rerun the tests when it
wrote a test or a rule), and put one line in READY's `## Evidence`:
`Documentation complete <path>` or `Documentation skipped <its reason>`.
A fix round may update that lesson file, never add one. A refresh ticket (`refresh: yes` in its brief) skips
this step: its work is the refresh its issue names.

## READY, review, PR

1. **READY** when the brief's acceptance criteria pass and the lesson step is done: `<coordination>/messages/<orch>/<UTC>-<your
   session name>.md` from `ready.md`, its last line `<!-- end -->`. Then `SendMessage` to the
   orchestrator's current session name (the newest launch record for `<orch>`) with only `New message:
   <file name>`. Stacked: READY waits until the lower ticket has merged (the guard refuses it before);
   meanwhile merge the lower branch's fix rounds upward, and fix the lower ticket first.
2. **Review**, with `run_in_background` (a review outlasts the shell's timeout): `python -I <main
   checkout>/.agents/kit/bin/review.py --ticket <n> --branch t<n> --head <40-hex sha> [--base t<m>]`.
   Act on its exit code:
   - 0 approved: the PR (step 3).
   - 4 changes needed: read the verdict under `verdicts/t<n>/`, fix each finding at `fix` test-first,
     push, and send a new READY with `round: <n>`.
   - 5 a stop for the user: stage `needs-you`; at `needs_decision`, message the orchestrator `kind:
     escalate` (from `message.md`) with the verdict's path. Wait for its answer.
   - 3 both reviewer checkouts busy: run it again later. 1 refused: do what its `Valid:` says.
   - 2 failed: run it once more; a second `FAILED` goes to the orchestrator as `kind: escalate`.
3. **The PR opens only when the ticket is cleared to merge** (decision 62): an approving verdict for the
   current head, or the user's known-limitation clearance. `gh pr create`; the body quotes any probe's
   four answers. Then message the orchestrator `kind: pr-open` and set stage `pr-open`. The merge is
   never yours; the merge script stops your session when the ticket merges.

Every PR comment you write starts `<!-- kit -->`; a reply starts `<!-- kit reply-to: <comment or review
id> -->` (C8 section 12). An unmarked comment reads as the user's and holds the merge.

## BLOCKED and escalations

- A missing decision, file or proof: a `kind: blocked` message from `blocked.md`. Only this ticket waits.
- What the brief's `## Stop and ask` lists (a paid service, a new key, a change of approach, a
  high-stakes output) goes to the orchestrator as `kind: escalate`, with the choice and its options.
- A change to a control file is the orchestrator's: report `BLOCKED`.
- A commit someone else pushed to your branch is part of your head: never revert or rewrite it. Send READY
  for the new head, or `BLOCKED` if it breaks your ticket. You have no question tool: everything for the user
  goes through the orchestrator.
- **Waiting on an escalation** (decision 123): stage `needs-you`, then stay idle; you keep your context. A
  `kind: wake` keepalive from the orchestrator gets a one-line reply, `waiting on <the escalation>`, and no
  other work. The orchestrator's `kind: answer` carries your answer: `fix` and the other go-ahead answers
  resume the ticket; `defer` parks it and `cancel` ends it (C9 section 4): hand off (below) and stop. Its
  request to hand off is a handoff (below).

## Steering and handoff

- A `STEER <id> from the orchestrator` reminder: follow it, then record `steer_ack: <id>` in your state
  file. A halt stops your tool calls; wait.
- At the context barrier's handoff level, or when the orchestrator asks: write
  `<coordination>/handoffs/<session name>-<UTC>.md` from `handoff.md` (its `## Next` is your successor's
  first concrete step), set stage `handing-off`, message the orchestrator `kind: handoff` naming the
  file, and stop. A builder whose ticket merged ends without one.
