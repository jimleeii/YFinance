---
description: "Regenerate the model catalog cache"
agent: "agent"
---

Refresh the Orchestrator model catalog cache on demand.

Run `scripts/refresh_model_catalog.py` from the workspace root to regenerate:

- `skills/model_catalog.json`
- `.github/agents/Orchestrator/skills/model_catalog.json`

Then verify the refreshed cache parses as JSON and contains models. Do not change hook logic.