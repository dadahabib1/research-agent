# Model, effort and cost

## Effort

- Claude's effort setting controls how many tokens it spends, thinking included.
  - **API:** `output_config.effort`, with levels low, medium, high, xhigh and max where the model supports them. The API default is high.
  - **Anthropic's guidance:** start with xhigh for coding and agentic work and high for other intelligence-sensitive work. Step down only after measuring that quality holds.
- **Claude Code** offers four ways to set it:
  - `/effort` during a session;
  - `--effort` at launch;
  - `effortLevel` in settings;
  - the `CLAUDE_CODE_EFFORT_LEVEL` environment variable.

  A skill or subagent can also set `effort` in its frontmatter, which overrides the session while it runs. Verify against the Claude Code model-configuration docs.

## Defaults for research runs

- **Research and synthesis runs** (agentic and long): xhigh, or high when cost matters more.
- **Independent review:** high.
- **Extraction, formatting and log tidying:** medium or low, only after checking quality on a sample.
- The plugin's subagents carry their effort in their definitions, so every run gets it: the researcher runs at xhigh and the reviewer at high, both on the session's model. A run's log header takes them from this line.

## Model

Use the strongest available model for synthesis and review. Use a cheaper model for bulk extraction only once it has been checked against a labelled sample.

## Cost controls

- Run one task per session, and stop when every completion criterion is met.
- Use bounded reads: targeted searches and limited output.
- For pipelines built on the API: batch work that can wait, and cache shared context such as the brief.
- Declare the budget at intake, and report spend at hand-over.
