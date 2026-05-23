---
description: "Append an informational log entry"
agent: "agent"
---
Update the repository log files from the current chat context with structured metadata.

Append concise entries to these files under `.wiki/orchestrator/`:
- `Behavior-Log.md` - orchestrator behavior observations
- `Skill-Usage-Log.md` - skill usage tracking

Use the structured context payload to populate template fields. Preserve existing content and append timestamped entries at the end of each file.

## Behavior-Log.md

```yaml
entry_template: |
	### OBS-YYYYMMDD-HHMMSS

	- Timestamp (UTC): timestamp_utc
	- Request Type: request_type
	- Subagent: subagent
	- Model Selection: model_selection
	- Routing Mode: routing_mode
	- Fallback/Override: fallback_override
	- Skills Used: skills_used
	- Prompt Normalization: prompt_normalization
	- Contract Score: contract_score
	- Outcome: outcome
	- Failure Mode (if any): failure_mode_if_any
	- Root Cause Hypothesis: root_cause_hypothesis
	- Follow-up Action: follow_up_action
	- Related: [Behavior-Patterns](Behavior-Patterns.md#PAT-YYYYMMDD-XXX), [Learning-Backlog](Learning-Backlog.md#LRN-YYYYMMDD-XXX)
	- Compaction Batch: compaction_batch
```

## Skill-Usage-Log.md

```yaml
entry_template: |
	### SKILL-YYYYMMDD-HHMMSS

	- Timestamp (UTC): timestamp_utc
	- Request Type: request_type
	- Routing Path: routing_path
	- Subagents: subagents
	- Skills Used: skills_used_ordered
	- Invocation Reason: invocation_reason
	- Outcome Impact: outcome_impact
	- Reuse Note: reuse_note
	- Compaction Batch: compaction_batch
```

Keep entries compact, factual, and properly formatted using the OBS-YYYYMMDD-HHMMSS pattern.
