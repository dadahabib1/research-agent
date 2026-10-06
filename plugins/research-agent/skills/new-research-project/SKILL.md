---
name: new-research-project
description: Set up a research program in a repository (folders, brief, domain rules, queue and prompt templates, and the CLAUDE.md pointer), then fill the brief and the domain rules through an intake interview. Use when starting a new research project or adding a research program to an existing repository.
---

# New research project

1. **Scaffold.** Create `docs/research/` with `prompts/`, `logs/` and `decisions/`. Copy `templates/brief.md` to `docs/research/strategy-research-brief.md` (or a name the requester chooses), `templates/domain-rules.md` to `docs/research/domain-rules.md`, and `templates/queue.md` to `docs/research/research-queue.md`.
   Done when the folders and the three files exist.
2. **Point.** Add a "Research" section to the repository's `CLAUDE.md`. List the brief, domain rules, queue, prompts, logs and decisions paths, and add the line "To run the next research task, use /run-next-task."
   Done when `CLAUDE.md` names every path.
3. **Fill the brief and the domain rules.** Interview the requester using the research-protocol skill's intake and questioning references, and write the answers into the brief's sections. Then work through the eight headings of the domain rules file: look up what can be looked up (the field's standard methods, its data sources and their licences, its timestamp conventions) and propose each as a recommended answer; ask the requester only for decisions and for facts about their situation. Mark every assumption, and write "none known" under a heading rather than delete it.
   Done when every brief section and every domain-rules heading is filled or marked as an open input.
4. **Write the first prompts.** For each research topic the requester names:
   - copy `templates/prompt.md` to `prompts/NN-<topic>.md`;
   - fill it in following `research-protocol/references/prompt-writing.md`, including its `Shape:` line;
   - add a queue row with its prerequisites.

   Done when every named topic has a prompt and a queue row.

Templates for logs (`templates/log.md`) and decision records (`templates/decision-record.md`) are used by `/run-next-task` and by decision sessions.
