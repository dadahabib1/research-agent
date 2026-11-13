---
format: brief
version: 1
headline: t<n>: <what the ticket makes true, under 80 characters>
ticket: <n>
issue: <the GitHub issue number>
spec: <the spec section and the commit read: docs/specs/merge.md#the-lock @ b1df0ee>
decisions: <comma list, or none>
files: <comma list, from the order-and-files table>
base: <origin/main, or the lower ticket's branch t<m>>
base_commit: <main's head when written, or the lower ticket's head>
stacked_on: <the lower ticket's number, or none>
lower_base_commit: <the lower ticket's own base commit, or none>
effort: <the effort asked for: the builder default or a raise>
effort_reason: <why; for max, where the user gave the OK>
effort_lowered_from: none
lessons: <comma list of docs/solutions/ files that touch this ticket's files, or none>
refresh: <no; yes only in the lesson refresh ticket's brief>
written_at: <ISO UTC: 2026-10-17T10:20:00Z>
---
## Issue

<The issue verbatim, with its intent block and AC ids.>

## Spec

<The spec section, quoted.>

## Prior art

<What the project's libraries and well-known maintained ones offer, or "none found:" and where you looked.>

## Files

<One line per file.>

## Stacking

<Only when stacked_on is not none; otherwise delete this section. The first command is
git diff <lower_base_commit>...t<m>. The lower ticket's fixes come first and merge upward each round.
READY goes after t<m> merges.>

## Stop and ask

<What goes to the user: a paid service, a new key, a change of approach, a project.high_stakes match.>
