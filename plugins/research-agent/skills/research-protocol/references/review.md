# Review

## Self-review, before hand-over

- Every factual claim cites an opened source, or is labelled snippet or [UNVERIFIED].
- Every number is REAL or ILLUSTRATIVE, hand-computed values are marked, and the scripts ran.
- Every input's knowledge timestamp falls on or before the as-of date.
- Every check the deliverable specifies has been run on its own reference cases.
- Rules were tested at boundaries and invariances. Examples:
  - at fair value, the edge is zero whatever the beta;
  - a symmetric input gives a symmetric output;
  - a noisy series does not create extra cycles.
- Every ratio, limit and percentage names its denominator and units.
- Every statistical criterion comes with power, sample size and time to result.
- Conflicting sources are shown side by side.
- Assumptions about the requester are listed, with their evidence.
- Drafts and brainstorms are labelled, and decisions sit in the decisions section rather than in the prose.
- The latest edition of every recurring source was checked.

## Independent review

A reviewer, person or agent, does what an author cannot do for themselves:
- re-runs every script from a clean state;
- tries to break each rule with boundary cases and invariance tables;
- checks input freshness, and drift since each source's date;
- searches for newer editions and for contrary evidence;
- reads the decisions section and asks whether each decision is actually supported.

Write review findings as numbered items, each with its evidence and the resolution expected.

## Revision

- Answer every review item: resolved in the document, or listed as open with the evidence that would resolve it.
- Where a rule changes, update its checks, its presentation, and the fixtures that exercise it.
- Return the complete document with a change log, not only the changes.

## Decision session

- The requester decides; the researcher recommends.
- Run the questioning protocol (`questioning.md`) over the deliverable's decisions.
- Record each decision as accepted, rejected or deferred. Only accepted decisions move to spec or action.
