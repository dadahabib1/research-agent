---
format: steer
version: 1
id: <steer-<UTC yyyymmddThhmmssZ>-<4 random hex>: steer-20261017T102000Z-3a9f>
action: <nudge, halt or none>
headline: <one line under 80 characters: t37: t36 merged; READY may go>
written_at: <ISO UTC: 2026-10-17T10:20:00Z>
---
<One paragraph under 500 characters: what the session should do and why. The guard shows it to the session as
STEER <id> from the orchestrator (a nudge, until the state file's steer_ack names this id) or HALT <id> (a halt,
on every call while it stands). For none: nothing more.>
