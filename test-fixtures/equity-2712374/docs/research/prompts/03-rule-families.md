# Prompt: rule families research

You are the strategy researcher for a personal US equity research app. Your job is to research deterministic rules that turn the pipeline's outputs and daily prices into proposed orders at daily-to-monthly cadence, and to write each rule as a testable definition.

Read `docs/research/strategy-research-brief.md` first; this prompt adds only the topic.

## The question

The pipeline produces two kinds of input:
- slow outputs (expected value, moat, scenarios, thesis-break measures), quarterly or when events occur;
- fast inputs (price, trend), daily.

Which rules should combine them, on what evidence, and with what exact definitions?

## Leading words

- **Rule family**: a class of rules that share a trigger and an action, for example value-gap execution.
- **Cadence**: how often a rule is evaluated, separate from how often it trades.
- **Turnover budget**: the most trading the account allows per period after fees and tax.

## Known issues

- Rules that react to events during the day, such as a filing or news, are intraday triggers: brief §8 says how to propose them, and they reopen `early-close-known-limitation`.

## Steps

### 1. Read

Read:
- the brief;
- `app-context.md`;
- `investment-methodology.md` §3.4 (alpha gate, buy/hold spread, hold and sell rules), §3.5 and §3.6;
- `actuator-supply-chain.md` §3.3 (catch-up time) and §5 (verdict rule);
- `fund-layer.md` and `validation-ladder.md`.

Done when you can state the entry gate, the exit rule and the both-bounds rule in three sentences.

### 2. Survey candidate families

Cover at least:
- value-gap execution: adds and trims as price crosses the buy threshold or expected value;
- thesis-break exits after filings;
- trend and momentum filters used for timing only (methodology grade B);
- short-horizon reversal;
- rebalancing, calendar versus bands;
- fund fallback when a theme looks attractive but no stock qualifies;
- cash management;
- staged entries and exits.

For each, research the evidence (effect size, sample, decay, costs), how it interacts with the methodology's gates, and its failure modes.

Done when every family has an evidence grade, a validation rung (from `validation-ladder.md`) and a verdict: build now, forward-test or reject.

### 3. Write testable definitions

For each family marked build or forward-test, specify:
- trigger;
- inputs and their data sources;
- cadence;
- action and size;
- parameters, with sources;
- interaction with the both-bounds verdict and catch-up time;
- the turnover it generates.

Done when a coding agent could implement each rule, and a test could pre-register it, with no further choice.

### 4. Resolve conflicts between rules

Specify precedence when rules disagree, for example a trend filter blocking a value-gap add, or a rebalance trade against a thesis-break exit. Specify the turnover budget that caps all rules together.

Done when every pair of rules has a precedence, or a proof that they cannot conflict.

### 5. Specify the order execution policy

Specify:
- order types and how the limit price is set;
- session: regular hours only (brief §3);
- timing relative to the open and close;
- partial fills and expiry;
- the approval flow.

Done when every proposed order carries every field the broker needs.

### 6. Write the deliverable

Write `docs/research/rule-families.md` in the brief's format (§7). Reference cases: synthetic price and value paths that exercise each rule and each precedence case, ready as fixtures.

Standards: brief §6.
