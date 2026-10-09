# Prompt: automated reference inputs research

You are the researcher for a personal US equity research app, equity_analyst. Your job is to find point-in-time, automatable sources for the inputs the app still enters by hand (equity risk premium, industry betas and returns, ISM survey history, and production stock prices), within the app's budget and licensing limits. The requester decides in a decision session; the app's orchestrator builds only on the accepted decision records on main, and pins each one it uses in its lock file.

Read `docs/research/strategy-research-brief.md` first. It holds the situation, settled decisions, standards and deliverable format; this prompt adds only the topic.

## Why the app needs this

- **Asked by:** the app's v2 planning (the requester and the app's orchestrator, 2026-10-05). Analysing many companies is impossible while each analysis needs inputs typed in by hand. The brief also leaves the production price source open (§8, "Price data").
- **Blocks:** the v2 spec's data tickets (not yet written).
- **Needed by:** no date; it has no prerequisites and can run first.

## What the app does today

- **Behaviour:** for the RRX case valued 2026-09-30, these inputs are entered by hand, each stored as a fact with source, known-from date and trust tier:
  - Damodaran's monthly implied equity risk premium with its paired Treasury rate (the September 1, 2026 pair: 4.75% and 4.09%);
  - Damodaran's industry betas (1.19 and 0.89 for the two industries RRX is weighted across) and sector returns on capital;
  - the ISM manufacturing report (August 2026: PMI 54.6, prior 55.6, New Orders 53.7, published 2026-09-01), archived as published, because ISM data left FRED on 2016-06-24;
  - prices: StockAnalysis's close of $155.89 on 2026-09-29 for the reference case; otherwise yfinance, labelled prototype data.

  Automated already: FRED through ALFRED vintages (DGS10 5.29% on 2026-09-30; INDPRO, TCU, USREC), and SEC filings.
- **Pinned by:** the app's reference-input, ISM, price and FRED tests read each value above back by date (for example: an ISM query as of 2026-09-30 returns 54.6; as of 2026-10-01 it returns September's 54.5).
- **Data and constraints:** `docs/research/app-context.md`. Accepted decisions `known-from-rule` and `macro-data-vintages` apply to every source: a value counts only from its publication time, and revised series keep their vintages. Budget: about $30 a month for Claude, data and hosting together (brief §3).

## The question

For each hand-entered input, which source can the app fetch automatically, with history, publication timestamps, and terms that allow personal use, within budget? Hypotheses: Damodaran's archived spreadsheets give ERP and beta history with dates; ISM's own releases are the only point-in-time ISM source, so archiving forward plus labelled revised history stays the rule; a low-cost end-of-day price API with corporate actions and delisted tickers beats yfinance for production.

## What the app needs back

| Proposed decision name | Question it answers | Parameters expected, with units | Accepted decisions it touches |
|---|---|---|---|
| `erp-source` | Where the implied ERP and its paired rate come from, with history and publication dates | refresh cadence (per month), history start (year) | `known-from-rule`, `macro-data-vintages` |
| `industry-beta-source` | Where industry betas and returns on capital come from, and how often they change | refresh cadence (per year) | `known-from-rule` |
| `ism-source` | How ISM readings are collected going forward and for history | publication lag (days) | `macro-data-vintages`, `rrx-case-august-ism` |
| `price-source` | The production end-of-day price source, with corporate actions and delisted tickers | cost (dollars per month), history start (year), adjustment method | `known-from-rule` |
| `reference-input-refresh` | When each input is refreshed, and what a run does when one is stale | staleness limit per input (days) | `known-from-rule` |

- **Fixture format:** a Python script with assertions per source that fetches the value the RRX case uses on its date (the values above) and asserts it, saved in `docs/research/`.
- **Reference case:** RRX as of 2026-09-30, the values listed above.
- **What the app must add:** list it in the deliverable (brief §7). Known gaps: a scheduler; storage for downloaded source files.

## Technical evidence

This request is mostly technical. For each source: cite its official documentation and terms of use, record the API or file format, rate limits, history depth, publication timestamps or vintages, cost and licence, and back each claim with a script you ran, recording its output and the versions. Mark an untested claim [UNVERIFIED]. Add a section **Existing tools and prior art**: Python packages and open-source projects that already fetch these sources. Keys or identities a script needs come from environment variables (for example `FRED_API_KEY`, `EDGAR_IDENTITY`); never write a key into a file.

## Leading words

- **Reference input:** a value the valuation uses that does not come from the company's filings: rates, risk premium, betas, survey data, prices.
- **Publication timestamp:** when a value became public, which decides when the app may use it (`known-from-rule`).

## Known issues

- Damodaran publishes the ERP monthly; the app may use it only from its publication date, so a case valued at a month-end uses the previous month's figure.
- Free price sources change terms and break without notice; prefer a source with a stated licence and a history of stability.

## Steps

### 1. Read

Read the brief, `app-context.md`, the decision records named above, and `actuator-supply-chain.md` §4 (the RRX case's inputs and the known-from rule).

Done when you can state, in three sentences, which inputs are hand-entered today, which rules any source must meet, and the budget.

### 2. Sources

For each input, list the candidate sources with format, history, timestamps, cost and licence, and fetch the RRX case's value from each viable one.

Done when every input has at least one viable source fetched by script, or is shown to have none, with the reason.

### 3. Point in time and refresh

For each chosen source, say how the app records publication time and revisions, how often it refreshes, and what a run does when an input is stale.

Done when each chosen source has a refresh rule and a staleness limit.

### 4. Write the deliverable

Write `docs/research/reference-inputs.md` in the brief's format (§7), with **Existing tools and prior art** and **What the app must add**.

Done when the brief's done-criterion is met and every decision in "What the app needs back" is proposed, deferred with a reason, or shown to be unnecessary.

Standards: brief §6, plus "Technical evidence" above.
