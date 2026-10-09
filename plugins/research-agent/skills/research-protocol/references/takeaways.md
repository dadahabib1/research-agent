# Takeaways from past research runs

Each entry gives the rule, the incident that taught it, and a check a reviewer can run. Entries 1 to 35 come from the project the plugin was generalised from (runs of 2026-10-02 to 2026-10-05), reworded to keep each mechanism in field-neutral words; entries from 36 come from runs under the plugin. Runs propose candidates in their change logs and pull requests (protocol step 10); the plugin's maintainer adds accepted ones here, after checking that no existing entry covers the rule.

## A. Evidence and sources

1. **Trace claims to the source that owns them.**
   *Incident:* a technical definition and several key figures first came from a blog post, a document-sharing upload and a blog summary of a paper; review required the primary sources.
   *Check:* every citation is the owning source, or is labelled secondary.
2. **Check for the latest edition.**
   *Incident:* an annual scorecard's year-end edition was cited although a newer mid-year edition had just been published.
   *Check:* search for a newer release of every recurring source.
3. **Snippets are not sources.**
   *Incident:* several figures came from search snippets of pages that could not be opened.
   *Check:* snippet-only claims are labelled and kept off decision-critical paths.
4. **Show conflicts; don't pick.**
   *Incident:* two summaries of the same scorecard gave different long-horizon figures.
   *Check:* conflicts appear side by side, with a grade.
5. **Report null results plainly.**
   *Incident:* an attractive theme turned out to be immaterial to the first case's result, and the research said so.
   *Check:* a materiality test comes before deep analysis, and small results are stated as results.

## B. Numbers and verification

6. **Reproduce before you rely.**
   *Incident:* re-running a brief's worked example in code exposed structural errors the prose hid: a missing transition stage, inconsistent intermediate quantities, the wrong timing convention, and stale and mismatched inputs.
   *Check:* every quantitative claim is re-derived from its stated inputs, and each error found becomes an automated check.
7. **Numbers come from executed code.**
   *Incident:* a research agent without code execution hand-computed its test values. Later revisions needed exact values computed elsewhere, and some values stayed unverified.
   *Check:* each test value's provenance is labelled (script-verified or hand-computed), and hand values are verified before use.
8. **Run your own checks on your own examples.**
   *Incident:* a reference case did not implement the method its document specified, and failed a check the same document defined.
   *Check:* every specified check runs against every reference case.
9. **Test invariances and boundaries.**
   *Incident:* a gate compared a quantity that included a compensation term against a hurdle that excluded it, so a fairly priced case looked like an opportunity; a reviewer's table of outcomes across values of that term exposed it.
   *Check:* include tests whose correct answer is known by construction (a case that is fair by construction passes no gate, whatever its compensation term; symmetric inputs give symmetric outputs).
10. **Name units and denominators.**
    *Incident:* limits and fractions did not say which total they were shares of: the whole, an allocation within it, or one part of that allocation.
    *Check:* every limit and ratio names its denominator.

## C. Time and point-in-time

11. **Give every input a knowledge timestamp.**
    *Incident:* an analysis dated September 30 used a survey published October 1. A later suggestion to use another figure published October 1 had the same flaw.
    *Check:* every input records when it became observable (observations when recorded, releases at publication), and that time is asserted to fall on or before the as-of date.
12. **Take jointly estimated inputs from the same date.**
    *Incident:* two jointly estimated inputs were taken from different dates after one of them had moved, and the conclusion flipped.
    *Check:* matched inputs share a date. When they drift apart, report a range and say whether it sits above, below or across the threshold.
13. **Use the data vintage in force at the time.**
    *Incident:* designing indicators raised the choice between revised and first-released data. Revised data embeds information that arrived later.
    *Check:* use the vintage in force at the as-of date.
14. **Watch for hindsight through flags.**
    *Incident:* excluding data that was flagged as wrong years later would make past accuracy look better than it really was.
    *Check:* rule-based flags are recomputed as of the date; flags based on later information apply only once that information was public.

## D. Rules, logic and methods

15. **Find the field's standard method first.**
    *Incident:* a home-made cycle-dating rule let a small rebound count as a new cycle. Standard turning-point algorithms with amplitude filters already solve this.
    *Check:* cite the standard method or justify the deviation, and add noisy test series.
16. **Compare like with like.**
    *Incident:* a check compared a blended figure, which included a part outside the method's scope, with a benchmark computed only on the part in scope.
    *Check:* the benchmark and the quantity share the same base.
17. **Separate axes before choosing.**
    *Incident:* two options were treated as alternatives, although one describes how decisions are made and the other how long their effects last. Separately, two statuses looked exclusive but both applied.
    *Check:* ask whether two options lie on different axes or can coexist.
18. **Prefer established estimation methods to intuition.**
    *Incident:* arbitrary scenario weights were replaced by a published discretization method with documented accuracy.
    *Check:* each judgment parameter cites a method, or is labelled [MY JUDGMENT] with a calibration plan.
19. **Make decisions that hold under uncertainty.**
    *Incident:* with one rate input unresolved, the verdict differed between bounds. The rule became "act only if the verdict holds at every bound".
    *Check:* unresolved inputs are carried as bounds all the way to the decision.
20. **Write interim rules.**
    *Incident:* research on validation methods was still pending while other runs needed a standard.
    *Check:* every pending rule has an explicit interim version and a trigger for replacing it.

## E. Feasibility

21. **Check power before adopting a criterion.**
    *Incident:* rollout gates required statistical significance that would take decades at a personal decision rate.
    *Check:* every statistical criterion comes with sample size, power and time to result. Infeasible criteria are recalibrated or declared infeasible.
22. **Verify data availability and licence.**
    *Incident:* a data plan assumed a data series was on a public database that had removed it years earlier.
    *Check:* confirm the source, access, licence and history before designing around a dataset.
23. **Compute costs at the real scale.**
    *Incident:* methods designed without a scale broke at the requester's real scale, through minimum fees and indivisible units.
    *Check:* compute costs at the requester's actual scale.

## F. The requester

24. **Reconcile, then ask.**
    *Incident:* a requester's short answer about their legal status was taken literally despite other signals about where they lived, and the plan had to be redone.
    *Check:* when a stated fact conflicts with another signal, ask before building on it.
25. **A restatement is not research.**
    *Incident:* a first pass on a topic mostly played back the requester's own ideas, with a few known findings attached. The requester rejected it.
    *Check:* the requester's views are framed as hypotheses and tested against evidence.
26. **Drafts stay drafts.**
    *Incident:* the requester declined to turn first-draft answers into a specification.
    *Check:* drafts are labelled, and only decisions accepted in a decision session move on.
27. **Facts are the researcher's job.**
    *Incident:* questions worked best when they asked the requester only for decisions and personal facts, each with a recommended answer.
    *Check:* no question asks for something the researcher could look up.
28. **Keep advice boundaries.**
    *Incident:* legal and regulatory rules mattered to every recommendation, but they are personal and complex.
    *Check:* such rules enter as sourced parameters, for a qualified professional to confirm.

## G. Process and cost

29. **Keep one source of truth.**
    *Incident:* writing the shared context once, in a brief that six prompts point to, kept those prompts consistent.
    *Check:* no meaning lives in two places.
30. **Match the venue to the work.**
    *Incident:* strategy questions answered in chat produced drafts. Evidence needed research runs, and numbers needed code.
    *Check:* chat for decisions, research runs for evidence, code for numbers.
31. **Put gates between dependent runs.**
    *Incident:* later topics depend on decisions made in earlier ones.
    *Check:* a run starts only when its prerequisites are accepted.
32. **Keep a research log.**
    *Incident:* reviewing a run is faster with its queries, sources and rejections on record, and the log feeds this file.
    *Check:* every run keeps a log.
33. **Use bounded reads.**
    *Incident:* an unbounded search through a long transcript dumped a huge block of text into context.
    *Check:* read with targeted queries and output limits.
34. **Set run settings explicitly.**
    *Incident:* early prompts never stated a model or effort level.
    *Check:* model and effort are set for every run.
35. **Stop on missing inputs.**
    *Incident:* an early prompt told the agent to stop and ask if anything was missing. Agents that fill gaps with guesses produce confident errors.
    *Check:* a missing input stops the run with a report.

## H. From the first plugin run (system review v1, 2026-10-05)

36. **A summarising fetch is not the page.**
    *Incident:* a fetch tool's summary of a published calendar invented a date the page's footnotes did not contain; two other summary-derived dates had to be marked [UNVERIFIED] or rejected.
    *Check:* decision-critical numbers, dates and quotations come from a raw fetch or a second route, or carry the summary-fetched label.
37. **Constants come from the owning source, not memory.**
    *Incident:* an organisation's classification code was typed from memory; the owning registry's record gave a different code, and a membership assertion failed.
    *Check:* every constant in a script cites its source and date.
38. **An error page is not a document.**
    *Incident:* two 403 responses were saved as `.pdf` files and counted as fetched sources.
    *Check:* a fetched file is opened and its first page read before it enters the Sources table.
39. **Compare numbers as numbers.**
    *Incident:* a duplicate check compared values as strings, so nine of ten "conflicts" were rounding artefacts.
    *Check:* comparisons apply the standard's rounding rule, and a known-duplicate fixture passes.
40. **One sample per ratio.**
    *Incident:* a share was computed with a numerator from one sample and a denominator from another, and the rule it fed was never run.
    *Check:* every ratio names the sample of both numerator and denominator, and the rule runs on a fixture.
41. **Set the run's settings before it starts.**
    *Incident:* the first plugin run recorded "effort not set; treated as high" although the researcher agent specifies xhigh, and spend was reported only after review.
    *Check:* the log header records shape, model and effort before intake, and the hand-over reports spend.
