# Research queue (docs/research/research-queue.md)

Status values: todo, waiting on requester, in review, accepted, rejected, deferred. The user updates status after each grilling session. A task may start only when its prerequisites are accepted.

Requested by names the requester, or the app's issue or ticket for a request from the app. Blocks names what in the app waits for the task, or none.

| Task | Prompt | Deliverable | Prerequisites | Requested by | Blocks | Status |
|---|---|---|---|---|---|---|
| System review v1 | prompts/07-system-review-v1.md | system-review-v1.md | none | app orchestrator (v2 planning, 2026-10-05) | v2 spec (not yet written) | todo |
| Real-data corpus | prompts/08-real-data-corpus.md | real-data-corpus.md | none | app orchestrator (v2 planning, 2026-10-05) | none | todo |
| Reference inputs | prompts/09-reference-inputs.md | reference-inputs.md | none | app orchestrator (v2 planning, 2026-10-05) | v2 spec (not yet written) | todo |
| Business-model templates | prompts/10-business-model-templates.md | business-model-templates.md | system review v1 | app orchestrator (v2 planning, 2026-10-05) | v2 spec (not yet written) | todo |
| Fund layer | prompts/01-fund-layer.md | fund-layer.md | none | requester | none | todo |
| Validation ladder | prompts/02-validation-ladder.md | validation-ladder.md | none | requester | none | todo |
| Earnings updates and scoring | prompts/11-earnings-update-workflow.md | earnings-update-workflow.md | validation ladder | app orchestrator (v2 planning, 2026-10-05) | v2 spec (not yet written) | todo |
| Industries and peers | prompts/12-industries-and-peers.md | industries-and-peers.md | business-model templates | app orchestrator (v2 planning, 2026-10-05) | v2 spec (not yet written) | todo |
| Coverage screen | prompts/13-coverage-screen.md | coverage-screen.md | business-model templates | app orchestrator (v2 planning, 2026-10-05) | v2 spec (not yet written) | todo |
| Rule families | prompts/03-rule-families.md | rule-families.md | fund layer, validation ladder | requester | none | todo |
| Account shape | prompts/04-account-shape.md | account-shape.md | fund layer, rule families | requester | none | todo |
| Sentiment pass 1 | prompts/05-sentiment-methodology.md | sentiment-methodology.md | validation ladder | requester | none | todo |
| Sentiment pass 2 | prompts/06-sentiment-data.md | sentiment-data-protocol.md | sentiment pass 1 | requester | none | todo |
