# Finance and investing add-on

## Point-in-time

- Use filing dates, not period ends. Use originally reported figures, not restated ones, until the restatement is public. Use the data vintage in force at the as-of date.
- Knowledge timestamp: market prices and yields count as known at that day's close; statistical releases at their publication time.
- Jointly estimated inputs, such as an implied equity risk premium and its risk-free rate, come from the same date.

## Backtests and evidence of edge

- A backtest needs:
  - a survivorship-free universe;
  - corporate actions;
  - realistic costs at the investor's scale;
  - taxes as parameters;
  - settlement rules.
- Multiple testing: require |t| > 3 for in-house tests (Harvey, Liu and Zhu 2016), and expect returns to decay after publication (McLean and Pontiff 2016).
- Language-model judgments are forward-tested only, because historical tests are contaminated by training data.
- Run a power analysis before adopting any statistical rule; personal decision rates are low.

## Valuation consistency

- Reinvestment is consistent with growth and returns on new capital in every stage, and fade stages land exactly on their terminal values.
- All inputs share one valuation date, cash flows use mid-year discounting, and share counts and balance sheets come from the same date.
- Separate the reward for market risk (beta) from mispricing (alpha). A fairly priced asset shows zero edge whatever its beta.
- Every limit names its denominator: total portfolio, equity allocation or active sleeve.
- Report values as ranges when inputs are unresolved, and act only if the verdict holds across the range.

## Standard methods to reuse

- **Cycle dating:** Bry–Boschan and Harding–Pagan turning-point rules, with amplitude filters.
- **Scenario weights:** extended Pearson–Tukey, using the 5th, 50th and 95th percentiles weighted 0.185, 0.63 and 0.185.
- **Per-company assumptions:** reference-class forecasting, with analogue rules fixed before outcomes are seen.
- **Benchmarks:** computed on the same base as the quantity they are compared with.

## Data

- Verify availability and licence before designing a pipeline. Some indexes are absent from public databases, and many free APIs are licensed for personal use only.
- Take prices and fees from official sources (the broker's own pages), and record the date checked.

## Tax and regulation

- Enter tax rules as sourced parameters. Give no tax or legal advice; name the professional who must confirm.
- Citizenship and residence can each create tax obligations; ask which apply.
