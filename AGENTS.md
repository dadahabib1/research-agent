<!-- agent-kit:begin -->
## agent-kit

This project runs on agent-kit. This block is the kit's: kit updates change it, so put your own
instructions below it. The kit's machinery is in `.agents/kit/`.

Where to go for what:
- **Settings:** `agent-kit.toml` (committed; a change is a PR the user merges) and
  `agent-kit.local.toml` (this machine). Every value and its source:
  `python -I .agents/kit/bin/kitconfig.py show`.
- **Lessons:** `docs/solutions/`, one file per solved problem, written and refreshed by the `ce-compound`
  skill. Never read whole: a ticket's brief names its lessons on its `lessons:` line.
<!-- agent-kit:end -->
