---
description: "Append an error log entry"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise error entry to these files under `.wiki/orchestrator/`:
- `Behavior-Log.md`
- `Project-Context-Log.md`

Use the current conversation and selected text, if any, to infer the event being logged. Preserve existing content and append a timestamped entry at the end of each file. Include the failure mode, likely cause, and the next corrective step if known.
