# Changelog

Every change to the plugin, by release. A pull request adds a line under `## Unreleased` and leaves the version alone. A release pull request moves those lines under `## X.Y.Z (date)`, sets `version` in `.claude-plugin/plugin.json`, updates `UPGRADING.md` and restamps the kit (`python tools/stamp_kit.py`); after its merge the merge commit is tagged `vX.Y.Z`, and the tag is never moved. Each release's "Contract" subsection records what changed in `CONTRACT.md`; `UPGRADING.md` says what a project does about it.

## Unreleased

## 0.8.0 (2026-11-08)

A run stops when its raw fetcher is down, the researcher no longer counts on Firecrawl tools that no server provides, and the fetch-raw server starts about twice as fast. A contract change: every host edits its `requires` line (`UPGRADING.md`).

- Added: the fetcher check (#62). `/run-next-task` calls `fetch_raw` once on the plugin's repository page at step 0, after the doctor, and again before each batch of researcher calls. If the tool is absent, the call fails, or the status is not OK, the run delegates nothing and fetches nothing with WebFetch: at step 0 it ends before selection with `Status: stopped: fetch_raw unavailable` and the error text; later it stops early on its branch. On 2026-11-08 a run whose server had failed to connect delegated three researchers onto WebFetch summaries (378,614 tokens, notes rejected); the requester's rule is "such an error should stop the process immediately and not waste my tokens".
- Added: the researcher's first step (#62). With no `fetch_raw` among its tools, or after a failed `fetch_raw` call, it returns at once with `fetch_raw unavailable` under Gaps and does not go on with WebFetch.
- Changed: `summary-fetched` now covers only a value from a page `fetch_raw` could not open while it worked (protocol core rules, `standards.md`, `searching.md`, the researcher), never a run without `fetch_raw` (#62).
- Changed: the researcher's text says that Firecrawl reaches it only inside `fetch_raw` (`FIRECRAWL_API_KEY`, raw bytes through the plugin's converter), that the two `mcp__firecrawl__` names exist only on a host that configures a `firecrawl` MCP server, and that they are never a fallback for `fetch_raw` (#63). The README's Firecrawl section says the same.
- Fixed: the fetch-raw server's start (#61). Each start recompiled about 1,490 library files, because uv installs without bytecode and the server turned bytecode writing off before any import; it now lets the libraries cache their bytecode in uv's environment, while its own modules still write none into the plugin folder. The fetcher (converter, network and PDF code) is imported on the first tool call instead of at start. Measured on one Windows machine on 2026-11-08: imports at start 7.6 to 8.9 s before, 3.6 to 5.1 s after; `uv run` to the `initialize` reply 10.6 to 40.8 s before (median 12.6 s, six starts) and 5.0 to 10.4 s after (median 6.1 s, five starts), interleaved on the same busy machine. The first start after an install compiles and writes the bytecode once (12.5 s measured). The tool's schema and replies are unchanged.
- Added: `MCP_TIMEOUT` (#61). `/new-research-project` writes `"MCP_TIMEOUT": "120000"` into the project's `.claude/settings.json` `env` block when absent (new and adopt modes), and the doctor's check 13 WARNs when it is set neither there nor in the environment.
- Deprecated: the `firecrawl` MCP server hook and its two tool names in the researcher's tool list, removed in 0.9.0 (#63). The doctor's check 14 reports a `firecrawl` server in the project's `.mcp.json` as DEPRECATED.
- Kit: `INTEGRATION.md` names contract 0.8 and `v0.8.x`; both files are restamped 0.8.0, so consumers copy the kit again.

### Contract

- Added: the fetcher check and its stop, `Status: stopped: fetch_raw unavailable` (at step 0 before selection with no claim, later by the early stop); the researcher's `fetch_raw unavailable` return; the doctor's checks 13 (WARN, `MCP_TIMEOUT`) and 14 (DEPRECATED, a `firecrawl` server).
- Changed: `summary-fetched` marks a value from a page `fetch_raw` could not open while it worked, never a run without `fetch_raw`.
- Deprecated in 0.8.0, removed in 0.9.0: the `firecrawl` server name and its two tool names in the researcher's tool list.
- Unchanged: the `fetch_raw` tool, its arguments, header fields, statuses and environment variables; skill and agent names; the hand-back's labels; the queue, the selector, the lock and the kit's paths and command lines.

## 0.7.0 (2026-10-10)

Parallel runs, the model named by reference, and the removals 0.6.0 announced. A contract change: every host edits its `requires` line (`UPGRADING.md`). Design: `docs/design/0.7.0.md`.

- Added: `tools/next_task.py`, the selector `/run-next-task` runs at step 1 (#28). It reads the queue on the remote's default branch and skips a `todo` task whose branch `research/<topic>` another run holds: claimed, in review, waiting on requester, or merged. It resumes a stopped run, and it claims the task it takes by pushing an empty claim commit without force, so of two sessions started together that pick one task, one push is rejected and that session takes the next task. A closed, unmerged pull request frees its task. `/run-next-task <topic>` runs a named task, which may resume a run waiting on the requester, take over a crashed run or re-run a merged task. `--list` prints every task's state.
- Changed: runs no longer edit the queue, so two runs' pull requests no longer conflict on its table (#28). A run's status lives in its hand-back, which now also ends the log; the decision session sets the task's row to `accepted`, `rejected` or `deferred` in its own pull request. A resumed run replaces the hand-back in its pull request. A stopped run is resumed by the next session without anyone editing the queue. With a remote but no `gh`, a run pushes its branch.
- Changed: where the host forbids model identifiers in the repository, the deliverable's heading, the log header and the hand-back's Spend line in the log and the pull request write `by reference`, and the session's closing message names the model (#42).
- Added: the drift tool's `PARTIAL` report, for an accepted decision not yet in the lock that supersedes a quoted part of a pinned decision. It stops once the new decision is pinned. 0.6.1 deferred it here (#14).
- Removed, as deprecated in 0.6.0: the fallback that read research paths from the `CLAUDE.md` "Research" section (the doctor FAILs check 1 without `research-agent.toml` and names the setup mode to run; the drift tool exits 2 on a research repository with no config on the ref), and domain rules written as bullets without an ID (check 4b FAILs).
- Kit: both files changed (the drift tool's reports; `INTEGRATION.md` for contract 0.7 and the queue), so consumers copy the kit again.

### Contract

- Added: the run states (running, stopped, waiting, in review, done, abandoned, free) and the selection rule over them; the claim commit and its subject `research-agent claim: research/<topic> <token>`; `/run-next-task <topic>`; the selector's command line, output and exit codes; the log's last section, Hand-back; `by reference` in place of the model; the drift report `PARTIAL`; the drift tool's exit 2 for a research repository without a config.
- Changed: the selection rule now skips a `todo` row whose run is running, in review, waiting or done, and resumes a stopped one; whoever adds a task writes `todo`, and the decision session writes `accepted`, `rejected` or `deferred`; a run writes no queue status; the hand-over claims the branch at selection, and with a remote but no `gh` pushes it; the hand-back is also the log's last section, and its Plugin line drops `legacy prose`.
- Removed: the legacy prose config and its log line; domain rules as bullets without an ID; the doctor's DEPRECATED items for checks 1, 4a, 4b and 7.
- Unchanged: queue statuses and columns (doctor check 5), skill and agent names, the branch name, the log path, the hand-back's labels, the lock, the kit's paths and command lines, and the `fetch_raw` tool.

## 0.6.2 (2026-10-10)

Nineteen lesson issues from runs under 0.6.1, folded into ten new takeaways and seven amendments. The protocol's steps, the hand-back, the kit's code and the contract are unchanged.

- Added: `takeaways.md` entries 55 to 64 (section J), from lesson issues #24, #25, #29 with #30, #31, #33, #34, #35, #37, #39 and #40. Most are checks before trusting a number: binary data files read by script (55), interacting parameters tested together on a replay (56), a rule scored only on a holdout drawn after it is frozen and labelled blind to its output (57), periods keyed by end date (58), a new extraction pattern run on one known document first (59), a test case for every step of an ordered rule (60), a weight's total and largest values checked (61), options compared on totals to the horizon's end (63), and every simulated variant shown in the comparison table (64). One is about cost: a subagent stopped by a usage limit is resumed, not relaunched (62).
- Changed: seven entries now cover a later case of their lesson. Entry 49 copies a subagent's return from the channel the harness delivers it on, final message or hand-back call, and checks the copy's length and first and last lines (#23, #36); 11 dates a file's contents by its edition, with as-of tests either side of each publication (#26); 52 names the counter behind every spend figure (#27); 45 logs a parameter change made after a result when it is made (#32); 37 labels figures fed by an ILLUSTRATIVE constant ILLUSTRATIVE (#38); 10 defines each formula symbol's basis and tests a change of basis (#41); 22 uses a regulator's or registry's filed copy where terms forbid automated access (#43).

### Contract

- Unchanged.

## 0.6.1 (2026-10-10)

Thirteen lessons from the first runs under 0.6.0, and a drift-check fix. The protocol's steps, the hand-back and the contract are unchanged.

- Added: `takeaways.md` entries 42 to 54 (section I), from lesson issues #9 to #13 and #15 to #21. Most are about cost: the main session keeps its context bounded by handing off or compacting at phase boundaries (48), copies subagent returns by script and edits in place (49), and keeps script output in files (50); a run says how its main session's spend can be measured (52). The rest: isolated measurement environments (42), raw fetches only on identity hosts (43, after #10 recurred), cached negative responses and kept failure bodies (44), samples named before results (45), escapes in files, not heredocs (46), style proxies tested on both backgrounds (47), long measurements with a limit, a cache and a checkpoint (51), bounds and counts on one unit (53), unique keys in merged selections (54).
- Fixed: the drift tool reported SUPERSEDED, with its "retire the old row" action, when an accepted decision's `supersedes` list quoted only a part of a pinned decision (for example `"<decision> rule 2, detection only"`). It now reports SUPERSEDED only when the list names the pinned decision alone, bare or quoted (#14). A partial supersession still reaches the host through the new decision's NEW report; a report of its own needs a contract change and waits for 0.7.0.

### Contract

- Unchanged. The SUPERSEDED line of `--help` now says what counts as naming a decision.

## 0.6.0 (2026-10-09)

One config file, a setup skill that adopts and checks, a consumer kit, a fixed hand-back, releases, and domain rules with IDs. The research protocol itself is unchanged, and so is `fetch_raw`'s code; only its version label moves with the release. Design: `docs/design/0.6.0.md`.

- Added: `research-agent.toml`, read by every skill; `tools/doctor.py`, run last by setup and at `/run-next-task` step 0; the consumer kit `kit/INTEGRATION.md` and `kit/research_drift.py`, copied into hosts with a version and content-hash stamp (`tools/stamp_kit.py` writes the stamps); templates for the config, the decision index, the consumer context file, the research pull request and the lock.
- Changed: `/new-research-project` detects its mode (new, adopt, consumer), writes only what is missing, routes its interview through a host, and ends with the doctor. `/run-next-task` takes its paths from the config, records the Applied rules, scopes lessons as `[tool]` or `[field]`, and ends with the `## Hand-back` block. The decider replaces the requester as the one who decides. The reviewer checks the Applied rules table. Finance examples left every file a run reads (takeaways, intake, standards, searching, prompt writing, the domain-rules template, the research-writing skill).
- Fixed: the drift tool reads git output as UTF-8, as the contract's hash requires; it used the platform's default encoding, so hashes differed between Windows and Linux, and non-ASCII text could crash `--hash`. Hosts whose own script hashed on Windows re-pin once (`UPGRADING.md`).
- Changed after the stage-2 trials: both skills open plugin files only by the paths they name and do not list or search the plugin folder, the run skill states the researcher's return sections, and `effort-and-cost.md` states the subagents' model and effort, so a host never opens the agent files; a run calls its subagents in the foreground and schedules no wake-ups; a run that must stop early hands back `stopped: <reason>` with the queue row `waiting on requester`, and the next session resumes it on the same branch; setup is merged before the first run, and runs branch from the default branch; setup asks the consumer question only in new or adopt mode; content a host proposes from its own knowledge is labelled `[PROPOSED: host]`; `research = "self"` gets its own `CLAUDE.md` pointer.
- Packaging: `plugin.json` gains `license`, `repository` and `homepage`; `LICENSE` is inside the plugin; the marketplace entry no longer carries a version. Test fixtures copied from a finance project moved to `test-fixtures/` at the repository root, outside the shipped plugin folder.

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
