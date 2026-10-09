# Prompt: industries and peers research

You are the researcher for a personal US equity research app, equity_analyst. Your job is to design how the app defines industries and peer sets from point-in-time data, without survivorship bias, and how industry-level analysis (industry cycles, peer comparisons, analogue panels) feeds the single-stock analysis. The requester decides in a decision session; the app's orchestrator builds only on the accepted decision records on main, and pins each one it uses in its lock file.

Read `docs/research/strategy-research-brief.md` first. It holds the situation, settled decisions, standards and deliverable format; this prompt adds only the topic.

## Why the app needs this

- **Asked by:** the app's v2 planning (the requester and the app's orchestrator, 2026-10-05). The brief's version plan puts "baskets and industries" in v2. The methodology's open item 8 asks for a survivorship-free peer panel to replace RRX's thin three-cycle amplitude base (`actuator-supply-chain.md` §5).
- **Blocks:** the v2 spec's industry tickets (not yet written).
- **Needed by:** no date.

## What the app does today

- **Behaviour:** the app has no peer sets or industry data of its own. Industry enters in three places:
  - the bottom-up beta is weighted across two Damodaran industries (Electrical Equipment; Machinery), entered by hand;
  - the analogue rule recorded with each assumption names an industry, the cycle phase, a size bucket ("large cap" at $10B) and the catalyst type; v1 has no analogue panel, so it records one rule per analysis;
  - the cycle amplitude comes from RRX's own history (three cycles, the third provisional), with the peers TKR, PH, ROK and the predecessors Rexnord and Altra proposed but not loaded.
- **Pinned by:** the app's discount-rate tests (relevered beta 1.3879) and its analogue-record tests.
- **Data and constraints:** `docs/research/app-context.md`; accepted decisions `cycle-turning-point-confirmation` and `known-from-rule`. The app reads SEC data for any filer, including companies that later delisted.

## The question

How should the app define an industry and a company's peers at a past date, and what should industry-level analysis contribute to a single-stock verdict? Hypotheses: SEC's SIC codes, refined by segment structure, give free point-in-time peer sets; industry cycles dated from peers' aggregated organic revenue give a sturdier amplitude than one company's history; peer multiples serve as a cross-check, never as the valuation; a "basket" in v2 means a set of companies analysed together for monitoring, distinct from the fund layer's baskets of funds (`prompts/01-fund-layer.md`).

## What the app needs back

| Proposed decision name | Question it answers | Parameters expected, with units | Accepted decisions it touches |
|---|---|---|---|
| `peer-set-rule` | How a company's peers are chosen at a past date, survivorship-free | minimum peers (count), signals with thresholds | `known-from-rule` |
| `industry-cycle-method` | How industry cycles are dated and how they feed a company's amplitude | weights, minimum confirmed cycles (count) | `cycle-turning-point-confirmation` |
| `analogue-panel` | How the analogue panel for assumptions is built and refreshed | panel size (count), history (years) | none |
| `peer-cross-check` | What peer comparisons the report shows, and whether any affects the verdict | metrics and their units | none |
| `basket-definition` | What a basket is in the app, and how it differs from the fund layer's | none | none |

- **Fixture format:** a CSV of RRX's peer set as of 2026-09-30 with the signals that chose each peer, and a Python script with assertions for the industry amplitude computed from it, saved in `docs/research/`.
- **Reference case:** RRX as of 2026-09-30: its peer set, and the amplitude from peers set beside its own 0.126.
- **What the app must add:** list it in the deliverable (brief §7). Known gaps: loading many companies (`prompts/07-system-review-v1.md` sizes this).

## Technical evidence

Measure what the free sources give: SEC's submissions API (SIC codes and their history), its frames API (one concept for every filer in a period, suited to industry aggregates), and filings of delisted companies. Cite official documentation at a pinned version and back each claim with a script run on real data, recording the script, its output and the versions; mark an untested claim [UNVERIFIED]. Add a section **Existing tools and prior art**, covering industry classification datasets and their licences. SEC requests use the `EDGAR_IDENTITY` environment variable, at most 10 a second.

## Leading words

- **Peer set:** the companies the app compares a company with at a given date.
- **Survivorship-free:** including companies that existed at the date and later delisted, merged or failed.
- **Basket:** see the question; the deliverable defines it.

## Known issues

- SIC codes are coarse and sometimes stale; the deliverable should say how often they misplace a company, from a sample.
- RRX merged with Rexnord's process and motion-control business in 2021 and bought Altra in 2023; its history mixes predecessors.

## Steps

### 1. Read

Read the brief, `app-context.md`, `actuator-supply-chain.md` §3.2 and §5 (open item 8), the business-model templates deliverable (`business-model-templates.md`, a prerequisite), and the decision records named above.

Done when you can state, in three sentences, where industry enters the app today, what open item 8 asks, and how templates group companies.

### 2. Peer sets

Write the peer-set rule and apply it to RRX and to a sample of other companies, including one that later delisted.

Done when each sample company has a peer set with its signals, and the rule's misplacements are listed.

### 3. Industry cycles and analogues

Date an industry cycle from peer aggregates and compare its amplitude with RRX's own; specify the analogue panel.

Done when the RRX comparison is computed by script and the panel has its size, history and refresh rule.

### 4. Write the deliverable

Write `docs/research/industries-and-peers.md` in the brief's format (§7), with **Existing tools and prior art** and **What the app must add**.

Done when the brief's done-criterion is met and every decision in "What the app needs back" is proposed, deferred with a reason, or shown to be unnecessary.

Standards: brief §6, plus "Technical evidence" above.
