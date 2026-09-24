
---
name: policy-precedence
description: "Determines precedence when multiple workspace policies conflict; prefer restrictive policy and escalate."
---

Policy.Precedence Skill

Documents how multiple policies should be evaluated when conflicts arise.

## Policy Precedence

Order of precedence when multiple policy files apply to the same action:

1. Security/Legal policies (highest)
2. Workspace-level policies (`Workspace.Policy.md`)
3. Rule-specific policies (`Comment.Policy.md`, `Markdown.Policy.md`, etc.)
4. Skill-level guidance and templates

When in doubt, escalate to human review and prefer the more restrictive policy.
