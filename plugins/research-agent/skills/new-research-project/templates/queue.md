# Research queue

Status values: todo, waiting on requester, in review, accepted, rejected, deferred. The requester updates status after each decision session. A task may start only when its prerequisites are accepted. Tasks run in table order: `/run-next-task` takes the first todo row whose prerequisites are all accepted, so the requester orders the rows.

| Task | Prompt | Deliverable | Prerequisites | Status |
|---|---|---|---|---|
