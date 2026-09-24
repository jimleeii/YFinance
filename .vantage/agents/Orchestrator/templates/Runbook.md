# Orchestrator Runbook

Document applied policy changes and outcomes.

Routing mode state source of truth: `.wiki/orchestrator/state.json`.

Runbook entries are audit evidence and must mirror state-changing events, but runbook content is not the canonical source for state reads.

## Change Record Template

The change-record template has been moved to `prompts/runbook.prompt.md`.
Use that prompt to append structured change records to this file.

---

## Validation Tracker

Use this tracker to evaluate recent CHG entries over their declared validation windows.

### Validation Criteria

- Prompt normalization was explicitly performed before dispatch.
- Clarifying questions were asked when critical context was missing.
- Dispatched tasks were unambiguous and required no avoidable rerouting.
- Follow-up rework due to intent misinterpretation was reduced.
