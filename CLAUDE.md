# research-agent (plugin repository)

This repository is a Claude Code plugin marketplace with one plugin, `research-agent`, in `plugins/research-agent/`. The plugin is a tool a project installs; it writes only into that project's repository, never into this one.

- Skills live in `plugins/research-agent/skills/`; agents in `plugins/research-agent/agents/`.
- Keep the research protocol general. Domain rules belong to the consuming project, written from `skills/new-research-project/templates/domain-rules.md` and pointed to by its brief §6; the plugin holds only general rules.
- `plugins/research-agent/CONTRACT.md` lists the names, paths and shapes consumers depend on. Changing any of them bumps the minor version and is recorded in that file's "Changes to the contract".
- After any change, bump `version` in both `plugins/research-agent/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, keeping the two equal.
- Test locally with `claude plugin validate ./plugins/research-agent` and `claude --plugin-dir ./plugins/research-agent` before pushing; after pushing, update installed copies with `claude plugin update research-agent@personal-agents`.
- Takeaways: runs propose candidates in their change logs and pull requests; a maintainer adds accepted ones to `skills/research-protocol/references/takeaways.md`, each with its incident and check, after checking that no existing entry already covers the rule.
