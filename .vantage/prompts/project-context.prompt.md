---
description: "Append a project context entry"
agent: "agent"
---
Update the repository log files from the current chat context.

Append a concise project context entry to this file under `.wiki/orchestrator/`:
- `Project-Context-Log.md`

Use the current conversation and selected text, if any, to infer the project checkpoint. Preserve existing content and append a timestamped entry at the end of the file. Keep the entry short and use the following template:

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

Rules:

- Keep entries short and descriptive.
- Max 7 bullets in Summary.
- One sentence per bullet.
- No secrets or sensitive data.
