# Changelog

Every change to the plugin, by release. A pull request adds a line under `## Unreleased` and leaves the version alone. A release pull request moves those lines under `## X.Y.Z (date)`, sets `version` in `.claude-plugin/plugin.json` and updates `UPGRADING.md`; after its merge the merge commit is tagged `vX.Y.Z`, and the tag is never moved. Each release's "Contract" subsection records what changed in `CONTRACT.md`; `UPGRADING.md` says what a project does about it.

## Unreleased

## 0.5.0 (2026-10-09)

The bundled raw page fetcher, `fetch_raw`.

### Contract

- Added: the bundled `fetch-raw` MCP server and its tool `mcp__plugin_research-agent_fetch-raw__fetch_raw`, with its arguments, header fields and statuses; the environment variables `FETCH_RAW_IDENTITY_HOSTS` and `FIRECRAWL_API_KEY`; the label `raw-fetched`. The plugin now needs `uv` on the PATH for the tool to start.
- Changed: the researcher's tool list adds the `fetch_raw` tool; WebFetch stays, for discovery. Decision-critical values come from `fetch_raw` or a second confirmed route; values from WebFetch stay summary-fetched; a BLOCKED result is a dead end.
- Unchanged: the `firecrawl` server name and its two tool names, the agent file names and every other name, path and shape.

## 0.4.1 (2026-10-09)

Agent wiring.

### Contract

- Clarified: the agents are invoked by their plugin-scoped names, `research-agent:researcher` and `research-agent:reviewer`, as Claude Code registers plugin agents; 0.4.0 said bare names. A project's own `.claude/agents/researcher.md` still replaces the plugin's researcher, now because `/run-next-task` calls the bare name `researcher` when the project defines one.
- Changed: the researcher sets `omitClaudeMd: true`, so the user, project and local `CLAUDE.md` files no longer reach it (requires Claude Code v2.1.271 or later; older versions ignore the field). Managed policy files and the git status snapshot still do.
- Unchanged: agent file names, tool lists, the `firecrawl` server name and every other name, path and shape.

## 0.4.0 (2026-10-07)

Run shapes, a web-only researcher, evidence by claim type, and domain rules owned by the project.

### Contract

- Added: the optional prompt lines `Shape:` and `Run settings:`; the log sections Frame and plan, Flagged content, Self-review, Review findings and Spend, and the header lines Shape and Fetch tools; the notes files; the optional decision-record field Reopen when; `templates/domain-rules.md`; the brief's §6 "Domain rules" pointer.
- Changed: the queue selection rule is table order (0.3.x: lowest-numbered prompt). The researcher agent is read-only (web search and fetch); the reviewer has no web access. `references/finance.md` is removed; domain rules belong to the project.
- Unchanged: skill names, queue statuses and columns, the decision-record heading and field names, brief section numbers, the log path, the branch name, and the cited headings.
