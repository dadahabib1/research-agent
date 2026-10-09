# Prompt: earnings-update workflow and scoring research

You are the researcher for a personal US equity research app, equity_analyst. Your job is to design what the app does when a company reports a new quarter (what triggers a new analysis, what is re-estimated and what is kept), and how the app scores its past verdicts and assumptions so that accuracy can be measured. The requester decides in a decision session; the app's orchestrator builds only on the accepted decision records on main, and pins each one it uses in its lock file.

Read `docs/research/strategy-research-brief.md` first. It holds the situation, settled decisions, standards and deliverable format; this prompt adds only the topic.

## Why the app needs this

- **Asked by:** the app's v2 planning (the requester and the app's orchestrator, 2026-10-05). The brief's version plan puts "the earnings-update workflow" in v2, and the app's first principle (ADR 0001) is that accuracy is the goal, which needs scoring.
- **Blocks:** the v2 spec's update and scoring tickets (not yet written).
- **Needed by:** no date.

## What the app does today

- **Behaviour:**
  - An analysis runs as of one date. A run reads with Claude only the earnings releases not stored yet since the base year ended; a stored release is never read again (`app-context.md`).
  - Every run saves an append-only analysis record and a paper trade (verdict, price, price source and date). Each assumption record has the research's fields (name, proposed value, evidence, analogue rule hash and N, uncertainty, user value and reason); the app's spec says "a later score (outcome, score) is a new row linked to the assumption, never an edit", but nothing computes scores yet.
  - Existing checks that bear on updates: `STALE_INPUT`, `PRICE_LAG`, `PHASE_STALE`. The thesis-break measure for RRX: break if the trailing-four-quarter adjusted EBITDA margin is below 21.05% at two consecutive 2027 quarter-ends while trailing organic growth is at least 3% (decision `thesis-break-band-midpoint`).
  - Catch-up: the value gap's half-life h is estimated per stock from its catalyst (RRX: 1.5 years, catalyst "cycle turn"); the share of the gap closed over the horizon H = 3 years is 1 − 2^(−H/h).
- **Pinned by:** the app's record tests (a saved analysis reloads to identical outputs; an edit attempt fails; paper trades list every verdict with its price and date) and its thesis-break and catch-up tests (band 0.2105).
- **Data and constraints:** `docs/research/app-context.md`; accepted decisions `known-from-rule`, `flags-by-provenance` (accuracy is reported as-known, primary, and cleaned, diagnostic) and `thesis-break-band-midpoint`.

## The question

When a new quarter arrives, what should the app re-run, and how should it score what it said before? Hypotheses: a new 10-Q, 10-K or earnings 8-K (item 2.02) triggers an update; the update re-estimates only assumptions whose evidence changed and keeps the rest with their age shown; a paper trade is scored by its return against a stated benchmark over the horizon H, and an assumption by its error against the later reported value; scores use as-known data only.

## What the app needs back

| Proposed decision name | Question it answers | Parameters expected, with units | Accepted decisions it touches |
|---|---|---|---|
| `update-triggers` | Which events start a new analysis of a covered company | per trigger: source and detection lag (hours) | `known-from-rule` |
| `update-scope` | What an update re-estimates and what it keeps | per assumption: re-estimate or keep, with the evidence age limit (days) | `thesis-break-band-midpoint` |
| `paper-trade-scoring` | How a past verdict is scored | horizon (years), benchmark, metric | `flags-by-provenance` |
| `assumption-scoring` | How a past assumption is scored against what was later reported | error metric, unit | `flags-by-provenance` |
| `update-cost-budget` | What an update may cost | dollars per company-quarter | none |

- **Fixture format:** a Python script with assertions: one RRX update worked through from its Q1 2026 report to its Q2 2026 report, released 2026-08-05 (which fields change, which assumptions are re-estimated), and one scoring example with exact inputs and output, saved in `docs/research/`.
- **Reference case:** RRX, analysed as of the day its Q1 2026 report became public and updated when its Q2 2026 report did (2026-08-05); the app's own case is valued 2026-09-30.
- **What the app must add:** list it in the deliverable (brief §7). Known gaps: a scheduler that polls for new filings; a scorer.

## Technical evidence

For filing detection: compare SEC's submissions API, its RSS feeds and full-text search for latency, rate limits and reliability, and check what edgartools offers (current filings, 8-K item codes), with scripts run on real recent filings and their measured delay between acceptance and availability. Cite official documentation at a pinned version; mark an untested claim [UNVERIFIED]. Add a section **Existing tools and prior art**: open-source approaches to paper-trade and forecast scoring. SEC requests use the `EDGAR_IDENTITY` environment variable, at most 10 a second.

## Leading words

- **Update:** a new analysis of a covered company when new evidence arrives, saved as a new record linked to the previous one.
- **Score:** a later row that measures a past verdict or assumption against what happened, never an edit of it.

## Known issues

- The validation ladder (`prompts/02-validation-ladder.md`, a prerequisite) decides how strong a scored record must be; this request only defines the scores.
- One company gives few scored events per year; the deliverable should say how many are needed before a score means anything.

## Steps

### 1. Read

Read the brief, `app-context.md`, the validation ladder deliverable (`validation-ladder.md`), `investment-methodology.md` (the accuracy metric of each component), and the decision records named above.

Done when you can state, in three sentences, what an analysis record holds, what the validation ladder requires of evidence, and what nothing scores today.

### 2. Triggers and scope

Define the triggers and what an update re-estimates, worked on RRX's Q2 2026 report.

Done when every assumption in the RRX case has a re-estimate-or-keep rule, and every trigger has its detection method and measured lag.

### 3. Scoring

Define the verdict and assumption scores, their horizon and benchmark, and how many scored events a meaningful accuracy figure needs.

Done when each score has an exact worked example and its minimum sample.

### 4. Write the deliverable

Write `docs/research/earnings-update-workflow.md` in the brief's format (§7), with **Existing tools and prior art** and **What the app must add**.

Done when the brief's done-criterion is met and every decision in "What the app needs back" is proposed, deferred with a reason, or shown to be unnecessary.

Standards: brief §6, plus "Technical evidence" above.
