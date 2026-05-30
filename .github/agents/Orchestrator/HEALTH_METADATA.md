# Health metadata contract

This document describes the `health_*` metadata contract used by the Orchestrator health-monitoring helpers. It lists the keys recognized by `HealthPolicy.from_metadata` and the keys emitted by `HealthDecision.to_metadata`, explains how to opt-in or override policies via dispatch metadata, and notes the registry scope and persistence model.

## Policy override keys (used by HealthPolicy.from_metadata)

Health policies may be provided in dispatch metadata to override default registry behaviour for a workspace. These keys are read by `HealthPolicy.from_metadata` when creating a policy from a metadata mapping:

- `health_failure_threshold` (int) — number of failures before opening the circuit (default: 1)
- `health_open_cooldown_seconds` (int) — seconds to keep circuit open before probing (default: 30)
- `health_probe_cooldown_seconds` (int) — seconds to wait between probes (default: 60)
- `health_probe_allowlist` / `probe_allowlist` / `health_probe_candidates` (str | list) — one or more agent IDs allowed for probe attempts
- `health_backoff_factor` (float) — backoff multiplier for probe scheduling (default: 2.0)
- `health_max_backoff_seconds` (int) — max backoff duration in seconds (default: 300)

Usage example (dispatch metadata):

```
metadata = {
    "health_failure_threshold": 2,
    "health_open_cooldown_seconds": 120,
    "health_probe_allowlist": ["Agent A", "Agent B"],
}
```

## Health telemetry keys emitted (HealthDecision.to_metadata)

When a routing decision is made, the Orchestrator exposes health information in two forms:

- a nested `health` mapping with structured fields, and
- top-level `health_*` keys for convenient logging and audit.

Common keys emitted by `HealthDecision.to_metadata` include:

- `health` (dict) — the full structured decision payload (workspace_id, session_id, task_family, state, action, reason, selected/suppressed candidates, snapshot, ...)
- `health_workspace_id`, `health_session_id`, `health_agent_id`, `health_task_family`, `health_model_id`
- `health_state` — one of `closed`, `open`, `half-open`
- `health_action` — one of `allow`, `probe`, `suppress`
- `health_failure_kind` — e.g. `exception`, `timeout`, `transport`, `malformed_output`
- `health_failure_message` — optional human-readable message
- `health_reason` — short reason string
- `health_selected_candidates` — list of selected candidate agent ids (when available)
- `health_suppressed_candidates` — list of suppressed candidate agent ids
- `health_probe_candidate` — the chosen probe candidate when action=`probe`
- `health_snapshot` — optional snapshot dict of the workspace registry

Note: `hooks.log_hooks` will also accept health information provided either as a nested `metadata["health"]` mapping or via the top-level `health_*` keys. `log_hooks` performs merging/normalization and may render lists as comma-separated strings for log templates.

## Opt-in / behavior

- To request health-aware routing metadata be considered for a dispatch, include either the `health` mapping or the relevant `health_*` keys in the dispatch `metadata` payload.
- To change the circuit-breaker policy for a specific dispatch/workspace, pass the policy override keys listed above in the dispatch metadata. These are converted into a `HealthPolicy` via `HealthPolicy.from_metadata`.

## Scope & persistence

- Registries are workspace-scoped: `get_workspace_health_registry(workspace_id)` returns an in-memory registry for that workspace id.
- In v1 the registry is in-memory and per-process only; there is no durable persistence across process restarts.

If you need persistent health across runs, implement an external store and hydrate the registry at startup in a custom integration.
