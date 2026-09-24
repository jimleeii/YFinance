
---
name: workspace-policy
description: "Workspace initialization, scaffold behavior, and skill discovery guidance."
---

Workspace.Policy Skill

Documents workspace initialization, scaffold behavior, and skill discovery guidance.

## Workspace Policy

Purpose: Document workspace initialization, runbook persistence, and scaffold behavior.

Key points:

- `.wiki/orchestrator/Runbook.md` is the canonical store for persisted mode and checkpoint entries.
- Workspace scaffold steps: verify `AGENTS.md`, create `.wiki/orchestrator/` files from templates when missing, and append a short scaffold summary to `Project-Context-Log.md`.
- Do not overwrite existing template sources in `templates/`.

Skill discovery guidance

 At session start, query the external system folder `%USERPROFILE%\.copilot\skills` read-only as a source for skill usage logging and metadata validation. Do not treat it as repo/workspace content. Fall back to a minimal canonical list if discovery is unavailable.

Minimal canonical defaults (examples — keep small):

- `prompt-optimizer`
- `verification-before-completion`
- `requesting-code-review`
- `writing-plans`

Initialization guardrails:

- Perform scaffold checks only on `workspace init` or first orchestration cycle.
- When creating files from templates, copy content verbatim and log the creation event.

Change process: Workspace policy edits should be coordinated with runbook checkpoint entries.

```yaml
pseudocode_workspace_init_and_scaffold: |
	# Pseudocode: Workspace initialization and scaffold procedure

	function workspace_init(force=false):
		if not force and already_initialized_this_session():
			return {status: 'skipped', reason: 'already initialized'}

		required_files = [ 'AGENTS.md', '.wiki/orchestrator/Home.md', '.wiki/orchestrator/Project-Context-Log.md', '.wiki/orchestrator/Behavior-Log.md', '.wiki/orchestrator/Skill-Usage-Log.md', '.wiki/orchestrator/Behavior-Patterns.md', '.wiki/orchestrator/Learning-Backlog.md', '.wiki/orchestrator/Runbook.md' ]
		created = []
		present = []

		for path in required_files:
			if file_exists(path):
				present.append(path)
			else:
				template = find_template_for(path)
				if template:
					copy_file(template, path)
					created.append(path)
				else:
					log_blocker('missing_template', path)
					return {status: 'blocked', missing_template: path}

		# Append scaffold summary to Project-Context-Log.md
		append_project_context_log({created: created, present: present, ts_utc: now_utc()})

		return {status: 'done', created: created, present: present}

	# Usage: run workspace_init on session start or when 'workspace init' trigger received.
```
