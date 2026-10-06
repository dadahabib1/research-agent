# Consumer contract

What a project that installs this plugin may depend on. Everything listed here keeps its name, path and shape within a minor version; a change to any of it bumps the minor version and is recorded under "Changes to the contract". Everything not listed (reference files and their headings, template wording, agent bodies) may change in any version.

## Skills and agents

- Skills: `research-protocol`, `research-writing`, `run-next-task` (`/run-next-task`), `new-research-project` (`/new-research-project`).
- Agents, invoked by their bare names as `subagent_type`: `researcher` (web search and fetch only), `reviewer` (reads and runs scripts; no web). A project that configures a raw-page fetcher as an MCP server named `firecrawl` makes its search and scrape tools available to the researcher; no other project tool reaches it. A project that needs a different fetch server may place its own `.claude/agents/researcher.md` (project agents outrank plugin agents for the bare name) with the same body and a `tools:` line that names its server's search and scrape tools and nothing else.

## What the plugin reads from the project

- The `CLAUDE.md` "Research" section, for the paths below.
- The brief at the path `CLAUDE.md` names (default `docs/research/strategy-research-brief.md`), with sections numbered as in `templates/brief.md`: §3 settled decisions, §6 evidence and validation standards (with the domain rules pointer), §7 deliverable format.
- The domain rules file the brief's §6 points to.
- The queue (default `docs/research/research-queue.md`): columns Prerequisites and Status; statuses `todo`, `waiting on requester`, `in review`, `accepted`, `rejected`, `deferred`; selection rule: the first `todo` row in table order whose prerequisites are all accepted.
- Prompts in `prompts/`, with the optional lines `Shape:` (new research, revision, clarification) and `Run settings:`.
- The project's context file, where `CLAUDE.md` names one.

## What the plugin writes into the project

- The deliverable at the path the prompt names, headed with run date, shape, model, effort and `research-agent plugin version`.
- The log at `logs/<topic>-log.md`, with the sections of `templates/log.md`: Intake record, Frame and plan, Searches, Sources, Dead ends, Flagged content, Verification, Self-review, Review findings, Spend. Researcher returns at `logs/<topic>-notes-<n>.md` and `logs/<topic>-notes-sweep.md`.
- Scripts and fixtures where the prompt or the brief names them.
- The queue row's status: `in review`, or `waiting on requester`.
- A branch `research/<topic>` and a pull request titled with the topic.

It never writes decision records (the decision session does, from the project's template), never merges, and never writes to its own files.

## Decision records

`templates/decision-record.md` keeps: the heading `### <decision-name>: <one-sentence decision>`; the field names Status, Decision, Parameters, Rule, Acceptance tests, Constraints and non-goals, Evidence, Depends on, Supersedes, Open items (Reopen when is optional); the status words `accepted | rejected | deferred`; the closing section `## Rejected and deferred decisions`. A project may prepend blocks (for example a machine-readable header) and add fields without leaving the contract.

## Headings and paths cited by name

- `skills/research-protocol/references/review.md`: the heading "Revision".
- `skills/research-writing/SKILL.md`: the heading "Writing for an implementing agent".
- `skills/new-research-project/templates/`: `prompt.md`, `log.md`, `decision-record.md`, `brief.md`, `domain-rules.md`, `queue.md`.

## Changes to the contract

### 0.4.0

- Added: the optional prompt lines `Shape:` and `Run settings:`; the log sections Frame and plan, Flagged content, Self-review, Review findings and Spend, and the header lines Shape and Fetch tools; the notes files; the optional decision-record field Reopen when; `templates/domain-rules.md`; the brief's §6 "Domain rules" pointer.
- Changed: the queue selection rule is table order (0.3.x: lowest-numbered prompt). The researcher agent is read-only (web search and fetch); the reviewer has no web access. `references/finance.md` is removed; domain rules belong to the project.
- Unchanged: skill names, queue statuses and columns, the decision-record heading and field names, brief section numbers, the log path, the branch name, and the cited headings.
