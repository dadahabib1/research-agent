<!-- research-agent 0.6.2 sha256:713af51563d2f867b86e2ab56c222d82940a85fa0e7c2f3acb18e391666fcbf5 -->
# Adopting research-agent (contract 0.6)

research-agent runs research projects: questions that need cited evidence and checked numbers before someone decides, answered under a fixed protocol that ends in a pull request and a decision session. Use it for those; answer quick lookups yourself.

1. **Set up.** Enable the plugin pinned to a `v0.6.x` tag and run `/new-research-project` in the repository that will hold the research, or, if your research lives in another repository, in your own to install this kit. Answer its questions from what your system already records, labelled `[PROVIDED: project]`, and ask your user the rest. Done when its doctor reports no FAIL and setup's changes are merged into the default branch.
2. **Add a task.** Fill a prompt from `templates/prompt.md` and add a row to `research-queue.md`, both under the `root` that `research-agent.toml` names, the way you make any other change to that repository. Your other changes there are the consumer context file; deliverables, logs and decision records change only through runs and decision sessions.
3. **Run it.** `/run-next-task`, in the foreground, a background agent or a cloud session; one task per session.
4. **Read the hand-back.** The run's pull request ends with a `## Hand-back` block: status, answer, proposed decisions, open items, flagged content, lesson candidates, spend, paths, plugin version. Proposed decisions are proposals: the decider accepts, rejects or defers them in a decision session, and you build only on decision records marked `accepted` on the research repository's main branch.
5. **Keep it current.**
   - **Pins.** When your work starts relying on an accepted decision, or on a domain rule whose `Host:` names you, add it to `docs/research-lock.md` with the hash from `.research-agent/research_drift.py --hash`. Run `.research-agent/research_drift.py` at startup and before writing a spec; `--help` gives the action for each report.
   - **Context.** Keep the consumer context file true to what your system can do today.
   - **Lessons.** File each `[tool]` lesson candidate as an issue on the plugin's repository with the label `lesson`. That repository is public and serves every project, so first check that the candidate reads without your project's files and names nothing from it; reword it in field-neutral words where it does not. `[field]` candidates reach the domain rules through the decision session.
