---
description: "Append a behavior pattern entry"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise pattern entry to this file under `.wiki/orchestrator/`:
- `Behavior-Patterns.md`

Use the current conversation and selected text, if any, to infer the recurring pattern. Preserve existing content and append a timestamped entry at the end of the file. Keep the entry focused and include the following template:

### PAT-YYYYMMDD-XXX

- Signal:
- Frequency:
- Impact:
- Affected Subagent(s):
- Likely Cause:
- Proposed Policy Change:
- Status: candidate | applied | rolled_back
- Compaction Batch: CB-YYYYMMDD-XX
- Evidence: [Behavior-Log](Behavior-Log.md#OBS-YYYYMMDD-XXX)

```yaml
entry_template: |
	### PAT-YYYYMMDD-XXX

	- Signal:
	- Frequency:
	- Impact:
	- Affected Subagent(s):
	- Likely Cause:
	- Proposed Policy Change:
	- Status: candidate | applied | rolled_back
	- Compaction Batch: CB-YYYYMMDD-XX
	- Evidence: [Behavior-Log](Behavior-Log.md#OBS-YYYYMMDD-XXX)
```
