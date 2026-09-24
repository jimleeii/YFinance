---
description: "Append a learning backlog item"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise learning-backlog item to this file under `.wiki/orchestrator/`:
- `Learning-Backlog.md`

Use the current conversation and selected text, if any, to infer the actionable improvement. Preserve existing content and append a timestamped entry at the end of the file. Keep the entry focused and include the following template:

### LRN-YYYYMMDD-XXX

- Priority: low | medium | high | critical
- Problem:
- Proposed Change:
- Scope: routing | skills | contract | acceptance-gate | output-format
- Safety Check:
- Owner: Orchestrator
- Status: pending | in_progress | done | rolled_back
- Linked Pattern: [Behavior-Patterns](Behavior-Patterns.md#PAT-YYYYMMDD-XXX)

```yaml
entry_template: |
	### LRN-YYYYMMDD-XXX

	- Priority: low | medium | high | critical
	- Problem:
	- Proposed Change:
	- Scope: routing | skills | contract | acceptance-gate | output-format
	- Safety Check:
	- Owner: Orchestrator
	- Status: pending | in_progress | done | rolled_back
	- Linked Pattern: [Behavior-Patterns](Behavior-Patterns.md#PAT-YYYYMMDD-XXX)
```
