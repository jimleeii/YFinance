# Project Context Log

Short, descriptive project memory across orchestration runs.

## Quick Trigger Commands

- `context kickoff` -> Run daily startup review and log kickoff context.
- `context sync` -> Log a short checkpoint context entry.
- `skills log` -> Log skills used this cycle into Skill-Usage-Log with reuse note.
- `context snapshot` -> Generate and log current status snapshot.
- `context blocker` -> Log blocker-focused entry with unblock condition.
- `context done` -> Log completion-focused entry.
- `context handoff` -> Log handoff summary with next owner/action.
- `context recall <topic>` -> Retrieve recent context related to a topic before routing.

## Entry Template

The project context entry template has been moved to `prompts/project-context.prompt.md`.
Use that prompt to append concise project checkpoints to this file.

Rules:

- Keep entries short and descriptive.
- Max 7 bullets in Summary.
- One sentence per bullet.
- No secrets or sensitive data.
