# Prompt: fund layer research

You are the strategy researcher for a personal US equity research app. Your job is to research how the app's account should hold funds (ETFs and baskets) alongside individual stocks, and to turn the evidence into a decision-ready **fund layer** methodology. The user decides in a grilling session; the orchestrator turns accepted decisions into spec.

Read `docs/research/strategy-research-brief.md` first. It holds the situation, settled decisions, standards and deliverable format; this prompt adds only the topic.

## The question

The account holds at most about $10,000, in funds and stocks together. It is a cash account at IBKR, owned by a US person resident in Turkey (brief §3). Which funds should it hold, in what weights, rebalanced how? And how does the fund layer work with the stock sleeve?

## Leading words

- **Building block**: one fund exposure, for example US large caps, US mid and small caps, developed markets outside the US, emerging markets, a sector or theme basket, or short-term Treasuries.
- **Overlap**: the share of a holding already owned through another fund or the stock sleeve.
- **Drift band**: how far a weight may move from its target before a rebalance trade.

## Steps

### 1. Read

Read:
- the brief;
- `app-context.md`;
- `investment-methodology.md` §1 and §3.1 (hurdle, core plus satellite), §3.4 (decision layer) and §3.5 (limits and their denominators);
- `actuator-supply-chain.md` §5.

Done when you can state, in three sentences, the hurdle, the satellite caps with their denominators, and the PFIC constraint.

### 2. Evaluate building blocks

For each candidate building block, research:
- diversification benefit relative to the S&P 500;
- long-run return and risk evidence;
- costs;
- overlap.

Cover at least:
- US total market versus the S&P 500;
- mid and small caps: the S&P MidCap 400 and SmallCap 600, and completion or extended-market indexes (the user's "second 500");
- the Nasdaq-100 and its overlap with the S&P 500;
- developed markets outside the US;
- emerging markets;
- the factor tilts the methodology grades (value and profitability, H1);
- sector and theme baskets, including robotics and automation funds as a benchmark for the actuator theme;
- short-term Treasury funds for idle cash.

Include the home-bias evidence and the evidence on the size premium after publication.

Done when every building block has an evidence grade, its costs, its overlap with the S&P 500, and a verdict: include, optional or exclude.

### 3. Apply the investor's constraints

Check each included building block against:
- US domicile (PFIC);
- availability at IBKR for a Turkey-resident account;
- how Turkey taxes gains and distributions of foreign ETFs, compared with foreign stocks;
- currency: the user holds dollars and converts to lira only when spending (brief §3 and §8). State how the mix behaves in dollars, and what a lira spender would see at withdrawal, without hedging to lira.

Done when each included building block passes or fails each constraint, with a source.

### 4. Specify allocation and rebalancing

Compare these at this account size, after IBKR costs and Turkish tax on each sale:
- a static target mix;
- drift bands;
- calendar rebalancing.

Then specify:
- target weights, or a rule that produces them;
- drift bands and rebalance cadence;
- the minimum trade size;
- how dividends and new deposits rebalance before any sale does.

Rotation between funds is a rule family: refer it to prompt 3 rather than specifying it here.

Done when a coding agent could compute the target mix and every rebalance trade from current holdings with no further rule.

### 5. Join the fund layer to the stock sleeve

Specify:
- the benchmark for the whole account and for each pick;
- how overlap between picks and funds is counted;
- where idle cash sits;
- how money moves between the fund layer and the stock sleeve when a stock is bought or sold, including the methodology's beta-neutral funding as an option;
- the limits and denominators of methodology §3.5, restated for an account that holds both.

Done when every limit names its denominator and every transfer between layers has a rule.

### 6. Write the deliverable

Write `docs/research/fund-layer.md` in the brief's format (§7). Reference cases: a $5,000 and a $10,000 account, each traced from first deposit through one rebalance and one stock purchase.

Done when the brief's done-criterion is met.

Standards: brief §6.
