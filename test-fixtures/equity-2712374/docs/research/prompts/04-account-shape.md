# Prompt: account shape research

You are the strategy researcher for a personal US equity research app. Your job is to research how an account of $5,000–10,000 holding funds and stocks should be shaped: number and size of positions, minimum orders, cash buffer, turnover, and the drag from fees, currency conversion and taxes.

Read `docs/research/strategy-research-brief.md` first; this prompt adds only the topic.

## The question

The methodology's sizing rules (quarter-Kelly, caps, denominators) were designed without a dollar scale. At this account size, fees, fractional shares and Turkish tax on every sale change the answer. What shape should the account take?

## Leading words

- **Fee drag**: annual costs as a share of the account.
- **Tax drag**: annual tax on realized gains as a share of the account, under the user's two tax systems.

## Steps

### 1. Read

Read the brief, `app-context.md`, `investment-methodology.md` §3.4–3.5, `fund-layer.md` and `rule-families.md`.

Done when you can list every sizing rule and limit that has a dollar consequence.

### 2. Diversification at small scale

Research:
- how many stocks and funds it takes to diversify away company-specific risk today, in classic and recent studies;
- the evidence that company-specific volatility has changed over time;
- how a fund core changes the answer.

Done when the recommended number of positions for each layer has evidence and a range.

### 3. Cost model

For the proposed shape, model:
- IBKR Pro Fixed and Tiered commissions;
- fractional-share pricing (reports conflict, so verify on IBKR's own pages);
- deposits in dollars from a US bank, and lira conversion only at withdrawal;
- regulatory fees.

Done when fee drag is computed for the reference accounts at the turnover `rule-families.md` implies.

### 4. Tax model (parameters, not advice)

Model, as parameters:
- Turkish tax on each sale: lira conversion at trade-date rates, Yİ-ÜFE indexation when the index rose 10% or more, progressive rates;
- Turkish tax on dividends;
- the US foreign tax credit in the passive category, including when gains count as foreign-source (brief §3).

Show how holding period and turnover change tax drag.

Done when tax drag is computed for the reference accounts under stated parameters, with every parameter sourced.

### 5. Sizing at this scale

Restate for this account:
- quarter-Kelly and single-name caps;
- minimum position size, rounding and fractional shares;
- cash buffer and deposit handling.

Resolve where the methodology's rules break at small scale.

Done when a coding agent could size any proposed order with no further rule.

### 6. Write the deliverable

Write `docs/research/account-shape.md` in the brief's format (§7). Reference cases: a $5,000 and a $10,000 account over one year, at the rule families' expected turnover, showing fee drag and tax drag.

Standards: brief §6.
