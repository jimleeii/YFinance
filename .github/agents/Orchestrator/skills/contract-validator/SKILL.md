---
name: contract-validator
description: "Self-check skill for subagents to validate their output against required contracts before returning to Orchestrator"
tools: [read/readFile, edit/editFiles]
---

# Contract Validator Skill

## Purpose

This skill enables subagents (Software Architect, Senior Developer, Code Reviewer) to validate their own output against the required contract artifacts **before** returning to the Orchestrator. It prevents contract violations, reduces rework, and improves dispatch success rates.

## When to Use

A subagent MUST invoke this skill immediately before returning a response to the Orchestrator, after completing all work but before finalizing the output.

## Validation Procedure

### Step 1: Identify Contract Type

Determine which contract applies based on subagent role:

| Subagent | Contract Name | Required Artifacts Reference |
|----------|---------------|------------------------------|
| Software Architect | Software Architect Contract | See `orchestrator.agent.md` → Software Architect Contract |
| Senior Developer | Senior Developer Contract | See `orchestrator.agent.md` → Senior Developer Contract |
| Code Reviewer | Code Reviewer Contract | See `orchestrator.agent.md` → Code Reviewer Contract |

### Step 2: Run Contract Checklist

For the identified contract, verify each required artifact exists in the response.

**Software Architect Checklist:**
- [ ] Problem framing (scope, constraints, and non-goals)
- [ ] At least 2 viable approaches with trade-offs
- [ ] Recommended architecture decision with rationale
- [ ] Interface and boundary definitions (components/services/modules)
- [ ] Risk register and mitigation plan
- [ ] Validation strategy

**Senior Developer Checklist:**
- [ ] Implementation summary tied to approved architecture
- [ ] Files/components changed (or intended change plan if read-only)
- [ ] Test evidence (what was run, what passed/failed, and gaps)
- [ ] Error handling and rollback/guardrail notes
- [ ] Known limitations and follow-up actions
- [ ] Commenting and Region compliance statement (for changed `.cs` files)

**Code Reviewer Checklist:**
- [ ] Correctness assessment
- [ ] Maintainability assessment
- [ ] Security assessment
- [ ] Performance assessment
- [ ] Specific findings (line numbers or file references)
- [ ] Recommendations for improvement
- [ ] Approval or rejection decision with justification

### Step 3: Check Response Format Compliance

Verify the response follows the required handoff response format:

- [ ] **Status** field present = `success`, `partial`, or `failure`
- [ ] **Artifacts** field present (inline content or file references)
- [ ] **Uncertainties** field present (can be empty array)
- [ ] **Follow-up recommendations** field present (can be empty if none)

### Step 4: Handle Validation Failures

If any checklist items are missing:

1. **Identify gaps** - List exactly which required artifacts are missing
2. **Attempt auto-repair** (if safe and deterministic):
   - Add missing status/format fields with placeholder values
   - For missing test evidence: add note that tests were not run
   - For missing file references: clarify what was changed
3. **If auto-repair not possible**:
   - Set Status = `partial`
   - Add to Uncertainties: "Missing required artifact: [artifact name]"
   - In Follow-up recommendations: "Reviewer should verify [missing item]"
4. **Log the gap** (optional, to `.wiki/orchestrator/Behavior-Log.md` for self-improvement)

### Step 4a: Architecture Gap Detection (Senior Developer only)

When validating a **Senior Developer** response with `status: partial`, additionally scan the `Uncertainties` list for architecture-related keywords:

| Keyword | Meaning |
|---------|---------|
| `architecture gap` | Overall design is incomplete |
| `design undefined` | A component or service has no design spec |
| `interface missing` | A required API or interface contract is absent |
| `boundary unclear` | Module/service ownership is ambiguous |
| `schema conflict` | Data model or DB schema contradicts assumptions |
| `contract` | Expected interface contract not established |
| `dependency` | Upstream or downstream dependency not designed |
| `component` | A required component has no specification |

If **any** uncertainty contains these keywords, mark the response with `escalation_required: true` and include `Escalation: developer→architect` in Follow-up recommendations. The Orchestrator's `workflow-policy` will then trigger the Developer→Architect escalation path.

### Step 5: Return Validated Response

Only after passing validation (or being marked as `partial` with clear uncertainties) should the subagent return the response to the Orchestrator.

## Example Usage

**Before validation (incomplete response):**
```markdown
I designed an API gateway pattern for the microservices. The auth service will use JWT tokens.