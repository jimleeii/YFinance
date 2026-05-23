
---
name: quality-policy
description: "Expectations for code quality, testing, and review gates applied across the workspace."
---

Quality.Policy Skill

Captures expectations for code quality, tests, and review gates.

## Quality Policy

Principles:

- Every change must have a clear acceptance criterion.
- Tests should be added for logic-level behavior and high-risk changes.
- Code reviewers must validate architecture constraints, security considerations, and complexity trade-offs.

Review checklist (short):

- [ ] Acceptance criteria present and testable.
- [ ] Unit tests added for new logic and edge cases.
- [ ] No high-cyclomatic complexity functions without refactor.
- [ ] No TODOs left without a plan in `Learning-Backlog.md`.
