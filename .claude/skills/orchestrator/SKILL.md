---
name: orchestrator
description: The kit orchestrator's loop - briefs, launches, READY, escalations, merges, takeovers, notices, tasks.md. Use when KIT_ROLE is orchestrator, on every loop turn and timer turn.
freedom: script
---

# Orchestrator

You run the project's tickets through builders and are also the user's working session. You act on other
sessions only through files, hook returns and the launch script: never by typing into a terminal, and
nothing sent to a session listed `waiting`. Each format has one template, under `.agents/kit/templates/`
(C9 rule 5); write coordination files with the Write tool. `<coordination>` is the coordination folder (the
`coordination` setting, default `.coordination` in the main checkout): every file this skill names by a bare
path (`briefs/`, `state/`, `steer/`, `tasks.md`) is under it, never in the checkout's root. `<orch>` is
`<project.name>-orch`; the scripts
are under `.agents/kit/bin/`, run with `python -I` from the main checkout, where you stay.

**Tag every reply's first line** `[loop]` (a turn from a message, a notice, the timer) or `[chat]` (the
user).

## Timer

Once per session (at your first turn, and in `/startup`): run with the Bash tool
`echo "${KIT_TIMER_CRON:-4,19,34,49 * * * *}"` (it prints `4,19,34,49 * * * *` unless a test set a faster
clock), then `CronCreate` with `cron:` that output, `recurring: true`,
prompt `Timer turn: run python -I .agents/kit/bin/tick.py`. Record its job id and date
under `## Notes`. A recurring job expires after 7 days: on a turn 6 days after arming, `CronDelete` it and
arm a new one (M114, M116). Call `CronCreate` yourself rather than through `/loop`, whose step a model
can skip (M116). **A timer turn** runs `tick.py` first: on exactly `nothing changed`, reply `[loop]
nothing changed` and end the turn; on anything else, run the loop turn below.

## A loop turn, in order

0. `python -I .agents/kit/bin/tick.py` (every loop turn, so the next timer turn compares against now).
1. **Messages.** `python -I .agents/kit/bin/formats.py unread <coordination>/messages/<orch>
   <read_through>` lists the complete messages after `read_through`, then the new `read_through`. Act on
   each message once, by its file name: a broken message earlier in the inbox holds `read_through` back,
   so later ones are listed again; skip a name already acted on (keep them under `## Notes` until
   `read_through` passes them). A message `tick.py` reports `(still incomplete)` goes under Needs you in
   `tasks.md`. By kind: record `ready` (the builder runs its own review); settle `blocked` or `escalate`
   as a small decision (below) or escalate it; `handoff` is step 7; `pr-open` is step 4.
2. **Notices.** For each name from `notices.py pending <coordination>`: send its line with
   `PushNotification`, then `notices.py sent <coordination> <name> <the tool's result>`, also for `Not
   sent`. Never resend.
3. **Stalled sessions.** A `claude agents --json` row with `status: "waiting"` not under `## Waiting
   sessions reported`: a notice (`notices.py write <coordination> stalled "<name> waits on you
   (<waitingFor>): claude attach <short id>"`) and list it. Remove an id no longer waiting.
4. **Merges**, before any takeover or launch. For each `pr-open` message, or a ticket at `pr-open` with no
   merge running: when the ticket is earned, `tickets.auto_merge` is on and nothing is stopped
   (`merge.py status`), run `python -I .agents/kit/bin/merge.py auto <N>` with `run_in_background`, one at
   a time; otherwise one `merge-yours` notice, `PR #<N> is yours: ! python -I .agents/kit/bin/merge.py yours <N> --head <its reviewed head, 12 hex>`
   (`kit merge` comes with the full step 7; decision 126). When a run ends: exit
   0, record it and `git pull --ff-only`; exit 1, its refusal under `## Notes`, and its `Valid:` acted on
   when it is a session's to do (a review round, the builder merging main), else a notice; exit 3 (red
   main), nothing more for that merge (the script opened the revert PR, stopped automatic merges and wrote
   the notice). The stop holds automatic merges only: every other step goes on (launches, reviews,
   successors), and each PR that is ready meanwhile gets its `merge-yours` notice; exit 2 or 4, `merge.py reconcile` next turn. Also pull main whenever `merges/` has
   a record newer than your last pull. Then the lesson refresh, after any merge tagged since your last
   check: `<k>` is the highest number among the issues titled `Refresh the lessons after merge <k>` (`gh
   issue list --state all --search "in:title Refresh the lessons after merge" --json title`; none: 0); when
   `git tag --list "merge/pr-*"` lists 10 or more tags beyond `<k>`, file a refresh ticket: that issue, with
   the tag count as `<k>`, and its brief (Briefs, below), which step 6 launches.
5. **Crashed sessions:** TAKEOVER (below).
6. **One builder per ticket.** For each briefed ticket with no live builder that is not merging, merged,
   cancelled or held because its PR waits on your merge (TAKEOVER), while builders are fewer than `sessions.max_builders` (decision 123), the ticket is not held and stacking
   allows it: write the brief, then `launch.py builder --ticket <n> [--base t<m>] [--effort <e> --reason
   "<r>"]`. On `launched`: record it in `## Tickets`; if its launch record has `effort_lowered_from`,
   rewrite the brief with the launched effort and that field. `REFUSED (memory)`: nudge an idle builder to
   hand off, else wait. `REFUSED (usage)`: the launch wrote the notice. `REFUSED` on config, guard, name
   or trust: a notice, and no launches until fixed. `FAILED AFTER START`: the same command next turn; a
   second failure, a notice.
7. **Successors.** A builder's `handoff` message, unless its ticket is merging, merged or cancelled:
   `launch.py builder --successor <its launch id>`.
8. **Stop what is over.** `claude stop <short id>` (a row with no `id` is interactive: `taskkill /PID
   <pid> /F`, M161), with a notice, for any project session whose role has a newer holder or whose ticket
   is done. Then steering (below).
9. Rewrite `<coordination>/state/orchestrator.md` (from `state-orchestrator.md`), then `<coordination>/tasks.md`
   (from `tasks.md`): every
   fact from a record or a state file.

After launching or messaging, end your turn: a message, a wake or the 15-minute timer starts the next
one, so never wait in a sleep or poll loop (a busy session is one no message or timer can start a turn
in; M131).

## Briefs

`<coordination>/briefs/t<n>.md` from `brief.md`, written before the launch, rewritten whole only to record a lowered
effort or a cancel. The builder relies solely on it: the issue verbatim, the spec section quoted with its
commit, prior art (what the project's libraries and maintained ones offer, or `none found:` and where you
looked), the files, the stacking lines, and `## Stop and ask`. A stacked brief bases on the lower ticket's
branch only when they change the same files, and only one level deep: never on a ticket that is itself
stacked (its brief's `stacked_on` is not `none`); a third same-file ticket waits for the lower merge.
Nothing is built on a ticket that is escalated or in its third fix round. `max` effort needs the user's OK, named in `effort_reason`.

`lessons:` lists the lesson files that touch the ticket: for each path in `files`, the files that name it,
`grep -rlF -e '<path>' docs/solutions --include='*.md'` (a fixed string, not a pattern), and those whose module
is its first path segment, `grep -rlE -e "^module:[[:space:]]*[\"']?<segment>[\"']?[[:space:]]*$" docs/solutions --include='*.md'`
(each of `.[]()*+?{}|^$\` in the segment escaped with a backslash); less `docs/solutions/README.md`,
comma-separated; `none` when none is found. `refresh:` is `no`, except in a refresh
ticket's brief: `refresh: yes` (the launch then runs that builder's subagents on Sonnet), `files:
docs/solutions/`, `lessons: none`, `spec: none: the lesson refresh`, and the issue's body asks the builder to run
`/ce-compound mode:refresh mode:non-interactive` with no scope and two limits: create no `CONCEPTS.md` (update one
only if it exists), and write nothing outside `docs/solutions/` and that file, so no promotion lands in
`CODING_STANDARDS.md`, a skill or an instruction file: each such change goes under the report's Recommended. It
commits what it changed and sends READY with the skill's full report as evidence, ending on `Promotion
candidates:` and each module that 3 or more lesson files share, with its count, from
`grep -rh -m1 "^module:" docs/solutions --include='*.md' | tr -d '\r' | sed -E "s/^module:[[:space:]]*['\"]?([^'\"]*[^'\"[:space:]])['\"]?[[:space:]]*$/\1/" | sort | uniq -c`,
or `none`. A promotion is the user's to file, by hand.

## Small decisions and escalations

- **Decide alone** only when all hold: (a) it follows existing text and adds no rule, threshold or
  assumption; (b) it touches no `project.high_stakes` output; (c) you and the author agree and the
  reviewer has not disputed; (d) it is recorded as a spec PR the user merges or reverts, with a
  `Decided:` notice. Everything else is escalated.
- **Escalate** with `python -I .agents/kit/bin/escalate.py --ticket <n> --trigger <trigger> --body-file
  <file>`, the body from `escalation.md` (triggers: `needs-decision`, `paid-or-key`, `approach`,
  `high-stakes`, `blocked`; the review script writes `round-cap` itself). Record the user's answer once:
  `escalate.py answer --escalation <id> --answer <answer> --quote "<their words>"`. File each `defer`
  follow-up as an issue.
- **An escalated builder waits** (decision 123) idle with its context, uncounted in `sessions.max_builders`.
  `tick.py` prints, every turn while it holds: `escalated <name> (<id>) idle <m> min: keepalive` (its last
  turn is over 40 minutes old): a `kind: wake` message, headline `t<n>: keepalive, reply in one line`, and
  its wake, which keeps its prompt cache warm; `escalated <name> (<id>) waited <h> h: hand off` (it has
  waited `sessions.escalation_wait_hours`): ask it to hand off (a message and a wake). When you record the
  answer: a `kind: answer` message and a wake to the waiting builder, which goes on with its context on a
  go-ahead answer, and on `defer` or `cancel` hands off and is stopped as step 8 does (C9 section 4). A
  launch `REFUSED (memory)` asks such a builder to hand off before any other. Once it has handed off, stop
  it as step 8 does, and hold step 7's successor until the answer is recorded (none on `defer` or `cancel`).
- **The night rule.** One `escalation` notice (the headline); mark the `holds` tickets needs-you and carry
  on with every other ticket within the usage stop. A machine or shared-service failure is a run-wide
  stop: launch nothing new and let running builders reach their next handoff.

## TAKEOVER

**When:** a session in `## Tickets` absent from `claude agents --json` (absence, not `idle`), with no
handoff since its launch and no launch record naming it in `successor_of`; or one stopped after the
missed-handoff check's last block. Never for a ticket that is merging (a `merge.py` run you started that
has not ended, or an in-progress marker under `merges/`: wait for it and for `merge.py reconcile`),
merged (a record with `result: merged`) or cancelled.

**Not while its PR waits on your merge.** Claude Code retires a background session after about an hour idle
(C9 section 16), so a builder whose ticket is at `pr-open` with its `merge-yours` notice out goes absent
with nothing to do. Do not take it over: set its `## Tickets` stage to `pr-open, waits on your merge` and
note its absence under `## Notes`. Take it over only when the ticket has builder work again: a refusal of
its PR whose `Valid:` is a session's to do (step 4: a review round, the builder merging main), from a
`not-merged` record of its PR under `merges/` or a refusal you bring to the chat; or a change you ask for.

**Steps:** (1) confirm from those records; (2) a `kind: takeover` message (from `message.md`) to the base
name: the predecessor's launch id and session, the reason (`absent`, `missed-handoff`, `stopped`), its
state file's headline and stage, and the output of `git -C <worktree> log --oneline -1` and `git -C
<worktree> status --short`; (3) `launch.py builder --successor <launch id>`, never `claude --resume`;
(4) record it in `## Tickets`, and a `takeover` notice.

## Steering

To reach a busy session, rewrite `<coordination>/steer/<base name>.md` from `steer.md`: `id`
(`steer-<UTC>-<4 hex>`), `action` (`nudge`, `halt` or `none`), `headline`, `written_at`, and one paragraph
under 500 characters. A nudge corrects
("hand off now, memory is short", "t36 merged; READY may go"); a halt stops a cancelled ticket or what the
user says to stop, and `none` lifts it, followed by a wake. An idle session gets a message and a wake
instead. Never steer for the usage stop.

## Rotation

At your handoff level, or after `context.rotate_orchestrator_after_merges` merges: write your handoff from
`handoff.md`, set stage `handing-off`, run `launch.py orchestrator --successor <your launch id>`, and end
your last reply with the line `claude attach <successor name>` (the name from the script's `launched` line;
the successor is a background session in the main checkout, as in equity_analyst, also listed in `claude
agents`). Then stop. Your successor stops and removes your process once it has read the handoff.

## Control changes

A change to control files (scripts, settings, skills, `agent-kit.toml`, anything under `.agents/kit/`)
has an issue and goes through its own worktree, never the main checkout:
1. `git fetch`, then `git worktree add -b control/<topic> .claude/worktrees/control-<topic> origin/<default
   branch>`; edit there.
2. `python -I -m unittest discover -s .agents/kit/tests` and the clean run there; commit; push.
3. For control code, or instruction text shipped as a workflow unit: a READY (from `ready.md`) to your own
   inbox, its `ticket` the issue and its `head` the pushed commit, with step 2's output; then the review
   script on that branch and head.
4. On approval (an instruction-text customization alone needs none): the PR. Its body's first line is
   `Kit change: customization` (then `prose-pr.md`'s shape) or `Kit change: workflow unit` (what changed,
   the decision, the evidence).
5. A `control-pr` notice: `PR #<N> is yours: ! python -I .agents/kit/bin/merge.py yours <N> --head <its head, 12 hex>`.

## PR comments

Every PR comment you write starts `<!-- kit -->`; a reply starts `<!-- kit reply-to: <comment or review
id> -->` (C8 section 12). An unmarked comment reads as the user's and holds the merge.
