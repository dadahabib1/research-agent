# Equity research (research repository)

Research for the personal US equity research app. This repository holds research documents only; the app's code and its orchestrator live in `dadahabib1/equity_analyst_v2`.

## Research

- Brief: `docs/research/strategy-research-brief.md`
- Domain rules: `docs/research/domain-rules.md` (the brief's §6 points to it)
- Queue: `docs/research/research-queue.md`
- Prompts: `docs/research/prompts/`
- Logs: `docs/research/logs/`
- Decision records: `docs/research/decisions/<topic>-<YYYY-MM-DD>.md`
- To run the next research task, use /run-next-task (research-agent plugin) and follow the research-protocol skill.
- Research deliverables: `docs/research/<topic>.md`; research logs: `docs/research/logs/<topic>-log.md`.
- Researcher returns: `docs/research/logs/<topic>-notes-<n>.md`; the review sweep: `docs/research/logs/<topic>-notes-sweep.md`.
- Decision index: `docs/research/decisions/INDEX.md`. Each decision opens with a fenced `yaml` block (name, status, decided, decided_by, moves_valuation, depends_on, supersedes, parameters with units, app); keep the block and the index row in the same pull request.
- App context: `docs/research/app-context.md`, what the app does today, the data it can reach and what a run costs. Read it before any task that serves the app.
- Accepted decision records stay here. The app (`dadahabib1/equity_analyst_v2`) reads them from main and pins each one it uses in its own lock file (`docs/research-lock.md`, in the app repository); it never copies them.
- The app writes here only research requests (a prompt in `docs/research/prompts/` and a queue row, by pull request, on a branch `request/<topic>`) and `docs/research/app-context.md`.

## Queue order

`/run-next-task` takes the first `todo` row in the queue's table order whose prerequisites are all accepted, not the lowest prompt number. The requester orders the rows:

- An app request whose Blocks names a current app ticket goes first; every other row keeps the requester's order.
- The app's request pull request proposes the row's position, and the requester confirms it by merging.

## Decision records

Decision sessions write every record from `docs/research/templates/decision-record.md`: the plugin's decision-record template plus the `yaml` block the app's drift check reads. Its header gives the rules for each field. In short:

- Decision names are stable kebab-case. `depends_on` and `supersedes` name decisions by that name. A change to an accepted decision is a new decision that supersedes it, never an edit in place.
- `moves_valuation` is `true` when the decision can change a valuation number or a verdict; the app takes those to the requester before building.
- Every new or changed record updates `docs/research/decisions/INDEX.md` in the same pull request, and every `yaml` block must parse.

## Requests from the app

The app's orchestrator writes its requests from these templates in `docs/research/templates/`; a research session runs them like any queued prompt:

- `app-request.md`: a research request, saying why the app needs it, what the app does today and the test that pins it, the decisions the run must produce, the fixture format and any date.
- `app-revision.md`: rework of an existing deliverable, listing each review item; the run answers with a change log.
- `app-clarification.md`: one methodology ambiguity met while building, answered with one decision under the same protocol and review gate.

## Hand-back for the app

Every research run that could feed the app follows these rules:

- **Intake.** Read `docs/research/app-context.md`, and record in the run's log any conflict between the prompt and what the app can do. Never edit `app-context.md`: if it looks wrong, record that as an open question in the log and in the pull request; the app's orchestrator answers by updating it. The app's repository is private and out of reach from here, so put any other question for the app in the pull request.
- **Decisions to grill.** For each decision, the deliverable proposes:
  - its kebab-case name;
  - its parameters, each with its unit and denominator;
  - its acceptance tests, with exact inputs and exact expected outputs;
  - its fixtures, as files the app can run (CSV, JSON, or a Python script with assertions), saved in `docs/research/` and named in the tests.
- **Reference cases** stay runnable scripts with assertions, like `rrx_reference_case.py`.
- **Requirements.** Only accepted records on main are requirements for the app. Branches, open pull requests and drafts are not.
