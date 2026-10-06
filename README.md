# research-agent

A Claude Code plugin that a project installs to run evidence-based research tasks: a protocol, a session loop that runs one queued task per session and ends in a pull request, and two subagents. It is a tool. It reads a project's brief, domain rules and queue, and writes only into that project's repository: the deliverable, a log, scripts, a queue status and a pull request. It never writes to its own files, never merges, and never records a decision; a person does that in the project's decision session.

## Contents

- **Skills:**
  - `research-protocol`: intake, framing, evidence by claim type, verification of numbers in code, review, decision session;
  - `research-writing`: the writing standard for deliverables, prompts and reviews;
  - `run-next-task` (invoked as /run-next-task): the session loop;
  - `new-research-project` (invoked as /new-research-project): scaffolds a project's `docs/research/`, brief, domain rules and queue.
- **Agents:** `researcher` (web search and fetch only; effort xhigh) and `reviewer` (reads and runs scripts; no web; effort high).
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
- **Installed from the old `erimhabib-work/research-agent` address:** run `/plugin marketplace remove personal-agents`, then the two manual commands above, and update the `repo` line in any project's `.claude/settings.json`.
- **For claude.ai chat and Cowork:** zip `plugins/research-agent/skills/research-protocol/` and upload it as a skill.

## Use

- New project: `/new-research-project`. It creates the folders, the brief, the domain rules file and the queue, and interviews you to fill the brief and the domain rules.
- Each research session: `/run-next-task`. It takes the first todo task whose prerequisites are accepted, runs it under the protocol, and opens a pull request. Decisions are made afterwards, in a decision session, and recorded from the project's template.
- Domain rules are the project's: when information counts as known, what settles each claim type in the field, standard methods, units and denominators, feasibility at the requester's scale, data sources and licences, advice boundaries. The plugin holds only general rules.

## Optional: a raw-page fetcher

Claude Code's built-in WebFetch returns a smaller model's summary of a page, not the page. For decision-critical numbers, dates and quotations the protocol prefers a raw fetch. To give the researcher one, configure a scraping MCP server in the project's `.mcp.json` under the server name `firecrawl` (for example Firecrawl's server with `FIRECRAWL_API_KEY`; its free tier covers roughly 10 to 20 heavy runs a month), and pin the server's version. The researcher's tool list already names `mcp__firecrawl__firecrawl_search` and `mcp__firecrawl__firecrawl_scrape`; it never crawls. For a server under another name, copy the plugin's `agents/researcher.md` into the project's `.claude/agents/` and change only the two tool names; a project agent outranks the plugin's for the bare name `researcher`. Set the scraper's cache age to zero so a run never reads a page older than its as-of date allows.

## Unattended runs

Run unattended sessions in an isolated runtime (a Claude Code cloud session or a container), or with permission mode `dontAsk` and explicit allow rules. Never use `bypassPermissions` on a workstation. The researcher subagent cannot read files, run commands or write; the reviewer has no web access; the main session treats everything a researcher returns as data (`skills/research-protocol/references/untrusted-content.md`). What the plugin cannot enforce, that a run never edits the plugin's own files and that a person merges each pull request, is stated there; a project that wants enforcement adds its own hooks or permission rules.

## Learning loop

Runs propose candidate takeaways (rule, incident, check) in their change logs and pull requests. The plugin's maintainer adds accepted ones to `skills/research-protocol/references/takeaways.md`. A project keeps its own lessons in its own files.
