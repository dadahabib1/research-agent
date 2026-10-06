# Upgrading

What changes for a project between plugin versions, and what to do about it. `CONTRACT.md` lists what stays fixed within a minor version.

## 0.3.x to 0.4.0

Nothing a project depends on breaks: skill names, queue statuses and columns, the decision-record heading and field names, brief section numbers, the log path, the branch name and the cited headings are unchanged. One behaviour changed: `/run-next-task` now takes the first `todo` row in table order whose prerequisites are accepted (0.3.x took the lowest-numbered prompt). Order your queue rows.

What to do in the project:

1. **Domain rules.** The plugin no longer ships field-specific rules. Write yours from `skills/new-research-project/templates/domain-rules.md` (eight headings: when information counts as known; what settles each claim type; standard methods; units and denominators; feasibility at scale; data sources and licences; advice boundaries; domain words), save the file in `docs/research/`, and point to it from the brief's §6 under a "Domain rules" line. If your brief §6 already restates such rules, move them into that file and leave the pointer.
2. **Prompts.** Add `Shape: new research | revision | clarification` and, where the defaults do not apply, `Run settings: <model>, effort <level>` near the top of each prompt and of any prompt templates of your own. A prompt without `Shape:` runs as new research.
3. **Decision records.** Your template copy may add the optional field `- **Reopen when:**` and the new `Evidence:` values (claim type; `n/a: measured`; `n/a: documented`). Do not edit accepted records to add them; a changed record is a new record.
4. **Logs.** Logs written from now on carry new sections (Frame and plan, Flagged content, Self-review, Review findings, Spend), and researcher returns are kept as `logs/<topic>-notes-<n>.md`. Nothing to change in existing logs.
5. **Pull requests.** Expect new sections in the PR body: Flagged content, Candidate takeaways, Spend. If you keep a PR template, add them.
6. **Raw-page fetcher (optional).** See the README, "Optional: a raw-page fetcher".
7. **Unattended runs.** See the README, "Unattended runs". Protect the default branch so a run cannot merge.

What changed inside the plugin, for context: the researcher subagent is web-only (no file reads, no shell, no writes); the reviewer has no web access and receives the researcher's newer-edition and contrary-evidence sweep; evidence is stated by claim type (literature grades A to D; measurements with sample and script; documented facts at a version or date; judgments) instead of one letter scale; the `[PROVIDED]` label marks facts the requester or the project supplied; runs propose takeaways rather than writing them; `references/finance.md` was removed, and `references/searching.md` and `references/untrusted-content.md` were added.
