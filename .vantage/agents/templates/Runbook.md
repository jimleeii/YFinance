# Orchestrator Runbook

Document applied policy changes and outcomes.

Routing mode state source of truth: `.wiki/orchestrator/state.json`.

Runbook entries are audit evidence and must mirror state-changing events, but runbook content is not the canonical source for state reads.

## Change Record Template

### CHG-YYYYMMDD-XXX

- Date:
- Trigger Pattern:
- Change Applied:
- Expected Effect:
- Validation Window:
- Observed Result:
- Decision: keep | revise | rollback
- Related Entries: [Behavior-Patterns](Behavior-Patterns.md#pat-yyyymmdd-xxx), [Learning-Backlog](Learning-Backlog.md#lrn-yyyymmdd-xxx)

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
	- Related Entries: [Behavior-Patterns](Behavior-Patterns.md#pat-yyyymmdd-xxx), [Learning-Backlog](Learning-Backlog.md#lrn-yyyymmdd-xxx)
```

---

## Validation Tracker

Use this tracker to evaluate recent CHG entries over their declared validation windows.

### Validation Criteria

- Prompt normalization was explicitly performed before dispatch.
- Clarifying questions were asked when critical context was missing.
- Dispatched tasks were unambiguous and required no avoidable rerouting.
- Follow-up rework due to intent misinterpretation was reduced.
