# Orchestrator Dispatch & Logging API

Quick reference for the runtime dispatch execution and full-log gating capabilities added in P1 hardening (2026-05-24).

---

## Dispatch Execution API

### `execute_dispatch_by_type(...)`

Execute a dispatch path and return structured runtime results. Supports `direct`, `single-agent`, `multi-agent`, and `concurrent` flows.

**Signature:**
```python
from src.orchestrator_runtime import execute_dispatch_by_type

result = execute_dispatch_by_type(
    dispatch_type: str,              # "direct" | "single-agent" | "multi-agent" | "concurrent"
    prompt: str,                     # request text
    metadata: Optional[Dict] = None, # cycle context including cycle_id, subagent, etc.
    subagents: Optional[List] = None,# list of subagent names
    run_agent: Optional[Callable] = None,  # callback: (agent_name, prompt, metadata) -> dict
    max_orchestration_cycles: Optional[int] = None,  # retry budget (default 3)
)
```

**Returns:**
```python
{
    "dispatch": str,                 # normalized dispatch type
    "cycle_id": str,                 # cycle identifier
    "orchestration_cycle": int,      # current cycle number
    "max_orchestration_cycles": int, # retry budget
    "status": str,                   # e.g. "direct-complete", "dispatched", "retry-budget-exhausted"
    "executed": bool,                # whether dispatch ran
    "retry_budget_exhausted": bool,  # true when max cycles reached
    "retries_remaining": int,
    "results": list,                 # subagent results (concurrent only)
    "primary_result": dict,          # winning result for concurrent; None for direct
    "action": str,                   # e.g. "hard-stop" when budget exhausted
    "reason": str,                   # reason for outcome (if applicable)
}
```

**Concurrent dispatch behavior:**
- Two or more subagents run in parallel via `ThreadPoolExecutor`.
- Results are sorted by `contract_score` (descending), then `artifact_weight`.
- The highest-ranked result becomes `primary_result`.
- All results are returned in `results[]` for audit.

**Retry budget enforcement:**
- If `orchestration_cycle > max_orchestration_cycles`, returns hard-stop immediately.
- No dispatch is executed.
- `status` is `"retry-budget-exhausted"` and `executed` is `false`.

**Example:**
```python
result = execute_dispatch_by_type(
    dispatch_type="concurrent",
    prompt="Implement the feature",
    metadata={"cycle_id": "CYC-20260524-123456-ABCD"},
    subagents=["Senior Developer A", "Senior Developer B"],
    run_agent=lambda agent, prompt, meta: {...},  # your agent runner
    max_orchestration_cycles=3,
)

if result["status"] == "retry-budget-exhausted":
    print(f"Exhausted retries: {result['reason']}")
elif result["dispatch"] == "concurrent":
    print(f"Winner: {result['primary_result']['agent']}")
```

---

## Full-Log Evidence Gating

### Strict Evidence Requirements for Curated Full Logs

The logging hook now enforces strict evidence gating for curated full-log writes (`/full-log`).

**Required evidence for full-log writes:**
1. `cycle_id` — present and non-empty
2. Meaningful request context — one of:
   - `project_request`
   - `normalized_request`
   - `request_title`
   - Non-noise `summary`
3. Meaningful change/work evidence — one of:
   - `change_applied`
   - `completed`
   - `files_touched` (non-empty)
   - `session_evidence` (non-empty)

**Downgrade behavior:**
If mandatory evidence is missing, the full-log write is:
- **Downgraded to compact** (`/info` command)
- **Not rejected** — no error is raised
- **Return payload includes** `action: "downgraded-full-log-to-compact"` with reason

**Example payload when evidence is missing:**
```python
{
    "level": "compact",
    "command": "/info",
    "action": "downgraded-full-log-to-compact",
    "reason": "missing required evidence: cycle_id",
    "returncode": "0",
}
```

**Usage in hooks:**
```python
from hooks.log_hooks import log_cycle

result = log_cycle(
    dispatch_path="multi-agent",
    summary="Refactored widget module",
    skills=["csharp-pro"],
    metadata={
        "cycle_id": "CYC-20260524-123456-ABCD",  # REQUIRED for full-log
        "project_request": "Refactor widget class structure",  # Required evidence
        "change_applied": "Extracted interface from monolithic class",  # Required evidence
        "files_touched": ["Widget.cs", "IWidget.cs"],
        "curated_log": True,  # Explicitly request full-log attempt
    },
    prompt_command="/full-log",  # Request full-log write
)
```

---

## Noise Suppression & Automatic Hooks

Automatic hook events (PreToolUse, PostToolUse) with noise-only summaries are skipped before reaching the evidence gate:

```python
# This will be skipped as noise, not downgraded:
log_cycle(
    dispatch_path="single-agent",
    summary="Post-tool invocation",  # noise value
    metadata={"hook_event_name": "PostToolUse"},
)
# Returns: {"level": "...", "action": "skipped-noise"}
```

---

## Backward Compatibility

- Single-agent and multi-agent flows are unchanged.
- Existing logging behavior for `minimal` and `compact` levels is preserved.
- Only new `concurrent` dispatch and curated full-log gating are additions.

---

## Testing & Verification

Run the Orchestrator test suite to verify dispatch and logging behavior:

```bash
rtk python -m pytest .github/agents/Orchestrator/ -q --tb=short
```

All 30+ tests pass, covering:
- Concurrent dispatch ranking
- Retry-budget exhaustion
- Full-log evidence gate downgrade
- Noise suppression

---

## CI integration (recommended)

To run the Orchestrator hook tests in CI, add a job/step that installs the repository dev dependencies and executes the hook test suite. Do NOT modify existing pipeline YAMLs here; instead, add a small step in your pipeline similar to the example below.

Example (bash / Linux runner):

```bash
# install dev deps (prefer using the repository's `rtk` wrapper where applicable)
python -m pip install -r requirements-dev.txt

# run only the Orchestrator hooks tests
python -m pytest .github/agents/Orchestrator/hooks -q
```

For Windows PowerShell runners prefer the repository `rtk` wrapper and PowerShell script:

```powershell
rtk pwsh -NoProfile -Command "python -m pip install -r requirements-dev.txt"
rtk python -m pytest .github/agents/Orchestrator/hooks -q
```

This keeps CI changes minimal and ensures the Orchestrator hooks are verified as part of PR validation. If you use a different test matrix, adapt the paths above to run only the hook tests you want to include.
