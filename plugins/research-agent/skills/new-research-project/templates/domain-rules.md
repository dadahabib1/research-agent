# Domain rules: <field> (<root>/domain-rules.md)

The rules of this field that the general research protocol cannot know. The researcher applies them, the reviewer checks them, and the brief's §6 points here. Keep every heading; write "none known" under a heading rather than delete it.

- **Precedence.** Accepted decision records in `decisions/` override this file. A decision that changes a rule here changes the rule in the same pull request.
- **Changes.** The decider changes this file by pull request, or a decision session does when it accepts a decision or a `[field]` lesson. A run proposes a change, with a rule ID or "new", in its deliverable's "Changes to existing decisions or methods" section and its hand-back; it never edits this file.
- **Decision-critical** means an input, value or claim that a recommendation, decision or reference case depends on. A rule scoped `decision-critical` does not apply to background facts.

Each rule is a `###` subsection under its heading:

```markdown
### <rule-id>: <the rule, one sentence a reviewer can check>
- Check: <how a reviewer verifies it>
- Scope: <decision-critical | all>
- Source: <owning source with a date, a decision record name, an incident (a log path), or the requester with a date>
- Added: <YYYY-MM-DD>
- Host: <consumer name>
```

- **ID:** lowercase words joined by hyphens, unique in this file, never renamed or reused. An edit keeps the ID.
- **Retiring:** a rule is never deleted. It gets a line `- Retired: <YYYY-MM-DD>; <reason>`, so citations in old logs still resolve.
- **Host** (optional): set it only when the configured consumer's code implements the rule and no accepted decision already states the rule's fact, because the consumer pins that decision and one fact pinned twice drifts twice.

The quoted examples under each heading are ILLUSTRATIVE, each from a different field, and belong to no real project. Replace them with this project's rules.

## 1. When information counts as known

Decide the knowledge-timestamp convention for each kind of input, and which data vintage an analysis uses.

> ILLUSTRATIVE (clinical trials):
>
> ### results-known-at-registry-posting: A trial result counts as known when it is posted to the trial registry, not at the trial's completion date.
> - Check: every trial result in the log names its registry posting date.
> - Scope: decision-critical
> - Source: the registry's data-element definitions, checked <date>
> - Added: <date>

## 2. What settles each claim type here

For literature claims: what a valid study or test looks like in this field (what results must account for, significance bars, replication). For measurements: the smallest sample that counts, and how a sample is named. For documentary facts: which sources count as owning.

> ILLUSTRATIVE (software performance):
>
> ### benchmark-needs-warm-runs: A latency measurement counts only from at least 30 runs after warm-up, reported as a median with its spread.
> - Check: every latency figure names its run count, its warm-up and its spread.
> - Scope: decision-critical
> - Source: requester, <date>
> - Added: <date>

## 3. Standard methods to reuse

Methods the field already has for problems a run is likely to meet, each with its owning source. A run cites one of these or justifies the deviation.

> ILLUSTRATIVE (public-health surveillance):
>
> ### outbreak-detection-standard-algorithm: Outbreak signals use the agency's published aberration-detection algorithm, not a home-made threshold.
> - Check: a reference case with a known injected outbreak raises a signal, and a flat series raises none.
> - Scope: decision-critical
> - Source: the agency's method documentation, <version>
> - Added: <date>

## 4. Units, denominators and bases

The denominators and bases every ratio, limit and percentage must name, and the ones that are easy to confuse.

> ILLUSTRATIVE (ecology):
>
> ### density-names-its-area: Every population density names its area unit and whether the area is total habitat or surveyed plots.
> - Check: every density in a decision names one of the two bases.
> - Scope: all
> - Source: requester, <date>
> - Added: <date>

## 5. Feasibility at the requester's scale

Costs, minimum sizes, sample sizes, time to result and other constraints that change the answer at the requester's actual scale.

> ILLUSTRATIVE (education):
>
> ### effect-detectable-at-class-count: A proposed evaluation states the smallest effect it can detect at the requester's number of classes, from a power calculation.
> - Check: every proposed evaluation shows its power calculation and the class count it assumes.
> - Scope: decision-critical
> - Source: requester, <date>
> - Added: <date>

## 6. Data sources, access and licence

The owning sources to go to first (endpoints, data files, registries), what is paid or licensed for restricted use, and what is known to be missing from public databases. This is also the field's search list for the protocol's `searching.md`.

> ILLUSTRATIVE (energy metering):
>
> ### meter-data-from-the-operator: Interval readings come from the grid operator's published data files, which own them; aggregator dashboards are secondary.
> - Check: every decision-critical reading cites the operator's file and its retrieval date.
> - Scope: decision-critical
> - Source: the operator's data portal, checked <date>
> - Added: <date>

## 7. Advice and regulatory boundaries

What the research must not give, and who must confirm what. Such rules enter as sourced parameters.

> ILLUSTRATIVE (transport):
>
> ### safety-limits-as-parameters: Regulatory safety limits enter as parameters with their source and version, and the deliverable names the authority that must confirm them.
> - Check: no decision states a compliance outcome as a fact.
> - Scope: all
> - Source: requester, <date>
> - Added: <date>

## 8. Domain words

Leading words whose meaning here differs from everyday use or from other fields, each defined once as a rule. The brief's §4 may point here.

> ILLUSTRATIVE (law):
>
> ### term-consideration: "Consideration" means something of value exchanged that makes a promise enforceable, not thoughtfulness.
> - Check: the word is used only in this sense.
> - Scope: all
> - Source: the jurisdiction's contract-law treatise, <edition>
> - Added: <date>
