# The kit's review standard

Kit-owned (contract C7 section 11): kit updates change this file. Your project's own rules go in
`standard.md` beside it. Every review checks the change against both.

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

## Also

- No mechanism the diff does not need: a finding asks for the smallest change that closes the problem.
- For a contract PR, each cold-read guess is answered, partly answered or not answered.

## The test rule

A test exists to catch a named failure in real use. Each of these is a finding:

1. A claim with no end-to-end proof: the real command on real files (a real session for anything a session
   meets), its result read from disk, logs or the transcript, never from the code's own report.
2. A test or a fix never seen failing. Check it: plant the break the test is meant to catch in the test
   copy, run the test, see it fail, undo the break.
3. A unit test that repeats an end-to-end test or restates the contract, rather than catching a case the
   end-to-end test cannot reach cheaply.
4. A removed or moved test or check without its list: what it caught, and for each, the test that still
   catches it or why that failure cannot happen in real use.
5. A claim about how Claude Code or Codex behaves with no measurement cited, and not marked as documented
   and not measured.

A test that cannot fail is a `blocker`, as is a breach of point 1, 4 or 5; points 2 and 3 are a `fix`.

## Control code

A change to the kit's machinery (hooks, the guard, permissions, the review and merge scripts, the tests in
`.agents/kit/tests/`) is checked for:

- the hook and permission semantics it relies on, each measured;
- errors that fail closed: a missing field, an unreadable file or an exception blocks, never passes;
- no banned call (the scan in `.agents/kit/tests/test_banned_calls.py`);
- the machinery tests, run with `python -I -m unittest discover -s .agents/kit/tests`, passing in the test
  copy.

A weakened safety rule is a `blocker`.
