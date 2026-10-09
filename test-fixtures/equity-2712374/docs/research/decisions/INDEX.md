# Decision index

Every decision in this folder, one row each, so an agent can find one by name without opening every record. Update this table in the same pull request that adds or changes a decision record. Each decision's machine-readable block (a fenced `yaml` block at the top of its subsection) is the authority; this table only points to it.

Search: `grep -rn "^name: <decision-name>" docs/research/decisions/` finds a decision's block; `grep -rn "status: accepted" docs/research/decisions/` lists the accepted ones.

| Decision | Status | Decided | Record | Supersedes |
|---|---|---|---|---|
| known-from-rule | accepted | 2026-10-03 | methodology-revision-5-2026-10-03.md | none |
| macro-data-vintages | accepted | 2026-10-03 | methodology-revision-5-2026-10-03.md | none |
| rrx-case-august-ism | accepted | 2026-10-03 | methodology-revision-5-2026-10-03.md | September 2026 ISM figures in revision 4 §4.3 |
| cycle-turning-point-confirmation | accepted | 2026-10-03 | methodology-revision-5-2026-10-03.md | revision 4 §3.2 peak rule |
| cycle-exposed-margin-check | accepted | 2026-10-03 | methodology-revision-5-2026-10-03.md | revision 4 MARGIN_ABOVE_MID on the blended margin |
| pass-through-margin-check | accepted | 2026-10-03 | methodology-revision-5-2026-10-03.md | none |
| flags-by-provenance | accepted | 2026-10-03 | methodology-revision-5-2026-10-03.md | applying every flag at every date |
| thesis-break-band-midpoint | accepted | 2026-10-03 | methodology-revision-5-2026-10-03.md | the 21.0% band in revision 4 §4.4 |
| theme-flip-cross-bound-verdict | accepted | 2026-10-04 | app-v1-build-2026-10-04.md | none |
| fact-store-same-time-conflicts | accepted | 2026-10-04 | app-v1-build-2026-10-04.md | none |
| filing-inputs-from-the-store | accepted | 2026-10-04 | app-v1-build-2026-10-04.md | hand-entered RRX inputs, for the app |
| early-close-known-limitation | accepted | 2026-10-04 | app-v1-build-2026-10-04.md | none |
