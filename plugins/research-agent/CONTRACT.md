# Contract

What a host that adopts this plugin may depend on: names, paths, formats and behaviours. A host is a research project (a repository that runs research), a consumer (a system that builds on another repository's accepted decisions), or both. Everything not listed here (reference files and their headings, template wording, agent bodies) may change in any release. The history of this file is in `CHANGELOG.md`, under each release's "Contract" subsection.

## Versioning and compatibility

- **Before 1.0:** a minor release (0.Y.0) may change the contract; a patch (0.Y.Z) never does.
- **From 1.0:** a major release changes or removes a contract element, a minor release only adds to it, and a patch changes neither.
- **Deprecation:** an element to be removed is marked "Deprecated in X; removed in Y" below. It keeps working for at least one minor release before 1.0, and one major release after. The doctor reports it as DEPRECATED, and `UPGRADING.md` gives the migration.
- **Releases:** the version changes only at release, in `.claude-plugin/plugin.json`. Each release has a git tag `vX.Y.Z` that is never moved. A host pins a tag: in project settings, a `github` marketplace source with `"ref": "vX.Y.Z"`, or `claude plugin marketplace add dadahabib1/research-agent@vX.Y.Z`.
- **Range:** a host declares the plugin versions it works with in `requires`. Comparators are `>=`, `>`, `<=`, `<` and `==`; a comma means "and". `/run-next-task` stops at step 0 when the installed version is outside the range.

## The config file: `research-agent.toml`

At the repository root. It holds only what differs between hosts; everything else is fixed below. Unknown keys are an error.

```toml
requires = ">=0.6.0, <0.7.0"           # required

[project]                               # present when research runs in this repository
root = "docs/research"                  # required
brief = "research-brief.md"             # optional; default "research-brief.md", under root
decider = "requester"                   # required: who accepts, rejects or defers decisions
env = ["SOME_API_KEY"]                  # optional: environment variable names the sources need, never values

[project.consumer]                      # optional: the system this research serves
name = "<consumer name>"                # required in the table
context = "consumer-context.md"         # required in the table; under root

[project.fetch_identity]                # optional: host suffix = environment variable name
"example.gov" = "EXAMPLE_IDENTITY"

[project.run_defaults]                  # optional; else references/effort-and-cost.md
model = "<model>"
effort = "xhigh"

[consumes]                              # present when this repository builds on decisions
research = "owner/repo"                 # required: owner/repo, or "self" for research in this repository
clone = "../repo"                       # optional; default ../<repo name>, relative to this repository's root
```

A file has `[project]`, `[consumes]` or both. `research = "self"` needs `[project]`. `CLAUDE.md` points to the file and does not repeat its paths.

**Deprecated in 0.6.0; removed in 0.7.0:** a repository without `research-agent.toml` whose `CLAUDE.md` has a "Research" section is read as in 0.5.0: the paths come from that section's `- <Label>: <path in backticks>` lines (Brief, Domain rules, Queue, Prompts, Logs, Decision records, and a line whose label names a context file). Logs then record `config: legacy CLAUDE.md prose (deprecated; removed in 0.7.0)`.

## The research project's layout

Under `root`:

- the brief (`brief`), `domain-rules.md`, `research-queue.md`;
- `prompts/`, `logs/`, `decisions/` with `decisions/INDEX.md`;
- the consumer context file, where `[project.consumer]` names one, with an `As of: YYYY-MM-DD` line;
- optional `templates/`: a file there named like a plugin template overrides it; other files are the project's own.

**`<topic>`** is the deliverable's file stem, from the queue row's Deliverable column (`system-review-v1.md` gives `system-review-v1`). The deliverable is `<root>/<topic>.md`, the log `<root>/logs/<topic>-log.md`, researcher returns `<root>/logs/<topic>-notes-<n>.md` and the sweep `<root>/logs/<topic>-notes-sweep.md`.

### The brief

Nine `##` headings numbered 1 to 9, as in `templates/brief.md`: 1 how to use, 2 situation, 3 settled decisions, 4 leading words, 5 the research program, 6 evidence and validation standards, 7 deliverable format, 8 open inputs, 9 prompt index. §6 has a line `Domain rules: <path in backticks>` naming the domain rules file, relative to the repository root or to `root`.

### The domain rules

Eight `##` headings numbered 1 to 8: when information counts as known; what settles each claim type here; standard methods to reuse; units, denominators and bases; feasibility at the requester's scale; data sources, access and licence; advice and regulatory boundaries; domain words. The preamble fixes three rules: accepted decision records override the domain rules, and a decision that changes a rule changes it in the same pull request; runs propose changes and never edit the file; "decision-critical" means an input, value or claim that a recommendation, decision or reference case depends on.

Each rule is a `###` subsection under its heading:

```markdown
### <rule-id>: <the rule, one sentence>
- Check: <how a reviewer verifies it>
- Scope: decision-critical | all
- Source: <owning source with a date, a decision record name, an incident (a log path), or the requester with a date>
- Added: YYYY-MM-DD
- Host: <the configured consumer's name>     (optional: that consumer's code implements the rule)
- Retired: YYYY-MM-DD; <reason>              (optional)
```

The ID is kebab-case, unique in the file, never renamed or reused. A rule is never deleted; it is retired. Prompts, delegations and reviews cite rules by ID.

**Deprecated in 0.6.0; removed in 0.7.0:** rules written as bullets without an ID.

### The queue

`research-queue.md` holds one table with at least the columns Task, Prompt, Deliverable, Prerequisites and Status; more columns are allowed. Prompt paths are relative to `root`. Prerequisites name task rows, comma-separated and matched case-insensitively, or "none". Statuses: `todo`, `waiting on requester`, `in review`, `accepted`, `rejected`, `deferred`. Selection rule: the first `todo` row in table order whose prerequisites are all `accepted`.

### Prompts

In `prompts/`, from `templates/prompt.md`, with the optional lines `Shape:` (new research, revision, clarification) and `Run settings:` (`<model>, effort <level>`).

### Decision records

In `decisions/`, from `templates/decision-record.md` (or the project's override). Each decision is a subsection `### <decision-name>: <one-sentence decision>` under the record's `## Decisions` heading, and opens with a fenced `yaml` header block. Every `###` heading with a colon under `## Decisions` is read as a decision; other sections may hold any headings:

```yaml
name: <decision-name>            # stable kebab-case; equals the subsection heading's name
status: accepted                 # accepted | rejected | deferred | superseded | withdrawn
decided: YYYY-MM-DD
decided_by: <the config's decider>
depends_on: [<decision-name>]    # [] when none
supersedes: [<decision-name>]    # or a quoted string naming a document and section
parameters:                      # [] when none
  - {name: <name>, value: <value>, unit: <unit, per denominator>, source: "<deliverable> §<n>"}
```

A project may add keys. The prose fields that follow keep the names Status, Decision, Parameters, Rule, Acceptance tests, Constraints and non-goals, Evidence, Depends on, Supersedes, Open items and the optional Reopen when; the record closes with `## Rejected and deferred decisions`. `decisions/INDEX.md` has one table row per decision with at least the columns Decision and Status, matching each header.

## What a run writes

- The deliverable at `<root>/<topic>.md`, headed with run date, shape, model, effort and plugin version.
- The log at `<root>/logs/<topic>-log.md`, with the sections of `templates/log.md`: Intake record, Frame and plan, Searches, Sources, Dead ends, Flagged content, Verification, Applied rules, Self-review, Review findings, Spend. Its header records the config line (`config: research-agent.toml`, or the legacy line above) and the doctor's WARN and DEPRECATED items.
- The notes files, scripts and fixtures, and the queue row's status: `in review` or `waiting on requester`.
- **Hand-over:** a branch `research/<topic>` and a pull request against the remote's default branch. With no remote or no `gh`, the run commits on the branch and the hand-back says `pull request: none`.

A run never writes decision records, never edits the domain rules, never merges, and never writes to the plugin's own files.

### Applied rules

The log's Applied rules table, one row per question group and rule in scope:

```markdown
| Question group | Rule ID | Result (pass / fail / n/a) | Where shown |
|---|---|---|---|
```

### The hand-back

Every run ends with this block, as the last section of the pull request body and as the session's last message. A host finds it by its heading and reads it by its labels.

```markdown
## Hand-back

- Status: in review | waiting on requester | stopped: <reason>
- Answer: <two to five sentences: what the research found>
- Proposed decisions:
  - `<decision-name>`: <one-sentence decision>. Parameters: `<name>` = <value> <unit> per <denominator>; … Evidence: §<n>, <claim type>, <grade or "measured" or "documented">. Touches: <accepted decision names, or "none">.
- Open items:
  - <item, with the evidence that would resolve it; for "waiting on requester", the questions>
- Flagged content:
  - <URL>: <what the text tried to do> | none
- Lesson candidates:
  - [tool] <rule>. Incident: <what happened in this run>. Check: <how a reviewer verifies it>.
  - [field] <rule ID, or "new">: <proposed rule>. Incident: <…>. Check: <…>.
- Spend: <tokens or cost>; model <model>; effort <level>
- Paths: deliverable `<path>`; log `<path>`; notes `<paths>`; scripts `<paths>`; branch `research/<topic>`; pull request <URL | none>
- Plugin: research-agent <version>; config <research-agent.toml | legacy prose>
```

Proposed decisions are proposals; only the decider decides, in a decision session. `[tool]` lessons are filed as issues labelled `lesson` on the plugin's repository (`repository` in `plugin.json`). `[field]` lessons reach the domain rules through the decision session.

## The doctor

`uv run --script ${CLAUDE_PLUGIN_ROOT}/tools/doctor.py --mode run|setup [--project PATH]` compares the config with the files on disk. `/new-research-project` runs it last with `--mode setup`; `/run-next-task` runs it at step 0 with `--mode run`. Each item prints on its own line as `FAIL`, `WARN` or `DEPRECATED` with its check number; the output names environment variables, never their values. Exit codes: 0 no FAIL; 1 at least one FAIL (the run or setup stops); 2 the doctor could not run. `--help` lists the checks. The identity check FAILs with `--mode run` and WARNs with `--mode setup` when `[project.fetch_identity]` and `FETCH_RAW_IDENTITY_HOSTS` differ or a named variable is unset; when the environment map is set but the config declares none, it WARNs in both modes. On the legacy prose config, a rule's `Host:` line is DEPRECATED, not checked, because there is no configured consumer to compare it with.

## The consumer kit

Setup copies these files into the host's `.research-agent/`. Each file's first line is a stamp inside a comment, `research-agent <version> sha256:<hex>`, where the hash is of the rest of the file with line endings normalised to `\n`. The doctor checks that the version is inside `requires` and that the hash matches.

- `.research-agent/INTEGRATION.md`: the integration prompt.
- `.research-agent/research_drift.py`: the drift tool (Python 3.11 or later, standard library only).

```
python .research-agent/research_drift.py [--research PATH] [--ref REF] [--no-fetch]
python .research-agent/research_drift.py --hash decision <record path> <decision-name>
python .research-agent/research_drift.py --hash rule <rule-id>
python .research-agent/research_drift.py --help
```

Exit codes: 0 no drift; 1 drift or pending rows; 2 setup error. Reports: `PENDING`, `CHANGED`, `SUPERSEDED`, `STATUS`, `MISSING`, `NEW`; `--help` gives each one's meaning and action. A decision's hash is of its subsection, from its `### <name>:` heading to the next `###` or `##` heading: lines right-stripped, joined with `\n`, sha256, first 12 hex characters. A rule's hash is the same on the domain rules file.

### The lock: `docs/research-lock.md`

```markdown
## Locked decisions

| Decision | Record | Research commit | Content hash | Used by | Read |
|---|---|---|---|---|---|

## Pinned rules

| Rule | Research commit | Content hash | Implemented in | Read |
|---|---|---|---|---|
```

A Research commit of `pending <PR URL>` marks a row that waits for a research merge. Backticks in cells are ignored.

## Skills and agents

- Skills: `research-protocol`, `research-writing`, `run-next-task` (`/run-next-task`), `new-research-project` (`/new-research-project`, modes new, adopt and consumer).
- Agents, invoked by their plugin-scoped names as `subagent_type`: `research-agent:researcher` (web search and fetch only; launched without the user, project and local `CLAUDE.md` files, so project facts reach it only through the delegation prompt), `research-agent:reviewer` (reads and runs scripts; no web). A project that configures a raw-page fetcher as an MCP server named `firecrawl` makes its search and scrape tools available to the researcher; no other project tool reaches it. A project that needs a different fetch server may place its own `.claude/agents/researcher.md` with `name: researcher`, the same frontmatter and body, and a `tools:` line that names its server's search and scrape tools and nothing else; `/run-next-task` then calls it by the bare name `researcher` in place of the plugin's.

## Raw fetch tool

- The plugin bundles a read-only MCP stdio server, `fetch-raw`, declared in `.mcp.json` and launched with `uv run --script`; it loads whenever the plugin is enabled. Its one tool is callable as `mcp__plugin_research-agent_fetch-raw__fetch_raw`, and the researcher's tool list names it.
- Arguments: `url`; `offset` (default 0); `max_chars` (default 40000, at most 100000); `route`: `auto` (direct, then Firecrawl when the page is blocked and a key is set), `direct` or `firecrawl`.
- Return: a header of `key: value` lines, `status` (`OK`, `BLOCKED` or `ERROR`, with the HTTP code), `reason` when not OK, `final_url`, `content_type`, `fetched_at` (UTC), `sha256` (of the body bytes), `route`, `bytes`, `total_chars`, `next_offset` (a number or `none`) and `warnings`; then, for OK only, a `--- content ---` line and the text. HTML text marks superscripts `^[x]` and subscripts `_[x]`; PDF text separates pages with `--- page N ---`.
- Environment variables, read from the environment Claude Code starts the server with:
  - `FETCH_RAW_IDENTITY_HOSTS` (optional): comma-separated `host-suffix=ENVVAR` pairs, such as `example.gov=EXAMPLE_IDENTITY`. A request to a matching host sends the named variable's value as its User-Agent; no other host receives it, and a matching host is never routed through Firecrawl. A missing variable gives `ERROR`. The server reads the map only from the environment; a project declares the same map in `[project.fetch_identity]`, and the doctor compares the two.
  - `FIRECRAWL_API_KEY` (optional): enables the Firecrawl fallback and `route: firecrawl`.
- Labels: `raw-fetched` (a value read from `fetch_raw`), next to `snippet` and `summary-fetched`.

## Headings and paths cited by name

- `skills/research-protocol/references/review.md`: the headings "Revision" and "Decision session".
- `skills/research-writing/SKILL.md`: the heading "Writing for an implementing agent".
- `skills/new-research-project/templates/`: `research-agent.toml`, `brief.md`, `domain-rules.md`, `queue.md`, `prompt.md`, `log.md`, `decision-record.md`, `decision-index.md`, `consumer-context.md`, `pull-request.md`, `research-lock.md`.
