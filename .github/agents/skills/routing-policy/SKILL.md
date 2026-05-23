---
name: routing-policy
description: "Skill and agent routing rules; choose the narrowest matching skill and log dispatch decisions."
---

Routing.Policy Skill

Documents skill/agent routing rules and selection precedence.
## Routing Policy

Purpose: Route tasks to the narrowest appropriate skill or agent while preserving auditability.

Rules:

- Narrowest-skill-first: prefer the most specific skill that matches the request.
- If multiple skills match, prefer the skill with recent successful usage for similar tasks.
- Fall back to generic orchestrator flows only when no narrow skill applies.
- Always append dispatch decisions to `Skill-Usage-Log.md`.

Pseudocode:

```python
def choose_skill(task):
    candidates = find_matching_skills(task)
    if not candidates:
        return 'orchestrator'
    # prefer exact-match then recent success
    exact = [s for s in candidates if s.exact_match(task)]
    if exact:
        return recent_success_pick(exact)
    return recent_success_pick(candidates)
```
