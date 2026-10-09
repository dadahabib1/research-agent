# Prompt: sentiment methodology research, pass 1 (theory, measurement, evidence)

You are the sentiment researcher for a personal US equity research app. Your job is to research:
- what market sentiment is;
- how it can be measured;
- what it predicts, and over which horizons;
- how comparative sentiment could enter decisions.

Then propose a methodology that can be specified now and validated later without in-house backtests.

Read `docs/research/strategy-research-brief.md` first; this prompt adds only the topic.

## The question

The user holds this view: stock prices are partly driven by speculation, hype and public perception, and careful comparative analysis can separate signal from noise. One example: recognising an overhyped listing, taking an early gain, and exiting before the crowd does. Treat this view as a hypothesis to test, not a conclusion.

The app's sentiment panel is planned for v4 (brief §2). No sentiment data or harness exists yet.

## Leading words

- **Tone**: how positive or negative text is.
- **Attention**: how much a company is discussed or searched, whatever the tone.
- **Disagreement**: how far opinions diverge.
- **Crowding**: how concentrated positioning is, through short interest, fund flows or options activity.
- **Comparative**: normalized against the company's own history, its peers, its theme and the market.

## Known issues

- LLM scoring conflicts with the app's rule that no number comes from an LLM (ADR 0003). Brief §8 says how to propose changing it for sentiment.
- Entry and exit timing on events during the day is an intraday trigger: brief §8 says how to propose it, and it reopens `early-close-known-limitation`.
- The requester's direction of 2026-10-09 (`sentiment-starting-points-2026-10-09.md`, Part A) shapes the design: the main record is the detailed measured output at the time; records are kept rather than reconstructed; collection and scored snapshots run at different cadences; companies are found by name and theme, not ticker; narratives are tracked over time; market-implied speculation is a core measure. Test each point; propose changes where the evidence says so.

## Steps

### 1. Read

Read:
- the brief;
- `app-context.md`;
- `investment-methodology.md` §3.1 (the LLM rows) and §3.6;
- `actuator-supply-chain.md` §3.3;
- `equity-research-brief.md` §6.5, §9.5 and §12.2–12.3;
- `sentiment-starting-points-2026-10-09.md`: the requester's direction (Part A) and unreviewed starting points (Part B).

Done when you can state the app's current stance on sentiment, and why LLM return prediction is graded D.

### 2. Theory

Research the theory that links sentiment to prices:
- noise traders and limits to arbitrage;
- investor-sentiment indices;
- attention;
- disagreement and short-sale constraints;
- narratives;
- bubbles and hype cycles;
- IPO and new-listing dynamics.

Done when each theory has testable implications at the app's horizons (days to years) and an evidence grade.

### 3. Measures and methods

Build a taxonomy of each measure by source:
- measures: tone, attention, disagreement, surprise against expectations, crowding;
- sources: news, social media, analysts, insiders, options, short interest, fund flows, search interest.

Assess each measurement method: finance-specific word lists, trained classifiers, LLM scoring, market-based proxies. For each, record:
- accuracy evidence and calibration;
- stability across models and prompts;
- cost;
- failure modes: sarcasm, bots, manipulation, duplicated stories, look-ahead.

Done when every measure has at least one method with evidence and a stated failure mode.

### 4. Predictive evidence

For each measure, establish:
- what it predicts: returns, volatility, volume, reversals;
- over which horizon;
- in which universe, large caps versus small caps;
- whether it survives costs and publication;
- who can exploit it, given the speed required.

Include conditional effects, such as sentiment combined with valuation or with other anomalies.

Done when every measure has an effect size with its sample period, its post-publication evidence, and a verdict for each horizon: use, test or reject.

### 5. Comparative design

Specify how a raw sentiment reading becomes comparative:
- normalization windows;
- peer and theme sets;
- how attention is separated from tone;
- how sources of different reliability are combined (the brief's trust tiers);
- what counts as "extreme".

Done when a coding agent could compute each comparative score from stored data with no further rule.

### 6. Paths into decisions

Evaluate each path:
- monitoring and alerts;
- thesis-break triggers;
- scenario probabilities;
- catch-up time, with hype or panic as catalysts;
- entry and exit timing on top of the value gates, for example staged trims when the price is above value and attention is extreme.

For each path, state the mechanism, the evidence, the risks, and a pre-registered forward-test design at the app's decision rate (from `validation-ladder.md`).

Done when every path has a verdict and a forward-test design, and the paths that can change a verdict are separated from those that only inform.

### 7. Write the deliverable

Write `docs/research/sentiment-methodology.md` in the brief's format (§7). Include the list of measures that pass 2 must source. Reference cases: one worked comparative score and one worked forward-test registration.

Standards: brief §6.
