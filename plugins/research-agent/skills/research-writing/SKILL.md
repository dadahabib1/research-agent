---
name: research-writing
description: The writing standard for research deliverables, which one decision-maker reads and must act on. Use whenever writing, drafting, editing or reviewing a research deliverable, decision memo, decision record, brief, summary of findings, research prompt, handoff or review, and before handing any of them over. Covers answer-first structure, writing for a smart outsider, evidence prose with citations, grades and calibrated hedges, sentence-level editing, decisions an implementing agent can turn into specs, and a final pass for AI writing patterns.
---

# Research writing

A research deliverable has one reader who decides: a decision-maker who must act on it. They read it once, they are busy, and they were not inside the research. The text succeeds when that reader can state the decision, the recommendation and the reason after one reading. Once decisions are accepted, a second reader arrives: an implementing agent who turns them into specs and tickets (see "Writing for an implementing agent").

Work the levels in order: document, reader, evidence, sentence, then the final pass. What counts as a source, a label or a grade is set by the research-protocol skill (`references/standards.md`); this skill covers how to write them down.

## 1. Document: answer first

- **Open with the answer and the decisions.** The first screen says what the research found, what the reader must decide, and the recommendation for each decision. Method and background come after, or go in an appendix.
- **Introduce only what the answer needs.** If the reader needs context first, give three sentences at most: the situation they already accept, what changed, and the question that change raises. Then answer it.
- **Build the structure from the reader's questions.** List the questions the decision-maker will ask, in the order they will ask them. Each becomes a section. Under each, group the supporting points so that:
  - each group answers one question and its heading summarises the group;
  - the points in a group are of one kind (all reasons, all steps, or all options);
  - the points run in a stated order: by time, by structure, or by importance;
  - together they cover the question, and no two overlap.
- **Write headings that state findings.** "Momentum survives costs only in large caps" tells the reader something; "Results" does not. A reader who reads only the headings should get the argument. Questions the reader would ask also work as headings. Use sentence case and keep text between a heading and its first subheading.
- **One topic per paragraph.** Put the topic sentence first; the rest of the paragraph supports it. End on the point, not on a digression.
- **Use tables for comparisons.** When options are compared on two or more attributes, use a table: one row per option, one column per attribute, units in the column headers. Introduce each table with a sentence saying what it shows. Sort rows by what matters to the decision. For rules with conditions, use an if-then table.
- **Give every number its context.** Each number has units, a denominator, a date or period, and a REAL or ILLUSTRATIVE label. A REAL number cites its source.
  - Weak: "Turnover fell 40%."
  - Strong: "Annual portfolio turnover fell from 120% to 72% of portfolio value (REAL; backtest 2015 to 2024, `scripts/turnover.py`)."
  - Both examples are ILLUSTRATIVE; the second shows the label a real number would carry.
- **Report small, conditional and null results as results,** in the place a positive result would have gone.

## 2. Reader: write for a smart outsider

Picture one reader: intelligent, willing to work, and outside your field. Write as if you were showing that reader something you both can see, in a conversation between equals. Neither lecture nor flatter them.

The main obstacle is the curse of knowledge: once you know something, it is hard to imagine not knowing it. Its symptoms are labels you coined during the research ("the v2 filter"), skipped steps, abbreviations, and abstractions that only an expert unpacks. To counter it:

- **Define each leading word on first use,** in one plain sentence, before relying on it. A leading word is one of the few concepts the document thinks with.
- **Use one word for one thing.** Once "drawdown" means peak-to-trough loss, it means that everywhere. Rotating synonyms makes the reader wonder whether a new thing has appeared.
- **Prefer a plain name to an abbreviation.** "The model" beats "MRFF-2". Keep abbreviations to the two or three the reader will meet constantly, and spell them out on first use.
- **Give the concrete example before the abstraction.** Show one worked case with real or labelled numbers, then state the general rule it illustrates.
- **Talk about the subject, not the document.** Cut "This section will discuss" and "As mentioned above"; a heading already signposts.
- **Test the draft on an outsider.** Give it to someone, or to a fresh agent, without your context. Ask them to state the decision, the recommendation and the main reason in their own words. Rewrite wherever their account goes wrong.

## 3. Evidence prose

Write each finding in a fixed order: the claim, its evidence with a citation, the evidence grade, then the caveat.

> **Claim.** Value tilts added 1.1 percentage points a year before costs in US large caps. **Evidence.** A replicated study of 1963 to 2019 data found this premium in 9 of 10 decades [Source 2024, table 3]. **Grade.** B: peer-reviewed and replicated, but gross of costs. **Caveat.** The premium was near zero from 2007 to 2020, so the decision should hold if it stays there.

The numbers and the source in this example are ILLUSTRATIVE.

- **The claim** is one specific sentence that could be wrong, with its number.
- **The evidence** names the source, what it measured and over which period, and cites it where the claim is made.
- **The grade** follows the protocol's evidence-by-claim-type table: A to D for a literature claim, the sample and script for a measurement, the version or date for a documented fact, and the label ([ESTABLISHED], [DEBATE], [MY JUDGMENT], [PROVIDED]) where one applies.
- **The caveat** is the limitation most likely to change the decision. One sharp caveat beats a list of every possible weakness.

Hedge in proportion to the evidence, once, where it applies.

| Evidence | How to state it |
|---|---|
| Grade A | Plainly: "X reduces Y by Z." |
| Grade B | "The evidence indicates X," then the main limitation. |
| Grade C | "One study found X"; name the study. |
| Grade D, opinion, untested | "X is untested"; say what test would settle it. |
| Measured (a script on a named sample) | Plainly, with the sample and script: "On the 2019 to 2025 sample (`scripts/x.py`), X is Z." |
| Documented (the owning source at a version or date) | Plainly, with the version or date: "Version 1.64 does X [docs, 2026-03]." |
| [PROVIDED] by the requester or project | As given, naming the provider and date: "The requester reports X (stated 2026-10-01)"; no grade. |

- Do not stack hedges ("may possibly suggest"). One qualifier, chosen to match the grade, is enough.
- Do not hedge what is certain, such as arithmetic or the text of a rule. Do not state as certain what was never tested.
- Keep findings and recommendations apart. A recommendation is labelled [MY JUDGMENT] and sits in the decisions section.
- Show conflicting sources side by side, each with its grade, and say which is stronger and why.

## 4. Sentence level

- **Active voice:** name who acts ("the reviewer re-ran the script"); use the passive only when the actor is unknown or beside the point.
- **Concrete words:** "lost money in 7 of 10 years", not "underperformed"; put the action in a verb ("we tested", not "testing was carried out").
- **Positive form:** say what is ("missed the deadline"), not what isn't ("did not meet the deadline"); keep "not" for real denials.
- **Needless words cut:** "to" for "in order to", "because" for "due to the fact that"; delete "it is worth noting that".
- **Parallel lists:** every item takes the same grammatical form.

When editing, run `references/plain-language.md`.

## 5. Final pass: AI writing patterns

Once the draft meets levels 1 to 4, read it once more for the habits of machine-generated prose. Wikipedia's editors keep a field guide to them, [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing). Treat each pattern as something that wastes the reader's attention, not as proof of who wrote the text. Fixing the surface is not enough: if a sentence holds nothing once the pattern is removed, delete the sentence.

Look for, and fix:

- **Puffed-up importance.** Sentences that call something crucial, pivotal or a testament to something, instead of saying what follows from it. Replace them with the consequence for the decision.
- **Unnamed authorities.** "Experts agree" or "research shows" without a citation. Cite the source or cut the claim.
- **Tacked-on commentary.** A clause hung on the end of a sentence that gestures at meaning ("..., highlighting the need for vigilance"). Either make the point with evidence or drop it.
- **Stock vocabulary.** Words such as delve, underscore, landscape, tapestry, robust, seamless and multifaceted, especially in clusters.
- **Avoiding plain verbs.** "Serves as", "stands as" or "boasts" where "is" or "has" would do.
- **Set-piece contrasts.** "Not just X, but Y" and "It's not X; it's Y" used for rhythm rather than to correct a real misreading.
- **Reflexive threes.** Lists of three adjectives or examples where the evidence supports two, or four.
- **Formatting as decoration.** Bold scattered through prose, dashes in place of commas and full stops, emoji, title-case headings, and bullet lists that break a single argument into fragments that belong in a paragraph.
- **Chat inside the deliverable.** "Great question", "I hope this helps", "Let me know if you'd like", "Certainly!". The deliverable addresses the decision, not the conversation.
- **Formula endings.** "In conclusion", a closing paragraph about challenges and future prospects, or a summary that repeats the summary.
- **Leftovers.** Placeholder text, notes about knowledge cutoffs, and citations whose links or identifiers do not resolve. Open every link and DOI, and check that it supports the claim.

## Prompts, briefs and reviews

The same standard applies when the reader is an agent or a reviewer.

- **A prompt or brief** is read by an agent with none of your context: the smart outsider, exactly. State the job and the done-criterion first, define the leading words, and give a worked example. See the research-protocol skill's `references/prompt-writing.md` for structure.
- **A review finding** leads with the defect, then its evidence, then the fix expected. Number the findings and rank them by how much each could change the decision.

## Writing for an implementing agent

After the decision session, an agent reads the decision records and writes specs and tickets from them. It reads literally, and it may read one decision without the rest of the document. Write each decision, in the deliverable and in the decision record (`new-research-project/templates/decision-record.md`), for that reader.

- **Make each decision stand alone.** A decision states everything needed to implement it: its parameters, its rule, its acceptance tests and its constraints. Never rely on "as above", "the usual threshold" or a definition three sections back; repeat the value or name the decision it depends on.
- **One term, one meaning.** Reuse the deliverable's leading words exactly, spelled the same way and with the same capitalisation. If a decision needs a new term, define it inside the decision.
- **State exact values.** Each value has its unit, its denominator and, where it varies, its allowed range with inclusive or exclusive bounds: "rebalance when a holding's weight drifts 5 percentage points or more from target (share of portfolio market value; range 3 to 7, inclusive)". Inside a decision, never write "about", "roughly" or "~".
- **Label a statement's status where the record's fields do not already give it,** as one of:
  - [FACT]: sourced or computed, with its section;
  - [ASSUMPTION]: taken as true until confirmed, with who confirms it;
  - [DECISION]: accepted in the decision session;
  - [OPEN]: unresolved, with the evidence that would resolve it.

  A recommendation stays [MY JUDGMENT] until the requester accepts it; then it becomes a [DECISION].
- **Use normative words in decisions, and hedges in evidence.** In a decision, "must" is a requirement, "must not" a prohibition, and "may" a permitted option. Do not use "should", "ideally" or "consider" there. Keep uncertainty in the evidence, where it is graded; a decision either holds or is deferred.
- **Give acceptance tests as concrete cases.** Each test has its inputs and its expected output, exact enough for the agent to write the test without asking: "target 60%, actual 65.0% → rebalance; actual 64.9% → hold". Point to a fixture file when one exists.
- **Name each decision stably.** Give it a short descriptive name in lowercase with hyphens, such as `rebalance-drift-band`, and use that name everywhere. Never rename or renumber a decision; a change is a new decision that supersedes the old one.
- **Point to evidence; don't restate it.** Each decision cites the deliverable section and commit that support it ("deliverable §4.2 at commit `abc1234`"), with its evidence grade and validation rung. The agent needs the reference, not the argument.

The values in this section's examples are ILLUSTRATIVE.

## Done when

- The first screen states the answer and each decision with its recommendation.
- Every heading states a finding or asks a question the reader would ask.
- Every number has units, a denominator, a date and a REAL or ILLUSTRATIVE label.
- Every leading word is defined on first use and used consistently.
- Every finding gives its claim, cited evidence, evidence kind and grade, and caveat, with hedges matching the evidence.
- The sentence-level edit and the AI-pattern pass are done.
- An outsider, person or fresh agent, can restate the decision and its reason.
- Every decision stands alone: a stable name, exact parameters, a normative rule, at least one acceptance test, and a pointer to its evidence.

## References

- `references/plain-language.md`: a condensed checklist from the US Federal Plain Language Guidelines. Run when editing.
- `references/SOURCES.md`: every source behind this skill, with its URL, licence and what was used.
