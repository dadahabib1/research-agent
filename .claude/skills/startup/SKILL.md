---
name: startup
description: Resume a kit role from its records - a successor's first prompt, or the orchestrator after a crash or reboot.
disable-model-invocation: true
freedom: script
---

# Startup

You take over a role (builder or orchestrator) from its records. Read only what each step names: the
records are the memory, not the chat. Templates are under `.agents/kit/templates/`. `<coordination>` is the
coordination folder (default `.coordination` in the main checkout); `launches/`, `handoffs/`, `messages/`,
`state/` and `verdicts/` below are under it.

1. **Who am I.** Your role is `KIT_ROLE`. Your launch record (`<coordination>/launches/`) is the one whose
   `session_id` is `$CLAUDE_CODE_SESSION_ID`; else the newest record for this role and folder that no
   state file names.
2. **Your predecessor.** Its launch id is your record's `successor_of`. Read its newest handoff
   (`handoffs/`) written after its `started_at`; else the `kind: takeover` message in your base name's
   inbox (`messages/<base name>/`): its `git log` and `git status` lines say what it left, and
   uncommitted work is what `git status` shows now; else (an orchestrator the user started after a
   crash) take over from the old state file yourself. Once you have read it, stop the predecessor if
   `claude agents --json` still lists it. A background row: `claude stop <its short id>`, and for an
   orchestrator then `claude rm <its short id>`, as equity_analyst does. An interactive row (the
   orchestrator the user started; `claude stop` cannot stop it, M161): `taskkill /PID <its pid> /F`.
   Then list again: if it is still there, a `stop-failed` notice naming it, and go on.
3. **Read state.** Your state file's front matter (`state/orchestrator.md`, or
   `state/builder-<base name>.md`), and for the orchestrator its `## Tickets`. Then the messages after
   `read_through`; then the live sessions (`claude agents --json`).
4. **Rebuild from records.**
   - Builder: `git status --short`, `git log --oneline <base_commit>..HEAD`, your verdicts
     (`verdicts/t<n>/`), your newest READY.
   - Orchestrator, in order: `python -I .agents/kit/bin/merge.py reconcile` (it settles a merge a crash
     left half done; exit 2 is a notice, and no automatic merge runs until a later pass succeeds); `git
     pull --ff-only`; open issues and PRs (`gh issue list`, `gh pr list`); launch records, verdicts,
     merge records, pending notices (`python -I .agents/kit/bin/notices.py pending <coordination>`).
5. **Rewrite the state file** from its template: `session`, `launch_id`, `handoff_read` (the handoff's file
   name, or the takeover message's), `read_through`, `headline: now: resuming at <Next>`.
6. **Nothing twice.** Before a launch, a review or a merge, look for its record: a listed session for the
   ticket means no launch; a verdict for this head, no review; a merge record, no merge.
7. **Continue** at the handoff's `## Next` (or the takeover's last step), following your role's skill:
   `builder` or `orchestrator`. An orchestrator arms its timer first (the `orchestrator` skill, Timer).
