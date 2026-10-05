---
name: research-protocol
description: Rigorous protocol for research work, covering evidence reviews, methodology design, decision memos, source-checked reports, and prompts, briefs or handoffs for research agents. Use it whenever a task asks to research, investigate, look into, evaluate the evidence for, or design a method for something, and whenever writing or reviewing a research prompt, brief or deliverable. It covers pre-research intake, source standards, verifying numbers in code, point-in-time discipline, review loops, and turning findings into decisions.
---

# Research protocol

A research run turns a question into evidence a decision-maker can act on. This protocol keeps every run consistent, whatever the topic: the same intake, standards, verification and review. Domain rules live in references; read the one for your domain.

## Roles

- **The requester** owns decisions: scope, money, risk, and every judgment call.
- **The researcher** owns facts: finding, verifying and grading them. Look up what can be looked up. Ask the requester only for decisions, and for facts about their own situation.
- **A reviewer** (a person or a second agent) checks the deliverable before any decision is made.

## The protocol

Work the steps in order. Each ends on a completion criterion.

1. **Set up the run.** Choose the model and effort level for the task type (`references/effort-and-cost.md`).
   Done when both are set explicitly and the budget is known.

2. **Intake.** Work through `references/intake.md`. Reconcile conflicting signals. Ask for what you cannot look up, using `references/questioning.md`.
   Done when the intake record exists and every input is answered, looked up, or recorded as a labelled assumption.

3. **Frame.** Write the questions the research must answer. Map each to the decision it informs and to its claim type:
   - an effect exists;
   - a specific rule works at the requester's scale and costs;
   - a judgment adds value.

   Treat the requester's own views as hypotheses to test.
   Done when every decision has at least one question and every question serves a decision.

4. **Plan.** For each question, record the sources to try, the method, the validation rung that would settle it (`references/standards.md`), the reference cases needed, and when to stop.
   Done when no question lacks a method and a stopping point.

5. **Gather evidence.**
   - Use primary sources first, and open every source you cite.
   - Log every query and every source, used or rejected, with the reason.
   - Check each recurring source for its latest edition.
   - Record conflicts side by side.

   Done when every question has graded evidence or an explicit "not found".

6. **Verify numbers.**
   - Re-derive every quantitative claim in code from its stated inputs.
   - Build reference cases with assertions, including boundary and invariance tests.
   - Check every input's knowledge timestamp against the as-of date.

   Done when the scripts run green, or each failure is documented as a finding.

7. **Write.** Write to the standard in the research-writing skill. Use the requester's template, or the default in `references/prompt-writing.md`: decisions first, then findings, components, validation plan, reference cases, changes, open questions, sources. Report small, conditional and null results as results.
   Done when every template field is filled and the research-writing skill's done-criteria hold.

8. **Self-review.** Run the checklist in `references/review.md`.
   Done when every item passes or is listed as open.

9. **Hand over.** Deliver for review. Then hold a decision session (`references/questioning.md`) in which the requester accepts, rejects or defers each decision.
   Done when the decisions are recorded. Only accepted decisions move on to spec or action.

10. **Revise and learn.** Answer each review item in a change log, return the complete document, and update fixtures with any rule change. Add each new failure mode to `references/takeaways.md`.
    Done when the change log maps every review item to a resolution.

## Core rules

Each rule's incident and check are in `references/takeaways.md`.

- **Reproduce before you rely.** A claim nobody re-computed is a lead, not a fact.
- **Numbers come from sources or executed code.** Mark hand-computed values until a script reproduces them.
- **Every input carries a knowledge timestamp.** Nothing observable only after the as-of date enters the analysis.
- **Primary sources first.** Label secondary and snippet-only sources; mark memory as [UNVERIFIED].
- **Show conflicts between sources side by side,** graded.
- **Test every rule at its boundaries and invariances** before trusting it.
- **Run every check you specify on your own reference cases.**
- **Every ratio, limit and percentage names its denominator and units.**
- **Check feasibility before adopting a criterion:** power, sample size, time to result, data availability, licence, cost at the real scale.
- **Find the field's standard method before inventing one.**
- **Reconcile conflicting signals about the requester's situation, then ask.** Statuses that look exclusive can coexist.
- **A restatement of the requester's ideas is a draft, not research.** Label drafts; decisions go through the decision session.
- **Carry unresolved inputs as bounds.** Act only when the decision holds at every bound.

## References

- `references/intake.md`: the pre-research intake checklist and procedure. Read at step 2.
- `references/standards.md`: sources, citations, labels, evidence grades and the validation ladder. Read at steps 4, 5 and 7.
- `references/prompt-writing.md`: how to write research prompts, briefs and handoffs for agents, plus the default deliverable template. Read when writing for another agent, and at step 7.
- `references/questioning.md`: how to ask questions in rounds, with recommended answers. Read at steps 2 and 9.
- `references/review.md`: self-review and reviewer checklists, revision rules and the decision session. Read at steps 8 to 10.
- `references/takeaways.md`: rules learned from past runs, each with its incident and check. Read at the start of every run; add to it at step 10.
- `references/finance.md`: rules for finance, investing and economics topics. Read for any such topic.
- `references/effort-and-cost.md`: model, effort and cost settings. Read at step 1.
- The research-writing skill: the writing standard for deliverables, briefs, prompts and reviews. Read at step 7, and whenever writing for the requester or another agent.
