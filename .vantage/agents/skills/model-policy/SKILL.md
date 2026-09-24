
---
name: model-policy
description: "Model selection, scoring, and fallback strategies for cost/latency vs correctness tradeoffs."
---

Model.Policy Skill

Contains model selection guidance, fallback strategies, and scoring considerations.

## Model Policy

Guidance:

- Prefer low-latency cheaper models for iterative work and higher-quality models for final runs or correctness-sensitive paths.
- Use ensemble or multiple-pass approaches for ambiguous tasks: first pass for extraction, second pass for reasoning.
- When cost and latency conflict with correctness, prefer correctness for safety-critical or regulatory content.

Model scoring pseudocode:

```python
def score_models(models, task):
    # factors: latency, cost, recent_success, capability_match
    return sorted(models, key=lambda m: (m.cost, -m.recent_success, -m.capability_match))
```
