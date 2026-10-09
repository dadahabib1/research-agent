# Domain rules: US equity research and investing (equity_research/docs/research/domain-rules.md)

The rules of this field that the general research protocol cannot know. The researcher applies them, the reviewer checks them, and the brief's §6 points here. Write each rule as a statement a reviewer can check, followed by its check, the way the protocol's `takeaways.md` writes its entries. Keep every heading; write "none known" rather than delete one.

Written 2026-10-07 from two sources: the research-agent plugin's former `references/finance.md` (last present at plugin commit `c8310e9`), and the field rules the brief's §6 restated before this file existed.

- **Precedence.** Accepted decision records in `decisions/` override this file. A decision that changes a rule here changes the rule in the same pull request.
- **Changes.** The requester changes this file by pull request, or a decision session does when it accepts a decision. A run proposes a change in its deliverable's "Changes to existing decisions or methodology" section; it never edits this file itself.
- **Decision-critical** means an input, value or claim that a recommendation, decision or reference case depends on. A check scoped to decision-critical items does not apply to background facts.

## 1. When information counts as known

Decide the knowledge-timestamp convention for each kind of input, and which data vintage an analysis uses.

- Filing-based figures count as known at their filing date, not at their period end. Check: every filing-based input in the log names its filing date.
- Originally reported figures are used, not restated ones, until the restatement is public. Check: a restated figure used in an analysis names the date its restatement became public, and that date is on or before the as-of date.
- An analysis uses the data vintage in force at its as-of date. Check: every decision-critical input from a revised series names its vintage.
- Market prices and yields count as known at that day's close; statistical releases at their publication time. Check: every decision-critical market or statistical input names the close or the release time it was taken at.
- Jointly estimated inputs, such as an implied equity risk premium and its risk-free rate, come from the same date. Check: each jointly estimated pair in a valuation shows one date.
- All inputs of a valuation share one valuation date; share counts and balance sheets come from the same date. Check: the valuation lists one date, and every input's date matches it.

## 2. What settles each claim type here

For literature claims: what a valid study or test looks like in this field (what results must be net of, significance bars, replication, out-of-sample rules). For measurements: the smallest sample that counts, and how a sample is named. For documentary facts: which sources count as owning.

- A backtest counts only with a survivorship-free universe, corporate actions, realistic costs at the investor's scale (heading 5), taxes as parameters (heading 7) and settlement rules. Check: the backtest's description names each of the five.
- An effect counts as an edge only net of realistic costs at the investor's scale. Check: each literature finding says whether its figures are gross or net of costs, and which costs.
- An in-house test needs |t| > 3, because of multiple testing (Harvey, Liu and Zhu 2016). Check: every in-house test reports its t-statistic against this bar.
- A published effect's returns are expected to decay after publication (McLean and Pontiff 2016). Check: a literature finding used to size an expected edge says whether its figure is from the original sample or from after publication.
- A judgment scored by a language model is forward-tested only, because historical tests are contaminated by its training data. Check: no recommendation rests on a historical backtest of model-scored inputs.
- A statistical rule is adopted only after a power analysis, because personal decision rates are low. Check: each proposed statistical rule states its power analysis: the sample it needs and how long that sample takes to collect.
- What a library, API or data source documents (its interface, limits, licence, price) is a documentary claim, settled by its official documentation or source code at a pinned version, or by the owning page with the date checked. Check: each such decision-critical claim cites the version or the check date.
- What a library, API or data source does on this project's data (coverage, field presence, latency, correctness) is a measurement, settled by a script run on real data, with the script, its output and the versions recorded in the deliverable or its log. Check: each such decision-critical claim points to its script and output.
- A decision-critical claim that cannot be checked in the run (a licensed source, a missing key, a claim that a feature is absent) is marked [UNVERIFIED] and listed under Open questions with the check that would settle it; it does not stop the run. Check: no recommendation rests on an [UNVERIFIED] claim without saying so.
- Measurements: the smallest sample that counts is none known yet. Each measurement names its sample (companies, filings or series, and dates). Check: every measurement names its sample.

## 3. Standard methods to reuse

Methods the field already has for problems a run is likely to meet, each with its owning source. A run cites one of these or justifies the deviation.

- Valuation consistency: reinvestment is consistent with growth and returns on new capital in every stage, and fade stages land exactly on their terminal values. Check: a reference case recomputes reinvestment from growth and return on new capital in each stage, and the last fade year equals the terminal-value inputs.
- Discounting: cash flows use mid-year discounting. Check: the discount factor for year t uses t − 0.5.
- Alpha and beta: the reward for market risk (beta) is separated from mispricing (alpha); a fairly priced asset shows zero edge whatever its beta. Check: a reference case with price equal to value shows zero edge at more than one beta.
- Unresolved inputs: values are reported as ranges, and a verdict is acted on only if it holds across the range. Check: every value that rests on an unresolved input is shown as a range, and the verdict is checked at both ends.
- Cycle dating: the Bry–Boschan and Harding–Pagan turning-point rules, with amplitude filters, not a home-made rule. Check: a noisy test series does not create extra cycles.
- Scenario weights: extended Pearson–Tukey, using the 5th, 50th and 95th percentiles weighted 0.185, 0.63 and 0.185. Check: the weights sum to 1 and are applied to those three percentiles.
- Per-company assumptions: reference-class forecasting, with the analogue rules fixed before outcomes are seen. Check: the analogue rules are dated before the outcome data they select.
- Benchmarks: computed on the same base as the quantity they are compared with. Check: each benchmark comparison names one base for both sides.

## 4. Units, denominators and bases

The denominators and bases every ratio, limit and percentage must name, and the ones that are easy to confuse.

- Every limit names its denominator: total portfolio, equity allocation or active sleeve. Check: every limit in a decision names one of these three.

## 5. Feasibility at the requester's scale

Costs, minimum sizes, sample sizes, time to result and other constraints that change the answer at the requester's actual scale.

- Costs are computed at the investor's scale (the account in the brief's §3), not per unit; in-house tests use costs at IBKR rates. Check: every method's cost is computed for the account's size and order sizes at IBKR's published rates, with the date the rates were checked.

## 6. Data sources, access and licence

The owning sources to go to first (endpoints, data files, registries), what is paid or licensed for personal use only, and what is known to be missing from public databases. This is also the field's search list for the protocol's `searching.md`.

- Sources in this order: peer-reviewed finance and accounting journals first; then index providers; regulators and official statistics; fund issuers' official documents; CFA Institute, McKinsey's *Valuation*, Damodaran, Counterpoint Global and the Kenneth French data library. Check: each cited source sits in this list or in the protocol's hierarchy, and a lower one is not used where a higher one owns the claim.
- Research published by asset managers or vendors is practitioner research. Check: every such source is flagged as practitioner research in the deliverable.
- Availability and licence are verified before a pipeline is designed: some indexes are absent from public databases, and many free APIs are licensed for personal use only. Check: each data source a design depends on names its availability and its licence terms, with the date checked.
- Prices and fees come from official sources, such as the broker's own pages, with the date checked. Check: every price or fee cites the official page and its check date.
- Every data value a deliverable hands to the app (an input, a reference case value, a source a design depends on) carries the app's trust tier, as `equity-research-brief.md` §9.1 defines them: T1 primary or official (filings, regulators, government statistics, company IR); T2 reputable press or curated data, verified against T1 for key numbers; T3 opinion, broker views or estimates, shown as opinion with their dispersion; T4 sentiment only, never a fact. The app stores the tier with each fact. The protocol's source hierarchy decides which source to prefer; the tier labels the value. Literature claims take the protocol's grades A to D instead of a tier. Check: every such value names T1, T2, T3 or T4.
- SEC requests (data.sec.gov, www.sec.gov) send the contact identity in the `EDGAR_IDENTITY` environment variable as the User-Agent, at most 10 requests a second. The identity goes only to SEC, never to a third-party fetcher or into a file. If it is missing, SEC-dependent measurements are marked [UNVERIFIED] and listed as a gap. Check: no script hard-codes an identity, and the log says whether `EDGAR_IDENTITY` was set.

## 7. Advice and regulatory boundaries

What the research must not give, and who must confirm what. Such rules enter as sourced parameters.

- Tax rules enter as sourced parameters. The research gives no tax or legal advice and names the professional who must confirm each rule. Check: no decision states a tax outcome as a fact, and each tax parameter names its source and the confirming professional.
- Citizenship and residence can each create tax obligations; ask which apply. Check: a deliverable that touches tax states which citizenships and residences it assumed (the brief's §3 records the investor's).

## 8. Domain words

Leading words whose meaning here differs from everyday use or from other fields, each defined once. The brief's §4 may point here.

- The leading words are defined in the brief's §4 and in the methodology it names; none are added here.
