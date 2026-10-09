# Decision record: <topic>

- Date: <YYYY-MM-DD>
- Deliverable: `<path>` at commit `<hash>`
- Decided by: <the config's decider>; recorded by <Claude or another agent>

Write each decision so an implementing agent can turn it into a spec without reading anything else (research-writing skill, "Writing for an implementing agent"). Use the deliverable's leading words exactly. In the Decision and Rule fields, use "must", "must not" and "may", and keep hedges out. "Reopen when" is optional; the other fields are not.

Each decision opens with a `yaml` header block. `name` equals the subsection heading's name; `status` is one of accepted, rejected, deferred, superseded or withdrawn; `depends_on`, `supersedes` and `parameters` are `[]` when empty, and `supersedes` may instead be a quoted string naming a document and section. A change to an accepted decision is a new decision that supersedes it, never an edit in place. Update `decisions/INDEX.md` in the same pull request.

## Decisions

### <decision-name>: <one-sentence decision>

```yaml
name: <decision-name>
status: <accepted | rejected | deferred | superseded | withdrawn>
decided: <YYYY-MM-DD>
decided_by: <the config's decider>
depends_on: []
supersedes: []
parameters:
  - {name: <name>, value: <value>, unit: "<unit, per denominator>", source: "<deliverable> §<n>"}
```

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
- **Evidence:** deliverable §<section> at commit `<hash>`; claim type <literature | measurement | documentary | judgment>; grade <A | B | C | D | n/a: measured | n/a: documented>; validation rung <rung from the validation ladder, or "measured on <sample>", or "documented at <version or date>">
- **Depends on:** <other decision names, or "none">
- **Supersedes:** <decision name and record path, or "none">
- **Open items:** <each [OPEN] item with the evidence that would resolve it, or "none">
- **Reopen when:** <inputs or dates whose change would invalidate this decision, or "none identified">

<Repeat the subsection for each decision.>

## Rejected and deferred decisions

- `<decision-name>`: <rejected | deferred>; <reason, in one line>
