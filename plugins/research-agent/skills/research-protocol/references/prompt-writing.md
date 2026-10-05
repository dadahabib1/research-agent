# Writing research prompts, briefs and handoffs

## A research prompt

This structure worked in past runs.

1. **Role and job** in two sentences, ending with where the output goes and who decides.
2. **A pointer to the shared brief** for the situation, settled decisions, standards and deliverable format. The prompt adds only its topic.
3. **The question**, with the requester's views stated as hypotheses.
4. **Leading words**: the few concepts the run thinks with, each defined once.
5. **Known issues**: problems found so far, each to be resolved or listed as open.
6. **Steps**, each ending in "Done when" with a criterion a reviewer can check and that demands completeness ("every candidate has a grade, an effect size and a verdict"). The first step is Read, with a criterion that proves comprehension, for example "state X, Y and Z in three sentences".
7. **The deliverable**: path, sections, reference cases, and the done-criterion for the whole run.
8. **Standards**: a pointer to the brief, plus any topic-specific additions.

## A brief

A brief holds what every run shares: the situation, settled decisions, leading words, the program in dependency order, standards, the deliverable format, and open inputs. Prompts point to the brief; nothing in it is repeated in prompts.

## A handoff

A handoff holds an agent's operating loop: select a task, check inputs, research, write, self-review, hand over. Each step has a completion criterion. Add working rules, suggested skills and setup notes.

## Writing rules

- Write prompts, briefs and handoffs to the research-writing skill; their reader is an agent with none of your context.
- Name sources as "starting points to verify, not conclusions".
- State the target behaviour positively. Keep prohibitions for hard guardrails, and pair each with the positive target.
- Use the same leading words in the brief, the prompts and the code.
- Keep each meaning in one place, and point to it instead of repeating it.
- Include "stop and report if an input is missing".
- Ask for honest verdicts explicitly.
- Set the model and effort for the run (`effort-and-cost.md`).
- Split dependent topics into separate runs, with a review gate between them.

## Default deliverable template

1. **Decisions to grill**: for each decision, its name (stable, lowercase with hyphens), the question it answers, the options, their trade-offs, the recommendation, the proposed parameters with units, its evidence grade and its validation rung.
2. **Summary.**
3. **Components**, each in the template: Decision · Evidence (graded) · Method · Data · Checks · Accuracy metric · Presentation (what the requester sees and records) · Phase.
4. **Validation plan.**
5. **Reference cases**, with every input and output, and a script with assertions. Hand-computed values are marked.
6. **Changes** to existing decisions or methods, with reasons.
7. **Open questions**, and the evidence that would resolve them.
8. **Sources.**

A revision adds a change log at the top, mapping each review item to where it is resolved, and returns the complete document.
