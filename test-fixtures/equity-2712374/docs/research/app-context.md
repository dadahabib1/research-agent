# App context (docs/research/app-context.md)

What the app, `dadahabib1/equity_analyst_v2`, can do today, so research serves the app as it is. Kept up to date by the app's orchestrator, by pull request, whenever a merge changes what the app can do; the research agent reads it and does not edit it.

- As of: 2026-10-05, app commit `7e89968` (tag `v1-ticket-6`)
- Version: v1 complete (15 tickets merged)

## What it does

v1 analyses one company, Regal Rexnord (RRX), end to end, as of 2026-09-30, and shows it in a Streamlit walkthrough page.

- **The analysis.** It reads facts from a point-in-time store, runs the cyclical template and the valuation engine, estimates assumptions from evidence, and ends in BUY, HOLD or SELL at two discount-rate bounds. It reproduces `rrx_reference_case.py`: HOLD (bound A BUY, bound B HOLD), scenario values $100.17 / $191.44 / $227.41 at bound A.
- **The page.** One scrolling report in learning format, with the user's overrides (each kept with its reason) and a saved record. Every analysis is saved, append-only, and logged as a paper trade.
- **Not yet:** analysing any other ticker. The RRX inputs the methodology enters by hand (reference inputs, theme levels, catalyst) are entered in code for RRX only; a second company needs its own entries, and a company that is not a cyclical component maker needs a template that does not exist yet. Generalising is v2 work.

## Data it can reach

| Data | Source | How | Point in time |
|---|---|---|---|
| Financial statements, segments, share counts | SEC XBRL through edgartools, 2016 on | automated, free | by filing acceptance time; amendments and restatements kept as versions |
| Earnings-release figures (segment adjusted EBITDA, orders, backlog) | 8-K exhibits | Claude reads, code verifies every number against a table cell or quote (ADR 0003) | by release time; each release read once |
| Rates and macro | FRED and ALFRED: DGS10, INDPRO, TCU, USREC | automated, free | the vintage in force on the as-of date |
| ISM manufacturing (PMI, New Orders) | ISM reports, archived by hand | manual | by publication time; not on FRED since 2016 |
| Implied ERP, industry betas, sector returns on capital | Damodaran | entered by hand | by publication date |
| Prices | StockAnalysis close (reference case); yfinance (prototype data, ADR 0002) | manual and automated | by that day's 16:00 US Eastern close |

Not available: transcripts, news, short interest, insider and 13F data, intraday prices, an exchange calendar, delisted companies, a backtest harness.

## Rules every answer must fit

- Every number comes from filings or code, never from an LLM (ADR 0003).
- Point-in-time: an input counts only from its publication time (decision `known-from-rule`); facts are append-only.
- Each stock analysis stands alone (ADR 0005); assumptions are estimated per stock from evidence and are inputs, never constants (ADR 0006).
- One template exists: cyclical component makers (ADR 0007).
- Accuracy is the goal; learning format is the method (ADR 0001).

## Cost and budget

- The first analysis of a company-quarter costs about $0.22 to $0.30 in Claude calls (reading new earnings releases); repeat runs and overrides cost nothing.
- Budget: about $30 a month for Claude, data and hosting together (brief §3).

## What the app can test

- Acceptance tests with exact inputs and outputs run as pytest. Fixtures are easiest as CSV, JSON or a Python script with assertions, like `rrx_reference_case.py`.
- Tests that need live SEC, FRED or Claude data run as live-gated tests.
- Backtests wait for the backtest harness, which is not built. Anything scored by an LLM can only be forward-tested.

## Known limitations of v1

Each is accepted by the requester (or deferred as rare under the app's review rules) and pinned by a test; none moves the RRX reference values.

- Early-close days keep the 16:00 close (decision `early-close-known-limitation`).
- A fourth quarter derived from an annual figure stays readable when a filing accepted in the same second later brings a different annual figure (the conflict is recorded, but the derived quarter is not reported as in conflict).
- Release tables that state no usable scale or unit are refused, with the reason.
- A ratio row with no ratio words that happens to sum exactly with dollar rows is read as dollars.
- Text a release hides or reorders is read as if visible.
- A per-share table with no per-share words is read as amounts; any row saying "per" is refused.
- A segment series across two filings accepted in the same second picks one of them.
- A reorganization that only drops a segment, or moves business between segments that keep their names, in a 10-Q is not seen until the next 10-K.
