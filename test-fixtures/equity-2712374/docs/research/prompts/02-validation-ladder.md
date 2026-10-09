# Prompt: validation ladder research

You are the strategy researcher for a personal US equity research app. Your job is to establish how strategy decisions can be validated rigorously before the app has its own backtest harness, which claims each method can support, and what the harness must do once it is built.

Read `docs/research/strategy-research-brief.md` first; this prompt adds only the topic.

## The question

The user asked whether any method is as sound as backtesting on their own code and harness. Sentiment data arrives only in v4, and the harness does not exist yet (brief §2 and §5). What can be decided now, on what evidence, and what must wait?

## Leading words

- **Claim type**, one of three:
  - (a) a general effect exists in the market;
  - (b) a specific rule earns that effect after costs at this account's size;
  - (c) the user's own judgment adds value.
- **Contamination**: any way a test sees information unavailable at decision time, including through an LLM's training data.

## Steps

### 1. Read

Read the brief, `app-context.md` and `investment-methodology.md` §3.1 (multiple testing) and §3.6 (accuracy loop and power analysis).

Done when you can state the |t| > 3 rule, the power-analysis result for rank IC, and why LLM judgment is forward-tested only.

### 2. Catalogue validation methods

Research at least:
- replicated peer-reviewed evidence and meta-studies, for example McLean and Pontiff (2016), Hou, Xue and Zhang (2020), Jensen, Kelly and Pedersen (2023), Chen and Zimmermann;
- public replicated datasets that allow re-testing, for example Open Source Asset Pricing, the JKP factor data and the Kenneth French library;
- third-party backtesting platforms and their typical defects: survivorship, look-ahead, costs, rebalancing assumptions;
- pre-registered forward paper tests;
- statistical guards against overfitting, for example the deflated Sharpe ratio and the probability of backtest overfitting;
- out-of-sample hold-outs;
- defences against LLM contamination: anonymization, testing only after the training cutoff, time-restricted models.

These names are starting points to verify.

Done when every method has:
- what it can establish, by claim type;
- its failure modes;
- its cost and time to result;
- an evidence grade for the method itself.

### 3. Build the ladder

Rank the methods into rungs by how strongly they support each claim type.

Done when each rung has entry criteria a reviewer can check.

### 4. Map components to rungs

Cover each component type the program will produce:
- fund allocation and rebalancing;
- value-gap execution;
- thesis-break exits;
- the trend filter;
- account shape and sizing;
- sentiment measures and their uses.

For each, state the highest rung reachable now, the rung required before live money, and what must wait for the harness.

Done when no component lacks a current rung and a required rung.

### 5. Specify the forward-test protocol

Specify:
- a pre-registration template: rule, parameters, metric, sample size, duration, stopping rule, analysis plan;
- power and duration estimates at this account's decision rate;
- how results are recorded so the accuracy loop can use them.

Done when a forward test can be registered by filling in the template.

### 6. Specify the harness requirements

State what the in-house harness must do:
- point-in-time data;
- a survivorship-free universe;
- corporate actions;
- IBKR costs;
- cash-account settlement;
- Turkish tax drag as a parameter.

Also list which decisions stay blocked until the harness exists.

Done when a coding agent could size the harness ticket.

### 7. Write the deliverable

Write `docs/research/validation-ladder.md` in the brief's format (§7). Reference cases:
- one worked pre-registration;
- one worked general-effect claim supported from a public dataset.

Close with replacement text for the brief's interim validation rule (§6).

Standards: brief §6.
