# research-agent respec: design input (2026-10-09)

Everything settled in the 2026-10-09 working session between the owner and the equity_analyst orchestrator about how research-agent should change. Its job is to make sure the redesign loses none of that context. Read it in full before writing the design doc or any respec code. It is input, not the design: the design doc builds on it and may revise points with reasons.

**Version numbering.** fetch_raw shipped as 0.5.0 (PR #5), so the respec described here is **0.6.0**. Wherever the session said "0.5.0 redesign", read 0.6.0.

## 1. The owner's goals (binding)

1. **A tool, not a skeleton.** research-agent stays a reusable, versioned, specialised **research-project** tool. Projects supply their own brief, domain rules and questions. The owner explicitly rejected turning it into a skeleton that each project forks. Its shapes (new research, revision, clarification) are dedicated to research projects and stay.
2. **Sprints, not per-use change.** The plugin improves from run experience in batches (releases). Consumers pin a release.
3. **Plug and play through one integration prompt.** Any agentic system must be able to adopt the plugin from one prompt the plugin ships, whatever that system's architecture: a dedicated research project, or a single generalist agent that is coder, designer and everything else and runs its own orchestration with subagents and background agents. The prompt onboards the plugin's research protocol onto the host. It tells the host:
   - what it must set up (brief, domain rules, queue, config);
   - how to call the plugin;
   - what comes back;
   - what the host owns afterwards.
   
   It is not a "lite mode" for quick questions. If a host has no research project, it should not call this protocol.
4. **Hard config, not prose.** Configuration is a structured file; CLAUDE.md just points to it.
5. **Accuracy is the product objective.** Research feeds an app whose goal is accurate analysis. Fidelity of facts and numbers outranks convenience.

## 2. Corrections the session made (don't repeat these mistakes)

- **"Single agent mode" is not a reduced protocol.** It means a generalist host agent with its own orchestration adopting the full protocol through the integration prompt.
- **"Request research" is a variant, not the default.** In the equity setup the app and the research repo are separate and the owner approves queue entries, so the app opens a PR with a prompt and a queue row. The general verb is **add a task**: fill the prompt template, add a queue row, run `/run-next-task` whenever wanted, now or later. Don't add a `queue: direct | by-pr` config option, and don't over-instruct. One line suffices: "add tasks the way you make any other change to that repository".
- **The setup skill already exists.** It is `new-research-project`. Extend it rather than inventing a new one. Building the integration around a setup command (like `npm init`) plus a doctor check is the expected, standard practice.
- **Reason from history before recommending.** Trace where something came from and why before proposing a change, and show the reasoning.

## 3. History that explains the current shape

- **2026-10-02.** The founding equity research brief (claude.ai Research mode) defined the app, its data sources and trust tiers T1–T4 (`equity_research/docs/research/equity-research-brief.md` §9.1). T1–T4 are part of the app's data model: every fact in its store carries `trust_tier`.
- **2026-10-05.** The plugin was generalised **from** the equity project. `takeaways.md` entries 1–35 come from that project's runs (2026-10-02 to 2026-10-05), and entries 36–41 from the first plugin run (the system review v1, equity_research PR #4). The former `references/finance.md` was that project's methodology (|t| > 3, extended Pearson–Tukey 0.185/0.63/0.185, point-in-time rules).
- **0.4.0** made the plugin domain-neutral. finance.md was removed, and project field rules moved to the project's `docs/research/domain-rules.md` (equity_research PR #5, with its follow-up commit bbac52c).
- **0.4.1** (PR #4) fixed the agent wiring:
  - scoped names `research-agent:researcher` / `research-agent:reviewer`, with a bare name only when a project defines its own agent;
  - the reviewer reads `review.md`, `untrusted-content.md` and the research-writing skill from `${CLAUDE_PLUGIN_ROOT}`;
  - `omitClaudeMd: true` on the researcher (needs Claude Code 2.1.271 or later; managed policy files and the git status snapshot still reach it).
- **0.5.0** (PR #5) added the `fetch_raw` MCP tool. Section 9 covers it.
- **Tags.** `v0.4.0` (69fac7f) and `v0.4.1` exist. Before 2026-10-09 there were none, and installs pulled `main`.

## 4. Audit of 0.4.0 as a plug-and-play tool (read-only, 2026-10-09)

**Requirement matrix (summary):**

| Requirement | Status | Reason |
|---|---|---|
| Tool, not skeleton | Partial | Config is prose plus brief section numbers |
| Versioned releases | Partial | Every merge bumps the version, so every merge is a release; no changelog |
| Consumer pin | Missing | Fixed in practice by the tags above |
| Sprint batching | Missing | No inbox for candidates |
| Project lessons separate from tool lessons | Partial | |
| Compatibility rules | Partial | No major, deprecation or consumer-range rules |
| Integration from one prompt | Missing | |
| Inline or path domain rules | Missing | Domain rules are reachable only through the brief's §6 pointer |
| Hand-back contract to a host | Missing | |
| Domain neutrality | Partial | |

**Structural problems, ranked:**
1. **The research capability is fused with one workflow.** The protocol is reachable only through brief → queue → PR → decision session, with no input spec and no hand-back. The protocol skill describes itself as working only "in a project that keeps a research brief, domain rules and a task queue … Not for quick questions."
2. **No release or pin mechanism.** Every merge is a release. Cloud installs `main`, and the cloud environment caches for about 7 days, so sessions can run different builds. A version label can misstate content.
3. **The learning loop has no inbox.** Candidate takeaways are stranded in consumer PR bodies, with no tool-versus-project scope.
4. **Finance residue sits in files every run reads:**
   - `takeaways.md` 1–35 (high-beta stock, risk-free rate, tax, account size, exchange calendar);
   - every ILLUSTRATIVE line in `templates/domain-rules.md`, which anchors a new project's interview;
   - `intake.md` (citizenship, residence, account size);
   - `prompt-writing.md` ("holdings, account size");
   - the research-writing examples (momentum, rebalance-drift-band);
   - `standards.md` ("net or gross", "out of sample", a ladder built on backtests).
   
   This pushes other fields toward backtest validity and tax questions.
5. **Config gaps.** Config is LLM-parsed prose plus brief section numbers; `<topic>` and the path roots are undefined.
6. **Subagent wiring.** Fixed in 0.4.1.

**The 13 respec items from the audit:**
1. A core input.
2. A fixed hand-back.
3. A decision owner.
4. Releases: tags, a CHANGELOG with an Unreleased section, bumps only at release, the version dropped from marketplace.json, consumers pinning a `ref`.
5. A lessons inbox: GitHub issues in the plugin repo, each candidate tagged `tool` or `project`.
6. A project lessons file.
7. Removing finance residue.
8. Machine-readable config.
9. Agent wiring (done in 0.4.1).
10. A hand-over mode: pr, commit or files.
11. A fuller scaffold: pinned enablement, a PR template, and a decision-session procedure with an index.
12. Packaging: `license` and `repository` in plugin.json, LICENSE inside the plugin directory.
13. Compatibility: major, minor and deprecation rules; the consumer declares a range; the run checks it.

**Session rulings on those items:**
- **Item 1** is reframed by goal 3. The integration prompt plus setup skill plus config replace the idea of a "run spec" lite adapter. A hand-back (item 2) is still needed.
- **Item 6 is rejected.** Field lessons go into the project's domain rules under its change rule. A separate lessons file would be a third place for field rules, next to the domain rules and the decision records.
- **Item 10:** don't over-instruct (section 2).
- **Before 0.4.1,** a bare `researcher` name did resolve in a `claude -p` test. The audit doubted that, but scoped names are still right.

## 5. Target architecture (agreed direction; details for the design doc)

- **Core:** the research protocol, the researcher, the reviewer and `fetch_raw`. Domain-neutral standards and examples. Generic takeaways only; incidents from the equity project are reworded neutrally or moved out of the files every run reads.
- **Setup skill (`new-research-project`, extended):**
  - writes the config file, the brief, domain rules, queue, prompt templates and the CLAUDE.md pointer;
  - writes what equity built by hand: a decision-record template with a header block, a decision index, the consumer context file and a PR template;
  - safe to re-run: re-running upgrades a project, and it can adopt an existing one such as equity_research by turning its CLAUDE.md prose into config;
  - works with a host agent: interview questions go through the host, which answers from its own context (labelled `[PROVIDED: project]`) or asks its user;
  - ends with a **doctor** check of config against files, which stops on any mismatch.
- **Integration prompt** (shipped by the plugin, versioned with the contract), a few lines:
  1. when the plugin applies;
  2. run the setup skill;
  3. add a task (prompt from template plus queue row, the way you change anything else in that repo);
  4. run `/run-next-task` (foreground, background or cloud);
  5. what comes back (the fixed hand-back);
  6. your upkeep jobs (below).
- **Config principle:** configure only what really varies between projects. Fix everything else in the contract: queue columns, statuses, brief headings, log sections, templates. Sketch:

```yaml
contract: "0.6"                      # plugin contract version the project targets
paths:  { root: docs/research, brief: ..., domain_rules: ..., queue: ..., decisions: ..., consumer_context: ... }
handover: { mode: pr, base: main }
decisions: { decider: requester }
consumer: { name: equity_analyst_v2, context_file: app-context.md }
fetch:   { identity: { "sec.gov": EDGAR_IDENTITY } }   # env var names only, never values
env:     { required: [EDGAR_IDENTITY, FRED_API_KEY] }
lessons: { tool: "github:dadahabib1/research-agent", field: domain_rules }
run_defaults: { model: ..., effort: ... }
```

  For one version the plugin keeps reading the old prose config as a fallback, so equity_research doesn't break.
- **Hand-back:** a fixed return:
  - the answer;
  - proposed decisions with parameters;
  - open items;
  - flagged content;
  - lesson candidates, scoped `tool` or `field`;
  - spend;
  - paths;
  - plugin version.
- **Drift tool:** the plugin ships the check equity wrote by hand (`equity_analyst_v2/scripts/research_drift.py`, about 155 lines). It compares each pinned decision with the research repo's main, using the decision header block and a pin file, so hosts don't each reinvent it.
- **Releases and sprints:**
  - git tags `vX.Y.Z`, a CHANGELOG, bumps only at release;
  - consumers and the cloud setup script pin `PLUGIN_REF` to a tag (editing that line forces a cloud rebuild);
  - tool lesson candidates go to plugin GitHub issues (the inbox), sorted each sprint into a release.

## 6. Host upkeep, and where a person is needed

| Job | Automated | Person needed |
|---|---|---|
| Consumer context file (what the host can do today) | The host updates it when its capabilities change; a doctor check warns when it is older than the host's latest release | No |
| Pins and drift | The drift tool flags changed or superseded decisions | No. Adopting a changed decision is ordinary host build work; the decision itself was already made in a decision session |
| Lessons | Captured in the hand-back and filed by the host | Yes, by design: the owner sorts tool lessons each sprint, and the decider accepts field-rule changes |

People are needed only for: decision sessions, accepting domain-rule changes, the sprint review of tool lessons, and merges wherever the host's own process requires one.

## 7. Domain-rules lifecycle (to standardise in 0.6.0)

Already done in equity_research (PR #5, bbac52c):
- a precedence rule: accepted decision records override the domain rules, and a decision that changes a rule changes it in the same PR;
- a change rule: runs propose changes and never edit the file;
- a definition of "decision-critical";
- trust tiers T1–T4 in domain rules heading 6;
- the technical-evidence rule split by claim type;
- the SEC identity rule.

Still open for the plugin and the projects:
1. **Learning route.** Plugin step 10 sends every candidate takeaway to the plugin maintainer. Add the scope split: `tool` candidates go to the plugin inbox; `field` candidates go to the project's domain rules through its change rule.
2. **Rule IDs.** Give each domain rule a stable ID plus fields: statement, Check, scope (decision-critical or all), source (owning source, decision record, incident or requester) and date added. Prompts, researcher delegations and reviews cite IDs instead of retyping text; the equity prompts 07–13 grew seven divergent copies of one technical-evidence rule.
3. **Applied-rules record.** The log gets a table of rule IDs applied per question group, with pass, fail or n/a, and the reviewer checks against it.
4. **Host pinning of rules it implements.** Rules the host's code implements (for equity: trust tiers, point-in-time filing dates) carry an `app` or `host` marker, and the host's lock file and drift check cover them.

## 8. Cloud facts (code.claude.com/docs/en/cloud-environments, checked 2026-10-09)

- Plugins declared in a repo's `.claude/settings.json` are **not** installed in cloud sessions. Only the owner's setup script installs research-agent. A project `.mcp.json` server does load in a single-repo cloud session.
- Network: Trusted reaches only registries, GitHub and cloud SDKs; sec.gov and FRED are not on it. The owner runs **Full** network. MCP connectors bypass the allowlist.
- Environment variables are set in the environment's `.env`-style field. EDGAR_IDENTITY, FRED_API_KEY and FIRECRAWL_API_KEY are set there. Network secrets (header-based, Pro/Max) are not available to the owner and don't fit FRED's query-string key.
- The setup script is cached as a filesystem snapshot for about 7 days and re-runs when the script or network hosts change. A change to a pinned `PLUGIN_REF` line forces a rebuild.
- uv is preinstalled. The fetch_raw pre-warm lines are in the 0.5.0 README; they are untested in a cloud session (the first cloud run should verify them).

## 9. fetch_raw (0.5.0) facts the redesign must keep

- **Tool name:** `mcp__plugin_research-agent_fetch-raw__fetch_raw`, bundled through the plugin's `.mcp.json` (uv, PEP 723, locked).
- **Fidelity:**
  - the whole page is converted; no readability-style extraction;
  - tables keep every cell;
  - sup/sub become `^[x]`/`_[x]`;
  - PDFs come back per page (pdfplumber), with exponents rebuilt from character size.
- **Labels:**
  - decision-critical values come from fetch_raw (labelled "raw-fetched") or a second route;
  - WebFetch is for discovery only (labelled "summary-fetched");
  - a BLOCKED result is a dead end to log, never content.
- **Identity:** `FETCH_RAW_IDENTITY_HOSTS=sec.gov=EDGAR_IDENTITY` sends the identity only to matching hosts, never to Firecrawl or into files. In 0.6.0 this moves into the config file's `fetch.identity`.
- **Firecrawl:**
  - a fallback transport only, through `rawBase64` (byte-identical bodies), always converted by our own converter;
  - its markdown and parse output merged superscripts and dropped footers, so it is never used for values;
  - map was incomplete; crawl and batch scrape add nothing; change tracking is markdown-only;
  - search is fine as a second discovery route.
- **Evidence behind the design:**
  - Jina's default mode silently dropped sections of the IBKR page;
  - Firecrawl markdown changed `0.00056^5` into `0.000565`;
  - Agent-Reach (rejected: it needs Bash, and SkillSpector said DO_NOT_INSTALL) offers nothing beyond Jina;
  - the NYSE page served a Cloudflare block with HTTP 200 on 1 call in 10.
- **Open:**
  - the first cloud run (proxy path, certificates, pre-warm);
  - Firecrawl getting past a live Cloudflare block;
  - multi-column PDFs interleave lines;
  - content hidden by CSS is kept.

## 10. Verification plan for 0.6.0

Two pass/fail trials in throwaway repositories, in a field other than finance, so any finance bias shows:
- **(a) Research project:** the integration prompt → setup skill → one `/run-next-task`.
- **(b) Generalist host:** a single agent with its own orchestration adopts the plugin from the integration prompt alone and runs one task.

Record every friction point. The trials on 0.4.0 were skipped as redundant with the audit.

## 11. Sequence after the design doc

1. Write the design doc as a draft PR in research-agent: architecture, setup and doctor, the integration prompt, config, hand-back, the drift tool, releases and inbox, neutralisation, the domain-rules lifecycle, all 13 audit items mapped and the session rulings applied. The owner reviews it.
2. Build 0.6.0, run both trials, fix, release, tag.
3. **equity_research adopts it:** run the setup skill in adopt mode to get the config; add rule IDs and sources to the domain rules.
4. **The app (equity_analyst_v2) adopts it:**
   - replace its hand-written integration (`docs/agents/research.md`, `docs/research-lock.md`, `scripts/research_drift.py`) with the plugin's integration prompt and drift tool;
   - pin the domain rules it implements.
5. **Then equity_research PR #4 (system review v1):**
   - decide whether it needs another pass under the new agent;
   - its blocking fix: committed `.pyc` files, and no `.gitignore` in equity_research;
   - check whether that cloud run could reach SEC at all (Trusted network blocks sec.gov).

## 12. Related context in the consumer projects

- **Sentiment** (equity_research `docs/research/sentiment-starting-points-2026-10-09.md`, PR #6) is not a queue priority, but the app is built with it in mind. It matters to the plugin only as a future consumer of fetch_raw (article text behind GDELT links).
- **Safety scans:** SkillSpector on research-agent 0.4.0 gave CAUTION with 4 MEDIUM flags, all false positives, in both the static and model passes. Scan again before installing a new release (the owner's global rule).
