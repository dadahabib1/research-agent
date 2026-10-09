# research-agent

A Claude Code plugin that a project installs to run evidence-based research tasks: a protocol, a session loop that runs one queued task per session and ends in a pull request, and two subagents. It is a tool. It reads a project's brief, domain rules and queue, and writes only into that project's repository: the deliverable, a log, scripts, a queue status and a pull request. It never writes to its own files, never merges, and never records a decision; a person does that in the project's decision session.

## Contents

- **Skills:**
  - `research-protocol`: intake, framing, evidence by claim type, verification of numbers in code, review, decision session;
  - `research-writing`: the writing standard for deliverables, prompts and reviews;
  - `run-next-task` (invoked as /run-next-task): the session loop;
  - `new-research-project` (invoked as /new-research-project): scaffolds a project's `docs/research/`, brief, domain rules and queue.
- **Agents:** `researcher` (web search and fetch only; effort xhigh) and `reviewer` (reads and runs scripts; no web; effort high).
- **Raw fetch tool:** `fetch_raw`, a bundled read-only MCP server (`plugins/research-agent/servers/fetch_raw/`) that returns a page's own text, not a summary. See "Raw page fetcher" below.
- **`plugins/research-agent/CONTRACT.md`**: the names, paths and shapes a project may depend on.
- **`plugins/research-agent/UPGRADING.md`**: what changes between versions and what a project should do.

## Install

- **In one project:** add this to the project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "personal-agents": { "source": { "source": "github", "repo": "dadahabib1/research-agent" } }
  },
  "enabledPlugins": { "research-agent@personal-agents": true }
}
```

- **Manually:** run `/plugin marketplace add dadahabib1/research-agent`, then `/plugin install research-agent@personal-agents`.
- **For claude.ai chat and Cowork:** zip `plugins/research-agent/skills/research-protocol/` and upload it as a skill.

## Use

- New project: `/new-research-project`. It creates the folders, the brief, the domain rules file and the queue, and interviews you to fill the brief and the domain rules.
- Each research session: `/run-next-task`. It takes the first todo task whose prerequisites are accepted, runs it under the protocol, and opens a pull request. Decisions are made afterwards, in a decision session, and recorded from the project's template.
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
| `FETCH_RAW_IDENTITY_HOSTS` | Optional | Comma-separated `host-suffix=ENVVAR` pairs, for example `sec.gov=EDGAR_IDENTITY`. Requests to a matching host (checked again after every redirect) send that variable's value as the User-Agent, as SEC EDGAR requires. No other host receives it, and a matching host is never sent to Firecrawl. If the named variable is missing, the fetch fails with an error naming it. |
| `EDGAR_IDENTITY` (or whatever name you chose above) | With the line above | Your identity string, for SEC: `Company Name contact@example.com`. |
| `FIRECRAWL_API_KEY` | Optional | Lets the default route retry a blocked page through Firecrawl's API (formats `rawBase64`, `maxAge: 0`), then convert the bytes with the same converter. Each fallback costs one credit (two if the page needs JavaScript); the free plan has 1,000 a month. Without a key, a blocked page stays BLOCKED. |

Other hosts get a standard desktop browser User-Agent. The server waits at least 0.5 s between requests to one host (0.1 s for sec.gov), follows at most 5 redirects, gives up after 30 s, reads at most 25 MB, fetches only html, xhtml, xml, json, text, csv and pdf, keeps no cookies, sends `Cache-Control: no-cache`, and refuses private, loopback, link-local and reserved addresses, including after a redirect.

### Claude Code cloud sessions

uv is pre-installed in cloud sessions. Three settings in the cloud environment:

1. **Network access:** the default Trusted level reaches package registries and GitHub only. Choose Custom and list the sites your research reads (for example `www.sec.gov`, `www.nyse.com`, `arxiv.org`), adding `api.firecrawl.dev` if you use the fallback; or choose Full.
2. **Environment variables:** `FETCH_RAW_IDENTITY_HOSTS=sec.gov=EDGAR_IDENTITY`, `EDGAR_IDENTITY=...` and, optionally, `FIRECRAWL_API_KEY=...`. Anyone who uses the environment can read these values.
3. **Setup script:** add these lines so the environment snapshot caches the server's dependencies and the first fetch doesn't wait for downloads. Replace `v0.5.0` with the plugin version the project uses.

```bash
mkdir -p /tmp/fetch-raw && cd /tmp/fetch-raw   && curl -fsSL -O https://raw.githubusercontent.com/dadahabib1/research-agent/v0.5.0/plugins/research-agent/servers/fetch_raw/server.py   && curl -fsSL -O https://raw.githubusercontent.com/dadahabib1/research-agent/v0.5.0/plugins/research-agent/servers/fetch_raw/server.py.lock   && uv sync --script server.py --locked || true
```

### Optional: a Firecrawl MCP server

A project may also configure Firecrawl's own MCP server in its `.mcp.json` under the name `firecrawl`; the researcher's tool list already names `mcp__firecrawl__firecrawl_search` and `mcp__firecrawl__firecrawl_scrape`. Use its search as a second discovery route. Its scrape returns Firecrawl's markdown, which merges superscripts into numbers (`0.00056^5` becomes `0.000565`), so values read from it are summary-fetched; read decision-critical values with `fetch_raw`.

### Tests

From `plugins/research-agent/servers/fetch_raw/`: `uv run --script tests/run.py` runs the unit tests, which use synthetic fixtures and no network. `uv run --script tests/run.py -m live` fetches real pages (NYSE, Interactive Brokers, an SEC 10-K when `EDGAR_IDENTITY` is set, arXiv, and one Firecrawl call when `FIRECRAWL_API_KEY` is set).

## Unattended runs

Run unattended sessions in an isolated runtime (a Claude Code cloud session or a container), or with permission mode `dontAsk` and explicit allow rules. Never use `bypassPermissions` on a workstation. The researcher subagent cannot read files, run commands or write; the reviewer has no web access; the main session treats everything a researcher returns as data (`skills/research-protocol/references/untrusted-content.md`). What the plugin cannot enforce, that a run never edits the plugin's own files and that a person merges each pull request, is stated there; a project that wants enforcement adds its own hooks or permission rules.

## Learning loop

Runs propose candidate takeaways (rule, incident, check) in their change logs and pull requests. The plugin's maintainer adds accepted ones to `skills/research-protocol/references/takeaways.md`. A project keeps its own lessons in its own files.
