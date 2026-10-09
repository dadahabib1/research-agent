# Decision index

Every decision in this folder, one row each, so an agent can find one by name without opening every record. The decision session updates this table in the same pull request that adds or changes a decision record. Each decision's `yaml` header block is the authority; this table points to it, and the doctor checks that each row's name and status match its header.

| Decision | Status | Decided | Record | Supersedes |
|---|---|---|---|---|
