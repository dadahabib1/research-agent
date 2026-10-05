---
name: new-research-project
description: Set up a research program in a repository (folders, brief, queue and prompt templates, and the CLAUDE.md pointer), then fill the brief through an intake interview. Use when starting a new research project or adding a research program to an existing repository.
---

# New research project

1. **Scaffold.** Create `docs/research/` with `prompts/`, `logs/` and `decisions/`. Copy `templates/brief.md` to `docs/research/strategy-research-brief.md` (or a name the requester chooses), and `templates/queue.md` to `docs/research/research-queue.md`.
   Done when the folders and both files exist.
2. **Point.** Add a "Research" section to the repository's `CLAUDE.md`. List the brief, queue, prompts, logs and decisions paths, and add the line "To run the next research task, use /run-next-task."
   Done when `CLAUDE.md` names every path.
3. **Fill the brief.** Interview the requester using the research-protocol skill's intake and questioning references, and write the answers into the brief's sections. Mark every assumption.
   Done when every brief section is filled or marked as an open input.
4. **Write the first prompts.** For each research topic the requester names:
   - copy `templates/prompt.md` to `prompts/NN-<topic>.md`;
   - fill it in following `research-protocol/references/prompt-writing.md`;
   - add a queue row with its prerequisites.

   Done when every named topic has a prompt and a queue row.

Templates for logs (`templates/log.md`) and decision records (`templates/decision-record.md`) are used by `/run-next-task` and by decision sessions.
