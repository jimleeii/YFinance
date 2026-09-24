
---
name: logging-policy
description: "Logging level rules, persistence, and selection pseudocode for orchestration cycles."
---

Logging.Policy Skill

Captures logging levels, persistence rules, and pseudocode for choosing verbosity.

## Logging Policy

Purpose: Reduce logging overhead for small tasks while retaining auditability for complex workflows.

Levels:

- `minimal`: used for direct/simple responses — no behavior wiki appends
- `compact`: single-agent cycles — one-line behavior checkpoint
- `full`: multi-agent cycles, failures, or policy changes — full behavior, skill-usage, and context logs

Rules:

- Default mapping: direct -> `minimal`, single-agent -> `compact`, multi-agent/failure -> `full`.
- On any persistent mode change or tier override, always use `full` for the cycle that caused the change.
- Keep behavior log entries compact; prefer checklist-style bullets and links to artifacts.
 - Persisted logging: All `full` logs and related artifacts (cycle transcripts, attachments, screenshots, policy-change records) MUST be written to the workspace root folder `.wiki/orchestrator/` and referenced from behavior log entries.

Configuration:

- `force_persist_all` (boolean): When `true`, override the logging level decision and treat every orchestration cycle as `full`, persisting artifacts to `.wiki/orchestrator/`. Default: `false`.

Change process: Logging level changes are small, reversible edits to this file and should be noted in `.wiki/orchestrator/Runbook.md`. All logging artifacts created for `full` cycles should be stored under the `.wiki/orchestrator/` folder (workspace root).

```yaml
pseudocode_choose_logging_level: |
	# Pseudocode: Determine logging verbosity for an orchestration cycle

	function choose_logging_level(dispatch_path, event_flags):
		# Configuration override
		if config.get('force_persist_all'):
			return 'full'
		# event_flags may include: persistent_mode_change, tier_override, failure_detected
		if event_flags.persistent_mode_change or event_flags.tier_override:
			return 'full'
		if event_flags.failure_detected:
			return 'full'
		if dispatch_path == 'multi-agent':
			return 'full'
		if dispatch_path == 'single-agent':
			return 'compact'
		return 'minimal'

	# Usage: call choose_logging_level before starting cycle and ensure logs are persisted per level.
```
