# Research queue

Status values: todo, waiting on requester, in review, accepted, rejected, deferred. Whoever adds a task writes todo; the decision session writes accepted, rejected or deferred. Runs never edit this file, so a row stays todo while its run is open: the run's state (running, in review, waiting on requester, stopped) is in its pull request's hand-back. A task may start only when its prerequisites are accepted. Tasks run in table order: `/run-next-task` takes the first todo row whose prerequisites are all accepted and that has no run in progress, in review, waiting or merged (the plugin's CONTRACT.md, "The queue"), so the decider orders the rows. Prerequisites name task rows (comma-separated, case ignored) or "none". The five columns below are required; a project may add more.

| Task | Prompt | Deliverable | Prerequisites | Status |
|---|---|---|---|---|
