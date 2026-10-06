# Domain rules: <field> (<project>/docs/research/domain-rules.md)

The rules of this field that the general research protocol cannot know. The researcher applies them, the reviewer checks them, and the brief's §6 points here. Write each rule as a statement a reviewer can check, followed by its check, the way the protocol's `takeaways.md` writes its entries. Keep every heading; write "none known" rather than delete one. The example lines are ILLUSTRATIVE and belong to no real project.

## 1. When information counts as known

Decide the knowledge-timestamp convention for each kind of input, and which data vintage an analysis uses.

- <Rule.> Check: <how a reviewer verifies it>.
- ILLUSTRATIVE: Market prices count as known at that day's close, statistical releases at publication, filings at the regulator's acceptance time; an analysis uses the vintage in force at its as-of date, not later revisions. Check: every input in the log names the timestamp rule it follows.

## 2. What settles each claim type here

For literature claims: what a valid study or test looks like in this field (what results must be net of, significance bars, replication, out-of-sample rules). For measurements: the smallest sample that counts, and how a sample is named. For documentary facts: which sources count as owning.

- <Rule.> Check: <...>.
- ILLUSTRATIVE: An effect counts as established only net of realistic costs at the requester's scale and replicated out of sample; in-house tests need |t| > 3 because of multiple testing. Check: each literature finding says whether it is net or gross, and whether it is replicated.

## 3. Standard methods to reuse

Methods the field already has for problems a run is likely to meet, each with its owning source. A run cites one of these or justifies the deviation.

- <Method: what it is for; owning source.>
- ILLUSTRATIVE: Turning-point dating: a published algorithm with amplitude filters, not a home-made rule. Check: a noisy test series does not create extra cycles.

## 4. Units, denominators and bases

The denominators and bases every ratio, limit and percentage must name, and the ones that are easy to confuse.

- <Rule.> Check: <...>.
- ILLUSTRATIVE: A position cap names its base: total portfolio, equity allocation or active sleeve. Check: every limit in a decision names one of these.

## 5. Feasibility at the requester's scale

Costs, minimum sizes, sample sizes, time to result and other constraints that change the answer at the requester's actual scale.

- <Fact or rule, with its source and date.> Check: <...>.
- ILLUSTRATIVE: Per-order minimum fees make methods with many small trades infeasible below a stated account size. Check: every method's cost is computed at the requester's scale, not per unit.

## 6. Data sources, access and licence

The owning sources to go to first (endpoints, data files, registries), what is paid or licensed for personal use only, and what is known to be missing from public databases. This is also the field's search list for the protocol's `searching.md`.

- <Source: what it owns; access; licence; checked on <date>.>
- ILLUSTRATIVE: The regulator's filing API owns filing dates and figures as first reported; free, no key, rate-limited. Check: filing-based numbers cite the API record, not a summary site.

## 7. Advice and regulatory boundaries

What the research must not give, and who must confirm what. Such rules enter as sourced parameters.

- <Rule.> Check: <...>.
- ILLUSTRATIVE: Tax rules enter as parameters with their source; the deliverable names the professional who must confirm them. Check: no decision states a tax outcome as a fact.

## 8. Domain words

Leading words whose meaning here differs from everyday use or from other fields, each defined once. The brief's §4 may point here.

- **<term>**: <definition in this field>.
