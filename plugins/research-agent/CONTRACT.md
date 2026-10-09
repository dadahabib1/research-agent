# Consumer contract

What a project that installs this plugin may depend on. Everything listed here keeps its name, path and shape within a minor version; a change to any of it bumps the minor version and is recorded in `CHANGELOG.md`, under its release's "Contract" subsection. Everything not listed (reference files and their headings, template wording, agent bodies) may change in any version.

## Skills and agents

- Skills: `research-protocol`, `research-writing`, `run-next-task` (`/run-next-task`), `new-research-project` (`/new-research-project`).
- Agents, invoked by their plugin-scoped names as `subagent_type`: `research-agent:researcher` (web search and fetch only; launched without the user, project and local `CLAUDE.md` files, so project facts reach it only through the delegation prompt), `research-agent:reviewer` (reads and runs scripts; no web). A project that configures a raw-page fetcher as an MCP server named `firecrawl` makes its search and scrape tools available to the researcher; no other project tool reaches it. A project that needs a different fetch server may place its own `.claude/agents/researcher.md` with `name: researcher`, the same frontmatter and body, and a `tools:` line that names its server's search and scrape tools and nothing else; `/run-next-task` then calls it by the bare name `researcher` in place of the plugin's.

## Raw fetch tool

- The plugin bundles a read-only MCP stdio server, `fetch-raw`, declared in `.mcp.json` and launched with `uv run --script`; it loads whenever the plugin is enabled. Its one tool is callable as `mcp__plugin_research-agent_fetch-raw__fetch_raw`, and the researcher's tool list names it.
- Arguments: `url`; `offset` (default 0); `max_chars` (default 40000, at most 100000); `route`: `auto` (direct, then Firecrawl when the page is blocked and a key is set), `direct` or `firecrawl`.
- Return: a header of `key: value` lines, `status` (`OK`, `BLOCKED` or `ERROR`, with the HTTP code), `reason` when not OK, `final_url`, `content_type`, `fetched_at` (UTC), `sha256` (of the body bytes), `route`, `bytes`, `total_chars`, `next_offset` (a number or `none`) and `warnings`; then, for OK only, a `--- content ---` line and the text. HTML text marks superscripts `^[x]` and subscripts `_[x]`; PDF text separates pages with `--- page N ---`.
- Environment variables, read from the environment Claude Code starts the server with:
  - `FETCH_RAW_IDENTITY_HOSTS` (optional): comma-separated `host-suffix=ENVVAR` pairs, such as `sec.gov=EDGAR_IDENTITY`. A request to a matching host sends the named variable's value as its User-Agent; no other host receives it, and a matching host is never routed through Firecrawl. A missing variable gives `ERROR`.
  - `FIRECRAWL_API_KEY` (optional): enables the Firecrawl fallback and `route: firecrawl`.
- Labels: `raw-fetched` (a value read from `fetch_raw`), next to `snippet` and `summary-fetched`.

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
