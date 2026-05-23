# Behavior Log

Use this page for chronological observations of subagent behavior.

## Entry Template

```yaml
entry_template: |
	### OBS-YYYYMMDD-XXX

	- Timestamp (UTC):
	- Request Type:
	- Subagent:
	- Model Selection: selected_model=<id> | task_type=<type> | criticality=<P0|P1|P2|P3>
	- Routing Mode: persistent=<adaptive-score-based|strict-deterministic> | effective=<adaptive-score-based|strict-deterministic> | source=<default|user-override|fallback-on-failure>
	- Fallback/Override: fallback_used=<yes|no> | fallback_reason=<if any> | override_phrase=<if any>
	- Skills Used:
	- Prompt Normalization: performed | skipped | not applicable
	- Contract Score:
	- Outcome: pass | revise | block
	- Failure Mode (if any):
	- Root Cause Hypothesis:
	- Follow-up Action:
	- Related: [Behavior-Patterns](Behavior-Patterns.md#pat-yyyymmdd-xxx), [Learning-Backlog](Learning-Backlog.md#lrn-yyyymmdd-xxx)
	- Compaction Batch: CB-YYYYMMDD-XX
```

---
