---
description: "Append a runbook change record"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise runbook change record to this file under `.wiki/orchestrator/`:
- `Runbook.md`

Use the current conversation and selected text, if any, to infer the change being recorded. Preserve existing content and append a timestamped entry at the end of the file. Include the following template for change records:

### CHG-YYYYMMDD-XXX

- Date:
- Trigger Pattern:
- Change Applied:
- Expected Effect:
- Validation Window:
- Observed Result:
- Decision: keep | revise | rollback
- Related Entries: [Behavior-Patterns](Behavior-Patterns.md#PAT-YYYYMMDD-XXX), [Learning-Backlog](Learning-Backlog.md#LRN-YYYYMMDD-XXX)

```yaml
entry_template: |
	### CHG-YYYYMMDD-XXX

	- Date:
	- Trigger Pattern:
	- Change Applied:
	- Expected Effect:
	- Validation Window:
	- Observed Result:
	- Decision: keep | revise | rollback
	- Related Entries: [Behavior-Patterns](Behavior-Patterns.md#PAT-YYYYMMDD-XXX), [Learning-Backlog](Learning-Backlog.md#LRN-YYYYMMDD-XXX)
```
