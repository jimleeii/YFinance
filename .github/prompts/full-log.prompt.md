---
description: "Append a full log entry across the orchestrator log set"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise entry to all of these files under `.wiki/orchestrator/`:
- `Behavior-Log.md`
- `Behavior-Patterns.md`
- `Learning-Backlog.md`
- `Project-Context-Log.md`
- `Runbook.md`
- `Skill-Usage-Log.md`

Use the current conversation and selected text, if any, to infer the event being logged. Preserve existing content and append a timestamped entry at the end of each file. Keep the entry compact, factual, actionable, and include the following templates:

Behavior-Log.md

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
	- Related: [Behavior-Patterns](Behavior-Patterns.md#PAT-YYYYMMDD-XXX), [Learning-Backlog](Learning-Backlog.md#LRN-YYYYMMDD-XXX)
	- Compaction Batch: CB-YYYYMMDD-XX
```

Behavior-Patterns.md

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

Learning-Backlog.md

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

Project-Context-Log.md

```yaml
entry_template: |
  ### CTX-YYYYMMDD-XXX

  - Timestamp (UTC):
  - Project/Request:
  - Stage: kickoff | in_progress | checkpoint | completed | blocked
  - Summary:
    - Completed:
    - In Progress:
    - Blockers/Risks:
    - Next Action:
  - Routing/Policy Changes: mode_change=<yes|no> | override=<yes|no> | fallback=<yes|no>
	- Related: [Behavior-Log](Behavior-Log.md#OBS-YYYYMMDD-XXX), [Learning-Backlog](Learning-Backlog.md#LRN-YYYYMMDD-XXX), [Runbook](Runbook.md#CHG-YYYYMMDD-XXX)
```

Runbook.md

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

Skill-Usage-Log.md

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
