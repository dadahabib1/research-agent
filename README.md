# research-agent

A Claude Code plugin that a project installs to run evidence-based research tasks: a protocol, a session loop that runs one queued task per session and ends in a pull request, and two subagents. It is a tool. A project describes itself in one config file, `research-agent.toml`; the plugin reads it with the project's brief, domain rules and queue, and writes only into that project's repository: the deliverable, a log, scripts, its branch and a pull request. It never writes to its own files, never edits the queue, never merges, and never records a decision; a person does that in the project's decision session.

## Contents

- **Skills:**
  - `research-protocol`: intake, framing, evidence by claim type, verification of numbers in code, review, decision session;
  - `research-writing`: the writing standard for deliverables, prompts and reviews;
  - `run-next-task` (invoked as /run-next-task): the session loop;
  - `new-research-project` (invoked as /new-research-project): sets a repository up in one of three modes (new, adopt or upgrade, consumer) and ends with the doctor.
- **Doctor:** `tools/doctor.py`, which compares the config with the files and stops a run on any mismatch.
- **Selector:** `tools/next_task.py`, which picks a run's task from the queue and claims its branch, so sessions started together take different tasks; `--list` shows each task's state.
- **Consumer kit:** `kit/INTEGRATION.md` (the integration prompt a host follows) and `kit/research_drift.py` (the drift check on pinned decisions and rules), copied into a host's `.research-agent/` by setup.
- **Agents:** `researcher` (web search and fetch only; effort xhigh) and `reviewer` (reads and runs scripts; no web; effort high).
- **Raw fetch tool:** `fetch_raw`, a bundled read-only MCP server (`plugins/research-agent/servers/fetch_raw/`) that returns a page's own text, not a summary. See "Raw page fetcher" below.
- **`plugins/research-agent/CONTRACT.md`**: the names, paths and shapes a project may depend on.
- **`plugins/research-agent/UPGRADING.md`**: what changes between versions and what a project should do.
- **`plugins/research-agent/CHANGELOG.md`**: every change by release, with each release's contract changes.

## Install

Pin a release tag; `/new-research-project` writes this for you.

- **In one project:** add this to the project's `.claude/settings.json`, with the tag the project uses:

```json
{
  "extraKnownMarketplaces": {
    "personal-agents": { "source": { "source": "github", "repo": "dadahabib1/research-agent", "ref": "v0.7.0" } }
  },
  "enabledPlugins": { "research-agent@personal-agents": true }
}
```

  Claude Code installs it once the folder is trusted.
- **Manually:** run `/plugin marketplace add dadahabib1/research-agent@v0.7.0`, then `/plugin install research-agent@personal-agents`.
- **Adopting from another agent:** give the agent `plugins/research-agent/kit/INTEGRATION.md`; it says how to set up, add a task, run it, read the hand-back and keep pins current.
- **For claude.ai chat and Cowork:** zip `plugins/research-agent/skills/research-protocol/` and upload it as a skill.

## Use

- **Set up:** `/new-research-project`. It detects its mode and says so before writing:
  - **new:** writes `research-agent.toml`, the brief, the domain rules, the queue and the rest of the layout, then interviews you (or the host agent, which answers from its own records) to fill the brief and the domain rules;
  - **adopt:** writes a config that matches an existing research program, or upgrades one to this version, and lists the content changes the contract asks for as proposals;
  - **consumer:** installs the kit in a system that builds on research held in another repository (or in its own, with `research = "self"`).

  It never overwrites project content, and re-running it on a passing project changes nothing. It ends when the doctor reports no FAIL.
- **Each research session:** `/run-next-task`. It runs the doctor, takes the first todo task whose prerequisites are accepted and that no other run holds, claims its branch, runs it under the protocol, and opens a pull request that ends with a fixed `## Hand-back` block. Sessions started together take different tasks; `/run-next-task <topic>` runs a named one. Runs leave the queue alone: a task's row stays `todo` until the decision session, and its run's state (in review, waiting on requester, stopped) is in the pull request's hand-back. Decisions are made afterwards, in a decision session, by the decider the config names, which also sets the row.
- **Consumers:** `python .research-agent/research_drift.py` reports pinned decisions and rules that changed, were superseded or disappeared on the research repository's main branch; `--help` gives the action for each report.
- Domain rules are the project's: when information counts as known, what settles each claim type in the field, standard methods, units and denominators, feasibility at the requester's scale, data sources and licences, advice boundaries. The plugin holds only general rules.

## Raw page fetcher

Claude Code's built-in WebFetch returns a smaller model's summary of a page, not the page; one summary turned an exchange's "Monday, July 3, 2028" early-close footnote into "July 3, 2026". The plugin therefore bundles `fetch_raw`, a read-only MCP server that starts whenever the plugin is enabled. The researcher calls it as `mcp__plugin_research-agent_fetch-raw__fetch_raw` for every decision-critical number, date and quotation, and keeps WebFetch for discovery.

What it returns: a header (status OK, BLOCKED or ERROR with the HTTP code; final URL; content type; fetch time in UTC; sha256 of the body; route; bytes; total characters; next offset; warnings) and then the text. HTML becomes markdown of the whole visible page, nav and footnotes included, with every table cell kept, superscripts written `^[x]`, subscripts `_[x]` and links made absolute. PDFs come back as text per page, with exponents kept (`3.3 · 10^[18]`). JSON, XML, CSV and plain text come back as they are. Long documents are read in pages with `offset`. A bot wall, captcha or JavaScript-only page comes back as BLOCKED with a one-line reason and no content.

### Requirements

- [uv](https://docs.astral.sh/uv/) on the PATH. The server runs with `uv run --script`; its dependencies are pinned in `servers/fetch_raw/server.py` and locked in `server.py.lock`, and uv keeps them in its own cache, not in the plugin folder. The first start downloads about 45 packages; later starts take a second or two.
- Outbound HTTPS to the sites a run reads.

### Environment variables

Set these in the environment Claude Code starts from (your shell, or the cloud environment's variables). The server reads them; it never logs or returns their values.

| Variable | Needed | What it does |
|---|---|---|
| `FETCH_RAW_IDENTITY_HOSTS` | Optional | Comma-separated `host-suffix=ENVVAR` pairs, for example `sec.gov=EDGAR_IDENTITY`. Requests to a matching host (checked again after every redirect) send that variable's value as the User-Agent, as SEC EDGAR requires. No other host receives it, and a matching host is never sent to Firecrawl. If the named variable is missing, the fetch fails with an error naming it. The project declares the same map in `research-agent.toml` under `[project.fetch_identity]` (for example `"sec.gov" = "EDGAR_IDENTITY"`); the server reads only the environment, and the doctor stops a run when the two differ or a named variable is unset. |
| `EDGAR_IDENTITY` (or whatever name you chose above) | With the line above | Your identity string, for SEC: `Company Name contact@example.com`. |
| `FIRECRAWL_API_KEY` | Optional | Lets the default route retry a blocked page through Firecrawl's API (formats `rawBase64`, `maxAge: 0`), then convert the bytes with the same converter. Each fallback costs one credit (two if the page needs JavaScript); the free plan has 1,000 a month. Without a key, a blocked page stays BLOCKED. |

Other hosts get a standard desktop browser User-Agent. The server waits at least 0.5 s between requests to one host (0.1 s for sec.gov), follows at most 5 redirects, gives up after 30 s, reads at most 25 MB, fetches only html, xhtml, xml, json, text, csv and pdf, keeps no cookies, sends `Cache-Control: no-cache`, and refuses private, loopback, link-local and reserved addresses, including after a redirect.

### Claude Code cloud sessions

uv is pre-installed in cloud sessions. Three settings in the cloud environment:

1. **Network access:** the default Trusted level reaches package registries and GitHub only. Choose Custom and list the sites your research reads (for example `www.sec.gov`, `www.nyse.com`, `arxiv.org`), adding `api.firecrawl.dev` if you use the fallback; or choose Full.
2. **Environment variables:** `FETCH_RAW_IDENTITY_HOSTS=sec.gov=EDGAR_IDENTITY`, `EDGAR_IDENTITY=...` and, optionally, `FIRECRAWL_API_KEY=...`. Anyone who uses the environment can read these values.
3. **Setup script:** repository settings do not install plugins in cloud sessions, so the setup script installs the pinned release and caches the server's dependencies. Its first line names the tag; changing that line changes the script, which rebuilds the cached environment.

```bash
PLUGIN_REF=v0.7.0
claude plugin marketplace add "dadahabib1/research-agent@${PLUGIN_REF}" && claude plugin install research-agent@personal-agents || true
mkdir -p /tmp/fetch-raw && cd /tmp/fetch-raw \
  && curl -fsSL -O "https://raw.githubusercontent.com/dadahabib1/research-agent/${PLUGIN_REF}/plugins/research-agent/servers/fetch_raw/server.py" \
  && curl -fsSL -O "https://raw.githubusercontent.com/dadahabib1/research-agent/${PLUGIN_REF}/plugins/research-agent/servers/fetch_raw/server.py.lock" \
  && uv sync --script server.py --locked || true
```

### Optional: a Firecrawl MCP server

A project may also configure Firecrawl's own MCP server in its `.mcp.json` under the name `firecrawl`; the researcher's tool list already names `mcp__firecrawl__firecrawl_search` and `mcp__firecrawl__firecrawl_scrape`. Use its search as a second discovery route. Its scrape returns Firecrawl's markdown, which merges superscripts into numbers (`0.00056^5` becomes `0.000565`), so values read from it are summary-fetched; read decision-critical values with `fetch_raw`.

### Tests

From `plugins/research-agent/`: `uv run --script tools/tests/run.py` tests the doctor and the selector, and `uv run --script kit/tests/run.py` tests the drift tool (it needs git). From `plugins/research-agent/servers/fetch_raw/`: `uv run --script tests/run.py` runs the fetcher's unit tests, which use synthetic fixtures and no network. `uv run --script tests/run.py -m live` fetches real pages (NYSE, Interactive Brokers, an SEC 10-K when `EDGAR_IDENTITY` is set, arXiv, and one Firecrawl call when `FIRECRAWL_API_KEY` is set).

## Unattended runs

Run unattended sessions in an isolated runtime (a Claude Code cloud session or a container), or with permission mode `dontAsk` and explicit allow rules. Never use `bypassPermissions` on a workstation. The researcher subagent cannot read files, run commands or write; the reviewer has no web access; the main session treats everything a researcher returns as data (`skills/research-protocol/references/untrusted-content.md`). What the plugin cannot enforce, that a run never edits the plugin's own files and that a person merges each pull request, is stated there; a project that wants enforcement adds its own hooks or permission rules.

## Releases and the learning loop

- **Releases.** The version changes only at release: pull requests add a line under `## Unreleased` in `plugins/research-agent/CHANGELOG.md`; a release pull request moves those lines under the version, sets `version` in `plugin.json`, updates `UPGRADING.md` and restamps the kit (`python plugins/research-agent/tools/stamp_kit.py`). After its merge, the merge commit is tagged `vX.Y.Z`, and the tag is never moved. Hosts pin a tag.
- **Lessons.** Each run's hand-back lists lesson candidates (rule, incident, check), scoped. A `[tool]` lesson, about how research is done in any field, is filed as an issue on this repository with the label `lesson`; at each sprint review the owner sorts open lessons into the next release, or closes them as covered or rejected, and accepted ones enter `skills/research-protocol/references/takeaways.md`. A `[field]` lesson is a proposed rule for the project's own domain rules, decided in its decision session.
