# Decision record: first topic

## Decisions

### first-choice: use the first option

```yaml
name: first-choice
status: accepted
decided: 2026-10-02
decided_by: requester
depends_on: []
supersedes: [older-choice]
parameters:
  - {name: limit, value: 30, unit: "seconds, per request", source: "first-topic.md §2"}
```

- **Status:** accepted
- **Decision:** The system must use the first option.

### older-choice: use the old option

```yaml
name: older-choice
status: superseded
decided: 2026-09-01
decided_by: requester
depends_on: []
supersedes: "the draft in first-topic.md §1"
parameters: []
```

- **Status:** superseded

## Rejected and deferred decisions

- none
