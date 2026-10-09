# Prompt: coverage screen research

You are the researcher for a personal US equity research app, equity_analyst. Your job is to design the code-only screen that runs over a broad universe of US-listed companies and chooses the about 20 names that get full reports, with the events that trigger a report, cheaply and without look-ahead or survivorship bias. The requester decides in a decision session; the app's orchestrator builds only on the accepted decision records on main, and pins each one it uses in its lock file.

Read `docs/research/strategy-research-brief.md` first. It holds the situation, settled decisions, standards and deliverable format; this prompt adds only the topic.

## Why the app needs this

- **Asked by:** the app's v2 planning (the requester and the app's orchestrator, 2026-10-05). The brief's settled coverage decision (§3): "a code-only screen over a broad universe; full Claude reports on about 20 names, triggered by events."
- **Blocks:** the v2 spec's screening tickets (not yet written).
- **Needed by:** no date.

## What the app does today

- **Behaviour:** nothing: the app analyses the one company it is given (RRX).
- **Pinned by:** no test.
- **Data and constraints:** `docs/research/app-context.md`. The screen must use only code (no LLM), point-in-time data (`known-from-rule`) and a survivorship-free universe, and stay within the budget (about $30 a month for Claude, data and hosting, brief §3). Full reports cost Claude calls; the screen must not.

## The question

What universe, what criteria and what rotation pick the about 20 names worth a full report, and which events trigger one? Hypotheses: a universe of US-listed companies above size and liquidity floors, screened monthly on figures from XBRL and prices, and restricted to companies a template can analyse (`prompts/10-business-model-templates.md`), keeps the cost near zero; triggers are a new filing, a large price move against the last verdict, and a thesis-break signal. The screen ranks candidates for research; it is not a trading rule (those are `prompts/03-rule-families.md`), and the deliverable must keep the two apart.

## What the app needs back

| Proposed decision name | Question it answers | Parameters expected, with units | Accepted decisions it touches |
|---|---|---|---|
| `coverage-universe` | Which companies the screen considers at a date, survivorship-free | size floor (dollars of market cap), liquidity floor (dollars of daily volume) | `known-from-rule` |
| `screen-criteria` | How candidates are ranked, from code-only point-in-time data | per criterion: formula and unit | `flags-by-provenance` |
| `coverage-size-and-rotation` | How many names get full reports, and how names enter and leave | names (count), rotation cadence (per month) | none |
| `report-triggers` | Which events start a full report on a covered or candidate name | per trigger: threshold and unit | `thesis-break-band-midpoint` |
| `screen-cost-and-runtime` | What a screen run may cost and take | dollars per run, minutes per run | none |

- **Fixture format:** a Python script with assertions that runs the screen on a small fixed universe as of 2026-09-30 and checks its ranking, and a CSV of that universe, saved in `docs/research/`.
- **Reference case:** the universe as of 2026-09-30, showing where RRX ranks and why.
- **What the app must add:** list it in the deliverable (brief §7). Known gaps: bulk loading of many companies, a price source for the whole universe (`prompts/09-reference-inputs.md`), a scheduler.

## Technical evidence

Measure how cheaply the screen's data can be had: SEC's frames API (one concept for every filer in one call), its nightly bulk company-facts file, and a bulk end-of-day price source; record download size, run time and storage, with scripts run on real data. Cite official documentation at a pinned version; mark an untested claim [UNVERIFIED]. Add a section **Existing tools and prior art**: open-source screeners and survivorship-free universe datasets, with their licences. SEC requests use the `EDGAR_IDENTITY` environment variable, at most 10 a second.

## Leading words

- **Coverage:** the about 20 companies that get full reports.
- **Screen:** the code-only ranking of the universe that proposes candidates for coverage.
- **Trigger:** an event that starts a full report.

## Known issues

- Ranking by cheapness alone favours value traps; the deliverable should say how the criteria avoid it, with evidence.
- The screen must not use any figure after its date: market caps need the shares outstanding known at that date.

## Steps

### 1. Read

Read the brief, `app-context.md`, the business-model templates deliverable (`business-model-templates.md`, a prerequisite), `investment-methodology.md` (what makes a stock decision-ready), and the decision records named above.

Done when you can state, in three sentences, the settled coverage decision, what a full report costs, and which companies a template can analyse.

### 2. Universe and data

Define the universe and fetch the data the screen needs for it as of 2026-09-30, with the cost and run time.

Done when the universe as of 2026-09-30 is built by script, including companies that later delisted, with its size and run time.

### 3. Criteria, rotation and triggers

Write the ranking, rotation and trigger rules, with the evidence behind each criterion (brief §6).

Done when the script ranks the fixed universe and every criterion has its formula, unit and evidence grade.

### 4. Write the deliverable

Write `docs/research/coverage-screen.md` in the brief's format (§7), with **Existing tools and prior art** and **What the app must add**.

Done when the brief's done-criterion is met and every decision in "What the app needs back" is proposed, deferred with a reason, or shown to be unnecessary.

Standards: brief §6, plus "Technical evidence" above.
