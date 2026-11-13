---
name: review
description: The kit's review procedure for one pushed head of a ticket, run by the review script (contract C7) in a reviewer checkout. Use only when the prompt says it is an agent-kit review.
---

# Reviewing a ticket

The review script (`.agents/kit/bin/review.py`, contract C7) started you in a reviewer checkout. You review
one pushed head against the review standard, run its tests in the test copy, and answer with findings in
the output schema. You do not approve or reject: the script and a triager do that from your findings. This
file, the standard and the hooks are main's, put over the candidate's, so a ticket cannot change the
instructions it is reviewed by.

## What you have

All paths are relative to the checkout you are in. This review's own values are in the JSON block after
this file (the same as `.kit-review/review.json`); the list before this file is each changed file's kinds,
which the script read from its path, for the review rules' table.

- `git diff <base_commit>...<head>` (the `diff` value): the change under review. The working tree holds
  main's control files over the candidate, so read the candidate's own versions of those files with
  `git show <head>:<path>`.
- `.kit-review/ticket.md` (the issue and its comments), `.kit-review/brief.md` (if the orchestrator wrote
  one), `.kit-review/ready.md` (the builder's READY and its evidence), `.kit-review/spec/` (main's copy of
  every spec, contract or ADR the ticket names).
- `.agents/skills/review/kit-standard.md` (the kit's rules) and `.agents/skills/review/standard.md` (this
  project's rules). Read both before you start.
- The test copy (`test_copy`): the candidate exactly, its own machinery included. Every test you run, runs
  there.

You cannot use `gh` or the network to fetch the issue; everything you need was exported above.

## The procedure

1. Read the ticket, the brief, the READY, the named specs and both standards.
2. **Read the script's stages, then run the tests left to you, in the test copy** (`cd <test_copy>`).
   Before you started, the script ran, in the test copy, the lint on the Python files the diff changes
   (`ruff check --isolated --select E9,F`) and, when main has a test map (`tests/map.toml`), the tests the
   map names for the changed paths, as one command. Their commands, exit codes and summary lines are
   `stages` in the JSON block after this file; they are in the round's record already, so do not run them
   again or list them in `tests`. Both were green or not run: a red stage stops the round before you. When
   `stages.clean_run` is `yours`, run the clean run: the offline suite and the free live tests on the
   changed paths, as the project's clean run runs them (`merge.clean_run` in `agent-kit.toml`; until that
   key exists, the test command the project documents). When it is `replaced`, the mapped tests stand for
   it: do not run the clean run. Either way, run `python -I -m unittest discover -s .agents/kit/tests` when
   the diff touches `.agents/kit/`, and what your checks need (step 4). When `review.json` names a
   `python`, it is first on your PATH: run every Python command with `python`, not the project's `.venv`,
   which your sandbox cannot run. Otherwise a tool in an ignored folder (such as a `.venv`) resolves against
   the main checkout. Paid model calls only when the builder's call report is missing or older than the
   last change to a prompt, model or the code around a call. Record each command with its summary line as
   printed, its exit code and the folder it ran in; record what you did not run and why.
3. Read the diff in full, then the code around it, and apply the review rules below. Check the claims in the
   ticket and the READY against the code, the tests and their output, not against what the builder says.
4. **Mutate to check a test** (the test rule's point 2): when a test is meant to catch a failure, plant
   that break in the test copy, run the test, see it fail, and undo the break. Mutate nothing outside the
   test copy.
5. Write each finding: `file` and `line` in the candidate, `what` is wrong, `why` it matters, `real_use`
   (who hits it in real use, and how), the smallest `fix`, and `real_data_count` (how many real records or
   cases it affects, or null). `line` is a line number; it is null only when `file` is a path the change
   deleted or should have added, and then `what` says which (an answer that breaks this is asked again
   once, then fails the round). In the review rules' order, every finding, notes beyond five included: your
   answer is the round's record, and the script shows the round's notes from the first five. Ids `F1`, `F2`,
   ... unique in the round, continued across runs.
6. For an agent-kit contract PR, answer each cold-read guess the contract lists as `answered`, `partly` or
   `not_answered` in `cold_read`; otherwise leave it empty.

## The review rules

<!-- The review rules: one text in kit-standard.md, the review skill and agent-kit's stopgap prompt (tests/test_skills.py) -->
**The round, in a fixed order.** Before reading, the lint runs on the pushed head, then the mapped tests: the
cheapest stage first, and a red stage stops the next one. Their results are kept with the round. Then the reviewer reads the change with the kind of each changed file read from
its path, never from the PR's title or the author's label, and applies the checks in this order, each check only
where the table says so:

| Kind of change | Spec | Tests | Guard | Probe | Defects |
|---|---|---|---|---|---|
| Other shared docs | yes | — | — | — | — |
| Docs the two docs tests read | yes | the two docs tests are green | — | — | every claim checked against the code |
| Pure logic in a script | yes | unit tests, shown failing first | — | if new | yes |
| A script driving git, Claude, Codex or files | yes | real-subprocess tests, shown failing first | if it touches one | if new | yes |
| A core file | yes | full suite, shown failing first | yes | if new | yes, plus every file that depends on it |
| A step the model decides | yes | its eval once evals exist; until then a note that none exists | — | if new | conflicting or ambiguous instructions, against the other skills and briefs |
| The guard or a control path | yes | the guard's self-test plus its live case | yes | yes, always | yes |
| Tests only | yes | the changed tests green; deletions, skips and loosened assertions named with reasons | — | — | each changed test still fails on the bug it targets |
| Several kinds | each file its own row; Guard and Probe from the strictest row | | | | |

The checks, defined:
- **Spec:** the PR meets the issue's acceptance list item by item; a missing item is a `fix`, a contradicted
  decision a `blocker`.
- **Tests:** the table's required tests exist, and the PR shows each failing before the fix and passing after. A
  test never seen failing is a `fix`; a test that cannot fail is a `blocker`.
- **Guard:** control paths and the safety guard stay intact: a weakened safety rule is a `blocker`; errors fail
  closed; no banned call.
- **Probe:** a new mechanism answers the impact probe's four questions in the PR; unanswered is a `fix`.
- **Defects:** a code reading, each finding with a concrete failure scenario (inputs and state, then the wrong
  output or crash), its file and line, who hits it in real use, and the smallest fix. A path reachable only by
  working against the kit on purpose is not a finding against the guards; a gap in the merge's checks is.

**A kit update** (decision 117): a PR whose paths include `kit.lock` is a kit update, and its review is also an
integration audit, four checks beside the table's: (1) each kit-owned file equals the release `kit.lock` names, or
differs from it only by the project's own change on the base branch, kept or merged; (2) the project-owned files
and the project's own settings entries are untouched; (3) each conflict was resolved the kit's way or the
project's way, never mixed, and no conflict marker is left; (4) the project's clean run passes on the result. A
miss on (1), (2) or (3) is a `blocker`; a red clean run is a `fix`.

**The evidence rule:** no finding without file and line and a failure scenario; no style findings; a stale doc on
changed code is a `fix`.

**Findings and notes.** A round reports every blocker and fix finding and at most five notes, kept in this order:
(1) blockers (a broken guard or control path, lost or corrupted data, a wrong result on the real path); (2) a spec
item not met; (3) a required test missing or not shown failing first; (4) other defects, most likely failure
first. The round states how many it found and how many it shows ("7 found, 5 shown") and writes all of them to its
record, so the cap never hides a finding. More than five blockers means escalate, not a fix list.

**The skip rule.** A re-review requested when no blocker or fix finding is open is skipped, and the skip is
recorded.

**Lessons.** A lesson file under `docs/solutions/` in the diff: each claim in it matches the diff or the code it
cites; a claim that does not is a `fix`.

**The lint.** `ruff check` with the rule set `select = ["E9", "F"]`: pyflakes, which reports no style, and files
that do not parse. A lint finding is a `fix`, never a `blocker`.
<!-- end of the review rules -->

## Severities

- **blocker**: contradicts a decision or the design unsaid; leaves a builder guessing a format, owner, path
  or interface; a test that cannot fail; a weakened safety rule; a breach of the test rule's point 1, 4 or 5.
- **fix**: an inconsistency, a wrong citation, an ambiguous sentence; a breach of the test rule's point 2 or
  3; a stale doc on changed code.
- **note**: worth saying, harmless to merge. Few.

## Handing off before you finish

When the kit warns you that your context is at the reviewer's handoff level, stop reviewing and write your
findings so far to the file in the environment variable `KIT_REVIEW_OUT`, in the output schema, with
`complete: false` and `remaining` naming what is left (paths or checks). Then end with the same JSON as your
answer. The script starts a fresh run with your findings and the remaining list. When you finish the whole
review, `complete` is true and `remaining` is empty.

## Your answer

Your final message is one JSON object in the output schema (`.kit-review/findings.schema.json`): `complete`,
`remaining`, `findings`, `tests` (what you ran; empty only when `stages.clean_run` is `replaced` and you
needed to run nothing more), `not_run`, `cold_read`. Nothing else: the script reads it
as JSON, and an answer that is not JSON or misses the schema fails the review.
