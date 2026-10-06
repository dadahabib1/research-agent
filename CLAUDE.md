# research-agent (plugin repository)

This repository is a Claude Code plugin marketplace with one plugin, `research-agent`, in `plugins/research-agent/`. The plugin is a tool a project installs; it writes only into that project's repository, never into this one.

- Skills live in `plugins/research-agent/skills/`; agents in `plugins/research-agent/agents/`.
- Keep the research protocol general. Domain rules belong to the consuming project, written from `skills/new-research-project/templates/domain-rules.md` and pointed to by its brief §6; the plugin holds only general rules.
- `plugins/research-agent/CONTRACT.md` lists the names, paths and shapes consumers depend on. Changing any of them bumps the minor version and is recorded in that file's "Changes to the contract".
- After any change under `plugins/research-agent/`, bump `version` in both `plugins/research-agent/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, keeping the two equal. Changes outside the plugin directory (this file, the root README) need no bump; installing projects never load them.
- Test locally with `claude plugin validate ./plugins/research-agent` and `claude --plugin-dir ./plugins/research-agent` before pushing; after merging, refresh this machine's copy with `claude plugin marketplace update personal-agents`, then `/reload-plugins` in open sessions. The plugin is a relative-path plugin enabled through project settings, so it has no install record and `claude plugin update` does not apply.
- Takeaways: runs propose candidates in their change logs and pull requests; a maintainer adds accepted ones to `skills/research-protocol/references/takeaways.md`, each with its incident and check, after checking that no existing entry already covers the rule.
