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
10. **Name units, denominators and bases.**
    *Incident:* limits and fractions did not say which total they were shares of: the whole, an allocation within it, or one part of that allocation. Later, a symbol in a rule's formula was measured at current value in the code and left undefined in the decision, so a rise in that value could trigger actions nobody had seen.
    *Check:* every limit and ratio names its denominator, and every symbol in a rule's formula has a definition line with its basis (for example at cost or at current value, before or after fees) and a test that changes the basis.

## C. Time and point-in-time

11. **Give every input a knowledge timestamp.**
    *Incident:* an analysis dated September 30 used a survey published October 1. A later suggestion to use another figure published October 1 had the same flaw. In a later run, a rule that dated a re-saved file by its fetch time would have handed an as-of test the previous edition and flipped its outcome; the independent review caught it.
    *Check:* every input records when it became observable (observations when recorded, releases at publication, a file's contents at their edition's publication even when the file was re-saved or fetched later), and that time is asserted to fall on or before the as-of date. As-of tests run on the day before and the day after each edition's publication.
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
22. **Verify data availability and licence; where terms forbid automated access, use a regulator's or registry's filed copy.**
    *Incident:* a data plan assumed a data series was on a public database that had removed it years earlier. Later, data files sat behind terms that forbid automated access, and the same data was in filings with a regulator.
    *Check:* confirm the source, access, licence and history before designing around a dataset. Every automated download's host permits it, or the source is a regulator's or registry's filed copy.
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
37. **Constants come from the owning source, not memory; a figure fed by an ILLUSTRATIVE constant is ILLUSTRATIVE.**
    *Incident:* an organisation's classification code was typed from memory; the owning registry's record gave a different code, and a membership assertion failed. Later, a constant labelled illustrative in a script fed a coefficient the deliverable called measured; computed from a sourced input, the coefficient moved a limit outside its band in 22% of windows.
    *Check:* every constant in a script cites its source and date, and every constant labelled ILLUSTRATIVE is traced to the deliverable: each figure it feeds is computed from a sourced input instead, or labelled ILLUSTRATIVE.
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

## I. From plugin runs under 0.6.0 (2026-10-09 and 2026-10-10)

42. **Isolate measurement environments, and record library versions.**
    *Incident:* a version probe ran inside a sibling checkout's environment and reported an older library version than the latest release.
    *Check:* every script command in the log uses the isolated form, and each output names the library versions it imported.
43. **On a host that needs an identity, fetch raw or report the gap.**
    *Incident:* summarising fetches to such a host went out without the identity, in two consecutive runs; the lesson filed after the first did not stop the second.
    *Check:* the notes' fetch labels show no summarising fetch to an identity host.
44. **Cache negative responses, and keep failed response bodies.**
    *Incident:* the reviewer's offline re-run met 15 uncached 404s, and the bodies of 15 failed fetches were not kept, so their cause stays unknown.
    *Check:* an offline re-run from the cache makes no network request, and each recorded failure has a saved body.
45. **Name samples before their results; disclose rules and parameters revised after first results, and log each change when it is made.**
    *Incident:* two samples were added and two rules revised after their first results, and the first draft did not say so. In a later run, a parameter was changed within a minute of an implausible reference result and committed without a log entry; the reviewer found it from commit times.
    *Check:* each sample appears in the plan or an amendment dated before its results, and each revised rule's Verification row gives the earlier result and the reason. Every parameter change made after a result was seen has a log amendment, time-stamped before its commit, naming the results seen before it.
46. **Write scripts with backslash escapes to files, not shell heredocs.**
    *Incident:* a heredoc turned a regular-expression escape into a control character.
    *Check:* scripts with escapes are files in the run's folder, run by path.
47. **Test a style-based proxy on light and dark backgrounds.**
    *Incident:* a first proxy for hidden text counted white backgrounds as hidden (200 of 234 documents).
    *Check:* the proxy's tests include white-on-dark and dark-on-white cases.
48. **Keep the main session's context bounded.**
    *Incident:* a main session let its context grow to about 1M tokens before an automatic compaction; calls above 500k of context made 77% of its re-reading, and the main session was about 62% of the run's input-equivalent tokens, while thinking was under 3%.
    *Check:* the main session hands off or compacts at phase boundaries (after the draft commit, before the review fixes), the log records each one, and no main-session call runs above a stated ceiling (for example 300k tokens).
49. **Copy subagent returns by script, from the channel the harness delivers them on, and edit documents in place.**
    *Incident:* a main session re-typed every researcher return into notes files, so each return sat in its context twice, and wrote the deliverable in full five times: about 750k characters of its own writes. In later runs, copy scripts read the last text of a subagent's transcript: one captured a 156-character interim note instead of a 27,093-character return, and one found no text because the returns arrived as a hand-back call.
    *Check:* each notes file matches its subagent's return exactly, as delivered (final message or hand-back call): same length, same first and last lines. After the first draft the deliverable changes by edits, not whole-file writes.
50. **Scripts print a summary; their full output goes to files.**
    *Incident:* command output was the largest single source of a main session's context growth (about 540k characters over 218 commands), more than any file it read.
    *Check:* each script's printed output stays under a stated size, and its full output is in the run's output folder (entry 33 covers reading it back).
51. **Give a long measurement a time limit, a resumable cache and a checkpoint.**
    *Incident:* a survey hit a 30-minute background limit and had to be re-run, and a container restart lost a running delegation; both resumed only from the cache or by relaunching.
    *Check:* the log names each long run's time limit and cache, and the checkpoint commit before each long delegation.
52. **Say how the main session's spend can be measured, and name the counter behind every figure.**
    *Incident:* two runs reported only their subagents' self-reported tokens (about 1.7M and 2.4M). Measured from one run's transcript, its subagents processed about 60M raw tokens, and its main session about twice the subagents' total. A later run's subagent transcripts summed 1,896 output tokens for subagents the harness reported at 2.24M tokens, two figures easy to confuse.
    *Check:* the spend line gives the run's start and end times and where the main session's tokens can be read (the local transcript, or the account's usage before and after). Every figure names its counter (a harness-reported total or a transcript sum, and which token kinds), and self-reports are labelled as final context plus output.
53. **Put a zero-event bound and its expected count on one unit.**
    *Incident:* a first draft multiplied a bound on a cluster's latest document by a count of clusters, which holds only when every document of an affected cluster is affected; the independent review caught it.
    *Check:* each bound-to-count conversion names one unit, and its verdict is tested at both ends of every unresolved input.
54. **Assert a unique key when merging selections.**
    *Incident:* two selection rules named the same item, and the merged list held it twice until review.
    *Check:* the build, or its fixture, fails on a repeated key.

## J. From plugin runs under 0.6.1 (2026-10-10)

55. **Read binary data files by script, and say so in the delegation.**
    *Incident:* researchers spent calls trying to read five spreadsheets the raw fetcher refused; every value from them came from scripts in the end.
    *Check:* each value taken from a binary file cites a script's output, not a researcher's reading, and each delegation names the binary files left to scripts.
56. **Test parameters that act on the same data together, on a replay of the history.**
    *Incident:* a delay that was fine on its own, combined with a limit, flagged 13 periods by construction; only the joint replay showed it, and the delay was shortened.
    *Check:* a replay under all proposed rules together shows no flag that the rules' combination creates by construction.
57. **Score a rule on a holdout drawn after the rule is frozen, and labelled before the labeller can see the rule's output for it; report that score.**
    *Incident:* a rule revised after its first scored run scored about ten points higher on the sample it was revised on than on a holdout drawn after it was frozen. In the same run, the rule's outputs for the whole population, holdout included, were committed minutes before the holdout was labelled, and a blind relabel found that both disagreements matched the rule's output.
    *Check:* every accuracy figure says whether the rule was frozen before its sample was drawn and labelled. The holdout labels' commit precedes every rule output covering its members, or a labeller without access to the outputs relabels a random subset.
58. **Key periods of varying length by their end date, with a tolerance, never by their midpoint.**
    *Incident:* keying yearly periods by their midpoint merged or dropped periods for about one entity in seventeen, those whose periods end near mid-year, and shortened the series a signal read.
    *Check:* every period-keyed series asserts one value per period and reports its internal gaps.
59. **Run a new extraction pattern on one known document before a batch; a zero count is a parsing failure until shown otherwise.**
    *Incident:* two batch measurements returned zero matches because a field name and a dimension name were written differently in a second file format.
    *Check:* each extraction script asserts at least one hit on a named known document before its batch result is used; only then is a zero a null result (entry 5).
60. **Give every step of an ordered rule a test case that reaches that step.**
    *Incident:* in two versions of a rule, codes meant for a later step were captured by an earlier, broader range, unnoticed until a population-wide review.
    *Check:* the fixture holds one constructed case per step, asserting that step's own result.
61. **Check a weight field's total and its largest values before weighting with it.**
    *Incident:* self-reported weights summed to about 76 times their plausible total, because about 1% of entities reported them at the wrong scale.
    *Check:* every weighted share states the weight total, the largest weights and any correction applied.
62. **Resume a delegated agent stopped by a usage limit, where the harness can resume it; don't relaunch it.**
    *Incident:* two of six parallel evidence-gathering agents stopped mid-task on a usage limit and were resumed after the reset with their context.
    *Check:* the log names each stop and resume, and the notes header says which run's return it holds.
63. **Compare options on their totals to the horizon's end; a deferred cost is not a saving.**
    *Incident:* one rule appeared to halve a cost until the cost still owed at the horizon's end was counted, when the rules came within 4.3%; a run with the inputs swapped turned a small lead into a tie.
    *Check:* each comparison reports the costs incurred and the costs still owed at the horizon's end, and a run with the inputs swapped.
64. **Show every variant a simulation ran in the comparison table, with what the recommendation gives up against each.**
    *Incident:* the two rules with the best outcome on the decision's own measure were in the simulation's output but not in the deliverable's table.
    *Check:* every variant key in a simulation's output appears in the deliverable's table, or is named as left out with the reason.
