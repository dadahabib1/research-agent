# Upgrading

What changes for a project between plugin versions, and what to do about it. `CONTRACT.md` lists the current contract; `CHANGELOG.md` lists every change by release.

## 0.5.x to 0.6.0

0.6.0 adds one config file, a doctor, a consumer kit, a fixed hand-back and rule IDs. A research project without the config keeps working on the 0.5.0 reading of its `CLAUDE.md` "Research" section, with DEPRECATED notices, until 0.7.0 removes that fallback. Nothing a project wrote before needs editing to keep running, and no accepted decision record is touched.

### A research project (adopt mode)

1. **Pin the release.** In `.claude/settings.json`, give the marketplace source `"ref": "v0.6.0"` (README, "Install"). In a cloud environment, start the setup script with `PLUGIN_REF=v0.6.0` and use it in the install and pre-warm lines (README, "Claude Code cloud sessions"). Until the next step, runs use the legacy fallback.
2. **Run `/new-research-project`.** It detects adopt mode and, after you confirm, writes:
   - `research-agent.toml`, matching your files: `root`, `brief` (keep your brief's file name; the new default is `research-brief.md`), `decider`, the consumer and its context file, `env`, and `[project.fetch_identity]` where your domain rules send an identity to a host;
   - the `CLAUDE.md` pointer to the config, in place of the path list (your own rules stay);
   - any missing file new mode writes: `<root>/templates/prompt.md`, `.gitignore` lines for `__pycache__/` and `*.pyc`, `.github/pull_request_template.md`;
   - a list of proposed content changes and of steps only a person can take.
   Done when the doctor reports no FAIL.
3. **Rule IDs.** By pull request, convert each domain-rules bullet to the rule format: a `### <rule-id>: <rule>` subsection with Check, Scope, Source and Added lines, and `Host: <consumer>` only on rules the consumer's code implements and no accepted decision already states. Add the template's three preamble rules (precedence, the change rule, "decision-critical") if they are missing. Until this merges, the doctor reports check 4b as DEPRECATED.
4. **Prompts not yet run.** Where a prompt retypes a domain rule, cite its rule ID instead (`templates/prompt.md`, the Standards line). Leave results, logs and accepted records alone.
5. **Environment.** Set every variable `[project.fetch_identity]` names, and `FETCH_RAW_IDENTITY_HOSTS` to the same map, wherever runs happen: `/run-next-task` now stops at step 0 when they differ or one is unset. Other `env` names only warn.
6. **Decision headers.** Each decision opens with a `yaml` block with at least `name`, `status`, `decided`, `decided_by`, `depends_on`, `supersedes` and `parameters`, and `decisions/INDEX.md` has a row per decision with the same name and status. The doctor fails on a mismatch. A project template that adds keys stays as an override in `<root>/templates/`.

Done when the doctor shows no FAIL after step 2 and no DEPRECATED after step 3.

What changes in runs: the log header records the config line and the doctor's items; the log gains an Applied rules table; lesson candidates are scoped `[tool]` or `[field]`; the pull request and the session end with the `## Hand-back` block (`CONTRACT.md`); with no remote, the run commits on its branch and says `pull request: none`.

### A consumer (consumer mode)

1. Enable the plugin pinned to `v0.6.0` and run `/new-research-project`. It detects consumer mode and writes a `[consumes]` table, `.research-agent/INTEGRATION.md` and `.research-agent/research_drift.py` (copied with their stamps), and `docs/research-lock.md` or, where it exists, its empty "Pinned rules" table.
2. **Check hash parity before deleting anything.** `python .research-agent/research_drift.py --no-fetch` must report no drift on the rows your own drift script passes today. The kit keeps the hash function, so existing hashes stay valid.
3. Retire your own drift script and its documentation, and point your `CLAUDE.md` and every reference to them at `.research-agent/INTEGRATION.md` and `.research-agent/research_drift.py`.
4. Pin a domain rule whose `Host:` names you once the research project has rule IDs (`--hash rule <rule-id>`).
5. Do not edit the kit's files: the doctor compares each file with its stamp. To upgrade the kit, run `/new-research-project` again after pinning the new release.

## 0.4.x to 0.5.0

The plugin now bundles a raw page fetcher, `fetch_raw` (an MCP server the researcher calls as `mcp__plugin_research-agent_fetch-raw__fetch_raw`). Nothing a project depends on breaks; the researcher's tool list gains one tool and keeps WebFetch and the `firecrawl` names.

What to do in the project:

1. **Install uv** where sessions run (it is pre-installed in Claude Code cloud sessions). Without it the tool doesn't start; the researcher then has WebFetch only and its values stay summary-fetched.
2. **Environment variables**, if you need them: `FETCH_RAW_IDENTITY_HOSTS` (for example `sec.gov=EDGAR_IDENTITY`) with the identity variable it names, and optionally `FIRECRAWL_API_KEY` for the fallback on blocked pages. See the README, "Raw page fetcher".
3. **Cloud environments:** allow the research sites in network access (Custom or Full), and add the pre-warm lines from the README to the setup script.
4. **Labels:** logs and deliverables gain the label `raw-fetched` for values read with `fetch_raw`. Values read with WebFetch stay summary-fetched until a raw fetch or a second route confirms them, and a BLOCKED result goes under Dead ends. If your brief §6 or domain rules list the fetch labels, add `raw-fetched`.
5. **A project-level researcher** (`.claude/agents/researcher.md`) doesn't get the new tool by itself: add `mcp__plugin_research-agent_fetch-raw__fetch_raw` to its `tools:` line.
6. **Firecrawl:** if you configured Firecrawl's MCP server under the name `firecrawl` only for raw pages, you may drop it; `fetch_raw` with `FIRECRAWL_API_KEY` uses Firecrawl's API for blocked pages and converts the raw bytes itself. Keep it if you want its search as a second discovery route.

## 0.3.x to 0.4.0

Nothing a project depends on breaks: skill names, queue statuses and columns, the decision-record heading and field names, brief section numbers, the log path, the branch name and the cited headings are unchanged. One behaviour changed: `/run-next-task` now takes the first `todo` row in table order whose prerequisites are accepted (0.3.x took the lowest-numbered prompt). Order your queue rows.

What to do in the project:

1. **Domain rules.** The plugin no longer ships field-specific rules. Write yours from `skills/new-research-project/templates/domain-rules.md` (eight headings: when information counts as known; what settles each claim type; standard methods; units and denominators; feasibility at scale; data sources and licences; advice boundaries; domain words), save the file in `docs/research/`, and point to it from the brief's §6 under a "Domain rules" line. If your brief §6 already restates such rules, move them into that file and leave the pointer.
2. **Prompts.** Add `Shape: new research | revision | clarification` and, where the defaults do not apply, `Run settings: <model>, effort <level>` near the top of each prompt and of any prompt templates of your own. A prompt without `Shape:` runs as new research.
3. **Decision records.** Your template copy may add the optional field `- **Reopen when:**` and the new `Evidence:` values (claim type; `n/a: measured`; `n/a: documented`). Do not edit accepted records to add them; a changed record is a new record.
4. **Logs.** Logs written from now on carry new sections (Frame and plan, Flagged content, Self-review, Review findings, Spend), and researcher returns are kept as `logs/<topic>-notes-<n>.md`. Nothing to change in existing logs.
5. **Pull requests.** Expect new sections in the PR body: Flagged content, Candidate takeaways, Spend. If you keep a PR template, add them.
6. **Raw-page fetcher (optional).** See the README, "Raw page fetcher" (0.5.0 bundles one).
7. **Unattended runs.** See the README, "Unattended runs". Protect the default branch so a run cannot merge.

What changed inside the plugin, for context: the researcher subagent is web-only (no file reads, no shell, no writes); the reviewer has no web access and receives the researcher's newer-edition and contrary-evidence sweep; evidence is stated by claim type (literature grades A to D; measurements with sample and script; documented facts at a version or date; judgments) instead of one letter scale; the `[PROVIDED]` label marks facts the requester or the project supplied; runs propose takeaways rather than writing them; `references/finance.md` was removed, and `references/searching.md` and `references/untrusted-content.md` were added.
