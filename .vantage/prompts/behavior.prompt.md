---
description: "Append a behavior observation entry"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise observation entry to this file under `.wiki/orchestrator/`:
- `Behavior-Log.md`

Use the current conversation and selected text, if any, to infer the observation. Preserve existing content and append a timestamped entry at the end of the file. Keep the entry compact, factual, and include the following template:

```yaml
entry_template: |
	### OBS-YYYYMMDD-XXX

	- Timestamp (UTC):
	- Request Type:
	- Subagent:
	- Model Selection: selected_model=<id> | task_type=<type> | criticality=<P0|P1|P2|P3>
	- Routing Mode: persistent=<adaptive-score-based|strict-deterministic> | effective=<adaptive-score-based|strict-deterministic> | source=<default|user-override|fallback-on-failure>
	- Fallback/Override: fallback_used=<yes|no> | fallback_reason=<if any> | override_phrase=<if any>
	- Health Scope: health_workspace_id=<id> | health_session_id=<id> | health_agent_id=<id> | health_task_family=<type> | health_model_id=<id>
	- Health Decision: health_state=<closed|half-open|open> | health_action=<allow|probe|suppress> | health_failure_kind=<if any> | health_reason=<if any>
	- Health Candidates: health_selected_candidates=<comma-separated> | health_suppressed_candidates=<comma-separated> | health_probe_candidate=<if any>
	- Skills Used:
	- Prompt Normalization: performed | skipped | not applicable
	- Contract Score:
	- Outcome: pass | revise | block
	- Failure Mode (if any):
	- Root Cause Hypothesis:
	- Follow-up Action:
	- Related: [Behavior-Patterns](Behavior-Patterns.md#PAT-YYYYMMDD-XXX), [Learning-Backlog](Learning-Backlog.md#LRN-YYYYMMDD-XXX)
	- Compaction Batch: CB-YYYYMMDD-XX
```

Avoid overwhelming verbosity. If the user provided tags, include them as a `Tags:` line before the message body.
