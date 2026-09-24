---
description: "Append a debugging log entry"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise debugging entry to these files under `.wiki/orchestrator/`:
- `Runbook.md`
- `Learning-Backlog.md`

Use the current conversation and selected text, if any, to infer the event being logged. Preserve existing content and append a timestamped entry at the end of each file. Record what was investigated, what was learned, and the next debugging step.
