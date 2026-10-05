# Decision record: <topic>

- Date: <YYYY-MM-DD>
- Deliverable: `<path>` at commit `<hash>`
- Decided by: <the requester's name or role>; recorded by <Claude or another agent>

Write each decision so an implementing agent can turn it into a spec without reading anything else (research-writing skill, "Writing for an implementing agent"). Use the deliverable's leading words exactly. In the Decision and Rule fields, use "must", "must not" and "may", and keep hedges out.

## Decisions

### <decision-name>: <one-sentence decision>

- **Status:** <accepted | rejected | deferred>
- **Decision:** <normative statement, using "must", "must not" or "may">
- **Parameters:**
  - `<name>` = <value> <unit>, per <denominator>; range <low> to <high>, <inclusive | exclusive> (source: deliverable §<section>)
- **Rule:** <formula, or numbered step-by-step logic, using only the parameters above and the inputs it names>
- **Acceptance tests:**
  - Inputs: <exact inputs> → expected output: <exact output>
  - Inputs: <a boundary case> → expected output: <exact output>
  - Fixture: `<path to fixture file, or "none">`
- **Constraints and non-goals:** <what the implementation must respect, and what this decision does not cover>
- **Evidence:** deliverable §<section> at commit `<hash>`; grade <A | B | C | D>; validation rung <rung from the validation ladder>
- **Depends on:** <other decision names, or "none">
- **Supersedes:** <decision name and record path, or "none">
- **Open items:** <each [OPEN] item with the evidence that would resolve it, or "none">

<Repeat the subsection for each decision.>

## Rejected and deferred decisions

- `<decision-name>`: <rejected | deferred>; <reason, in one line>
