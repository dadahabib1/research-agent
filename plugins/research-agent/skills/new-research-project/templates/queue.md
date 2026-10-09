# Research queue

Status values: todo, waiting on requester, in review, accepted, rejected, deferred. The decider updates status after each decision session. A task may start only when its prerequisites are accepted. Tasks run in table order: `/run-next-task` takes the first todo row whose prerequisites are all accepted, so the decider orders the rows. Prerequisites name task rows (comma-separated, case ignored) or "none". The five columns below are required; a project may add more.

| Task | Prompt | Deliverable | Prerequisites | Status |
|---|---|---|---|---|
