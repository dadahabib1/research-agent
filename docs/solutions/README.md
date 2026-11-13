# Lessons

This folder is the project's lasting memory: one Markdown lesson file per solved problem worth keeping, at
`<category>/<name>.md`, with the front matter the `ce-compound` skill defines in
`.claude/skills/ce-compound/references/schema.yaml` (its track, category, module and the paths it cites). A
builder writes at most one per ticket, with `/ce-compound mode:non-interactive depth:lightweight` after its tests
pass and before READY, and commits it in the ticket's diff, so the review checks each claim against the code it
cites. Every 10 merges the orchestrator files a refresh ticket, whose builder audits the whole folder with
`/ce-compound mode:refresh mode:non-interactive`: each lesson kept, updated, consolidated, replaced or deleted
against the current code. Nothing here loads at a session's start; a brief's `lessons:` line names the files that
touch its ticket. A lesson that keeps coming back is promoted by hand into a skill or an instruction file. This
README is the kit's (kit updates change it); the lesson files are yours.
