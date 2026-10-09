# Pre-research intake

Intake gathers everything a run needs before research starts. Many failures in past runs traced back to intake: a fact assumed instead of asked, an input dated after the decision date, a constraint nobody stated. The run's shape sets the depth: a new research run works the whole list; a revision reuses the original record and adds what the review items need; a clarification reads the brief and the project context and asks only when blocked.

## Inputs to collect

**Purpose and decisions**
- The decisions the research informs, who makes them, and by when.
- What the requester will do differently depending on the answer.
- Acceptance criteria: what makes the deliverable good enough.

**Requester and audience**
- Expertise level and how results should be presented, for example a learning format that shows what was done, why, the evidence, and the judgment to record.
- Language and formatting preferences.

**Scope**
- What is in scope and out of scope.
- Settled decisions. These are inputs, not questions; reopening one needs evidence.
- Known issues and prior findings, each to resolve or build on.

**The requester's situation** (facts that change answers)
- The requester's circumstances that change answers: where they are, what resources and budget they have, what tools and accounts they can use.
- Check each fact against other signals in the conversation and documents. When signals conflict, ask.
- These facts stay in the main session. They are never passed to the researcher subagent, which reads the open web (`untrusted-content.md`).
- They are the project's data. In a research repository that is public, keep them in a file the repository excludes, and refer to them by label in the brief and the log.

**Constraints**
- Legal and regulatory boundaries, including what would count as advice the research must not give (the project's domain rules, heading 7).
- Data access, licences, and the budget for paid data (domain rules, heading 6).
- Tools in the research environment: web search; fetch tools, and whether each returns the raw page or a summary; code execution; repository access. Record them in the log header. If code cannot run, plan how numbers will be verified.
- Time and money budget for the run.

**Time**
- The as-of date for the analysis.
- The rule for when information counts as known (domain rules, heading 1).

**Standards**
- Source hierarchy, evidence by claim type, labels and grades (`standards.md`), plus the project's domain rules named in its brief §6.
- Tolerance for practitioner or secondary sources.

**Context and prior work**
- Documents to read, previous deliverables, reviewer feedback, templates, and the project's context file where one exists. Facts taken from these that the run cannot verify are labelled [PROVIDED: project].

**Deliverable and validation**
- Format for the run's shape, path or delivery channel, sections, expected length.
- Reference cases and scripts required, and who runs them.

**Review and decisions**
- Who reviews, the gates between dependent runs, how decisions are recorded, and what happens to accepted decisions.

**Run settings**
- Shape, model, effort level and budget (`effort-and-cost.md`).

## Procedure

1. Extract every answer you can from the request, the attached documents and earlier conversation.
2. Look up facts the environment can answer: files, documentation, public sources. These are the researcher's job, not the requester's.
3. List what is still missing, and sort each gap:
   - decisions, and personal facts only the requester knows: ask them using `questioning.md` (one round when the gaps are few and independent, more rounds when answers depend on each other);
   - everything else: record as an explicit, labelled assumption.
4. Reconcile conflicts. When a stated fact disagrees with another signal, ask. First check whether both can be true at once (for example, two statuses that look exclusive, such as two memberships with different rules, can both apply).
5. If a required input is missing (a file, or a prerequisite deliverable), stop and report it.
6. Write the intake record at the top of the research log: each answer with its source (looked up, requester, project context, or assumption) and its date.

Done when the intake record exists and every input is answered, looked up, or recorded as a labelled assumption.
