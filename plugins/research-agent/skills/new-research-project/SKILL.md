---
name: new-research-project
description: Set up research-agent in a repository and check it with the doctor. Three modes, detected from the repository - new (a fresh research program - config, brief, domain rules, queue and the intake interview that fills them), adopt (an existing research program, or an upgrade to this plugin version) and consumer (install the consumer kit in a system that builds on research held elsewhere). Safe to re-run. Use when starting or adopting a research project, upgrading the plugin, or connecting a consumer.
allowed-tools: Bash(uv run --script ${CLAUDE_PLUGIN_ROOT}/tools/doctor.py *), Bash(mkdir -p .research-agent), Bash(cp ${CLAUDE_PLUGIN_ROOT}/kit/INTEGRATION.md ${CLAUDE_PLUGIN_ROOT}/kit/research_drift.py .research-agent/)
---

# Set up research-agent

The contract is `${CLAUDE_PLUGIN_ROOT}/CONTRACT.md`: the config schema, the fixed layout and every format named below. Templates are in `${CLAUDE_PLUGIN_ROOT}/skills/new-research-project/templates/`. The plugin's version is `version` in `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`.

**Writes.** Every write is "create if missing; otherwise compare and report". Never overwrite project content, never delete a file, never edit an accepted decision record. Changes to an existing file (the `CLAUDE.md` pointer, `.gitignore` lines, settings, a new `requires`) are listed first and made only after the host or user confirms. Leave everything in the working tree; the host commits it its usual way. A second run on a project that passed the doctor changes nothing.

## Steps

1. **Detect the mode.** Run `uv run --script ${CLAUDE_PLUGIN_ROOT}/tools/doctor.py --mode setup` at the repository root and read its `config:` line and check 1:
   - **new:** no `research-agent.toml` and no research files (check 1 FAIL: no config and no "Research" section);
   - **adopt:** research files exist with no config (check 1 DEPRECATED), or a config whose `requires` excludes this plugin version (check 1 FAIL on the range). Upgrading is adopt on a project that has a config;
   - **consumer:** ask whether this repository builds on decisions from research held in another repository. If yes, consumer mode runs as well, alone or after new or adopt. A repository that runs research and builds on it itself gets `[consumes] research = "self"` and the kit, after new mode.
   - A config that passes and needs no consumer change: nothing to set up; report the doctor's result and end.

   State the mode and the files it will write, then wait for the host or user to confirm.

2. **Write, by mode.**
   - **new:**
     - `research-agent.toml` from `templates/research-agent.toml`, with only the tables that apply. `requires = ">=<version>, <0.<minor+1>.0"` for this plugin version. `root` defaults to `docs/research`.
     - Under `root`: the brief (`templates/brief.md`, named by `brief`, default `research-brief.md`), `domain-rules.md` (`templates/domain-rules.md`), `research-queue.md` (`templates/queue.md`), `templates/prompt.md` (a copy, so prompts can be filled from a file on disk), `prompts/`, `logs/` (with a `.gitkeep`), `decisions/INDEX.md` (`templates/decision-index.md`), and `decisions/` gets no other file. Write the brief's §6 line as ``Domain rules: `<root>/domain-rules.md` ``.
     - The consumer context file (`templates/consumer-context.md`, at `root`/`context`) when a consumer is named.
     - `.github/pull_request_template.md` from `templates/pull-request.md`, unless the repository already has one.
     - `.gitignore` lines `__pycache__/` and `*.pyc`.
     - A "Research" section in `CLAUDE.md`: "Research config: `research-agent.toml` (research-agent plugin; the contract is the plugin's CONTRACT.md). To run the next research task, use /run-next-task." Paths are not repeated there.
     - Pinned enablement in `.claude/settings.json`: `extraKnownMarketplaces` entry `"personal-agents": {"source": {"source": "github", "repo": "dadahabib1/research-agent", "ref": "v<version>"}}` and `enabledPlugins` `"research-agent@personal-agents": true`, merged into any existing file.
   - **adopt without a config:** a `research-agent.toml` that matches the existing files: `root`, `brief` and the context file from the `CLAUDE.md` "Research" section and the files themselves; `decider` and `env` from the brief, the domain rules and the requester; `[project.fetch_identity]` from the domain rules' identity rule, if one names a host and a variable. Replace the prose paths in `CLAUDE.md` with the pointer, keeping every rule that is the project's own. Then every file new mode writes that is missing, such as `templates/prompt.md`, `.gitignore` lines and the pull request template.
   - **adopt with a config (upgrade):** the new `requires`, the pinned `ref`, the mechanical steps in `${CLAUDE_PLUGIN_ROOT}/UPGRADING.md` for each version crossed, any missing file new mode writes, and the kit copied again where its stamp is older (see consumer).
   - **adopt, both cases:** list as proposals, not edits, the content changes the contract asks for (for example domain rules as bullets to convert to rule IDs, DEPRECATED items from the doctor) and the steps only a person can take (setting environment variables, the cloud setup script's `PLUGIN_REF`).
   - **consumer:**
     - A `[consumes]` table: `research = "<owner/repo>"` (or `"self"`), and `clone` only when the clone is not at `../<repo name>`.
     - The kit: `mkdir -p .research-agent`, then `cp ${CLAUDE_PLUGIN_ROOT}/kit/INTEGRATION.md ${CLAUDE_PLUGIN_ROOT}/kit/research_drift.py .research-agent/`. Copy with `cp`, never by rewriting, so the stamps match. Replace an existing kit file only when the doctor reports its stamp's version outside `requires` and no local edit; report a local edit instead.
     - `docs/research-lock.md` from `templates/research-lock.md`, if missing; if it exists without a "Pinned rules" table, add the empty table.
     - The `CLAUDE.md` pointer: "Research: this repository builds on `<owner/repo>` (`research-agent.toml`); how to consume it: `.research-agent/INTEGRATION.md`."

   Done when every file the mode writes exists, and every confirmed change is made.

3. **Fill the brief and the domain rules** (new mode, or adopt where they are empty). Run the interview through whoever invoked this skill:
   - **A host agent** answers each question from what its own system records, and the answer is labelled `[PROVIDED: project]` with its source and date. The host passes to its user only what it cannot answer: decisions, and facts about the requester.
   - **A person** is interviewed directly, using the research-protocol skill's `references/intake.md` and `references/questioning.md`.
   - Ask each question once; never ask the host and then the user. Record each answer's source (requester, `[PROVIDED: project]`, looked up, or assumption) as `intake.md` does for runs.
   - For the domain rules, work through the eight headings: look up what can be looked up (the field's standard methods, its data sources and their licences, its timestamp conventions) and propose each as a recommended answer; ask only for decisions and facts about the requester's situation. Write each rule in the rule format with an ID, Check, Scope, Source and Added; replace the ILLUSTRATIVE examples; write "none known" under a heading with no rule.

   Done when every brief section and every domain-rules heading is filled or marked as an open input.

4. **Write the first prompts.** For each research topic the requester names, copy `<root>/templates/prompt.md` to `prompts/NN-<topic>.md`, fill it following `research-protocol/references/prompt-writing.md` (with its `Shape:` line, and the IDs of the domain rules that apply), and add a queue row with its prerequisites.
   Done when every named topic has a prompt and a queue row.

5. **Check.** Run `uv run --script ${CLAUDE_PLUGIN_ROOT}/tools/doctor.py --mode setup`. Fix each FAIL that this setup caused; report the rest, with each WARN and DEPRECATED item, to the host or user.
   Done when the doctor reports no FAIL.
