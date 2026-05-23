---
description: "Append a skill usage entry"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise skill-usage entry to this file under `.wiki/orchestrator/`:
- `Skill-Usage-Log.md`

Use the current conversation and selected text, if any, to infer which skills were used and why. Preserve existing content and append a timestamped entry at the end of the file. Use the following template:

### SKL-YYYYMMDDHHMMSS

- Timestamp (UTC):
- Request Type: chat-conversion
- Routing Path: direct | single-agent | multi-agent
- Subagent(s):
- Skills Used (ordered):
- Invocation Reason:
- Outcome Impact: positive | neutral | negative
- Reuse Note:

```yaml
entry_template: |
	### SKL-YYYYMMDDHHMMSS

	- Timestamp (UTC):
	- Request Type: chat-conversion
	- Routing Path: direct | single-agent | multi-agent
	- Subagent(s):
	- Skills Used (ordered):
	- Invocation Reason:
	- Outcome Impact: positive | neutral | negative
	- Reuse Note:
```
