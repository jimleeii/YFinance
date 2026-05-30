# Orchestrator Wiki Cleanup + Audit (7-day retention)

You are performing a **wiki audit and cleanup pass** for the Orchestrator knowledge base under:

- `.wiki/orchestrator/`

## Objective

1. Audit current logging quality and consistency.
2. Remove logging entries older than **7 days** from logging files.
3. Write a new audit report in `.wiki/orchestrator/audits/`.
4. Update `.wiki/orchestrator/Home.md` to reference the new audit report.

## Scope

### Logging files to clean (7-day retention)

- `.wiki/orchestrator/Behavior-Log.md`
- `.wiki/orchestrator/Skill-Usage-Log.md`
- `.wiki/orchestrator/Project-Context-Log.md`
- `.wiki/orchestrator/Runbook.md`

### Files to update/create

- Create: `.wiki/orchestrator/audits/orchestrator-wiki-audit-<YYYY-MM-DD>.md`
- Update: `.wiki/orchestrator/Home.md`

Do **not** modify transcript files under `.wiki/orchestrator/transcripts/`.

## Retention and Safety Rules

1. Keep file title/header blocks and explanatory notes at the top of each log file.
2. Remove only entry blocks older than 7 days based on their timestamp field.
3. If timestamp is missing/unparseable, keep entry and list it under "timestamp anomalies" in the audit report.
4. Preserve markdown validity and section order.
5. Never remove entries from the last 7 days.

## Timestamp Parsing Guidance

Treat these as valid timestamp markers (UTC or offset):

- `- Timestamp (UTC): 2026-05-23T18:42:37Z`
- `- Timestamp (UTC): 2026-05-23T18:42:37+00:00`
- Heading timestamps like `### 2026-05-23T18:42:37-06:00 — /info — setup`

Use the current local date/time as execution reference and compute cutoff = now - 7 days.

## Audit Report Requirements (JAMES-aligned)

Build report content using principles and terminology aligned to `C:\Users\wei_li.EDDYFINDT\Documents\Obsidian Vault\JAMES`:

- **Agent Observability / Workflow Observability**: coverage of log quality, traceability, and signal-to-noise.
- **Context Compaction**: what was removed vs retained and why.
- **AI Coding Workflow Governance**: correctness, minimality, reversibility, and safety notes.
- **SMART Goals**: define next-cycle cleanup goals as Specific/Measurable/Achievable/Realistic/Timely.

### Required audit sections

1. `# Orchestrator Wiki Audit — <YYYY-MM-DD>`
2. `## Executive Summary`
3. `## Scope and Inputs`
4. `## Method`
	- retention rule
	- timestamp parsing logic
	- anomaly handling
5. `## Findings`
	- noise patterns
	- duplicate patterns
	- unresolved placeholder patterns
	- cross-file consistency notes
6. `## Cleanup Actions`
	- per-file before/after counts
	- number removed (>7 days)
	- number retained (<=7 days)
7. `## Risk and Rollback Notes`
8. `## SMART Follow-ups (7-day horizon)`
9. `## References`
	- link to relevant `.wiki/orchestrator/*.md` files
	- note alignment with JAMES concepts listed above

## Home.md Update Requirements

In `.wiki/orchestrator/Home.md`:

1. Add or update a bullet under **Audits** linking the new audit file, e.g.:
	- ``[`audits/orchestrator-wiki-audit-<YYYY-MM-DD>.md`](audits/orchestrator-wiki-audit-<YYYY-MM-DD>.md)``
2. Keep existing prior audit references; append newest first.
3. Do not remove existing operational guidance text.

## Output Contract

At completion, provide:

1. List of changed files.
2. Short summary of removed-entry counts per log file.
3. Confirmation that `Home.md` references the new audit file.
4. Any unresolved anomalies requiring manual review.

## Acceptance Checklist

- [ ] New audit file created in `.wiki/orchestrator/audits/`
- [ ] Log entries older than 7 days removed from all in-scope logging files
- [ ] Recent entries (<=7 days) preserved
- [ ] `Home.md` updated with link to latest audit
- [ ] Audit report includes JAMES-aligned observability/governance/SMART sections
