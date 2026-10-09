# Prompt: real-data reference corpus research

You are the researcher for a personal US equity research app, equity_analyst. Your job is to specify a versioned corpus of real SEC filings and earnings releases, with known correct readings, that the app uses to test its code on real data and to judge whether a reported defect can happen in practice. The requester decides in a decision session; the app's orchestrator builds only on the accepted decision records on main, and pins each one it uses in its lock file.

Read `docs/research/strategy-research-brief.md` first. It holds the situation, settled decisions, standards and deliverable format; this prompt adds only the topic.

## Why the app needs this

- **Asked by:** the app's v2 planning (the requester and the app's orchestrator, 2026-10-05). In v1, review findings were often argued case by case: was an input real or invented? Each impact analysis then collected its own sample, which cost time and was never reused.
- **Blocks:** none directly; it speeds up every v2 ticket's review, and the business-model templates request (`prompts/10-business-model-templates.md`) can test its classification rule on it.
- **Needed by:** no date; earlier is better, because every v2 ticket benefits.

## What the app does today

- **Behaviour:** the app's review rule (its "real-data rule", quoted): a finding counts as *real data* when "the input occurs, or could plausibly occur, in SEC filings, earnings releases or reference inputs of US-listed companies generally, not only the covered company's; when unsure, it is real data". A medium finding blocks a merge when real data can hit it. To settle disputed cases, the app ran one-off impact analyses: 112 earnings-release exhibits from 28 companies (ticket 4, extraction), and 620 filings of 27 companies plus 6,629 filings of 60 companies (ticket 11, segments). Each probe found its own sample; none is kept as a reusable set.
- **Pinned by:** the app's tests use constructed inputs plus RRX's real filings; known limitations are pinned with constructed cases (the app's `tests/research/test_known_limitations.py`).
- **Data and constraints:** `docs/research/app-context.md`, as of 2026-10-05 and app commit `7e89968`. SEC data is public; the app reads it with edgartools.

What the v1 probes found about real filings, to start from:
- filer agents write HTML differently: Workiva raises text with CSS (`position:relative;top:-3.5pt`) hundreds of times per release; footnote marks sit on labels or after numbers depending on the company;
- per-share rows say "per share" or "EPS" in practice; ratio rows sit between dollar rows;
- segment structures change often: in 7 of 27 large companies (2021 to 2026) a new structure first appeared in a 10-Q, 9 times in all (DuPont twice, Pfizer twice, Johnson Controls, Carrier, Stanley Black & Decker, Xylem, Cummins);
- filings accepted in the same second with different values: 2 pairs in 6,629 filings, both from 1994.

## The question

Which filings and releases make a corpus small enough to run in minutes, yet varied enough that a defect that never shows up on it is unlikely to matter? Hypothesis: about 30 companies across industries, sizes, fiscal year-ends and filer agents, each with 8 quarters of filings and earnings releases, plus a list of known edge cases (recasts, amendments, restatements, unusual table layouts), is enough.

## What the app needs back

| Proposed decision name | Question it answers | Parameters expected, with units | Accepted decisions it touches |
|---|---|---|---|
| `corpus-composition` | Which companies and documents, chosen by which rule | companies (count), quarters per company, document types, edge cases (count) | none |
| `corpus-labels` | Which fields carry verified expected readings, and how they were verified | labelled fields (list), labelled documents (count) | `filing-inputs-from-the-store` |
| `corpus-storage-and-versioning` | How the corpus is stored (a manifest of accession numbers and a fetch script, or copies) and versioned | size (MB), fetch time (minutes) | `known-from-rule` |
| `real-data-test-rule` | How a review uses the corpus to label a finding real or invented | none, or a hit-rate threshold (findings per thousand documents) | none |

- **Fixture format:** a CSV manifest (company, CIK, form, accession, period, filer agent, edge-case tags) and a Python fetch-and-check script that loads the manifest with edgartools and asserts each labelled reading, saved in `docs/research/`.
- **Reference case:** RRX's 43 filings since 2016 and its Q4 2025 earnings release (8-K 0000082811-26-000041, EX-99.1) belong in the corpus.
- **What the app must add:** list it in the deliverable (brief §7). Known gaps: a test runner that runs a probe over the corpus.

## Technical evidence

For any claim about what a library, API or data source does: cite its official documentation or source code at a pinned version, and back the claim with a script you ran on real data, recording the script, its output and the versions. Mark an untested claim [UNVERIFIED]. Add a section **Existing tools and prior art**: existing public test sets of SEC filings, XBRL validation suites, and edgartools features for finding filings by form, item and filer agent. SEC requests need a contact identity from the `EDGAR_IDENTITY` environment variable; keep to SEC's 10 requests a second.

## Leading words

- **Corpus:** a fixed, versioned set of real documents with known readings, used to test code on real data.
- **Edge case:** a real document whose shape broke, or nearly broke, a parser (a recast, an amendment, a superscript footnote, a ratio row).
- **Filer agent:** the software or service that produced a filing's HTML (Workiva, Donnelley, Toppan Merrill and others).

## Known issues

- Labels cost effort: verified expected readings are feasible for a subset, not every figure in every document.
- The corpus must stay point-in-time: an amendment filed later is a separate document with its own acceptance time.

## Steps

### 1. Read

Read the brief, `app-context.md`, the decision records named above, and `actuator-supply-chain.md` §3.2 (segments and the cyclical template).

Done when you can state, in three sentences, how v1 settled real-data questions, why that was slow, and what a reusable corpus must contain.

### 2. Composition

Choose the companies and documents, with the rule that chose them (industry spread, size, fiscal year-end, filer agent, history of recasts and amendments), and the edge cases, each with its document and why it is hard.

Done when the manifest exists and every edge case found by the v1 probes above is in it or replaced by a stronger example.

### 3. Labels and checks

Decide which readings are labelled (for example: consolidated revenue, segment totals, share counts, one earnings-release table figure per release) and verify them against the filing itself.

Done when the fetch-and-check script runs over the whole manifest and every labelled reading passes, with its run time recorded.

### 4. Use in review

Write the rule by which a review labels a finding real data or invented input with the corpus, and what happens when a finding reproduces outside it.

Done when the rule covers a finding that reproduces on the corpus, one that does not, and one found on a document outside it.

### 5. Write the deliverable

Write `docs/research/real-data-corpus.md` in the brief's format (§7), with **Existing tools and prior art** and **What the app must add**, and the manifest and script beside it.

Done when the brief's done-criterion is met and every decision in "What the app needs back" is proposed, deferred with a reason, or shown to be unnecessary.

Standards: brief §6, plus "Technical evidence" above.
