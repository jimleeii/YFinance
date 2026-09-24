# Skill Usage Log

Track which skills were used per orchestration cycle and what should be reused later.

## Entry Template

### SKL-YYYYMMDD-XXX

- Timestamp (UTC):
- Request Type:
- Routing Path: direct | single-agent | multi-agent
- Subagent(s):
- Skills Used (ordered):
- Invocation Reason:
- Outcome Impact: positive | neutral | negative
- Reuse Note:
- Related: [Behavior-Log](Behavior-Log.md#obs-yyyymmdd-xxx), [Behavior-Patterns](Behavior-Patterns.md#pat-yyyymmdd-xxx), [Learning-Backlog](Learning-Backlog.md#lrn-yyyymmdd-xxx)

```yaml
entry_template: |
	### SKL-YYYYMMDD-XXX

	- Timestamp (UTC):
	- Request Type:
	- Routing Path: direct | single-agent | multi-agent
	- Subagent(s):
	- Skills Used (ordered):
	- Invocation Reason:
	- Outcome Impact: positive | neutral | negative
	- Reuse Note:
	- Related: [Behavior-Log](Behavior-Log.md#obs-yyyymmdd-xxx), [Behavior-Patterns](Behavior-Patterns.md#pat-yyyymmdd-xxx), [Learning-Backlog](Learning-Backlog.md#lrn-yyyymmdd-xxx)
```

---
