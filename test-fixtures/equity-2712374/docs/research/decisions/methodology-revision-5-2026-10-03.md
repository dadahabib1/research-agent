# Decision record: methodology revision 5

- Date: 2026-10-03 (decided); recorded 2026-10-05
- Deliverable: `docs/research/methodology-revision-5-expert-answers.md` and `docs/research/actuator-supply-chain.md` §5.1, at commit `0e6e0ea`
- Decided by: the requester, 2026-10-03; recorded by the equity_analyst_v2 orchestrator (Claude) from the app's merged records (pull requests #19 to #24, #41, `docs/spec/decision-log.md`), because the decisions were made and built before this repository held decision records

Every decision below is accepted and already built in equity_analyst_v2 v1. Each opens with a machine-readable block; the prose fields follow the decision-record template. Evidence grades and validation rungs were not assigned at the time: the validation ladder (prompt 2) has not run yet.

## Decisions

### known-from-rule: an input counts as known only from its publication time

```yaml
name: known-from-rule
status: accepted
decided: 2026-10-03
decided_by: requester
moves_valuation: false
depends_on: []
supersedes: []
parameters:
  - {name: market_close, value: "16:00", unit: US Eastern time, source: "actuator-supply-chain.md §4"}
app: {spec: [ticket 1, ticket 9], merged: ["PR #23", "PR #48"]}
```

- **Status:** accepted
- **Decision:** Market data (prices, Treasury yields) must count as known at that day's close. A statistical release must count as known only from its publication time. A case valued at date V must not use any input published after V's close.
- **Parameters:**
  - `market_close` = 16:00 US Eastern time, per trading day (source: deliverable §4, known-from rule)
- **Rule:** known(x, V) holds when the publication time of x is at or before 16:00 US Eastern on V. A query as of V returns, for each series, the latest value whose publication time satisfies it.
- **Acceptance tests:**
  - Inputs: ISM manufacturing PMI, as of 2026-09-30 → expected output: the August 2026 report, PMI 54.6, published 2026-09-01
  - Inputs: the same query as of 2026-10-01 → expected output: the September report, PMI 54.5
  - Inputs: Damodaran's implied ERP of 2026-10-01, case valued 2026-09-30 → expected output: excluded; usable only in a case re-dated to 2026-10-01
  - Fixture: none
- **Constraints and non-goals:** early-close sessions keep the 16:00 close (see `early-close-known-limitation` in `app-v1-build-2026-10-04.md`).
- **Evidence:** `actuator-supply-chain.md` §4 and §5.1 item 1; expert answers; grade not assigned; validation rung not assigned
- **Depends on:** none
- **Supersedes:** none
- **Open items:** none

### macro-data-vintages: macro series are read as published on the as-of date

```yaml
name: macro-data-vintages
status: accepted
decided: 2026-10-03
decided_by: requester
moves_valuation: false
depends_on: [known-from-rule]
supersedes: []
parameters:
  - {name: fred_vintage_series, value: [DGS10, INDPRO, TCU, USREC], unit: FRED series ids, source: "actuator-supply-chain.md §3.2 Phase"}
  - {name: ism_ambiguous_band, value: [49.5, 50.5], unit: index points, inclusive: true, source: "actuator-supply-chain.md §3.2 Phase"}
app: {spec: [ticket 9], merged: ["PR #23", "PR #48"]}
```

- **Status:** accepted
- **Decision:** FRED series must be read through ALFRED vintages, so a query as of D returns the value from the vintage in force on D. ISM releases must be archived as published, with their publication time, because ISM data left FRED on 2016-06-24. History may use ISM's revised seasonally adjusted values, labelled as revised.
- **Parameters:**
  - `fred_vintage_series` = DGS10, INDPRO, TCU, USREC (source: deliverable §3.2, Phase)
  - `ism_ambiguous_band` = 49.5 to 50.5 index points, inclusive; a reading inside it is treated as ambiguous (source: deliverable §3.2, Phase)
- **Rule:** for a FRED series, return the observation from the vintage whose real-time period contains D. For ISM, return the latest archived release whose publication time is known at D (`known-from-rule`).
- **Acceptance tests:**
  - Inputs: DGS10 for 2026-09-30 → expected output: 5.29%
  - Inputs: TCU as of 2026-09-30 → expected output: the value from the vintage in force on 2026-09-30
  - Inputs: the Fed's annual revision of INDPRO and TCU on 2026-11-24, queried as of any date before it → expected output: the pre-revision values (tested with recorded vintages)
  - Fixture: none
- **Constraints and non-goals:** capacity utilization and industrial production from ALFRED stay the main phase inputs where ISM history is revised.
- **Evidence:** `actuator-supply-chain.md` §3.2 (Phase) and §5.1 item 5; grade not assigned; validation rung not assigned
- **Depends on:** known-from-rule
- **Supersedes:** none
- **Open items:** none

### rrx-case-august-ism: the RRX case uses the August 2026 ISM report

```yaml
name: rrx-case-august-ism
status: accepted
decided: 2026-10-03
decided_by: requester
moves_valuation: false
depends_on: [known-from-rule]
supersedes: ["the September 2026 ISM figures in actuator-supply-chain.md revision 4 §4.3"]
parameters:
  - {name: rrx_ism_report, value: "August 2026, published 2026-09-01", source: "actuator-supply-chain.md §4.3"}
app: {spec: [ticket 9, ticket 12], merged: ["PR #19", "PR #34"]}
```

- **Status:** accepted
- **Decision:** The RRX case valued at 2026-09-30 must use the August 2026 ISM report (PMI 54.6, prior 55.6, New Orders 53.7, published 2026-09-01). It must not use the September report, published 2026-10-01, after the valuation date.
- **Parameters:**
  - `rrx_ism_report` = August 2026, published 2026-09-01 (source: deliverable §4.3)
- **Rule:** apply `known-from-rule` to the case's cycle inputs.
- **Acceptance tests:**
  - Inputs: phase classifier with PMI 54.6, prior 55.6, New Orders 53.7 → expected output: early expansion (unchanged)
  - Inputs: the RRX cyclical template → expected output: amplitude 0.126, gap 0.0983, mid-cycle margin 23.19% (unchanged)
  - Fixture: `rrx_reference_case.py`
- **Constraints and non-goals:** an erratum; no reference value changes.
- **Evidence:** `actuator-supply-chain.md` §4.3 erratum and §5.1 item 1; source S17; grade not assigned; validation rung not assigned
- **Depends on:** known-from-rule
- **Supersedes:** the September 2026 ISM figures (PMI 54.5, New Orders 55.3) in revision 4 §4.3
- **Open items:** none

### cycle-turning-point-confirmation: peaks and troughs are confirmed by a 5% move both ways

```yaml
name: cycle-turning-point-confirmation
status: accepted
decided: 2026-10-03
decided_by: requester
moves_valuation: false
depends_on: []
supersedes: ["revision 4 §3.2 peak rule: local maximum before a decline of 5% or more"]
parameters:
  - {name: confirm_threshold, value: 0.05, unit: fraction of the turning point's level, sensitivity: [0.03, 0.05, 0.08], source: "actuator-supply-chain.md §3.2"}
  - {name: min_phase_cycle_monthly, value: [6, 15], unit: months, source: "§3.2"}
  - {name: min_phase_cycle_quarterly, value: [2, 5], unit: quarters, source: "§3.2"}
  - {name: min_phase_cycle_annual, value: [1, 2], unit: years, source: "§3.2"}
  - {name: short_phase_override, value: 0.10, unit: fraction move, source: "§3.2"}
  - {name: amplitude_min_cycles, value: 3, unit: confirmed cycles, source: "§3.2"}
app: {spec: [ticket 12], merged: ["PR #20", "PR #34"]}
```

- **Status:** accepted
- **Decision:** A peak must be confirmed only when the index falls at least `confirm_threshold` below it before it rises the same amount above it; a trough is the mirror image. Turning points must alternate. A turning point inside the last minimum phase, or not yet confirmed, must be marked provisional, and so must a cycle that ends on one.
- **Parameters:**
  - `confirm_threshold` = 5% of the turning point's level, inclusive; sensitivity reported at 3%, 5% and 8% (source: deliverable §3.2)
  - `min_phase_cycle_*` = 6 and 15 months, 2 and 5 quarters, or 1 and 2 years, by data frequency (source: §3.2)
  - `short_phase_override` = 10%: a shorter phase counts if its move is at least this, inclusive (source: §3.2)
  - `amplitude_min_cycles` = 3 confirmed cycles (source: §3.2)
- **Rule:**
  1. Between two peaks with no confirmed trough between them, keep the higher; between two troughs, keep the lower.
  2. Drop a phase shorter than the minimum for its frequency unless its move is at least 10%.
  3. Amplitude = median peak-to-trough decline over the confirmed cycles.
  4. `CYCLE_HISTORY` fires when the amplitude rests on fewer than 3 confirmed cycles, or margins on less than 1 full confirmed cycle.
- **Acceptance tests:**
  - Inputs: annual index 100, 80, 82, 75 → expected output: one cycle, decline 25%
  - Inputs: 100, 80, 86, 75 → expected output: two cycles, declines 20% and 12.8%
  - Inputs: 100, 80, 84, 75 (a rebound of exactly 5%) → expected output: two cycles, 20% and 1 − 75/84; and 100, 80, 83.9, 75 → one cycle of 25%
  - Inputs: RRX organic index 2022 = 100, 2023 92.0, 2024 87.4, 2025 88.1 → expected output: the 2024 trough provisional; `CYCLE_HISTORY` fires with two confirmed cycles; amplitude 0.126, gap 0.0983, mid-cycle margin 23.19% unchanged
  - Fixture: `rrx_reference_case.py`
- **Constraints and non-goals:** prefer quarterly organic data where available; annual reported revenue smooths the amplitude.
- **Evidence:** `actuator-supply-chain.md` §3.2 and §5.1 item 2; source S37 (Bry and Boschan 1971; Harding and Pagan 2002; Pagan and Sossounov 2003; Lunde and Timmermann 2004), thresholds [UNVERIFIED] until opened; grade not assigned; validation rung not assigned
- **Depends on:** none
- **Supersedes:** revision 4 §3.2's peak rule (local maximum before a decline of 5% or more)
- **Open items:** the cycle amplitude panel (§5 open item 8): three RRX cycles are a thin base, the third provisional

### cycle-exposed-margin-check: MARGIN_ABOVE_MID reads the cycle-exposed margin

```yaml
name: cycle-exposed-margin-check
status: accepted
decided: 2026-10-03
decided_by: requester
moves_valuation: false
depends_on: [cycle-turning-point-confirmation]
supersedes: ["revision 4 §3.2 MARGIN_ABOVE_MID on the blended margin"]
parameters:
  - {name: margin_tolerance, value: 2, unit: percentage points above mid-cycle, source: "actuator-supply-chain.md §3.2 Checks"}
app: {spec: [ticket 13], merged: ["PR #21", "PR #37"]}
```

- **Status:** accepted
- **Decision:** `MARGIN_ABOVE_MID` must test the explicit cycle-exposed margins, excluding pass-through lines. A margin more than `margin_tolerance` above the mid-cycle margin must carry a written reason. The blended margin may be shown, for information only.
- **Parameters:**
  - `margin_tolerance` = 2 percentage points above the mid-cycle margin, exclusive (source: deliverable §3.2, Checks)
- **Rule:** for each explicit year and scenario, cycle-exposed margin = cycle-exposed adjusted EBITDA ÷ cycle-exposed sales; flag when it exceeds mid-cycle margin + 2 pp without a reason.
- **Acceptance tests:**
  - Inputs: RRX base case 2027 → expected output: cycle-exposed margin 22.15% beside blended 21.99%; check passes
  - Inputs: RRX highest cycle-exposed margin in any scenario (bull, 2030) → expected output: 24.08%, within 2 pp of 23.19%; passes
  - Inputs: a high-margin pass-through line that trips the blended check → expected output: the cycle-exposed check does not fire; a low-margin line hiding stretch → expected output: the cycle-exposed check fires
  - Fixture: `rrx_reference_case.py`
- **Constraints and non-goals:** mid-cycle margin belongs to the cyclical business only.
- **Evidence:** `actuator-supply-chain.md` §3.2, §4.5 and §5.1 item 3; grade not assigned; validation rung not assigned
- **Depends on:** cycle-turning-point-confirmation
- **Supersedes:** revision 4's `MARGIN_ABOVE_MID` on the blended margin
- **Open items:** none

### pass-through-margin-check: each pass-through line is tested against its own benchmark

```yaml
name: pass-through-margin-check
status: accepted
decided: 2026-10-03
decided_by: requester
moves_valuation: false
depends_on: [cycle-exposed-margin-check]
supersedes: []
parameters:
  - {name: pass_through_tolerance, value: 2, unit: percentage points above the line's benchmark, source: "actuator-supply-chain.md §3.2 Checks"}
app: {spec: [ticket 13], merged: ["PR #21", "PR #37"]}
```

- **Status:** accepted
- **Decision:** `PASS_THROUGH_MARGIN` must test each pass-through line (contracted revenue at its own margin, such as a project backlog) against its own benchmark: a contract or stated margin, or a peer range. A margin more than `pass_through_tolerance` above it must carry a written reason.
- **Parameters:**
  - `pass_through_tolerance` = 2 percentage points, exclusive (source: deliverable §3.2, Checks)
- **Rule:** flag a pass-through line whose margin exceeds its benchmark + 2 pp without a reason.
- **Acceptance tests:**
  - Inputs: RRX E-Pod line at 20% against management's stated 20% → expected output: passes
  - Inputs: the same line at 22.5% without a reason → expected output: fails
  - Fixture: none
- **Constraints and non-goals:** none
- **Evidence:** `actuator-supply-chain.md` §3.2 and §5.1 item 3; source S4; grade not assigned; validation rung not assigned
- **Depends on:** cycle-exposed-margin-check
- **Supersedes:** none
- **Open items:** none

### flags-by-provenance: a flag applies by where its evidence came from

```yaml
name: flags-by-provenance
status: accepted
decided: 2026-10-03
decided_by: requester
moves_valuation: false
depends_on: [known-from-rule]
supersedes: ["applying every flag at every as-of date"]
parameters: []
app: {spec: [ticket 14], adr: "0009", merged: ["PR #22", "PR #40"]}
```

- **Status:** accepted
- **Decision:** A rule-based flag (from a check that uses only facts public at the as-of date) must apply at any as-of date where its check, recomputed on the facts known then, fails. An information-based flag (a restatement, an amended filing, a finding prompted by later events) must apply only from the date its evidence became public; before it, the value as first reported is used. A flag without provenance must be refused.
- **Parameters:** none
- **Rule:** each flag stores its rule ID and version, its provenance (rule or information) and its evidence date; each rule records when it was written. Accuracy is reported twice: as-known (primary, flags by provenance) and cleaned (diagnostic, every flag applied).
- **Acceptance tests:**
  - Inputs: a segment-sum flag written after the as-of date, its inputs public at it → expected output: applied
  - Inputs: a restatement flag queried before its evidence date → expected output: not applied, the original value returned; after it → applied
  - Inputs: the cleaned view → expected output: both flagged facts excluded
  - Inputs: a flag without provenance → expected output: refused
  - Fixture: none
- **Constraints and non-goals:** a rule written after seeing an error counts out of sample only for later periods.
- **Evidence:** expert answers decision 2; `actuator-supply-chain.md` §5.1 item 4; Orphanides (2001) on revised data; grade not assigned; validation rung not assigned
- **Depends on:** known-from-rule
- **Supersedes:** applying every flag at every date
- **Open items:** none

### thesis-break-band-midpoint: the thesis-break band sits exactly halfway between base and bear

```yaml
name: thesis-break-band-midpoint
status: accepted
decided: 2026-10-03
decided_by: requester
moves_valuation: false
depends_on: []
supersedes: ["the 21.0% band in actuator-supply-chain.md revision 4 §4.4"]
parameters:
  - {name: band_position, value: 0.5, unit: fraction of the distance from the bear path to the base path, source: "actuator-supply-chain.md §3.3(d)"}
app: {spec: [ticket 8], merged: ["PR #38", "PR #41"]}
```

- **Status:** accepted
- **Decision:** The thesis-break band must sit exactly halfway between the base and bear paths of the break measure, with no rounding before the midpoint is taken.
- **Parameters:**
  - `band_position` = 0.5 of the distance from the bear path to the base path (source: deliverable §3.3(d))
- **Rule:** band = (base + bear) ÷ 2, on unrounded paths.
- **Acceptance tests:**
  - Inputs: RRX 2027 trailing-four-quarter adjusted EBITDA margin, base 21.9933%, bear 20.1132% → expected output: band 21.05% (0.2105 to four decimals)
  - Fixture: `rrx_reference_case.py`
- **Constraints and non-goals:** none
- **Evidence:** `actuator-supply-chain.md` §3.3(d) and §4.4 (corrected to 21.05%); grade not assigned; validation rung not assigned
- **Depends on:** none
- **Supersedes:** the 21.0% band in revision 4 §4.4, which averaged rounded paths
- **Open items:** none

## Rejected and deferred decisions

- `flags-from-write-date`: rejected; applying a flag only from the date it was written lets through errors the method would have caught at the time (ADR 0009).
