# Prompt: system review of v1

You are the researcher for a personal US equity research app, equity_analyst. Your job is to review the app's v1 as built, its methodology choices and its technical design, and propose what to keep, fix or change before v2 analyses many companies instead of one. The requester decides in a decision session; the app's orchestrator builds only on the accepted decision records on main, and pins each one it uses in its lock file.

Read `docs/research/strategy-research-brief.md` first. It holds the situation, settled decisions, standards and deliverable format; this prompt adds only the topic.

## Why the app needs this

- **Asked by:** the app's v2 planning (the requester and the app's orchestrator, 2026-10-05). The requester asked that research also review the system itself, once per version boundary, not only the methodology as specified.
- **Blocks:** the v2 spec (not yet written) and the business-model templates request (`prompts/10-business-model-templates.md`).
- **Needed by:** no date; it gates the v2 spec.

## What the app does today

- **Behaviour:** v1 analyses Regal Rexnord (RRX) end to end as of 2026-09-30 and reproduces `rrx_reference_case.py`: HOLD (bound A BUY, bound B HOLD), scenario values $100.17 / $191.44 / $227.41 at bound A. The rest is in `app-context.md`.
- **Pinned by:** about 1,230 offline tests and about 1,300 live tests (real SEC, FRED, price and Claude calls). For example, the app's pipeline test reproduces the reference case's values within $0.01.
- **Data and constraints:** `docs/research/app-context.md`, as of 2026-10-05 and app commit `7e89968`. Since then the page reads its key from `.env`, serves only localhost, and is named equity_analyst (app commit `c8218db`).

What you cannot see in the app's private repository, quoted here:

- **Modules** (Python 3.13; dependencies anthropic, edgartools, python-dotenv, streamlit, yfinance):
  - `data`: SEC loading (`sec/load.py`, `sec/source.py`), the append-only SQLite fact store (`facts/store.py`; database triggers reject UPDATE and DELETE), tag families (`facts/families.py`), statements and segments (`facts/statements.py`, `facts/segments.py`), the derived fourth quarter (`facts/quarters.py`), FRED/ALFRED vintages (`fred/source.py`), hand-entered reference inputs (`reference/inputs.py`, `reference/ism.py`, `reference/prices.py`), the analysis record and paper trades (`records/store.py`);
  - `research`: earnings-release extraction (`research/extraction.py`, `tables.py`, `quotes.py`, `releases.py`): code picks tables, Claude Sonnet 5.5 points at cells by their labels, code reads the value, Claude Haiku 4.5 confirms the labels; a number without "$" or "%" counts as an amount only when the table's own sums prove it; sentence figures need three readings to agree;
  - `analysis`: the FCFF DCF engine, discount rate, checks, verdict, the cyclical template, theme exposure, assumption estimation, implied values;
  - `pipeline`: one analysis end to end (`pipeline/run.py`, with RRX's hand-entered inputs in `pipeline/rrx.py`);
  - `ui`: the Streamlit walkthrough.
- **Known-from rule:** a fixed 16:00 US Eastern close; no exchange calendar.
- **Where building was hard** (fix rounds after review, per ticket): extraction (ticket 4) 6 rounds; flags by provenance (14) 5; FRED and reference inputs (9) 5; analysis record (3), same-moment conflicts (15) and the walkthrough (6) 2 each; assumption estimation (8), theme exposure (7), filing inputs (11) and the end-to-end run (10) 1 each; the rest 0. In ticket 4, table reading was first built by hand before the team found that edgartools reads earnings-release tables.

## The question

What in v1 should change before the app covers many companies? Hypotheses: the methodology holds, but some choices were made for one cyclical company and will not generalise; several known limitations become real at scale; some custom code duplicates what maintained libraries already do; the SQLite store and the one-company pipeline may not scale to hundreds of companies.

## What the app needs back

| Proposed decision name | Question it answers | Parameters expected, with units | Accepted decisions it touches |
|---|---|---|---|
| `v2-scale-targets` | How many companies, how often, within what time and cost the v2 system must handle | companies (count), refresh cadence (per quarter), full load time (hours), cost (dollars per month) | none |
| `methodology-changes-before-v2` | Which methodology choices change before v2, with the evidence | per change: the section and the new rule | any of the 12 accepted decisions it revises |
| `known-limitations-before-v2` | Which v1 known limitations must be fixed before v2, which can wait | per limitation: fix or keep, with the rate at which real data hits it | `early-close-known-limitation` and the others in `app-context.md` |
| `library-replacements` | Which custom modules a maintained library should replace | per module: the library, its pinned version, what it covers | none |
| `fact-store-at-scale` | Whether the SQLite fact store holds at v2 scale, or what replaces it | rows (count), database size (GB), query time (seconds) at the target | `fact-store-same-time-conflicts`, `flags-by-provenance` |

- **Fixture format:** a Python script with assertions for any measured number (load time, store size, query time), saved in `docs/research/`.
- **Reference case:** RRX as of 2026-09-30, plus a sample of other US-listed companies you choose and name.
- **What the app must add:** list it in the deliverable (brief §7). Known gaps to start from: an exchange calendar; a multi-company pipeline.

## Technical evidence

This request is half technical. For any claim about what a library, API or data source does: cite its official documentation or source code at a pinned version, and back the claim with a script you ran on real data, recording the script, its output and the versions in the deliverable or its log. Mark an untested claim [UNVERIFIED]. Add a section **Existing tools and prior art** to the deliverable: maintained libraries and open-source projects that already do parts of what v1 built by hand, each checked on RRX where possible. SEC requests need a contact identity: use the `EDGAR_IDENTITY` environment variable; if it is missing, mark SEC-dependent measurements [UNVERIFIED] and list the gap.

## Leading words

- **System review:** a review of the app as built, its methodology and its technical design together, at a version boundary.
- **Scale target:** the number of companies, refresh cadence, time and cost the next version must handle.

## Known issues

- The review cannot read the app's code; it works from this prompt, `app-context.md`, the methodology and the decision records, and tests libraries directly.
- Only one company has been analysed end to end, so evidence about other companies comes from your own samples.

## Steps

### 1. Read

Read:
- the brief;
- `app-context.md`;
- `investment-methodology.md`, `actuator-supply-chain.md` (revision 5) and `rrx_reference_case.py`;
- every record in `decisions/` (`decisions/INDEX.md`).

Done when you can state, in three sentences, what v1 does, which parts were hardest to build, and which choices depend on RRX being a cyclical component maker.

### 2. Methodology at scale

For each methodology component, say whether it generalises beyond a cyclical component maker, with the evidence (brief §6). Flag choices that rest on one company.

Done when every component in the methodology's template list has a verdict: generalises, generalises with a change (name it), or is specific to the cyclical template.

### 3. Known limitations at scale

For each known limitation in `app-context.md`, estimate how often real filings of other companies hit it, from a sample you load and name.

Done when each limitation has a measured or estimated rate, its sample, and a recommendation.

### 4. Technical audit

Measure, with scripts on real data: SEC load time per company at 10 requests a second; fact-store rows and size per company-decade, projected to the scale target; extraction cost per company-quarter at the app's models; and which custom modules a maintained library (edgartools first) already covers, checked on RRX.

Done when each measurement has its script and output, and each custom module listed above has a replace-or-keep verdict.

### 5. Write the deliverable

Write `docs/research/system-review-v1.md` in the brief's format (§7), with the sections **Existing tools and prior art** and **What the app must add**.

Done when the brief's done-criterion is met and every decision in "What the app needs back" is proposed, deferred with a reason, or shown to be unnecessary.

Standards: brief §6, plus "Technical evidence" above.
