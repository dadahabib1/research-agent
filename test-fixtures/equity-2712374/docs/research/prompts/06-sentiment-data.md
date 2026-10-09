# Prompt: sentiment research, pass 2 (data, costs, integrity, collection protocol)

You are the sentiment researcher for a personal US equity research app. Your job is to find sources that can deliver the measures `sentiment-methodology.md` selected, within budget and terms, and to write the v4 collection protocol that keeps later forward tests honest.

Read `docs/research/strategy-research-brief.md` first; this prompt adds only the topic.

## The question

Pass 1 decided what to measure. Now:
- Which sources can supply those measures at this budget (brief §3)?
- Under which terms, with which timestamps and how much history?
- How must the data be collected, stored and scored so that tests run on it are point-in-time?

## Leading words

- **Point-in-time record**: the raw item, its source, publication timestamp, retrieval timestamp and licence, plus every score with the model and prompt version that produced it.
- **Rescoring**: computing a new score for old items. Allowed only under a new version label, never overwriting the original.

## Known issues

- An LLM scoring pipeline conflicts with the app's rule that no number comes from an LLM (ADR 0003). Brief §8 says how to propose changing it for sentiment; the collection protocol must keep scores reproducible and checkable.
- Reddit is not available lawfully, and speculative retail talk is the gap: see `sentiment-starting-points-2026-10-09.md`. The budget can rise for a source that captures speculative sentiment; cost each route at about 5 and about 50 companies. Rank sources by fit to the goal, and by broad collection with our own name-and-theme linking, not by ticker search.

## Steps

### 1. Read

Read:
- the brief;
- `app-context.md`;
- `sentiment-methodology.md`;
- `equity-research-brief.md` §9.4–9.5 (a source survey as of October 2, 2026; starting points to re-verify);
- `sentiment-starting-points-2026-10-09.md` (the requester's direction, a probed source survey as of October 9, 2026, rough costs and open questions; starting points to re-verify).

Done when you can list the measures to source and the budget left for them.

### 2. Source survey

For each measure, survey candidate sources on their official pages. Record coverage, history depth, timestamps, rate limits, price, terms (personal use, redistribution, AI processing) and reliability. Include:
- free official data: SEC filings including 8-K and Form 4, FINRA short interest, FRED;
- news, for example GDELT and licensed news APIs;
- social platforms;
- search interest;
- options and fund-flow data.

Done when every selected measure has at least one source that fits the budget and terms, or is marked unsourceable with the cheapest option named.

### 3. Integrity

Specify defences against:
- bots and manipulation;
- duplicated and syndicated stories;
- prompt injection in the text being scored;
- survivorship in source coverage;
- LLM look-ahead when scoring older items.

Done when each threat has a check a script can run.

### 4. Collection protocol

Specify what is stored from the first day of v4:
- the point-in-time record schema;
- retention;
- the licence log;
- the scoring pipeline, with pinned model and prompt versions;
- the rescoring policy;
- daily cost within budget, Claude scoring included.

Done when a coding agent could build the collector and the forward-test datasets from the protocol alone.

### 5. Write the deliverable

Write `docs/research/sentiment-data-protocol.md` in the brief's format (§7). Reference cases: a sample day of records for two companies with their comparative scores, and the monthly cost estimate.

Standards: brief §6.
