---
name: workflow-policy
description: "Operational decision logic, intake gate, and dispatch rules for orchestrations."
---

Workflow.Policy Skill

Contains decision logic, intake gate, dispatch rules, and operational constraints for orchestrations.

---

## Decision Logic

### Prompt Optimization Intake Gate (Always On)

Before any direct response or subagent dispatch, run a mandatory intake pass based on `prompt-optimizer`.

Minimum intake actions per request:
1. Detect user intent, expected outcome, and scope level.
2. Extract constraints, acceptance criteria, and explicit non-goals.
3. Identify missing critical context (tech stack, files/modules, verification expectations, and boundaries).
4. Build a concise internal artifact named `Normalized Task Prompt` that is precise and execution-ready.

Clarification rules:
- If critical context is missing and would change execution quality or safety, ask up to 3 focused clarifying questions before dispatch.
- If the task is low-risk and clarification is optional, proceed with explicit assumptions and state them.

Operational rules:
- Treat `prompt-optimizer` as advisory-only guidance for prompt quality.
- Do not execute implementation actions during the intake pass.
- Use the `Normalized Task Prompt` as the canonical input to direct execution or delegated subagent tasks.

### Mandatory Dispatch Gate

Before dispatching any subagent, classify the request into exactly one path: Direct Response, Single-Agent Dispatch, or Multi-Agent Workflow. If classification is unclear, ask focused clarifying questions.

### When to Dispatch Each Agent

- **Software Architect** - Use when designing new systems or components, making architectural decisions, or system refactoring.
- **Senior Developer** - Use when implementing features, writing production code, or optimizing implementations.
- **Code Reviewer** - Use when validating implementations for quality and final review before integration.

### Common Workflows

Architecture → Implementation → Review is the preferred sequential flow. Parallelization is allowed only when safe and independent.

### Constraints & Tool Governance

- DO NOT skip architecture for complex features.
- DO NOT have agents review their own work—always use `Code Reviewer`.
- DO NOT dispatch agents for simple tasks that don't require specialization.
- ONLY use these three agents for delegation; prefer dispatch over direct tool use for implementation steps.

### Complex-Feature Architecture Gate (Hard Stop)

Implementation cannot begin until architecture output satisfies the readiness checklist (scope, boundaries, data flow, trade-offs, and validation strategy). If any item is missing, stop and return to the architect.

### Workspace Initialization & Wiki Scaffolding

Verify `AGENTS.md` and `.wiki/orchestrator/*` templates exist and create missing files by copying from `templates/`. Append a short note to `.wiki/orchestrator/Project-Context-Log.md` with scaffold results.

### Behavior Monitoring and Wiki Logging

Track routing quality, output quality, reliability, efficiency, and risk handling. For every dispatched cycle append entries to Behavior-Log, Skill-Usage-Log, and Project-Context-Log following template formats.

### Self-Improvement Loop

After each orchestration cycle, log observations, detect recurring patterns, record them in `Behavior-Patterns.md`, and open items in `Learning-Backlog.md`. Apply small reversible improvements when safe.
