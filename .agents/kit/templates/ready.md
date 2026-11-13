---
format: message
version: 1
from: <your session name>
to: <project.name>-orch
kind: ready
ticket: <n>
headline: READY t<n>: <what now works, under 80 characters>
reply_to: none
head: <the pushed commit to review>
branch: t<n>
base_commit: <the brief's base_commit>
round: <0, or n after fix round n>
effort: <as launched>
written_at: <ISO UTC: 2026-10-17T10:20:00Z>
---
READY t<n> at <head>

## Acceptance

<Each AC id and the test that proves it: path::name.>

## Evidence

<Fenced blocks, each a command line ($ , > or PS> ) and its output pasted unedited: the end-to-end test of
the ticket's claim, the offline suite, free live tests on its paths, the paid-call report when it makes
paid calls.>

## Red first

<Per new test and fix, the failing run seen first: commit, command, failing line.>

## Prior art

<Each candidate, its cost (money, a key, a dependency), used or not and why.>

## Cuts

<Each test or check removed or moved, what it caught, what still catches it; or none.>

## Open

<Known gaps, or none.>

<!-- end -->
