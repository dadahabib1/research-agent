# Prompt: business-model templates research

You are the researcher for a personal US equity research app, equity_analyst. Your job is to decide which forecast templates the app needs beyond its one cyclical template so that it can analyse most US-listed companies, how each values a company, what data each needs, and how the app assigns a company to a template from point-in-time data. The requester decides in a decision session; the app's orchestrator builds only on the accepted decision records on main, and pins each one it uses in its lock file.

Read `docs/research/strategy-research-brief.md` first. It holds the situation, settled decisions, standards and deliverable format; this prompt adds only the topic.

## Why the app needs this

- **Asked by:** the app's v2 planning (the requester and the app's orchestrator, 2026-10-05). v1 analyses one company; analysing any ticker is v2's main goal (`app-context.md`).
- **Blocks:** the v2 spec's template tickets, and the industries and coverage-screen requests (`prompts/12-industries-and-peers.md`, `prompts/13-coverage-screen.md`).
- **Needed by:** no date; it is the largest v2 blocker.

## What the app does today

- **Behaviour:** the app's ADR 0007 (quoted): "A forecast template describes how a kind of business turns operating drivers into revenue and profit (for example installed base with recurring use, cyclical capital goods, pre-profit growth). Templates are organised by business model, not by theme or sector, because one theme spans several business models." One template exists: cyclical component makers (`actuator-supply-chain.md` §3.2), forecasting segment growth and adjusted EBITDA margin, valuing on mid-cycle earnings through a three-stage FCFF DCF (`investment-methodology.md` §3.2). The DCF engine, discount rate, checks and verdict are shared by every template.
- **Pinned by:** the app's cyclical-template tests reproduce RRX §4.3 and §4.5: organic index 92.0 / 87.4 / 88.1, amplitude 0.126, gap 0.0983, mid-cycle margin 23.19%, base forecast sales $6,211.6M to $7,724.6M, terminal NOPAT $1,165.6M.
- **Data and constraints:** `docs/research/app-context.md`. Numbers come from filings or code, never from an LLM (the app's ADR 0003); assumptions are estimated per stock from evidence (ADR 0006); each analysis stands alone (ADR 0005).

## The question

Which templates cover most US-listed companies, how does each value a company, and how is a company assigned to one? Hypotheses: an FCFF DCF fits most non-financial businesses with template-specific drivers (steady growers, installed base with recurring revenue, pre-profit growth, commodity producers); banks and insurers need an equity-based valuation (excess return on equity), because debt is their raw material; REITs need funds from operations and net asset value, which are non-GAAP and come from earnings releases rather than XBRL; a company can be assigned from its SIC code, its XBRL tags and its segment structure, with a fallback to "no template" rather than a wrong one.

## What the app needs back

| Proposed decision name | Question it answers | Parameters expected, with units | Accepted decisions it touches |
|---|---|---|---|
| `template-taxonomy` | Which templates exist, and what share of US-listed companies (count and market cap) each covers | coverage per template (percent of companies; percent of market cap) | none |
| `template-assignment-rule` | How the app assigns a company to a template from point-in-time data, and when it refuses | signals and thresholds, with units | `known-from-rule` |
| `template-build-order` | Which templates to build first in v2 | per template: coverage gained (percent) | none |
| `<template>-method` (one per template proposed for v2) | The valuation approach, drivers, checks and data for that template | per driver: unit and source (XBRL tag or release figure) | `cycle-turning-point-confirmation`, `cycle-exposed-margin-check` where cyclical |

- **Fixture format:** a CSV of companies with their expected template and the signals that assign it, and a Python script with assertions that applies the assignment rule, saved in `docs/research/`. For each template proposed for v2, one worked reference case with every input and output.
- **Reference case:** RRX as of 2026-09-30 must stay on the cyclical template with its reference values unchanged.
- **What the app must add:** list it in the deliverable (brief §7). Known gaps: release-only figures (such as FFO) need the app's quote-verified extraction for new metrics.

## Technical evidence

For each template's data needs: say whether XBRL carries each driver (name the us-gaap tags, and how many companies report each, measured with SEC's frames or company-facts API) or whether it must come from earnings releases. For the assignment rule: which signals are free and point-in-time (SEC's SIC codes in the submissions API, XBRL tags present, segment structure) and which are licensed (GICS). Cite official documentation at a pinned version and back each claim with a script run on real data, recording the script, its output and the versions; mark an untested claim [UNVERIFIED]. Add a section **Existing tools and prior art**, covering what edgartools already offers for statements, segments and financial-company data. SEC requests use the `EDGAR_IDENTITY` environment variable, at most 10 a second.

## Leading words

- **Template:** how a kind of business turns operating drivers into revenue and profit (the app's ADR 0007).
- **Assignment rule:** the point-in-time rule that picks a company's template, or refuses.

## Known issues

- The app's real-data corpus (`prompts/08-real-data-corpus.md`) may not exist yet; if it does, test the assignment rule on it.
- A company with segments of different business models (a conglomerate) needs a rule: one template per segment, or a refusal.

## Steps

### 1. Read

Read the brief, `app-context.md`, `investment-methodology.md` §3.2, `actuator-supply-chain.md` §3.2, the system review deliverable (`system-review-v1.md`, a prerequisite), and the decision records named above.

Done when you can state, in three sentences, how the cyclical template works, what every template shares, and what the system review concluded about templates.

### 2. Taxonomy and coverage

Propose the templates and measure how much of the US-listed universe each covers, by company count and market cap, from a sample you name.

Done when the templates proposed cover at least the share of market cap the deliverable states, and each has its valuation approach.

### 3. Data per template

For each template proposed for v2, list its drivers and where each comes from, measured on real filings.

Done when every driver has its source and the share of sampled companies that report it.

### 4. Assignment rule

Write the rule and test it on a labelled sample, reporting its accuracy and its refusals.

Done when the script runs on the sample, RRX is assigned to the cyclical template, and every misassignment is listed.

### 5. Write the deliverable

Write `docs/research/business-model-templates.md` in the brief's format (§7), with **Existing tools and prior art** and **What the app must add**.

Done when the brief's done-criterion is met and every decision in "What the app needs back" is proposed, deferred with a reason, or shown to be unnecessary.

Standards: brief §6, plus "Technical evidence" above.
