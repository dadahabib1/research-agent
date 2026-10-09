# Research lock

Every accepted decision record from `dadahabib1/equity_research` that this repository builds on, pinned to the research commit it was read at. Research results and decision records stay in equity_research; this file only records what was read, so a later change there is found (CLAUDE.md, "Research").

## How it is maintained

- **Add a row** when a spec, ticket or ADR starts relying on a decision, in the same pull request (`docs/agents/research.md`, "Consuming a decision"). The content hash comes from `python scripts/research_drift.py --hash <record> <decision>`.
- **Check for drift** with `python scripts/research_drift.py`: at every orchestrator startup, and before writing any spec or ticket. It lists decisions changed, superseded, no longer accepted or missing on equity_research's main, accepted decisions not yet in this lock, and rows still pending.
- **Update a row** only after its change has gone through "Consuming a decision" again: new commit, new hash, new date.
- **Pending rows** name the equity_research pull request they wait for; the orchestrator replaces "pending" with that merge's commit once it is merged.

## Locked decisions

| Decision | Record | Research commit | Content hash | Used by | Read |
|---|---|---|---|---|---|
| known-from-rule | docs/research/decisions/methodology-revision-5-2026-10-03.md | 3edc7b9 | 5cb4d62b0cda | spec tickets 1, 9 | 2026-10-05 |
| macro-data-vintages | docs/research/decisions/methodology-revision-5-2026-10-03.md | 3edc7b9 | 920ef06eba10 | spec ticket 9 | 2026-10-05 |
| rrx-case-august-ism | docs/research/decisions/methodology-revision-5-2026-10-03.md | 3edc7b9 | fa332652b197 | spec tickets 9, 12 | 2026-10-05 |
| cycle-turning-point-confirmation | docs/research/decisions/methodology-revision-5-2026-10-03.md | 3edc7b9 | c2cd15039353 | spec ticket 12 | 2026-10-05 |
| cycle-exposed-margin-check | docs/research/decisions/methodology-revision-5-2026-10-03.md | 3edc7b9 | 73a68c9f7365 | spec ticket 13 | 2026-10-05 |
| pass-through-margin-check | docs/research/decisions/methodology-revision-5-2026-10-03.md | 3edc7b9 | c706e7b5b5c0 | spec ticket 13 | 2026-10-05 |
| flags-by-provenance | docs/research/decisions/methodology-revision-5-2026-10-03.md | 3edc7b9 | dd98606c2f6b | spec ticket 14; ADR 0009 | 2026-10-05 |
| thesis-break-band-midpoint | docs/research/decisions/methodology-revision-5-2026-10-03.md | 3edc7b9 | 7f3f6abc7025 | spec ticket 8 | 2026-10-05 |
| theme-flip-cross-bound-verdict | docs/research/decisions/app-v1-build-2026-10-04.md | 3edc7b9 | 454d52b25960 | spec tickets 7, 10 | 2026-10-05 |
| fact-store-same-time-conflicts | docs/research/decisions/app-v1-build-2026-10-04.md | 3edc7b9 | 86b5ce383634 | spec ticket 15 | 2026-10-05 |
| filing-inputs-from-the-store | docs/research/decisions/app-v1-build-2026-10-04.md | 3edc7b9 | e25efbfc5826 | spec ticket 11 | 2026-10-05 |
| early-close-known-limitation | docs/research/decisions/app-v1-build-2026-10-04.md | 3edc7b9 | 54296acf6e1b | spec "Known limitations"; ticket 15 | 2026-10-05 |
