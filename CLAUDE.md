# research-agent (plugin repository)

This repository is a Claude Code plugin marketplace with one plugin, `research-agent`, in `plugins/research-agent/`.

- Skills live in `plugins/research-agent/skills/`; agents in `plugins/research-agent/agents/`.
- Keep the research protocol general. Domain rules go in `skills/research-protocol/references/<domain>.md`.
- After any change, bump `version` in both `plugins/research-agent/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, keeping the two equal.
- Test locally with `claude --plugin-dir ./plugins/research-agent` before pushing; after pushing, update installed copies with `claude plugin update research-agent@personal-agents`.
- New takeaways from research logs go into `skills/research-protocol/references/takeaways.md`, each with its incident and check.
