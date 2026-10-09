# Changelog

Every change to the plugin, by release. A pull request adds a line under `## Unreleased` and leaves the version alone. A release pull request moves those lines under `## X.Y.Z (date)`, sets `version` in `.claude-plugin/plugin.json`, updates `UPGRADING.md` and restamps the kit (`python tools/stamp_kit.py`); after its merge the merge commit is tagged `vX.Y.Z`, and the tag is never moved. Each release's "Contract" subsection records what changed in `CONTRACT.md`; `UPGRADING.md` says what a project does about it.

## Unreleased

## 0.6.0 (2026-10-09)

One config file, a setup skill that adopts and checks, a consumer kit, a fixed hand-back, releases, and domain rules with IDs. The research protocol itself is unchanged, and so is `fetch_raw`'s code; only its version label moves with the release. Design: `docs/design/0.6.0.md`.

- Added: `research-agent.toml`, read by every skill; `tools/doctor.py`, run last by setup and at `/run-next-task` step 0; the consumer kit `kit/INTEGRATION.md` and `kit/research_drift.py`, copied into hosts with a version and content-hash stamp (`tools/stamp_kit.py` writes the stamps); templates for the config, the decision index, the consumer context file, the research pull request and the lock.
- Changed: `/new-research-project` detects its mode (new, adopt, consumer), writes only what is missing, routes its interview through a host, and ends with the doctor. `/run-next-task` takes its paths from the config, records the Applied rules, scopes lessons as `[tool]` or `[field]`, and ends with the `## Hand-back` block. The decider replaces the requester as the one who decides. The reviewer checks the Applied rules table. Finance examples left every file a run reads (takeaways, intake, standards, searching, prompt writing, the domain-rules template, the research-writing skill).
- Packaging: `plugin.json` gains `license`, `repository` and `homepage`; `LICENSE` is inside the plugin; the marketplace entry no longer carries a version.

### Contract

- Added: the config schema (`requires`, `[project]`, `[project.consumer]`, `[project.fetch_identity]`, `[project.run_defaults]`, `[consumes]`); the fixed layout under `root` and `<topic>`; the brief's nine and the domain rules' eight numbered headings; the rule format with IDs; the decision header's core keys and the index; the Applied rules table; the hand-back; the hand-over with its no-remote fallback; the lock format with a "Pinned rules" table; the kit's paths, command lines, reports and exit codes; the doctor's command line and exit codes; the version range rule and the release rules.
- Changed: the brief's default name is `research-brief.md` (was `strategy-research-brief.md`; `project.brief` keeps the old name); decision records open each decision with a `yaml` header block; statuses for decisions add `superseded` and `withdrawn`; the queue allows extra columns; `[tool]` lesson candidates are written in field-neutral words, and the host checks them before filing them on the public repository.
- Deprecated in 0.6.0, removed in 0.7.0: paths read from the `CLAUDE.md` "Research" section instead of `research-agent.toml`; domain rules written as bullets without an ID.
- Unchanged: skill and agent names, the `fetch_raw` tool and its arguments and returns, `FETCH_RAW_IDENTITY_HOSTS` as the server's only identity input, queue statuses and the selection rule, the log path and the branch name.

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
