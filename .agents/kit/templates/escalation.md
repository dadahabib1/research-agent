---
format: escalation
version: 1
id: <filled by the script: escalation-<UTC>-t<n>-<head, 7 hex>-<4 hex>>
ticket: <n>
trigger: <round-cap, needs-decision, paid-or-key, approach, high-stakes or blocked>
headline: t<n> needs you: <the choice, under 80 characters>
by: <filled by the script: review.py or escalate.py>
review: <the review id, or none>
round: <the review round, or 0>
head: <the ticket's head>
verdict: <the verdict path, or none>
holds: <the tickets it stops: itself and those stacked on it or sharing its files or external state>
answers: fix, defer, known-limitation, ask-research, cancel
written_at: <filled by the script>
---
## The choice

<One paragraph: what the user decides.>

## Findings

<For round-cap: each persistent finding, the fix tried per round, the likely root cause. Otherwise what
led here.>

## Options

<Each answer, its cost, what follows.>

## Recommendation

<The answer you recommend, with its reason.>
