# Orchestrator Wiki Home

## Purpose

This wiki tracks subagent behavior, recurring patterns, and orchestrator self-improvement actions.

## Pages

- [Project-Context-Log](Project-Context-Log.md)
- [Behavior-Log](Behavior-Log.md)
- [Skill-Usage-Log](Skill-Usage-Log.md)
- [Behavior-Patterns](Behavior-Patterns.md)
- [Learning-Backlog](Learning-Backlog.md)
- [Runbook](Runbook.md)

## Operating Cycle

0. Read [Project-Context-Log](Project-Context-Log.md) at day start and capture a short Today Context summary.
1. Dispatch subagent and evaluate output.
2. Append observation to [Behavior-Log](Behavior-Log.md).
3. Append skills used and reuse notes to [Skill-Usage-Log](Skill-Usage-Log.md).
4. Extract recurring issues to [Behavior-Patterns](Behavior-Patterns.md).
5. Add actionable fixes to [Learning-Backlog](Learning-Backlog.md).
6. Apply one safe policy improvement and document in [Runbook](Runbook.md).
7. Append short execution context to [Project-Context-Log](Project-Context-Log.md).

## Cadence

- Once per day before first task: review [Project-Context-Log](Project-Context-Log.md), [Learning-Backlog](Learning-Backlog.md), and latest [Runbook](Runbook.md) checkpoint.
- Every 10 new observations in [Behavior-Log](Behavior-Log.md): run pattern compaction in [Behavior-Patterns](Behavior-Patterns.md).
- Every 15 new entries in [Skill-Usage-Log](Skill-Usage-Log.md): summarize high-value skill combinations in [Behavior-Patterns](Behavior-Patterns.md).
- Every 7 days: triage [Learning-Backlog](Learning-Backlog.md) priorities and statuses.
- After each triage: add a checkpoint in [Runbook](Runbook.md) with what changed.
