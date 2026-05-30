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

### Concurrent Dispatch Classification

Use `dispatch="concurrent"` when ALL of the following are true:
1. Two or more subagents are planned.
2. The subtasks have **no shared state** — neither task depends on the output of the other.
3. Each subtask produces a self-contained artifact (separate files, independent analysis, etc.).
4. The tasks are of comparable complexity so neither trivially dominates.

When the Orchestrator dispatches concurrently:
1. Fan out to both subagents in the same turn (use the `dispatching-parallel-agents` skill).
2. Receive both responses.
3. Score each response using `contract-validator` and `score.py`.
4. Select the **higher-scoring** response as the canonical output. In case of a tie, prefer the response that covers more required artifacts.
5. Log both results in `Behavior-Log.md` with `routing_mode: concurrent` and include both scores.
6. Pass only the winning response to the Code Reviewer.

Do **not** use concurrent dispatch when:
- Tasks share state (e.g., both modify the same module or schema).
- One task's design is an input to the other (sequential dependency).
- Only one subagent is needed.

The Python runtime helper `classify_dispatch_type(subagents, task_flags)` can assist with the decision: pass `task_flags={"independent_tracks": True}` to receive `"concurrent"` as the recommendation.

### Developer → Architect Escalation Path

When a Senior Developer returns `status: partial` **and** any entry in `Uncertainties` contains an architecture-related keyword (e.g. "architecture gap", "design undefined", "interface missing", "boundary unclear", "schema conflict"), the Orchestrator MUST pause the implementation cycle and re-dispatch to the Software Architect before allowing the Developer to continue.

Escalation procedure:
1. Detect `status: partial` in Developer response.
2. Scan `Uncertainties` for architecture keywords (case-insensitive): `architecture`, `design`, `interface`, `boundary`, `schema`, `contract`, `dependency`, `component`.
3. If found, extract the specific gap description and build a scoped addendum prompt for the Architect.
4. Dispatch Software Architect with: original design + Developer gap description as context.
5. Architect returns a scoped design addendum (does **not** need to satisfy the full Architect contract — only the gap must be addressed).
6. Dispatch Senior Developer again with: original task + original design + Architect addendum.
7. Log the escalation as a `full` cycle in Behavior-Log with `escalation: developer→architect` in metadata.

Limits:
- Maximum **one** escalation per implementation task to prevent loops.
- If the Developer returns `status: partial` a second time with the same architecture keyword, escalate to the user for manual resolution instead of re-routing.

### Constraints & Tool Governance

- DO NOT skip architecture for complex features.
- DO NOT have agents review their own work—always use `Code Reviewer`.
- DO NOT dispatch agents for simple tasks that don't require specialization.
- ONLY use these three agents for delegation; prefer dispatch over direct tool use for implementation steps.

### P0/P1 Architect Peer Review (Hard Requirement)

For any task with `criticality: P0` or `criticality: P1`, the Orchestrator MUST run an Architect peer-review round before handing the design to the Senior Developer.

Peer review procedure:
1. **First Architect dispatch** — standard architecture phase; receives the full task prompt and produces the primary design.
2. **Challenger Architect dispatch** — a second Software Architect instance receives:
   - The original task prompt.
   - The first Architect's design artifacts (as `parent_context.prior_design`).
   - Instruction: *"Challenge this design. Identify assumptions, risks, missing edge cases, and alternative approaches. Do not simply agree."*
3. **Reconcile** — the Orchestrator reviews both outputs:
   - If the challenger identifies a critical gap, send both outputs back to the first Architect with the challenger's objections for a final revision.
   - If the challenger confirms the design or raises only minor concerns, proceed to implementation with the original design plus a brief reconciliation note.
4. Log the peer-review round in `Behavior-Log.md` with `routing_mode: p0p1-peer-review` and include both Architect scores.
5. Implementation begins only after reconciliation is complete.

Limits:
- Peer review applies to architecture only, not to Senior Developer or Code Reviewer phases.
- Maximum one reconciliation pass — do not loop the two Architects indefinitely.
- If `criticality` is not set, default to P2 behavior (no peer review).

### Complex-Feature Architecture Gate (Hard Stop)

Implementation cannot begin until architecture output satisfies the readiness checklist (scope, boundaries, data flow, trade-offs, and validation strategy). If any item is missing, stop and return to the architect.

### Workspace Initialization & Wiki Scaffolding

Verify `AGENTS.md` and `.wiki/orchestrator/*` templates exist and create missing files by copying from `templates/`. Append a short note to `.wiki/orchestrator/Project-Context-Log.md` with scaffold results.

### Behavior Monitoring and Wiki Logging

Track routing quality, output quality, reliability, efficiency, and risk handling. For each completed, user-visible orchestration cycle append one concise checkpoint to the relevant wiki pages. Automatic tool hooks may collect telemetry, but they must not create curated multi-page wiki updates unless structured metadata explicitly marks the checkpoint as curated.

### Self-Improvement Loop

After each curated orchestration cycle, log observations, detect recurring patterns, record them in `Behavior-Patterns.md`, and open deduplicated items in `Learning-Backlog.md`. Apply small reversible improvements when safe, and prefer updating an existing learning item over creating a duplicate placeholder entry.
