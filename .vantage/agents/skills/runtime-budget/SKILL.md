
---
name: runtime-budget
description: "Runtime cost and retry budget guidance for orchestration cycles and escalation rules."
---

Runtime.Budget Skill

Contains guidance on runtime cost controls, retry budgets, and escalation.

## Runtime Budget

Purpose: Limit runaway compute and cost during multi-agent orchestration. Provide a capped retry policy and cost-aware fallback rules.

### Budgeting Rules

- Default attempt budget per task: 3 attempts across Dev-QA cycles (configurable via `max_orchestration_cycles`).
- CPU/time budgets: prefer light-weight models for repeated retries, escalate to heavier models only on final attempt or when accuracy is critical.
- Cost-aware fallback: If an expensive model (e.g., >X cost per call) is required, attempt cheaper models first unless correctness is non-negotiable.

### Escalation

- After exhausting retries, escalate to human-in-the-loop review via a `Code Reviewer` or `Project Shepherd` with an explicit summary of attempts and artifacts.

### Pseudocode

```python
def choose_model(attempt, task_critical):
    if attempt == 1:
        return cheap_model
    if attempt == 2 and not task_critical:
        return medium_model
    return expensive_model

def run_with_budget(task):
    for attempt in range(1, max_attempts+1):
        model = choose_model(attempt, task.critical)
        result = run_model(model, task)
        if validate_result(result):
            return result
    escalate_to_human(task)
```
