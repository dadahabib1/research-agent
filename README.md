# research-agent

A Claude Code plugin for evidence-based research projects. It provides a research protocol, a session loop that runs one queued research task per session, and researcher and reviewer subagents.

## Contents

- **Skills:**
  - `research-protocol`;
  - `run-next-task` (invoked as /run-next-task);
  - `new-research-project` (invoked as /new-research-project).
- **Agents:** `researcher` (effort xhigh) and `reviewer` (effort high).

## Install

- **In one project:** add this to the project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "personal-agents": { "source": { "source": "github", "repo": "erimhabib-work/research-agent" } }
  },
  "enabledPlugins": { "research-agent@personal-agents": true }
}
```

- **Manually:** run `/plugin marketplace add erimhabib-work/research-agent`, then `/plugin install research-agent@personal-agents`.
- **For claude.ai chat and Cowork:** zip `plugins/research-agent/skills/research-protocol/` and upload it as a skill.

## Use

- New project: `/new-research-project`.
- Each research session: `/run-next-task`.
