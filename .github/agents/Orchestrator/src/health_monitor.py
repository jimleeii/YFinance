from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Mapping, Sequence

from src.health_types import (
    HEALTH_FAILURE_KINDS,
    HealthDecision,
    HealthObservation,
    HealthPolicy,
    HealthRecord,
    HealthScope,
    HealthSnapshot,
    HealthState,
)


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()
    return text or default


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text if text else None


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed if parsed > 0 else default


def _non_negative_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed if parsed >= 0 else default


def _utc_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso_now(now: datetime | None = None) -> str:
    return _utc_now(now).replace(microsecond=0).isoformat()


def _iso_plus_seconds(now: datetime, seconds: int) -> str:
    return (_utc_now(now) + timedelta(seconds=max(0, int(seconds)))).replace(microsecond=0).isoformat()


def _resolve_workspace_id(workspace_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> str:
    explicit = _text(workspace_id)
    if explicit:
        return explicit

    source = metadata or {}
    for key in (
        "workspace_id",
        "workspace_root",
        "workspace_path",
        "target_root",
        "root",
    ):
        candidate = _text(source.get(key))
        if candidate:
            return candidate

    return os.path.abspath(os.getcwd())


def _resolve_session_id(metadata: Mapping[str, Any] | None = None) -> str:
    source = metadata or {}
    for key in (
        "session_id",
        "request_group_id",
        "cycle_id",
    ):
        candidate = _text(source.get(key))
        if candidate:
            return candidate
    return "session-unknown"


def _resolve_task_family(dispatch_type: str | None = None, metadata: Mapping[str, Any] | None = None) -> str:
    source = metadata or {}
    for key in (
        "health_task_family",
        "task_family",
        "task_type",
        "routing_mode",
    ):
        candidate = _text(source.get(key))
        if candidate:
            return candidate
    return _text(dispatch_type, default="dispatch")


def _resolve_model_id(metadata: Mapping[str, Any] | None = None) -> str | None:
    source = metadata or {}
    for key in (
        "health_model_id",
        "selected_model",
        "cycle_selected_model",
        "model",
    ):
        candidate = _optional_text(source.get(key))
        if candidate:
            return candidate
    return None


def _unique_candidates(candidates: Sequence[str]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = _text(candidate)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return tuple(merged)


def _normalize_allowlist(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set, frozenset)):
        items = [str(item).strip() for item in value]
    else:
        items = [str(value).strip()]
    return tuple(item for item in items if item)


def classify_execution_failure_kind(error: BaseException | None = None, payload: Any = None) -> str | None:
    if error is not None:
        name = error.__class__.__name__.lower()
        message = _text(error).lower()
        if isinstance(error, TimeoutError) or "timeout" in name or "timeout" in message:
            return "timeout"
        if isinstance(error, (ConnectionError, OSError)) or "transport" in name or "transport" in message:
            return "transport"
        return "exception"

    if payload is None:
        return None

    if not isinstance(payload, dict):
        return "malformed_output"

    failure_kind = _optional_text(payload.get("health_failure_kind"))
    if failure_kind:
        failure_kind = failure_kind.replace("-", "_").replace(" ", "_").lower()
        if failure_kind in HEALTH_FAILURE_KINDS:
            return failure_kind

    if payload.get("transport_error") or payload.get("transport_failure"):
        return "transport"
    if payload.get("timed_out") or payload.get("timeout"):
        return "timeout"

    status = _text(payload.get("status")).lower()
    if status in {"failure", "failed", "error"} and _text(payload.get("error")):
        return "exception"

    return None


def _build_scope(
    *,
    workspace_id: str,
    session_id: str,
    agent_id: str,
    task_family: str,
    model_id: str | None,
) -> HealthScope:
    return HealthScope(
        workspace_id=workspace_id,
        session_id=session_id,
        agent_id=agent_id,
        task_family=task_family,
        model_id=model_id,
    )


class WorkspaceHealthRegistry:
    """Workspace-scoped in-memory health registry with a coarse RLock."""

    def __init__(self, workspace_id: str, policy: HealthPolicy | None = None):
        self.workspace_id = _resolve_workspace_id(workspace_id)
        self.policy = policy or HealthPolicy()
        self._lock = RLock()
        self._states: dict[tuple[str, str, str, str, str], HealthState] = {}
        self._scopes: dict[tuple[str, str, str, str, str], HealthScope] = {}

    def _state_for(self, scope: HealthScope) -> HealthState:
        return self._states.get(scope.to_key(), HealthState())

    def _store(self, scope: HealthScope, state: HealthState) -> None:
        key = scope.to_key()
        self._states[key] = state
        self._scopes[key] = scope

    def _scope_from_key(self, key: tuple[str, str, str, str, str]) -> HealthScope:
        workspace_id, session_id, agent_id, task_family, model_id = key
        return HealthScope(
            workspace_id=workspace_id,
            session_id=session_id,
            agent_id=agent_id,
            task_family=task_family,
            model_id=model_id or None,
        )

    def _backoff_seconds(self, failure_count: int) -> int:
        policy = self.policy
        failure_streak = max(1, failure_count - policy.failure_threshold + 1)
        try:
            backoff = policy.open_cooldown_seconds * (policy.backoff_factor ** max(0, failure_streak - 1))
        except Exception:
            backoff = policy.open_cooldown_seconds
        backoff_seconds = int(round(backoff))
        if backoff_seconds < policy.open_cooldown_seconds:
            backoff_seconds = policy.open_cooldown_seconds
        if policy.max_backoff_seconds > 0:
            backoff_seconds = min(backoff_seconds, policy.max_backoff_seconds)
        return max(0, backoff_seconds)

    def _open_state(self, state: HealthState, now: datetime, *, reopen: bool = False) -> HealthState:
        failure_count = state.failure_count + 1
        backoff_seconds = self._backoff_seconds(failure_count)
        return replace(
            state,
            status="open",
            failure_count=failure_count,
            success_count=0,
            open_until=_iso_plus_seconds(now, backoff_seconds),
            probe_reserved_until=None,
            last_observed_at=_iso_now(now),
            last_failure_at=_iso_now(now),
            probe_count=state.probe_count,
            reopen_count=state.reopen_count + (1 if reopen or state.status == "half-open" else 0),
        )

    def _close_state(self, state: HealthState, now: datetime) -> HealthState:
        return replace(
            state,
            status="closed",
            failure_count=0,
            success_count=state.success_count + 1,
            open_until=None,
            probe_reserved_until=None,
            last_observed_at=_iso_now(now),
            last_success_at=_iso_now(now),
        )

    def _reserve_probe(self, state: HealthState, now: datetime) -> HealthState:
        reserved_until = _iso_plus_seconds(now, self.policy.probe_cooldown_seconds)
        return replace(
            state,
            status="half-open",
            probe_count=state.probe_count + 1,
            last_observed_at=_iso_now(now),
            last_probe_at=_iso_now(now),
            probe_reserved_until=reserved_until,
        )

    def _record_locked(self, observation: HealthObservation, now: datetime) -> HealthState | None:
        scope = observation.scope
        if scope.workspace_id != self.workspace_id:
            raise ValueError(
                f"observation workspace_id '{scope.workspace_id}' does not match registry workspace_id '{self.workspace_id}'"
            )

        current = self._state_for(scope)

        if observation.outcome == "success":
            updated = self._close_state(current, now)
            self._store(scope, updated)
            return updated

        if observation.outcome != "failure" or not observation.counts_toward_health:
            return current if scope.to_key() in self._states else None

        if observation.failure_kind not in HEALTH_FAILURE_KINDS:
            return current if scope.to_key() in self._states else None

        if current.status == "half-open":
            updated = self._open_state(current, now, reopen=True)
        elif current.failure_count + 1 >= self.policy.failure_threshold:
            updated = self._open_state(current, now)
        else:
            updated = replace(
                current,
                failure_count=current.failure_count + 1,
                success_count=0,
                last_observed_at=_iso_now(now),
                last_failure_at=_iso_now(now),
                last_failure_kind=observation.failure_kind,
                last_failure_message=observation.message or None,
            )

        updated = replace(
            updated,
            last_failure_kind=observation.failure_kind,
            last_failure_message=observation.message or None,
        )
        self._store(scope, updated)
        return updated

    def record_observation(self, observation: HealthObservation, now: datetime | None = None) -> HealthState | None:
        with self._lock:
            current_now = _utc_now(now)
            return self._record_locked(observation, current_now)

    def _make_snapshot(self, *, now: datetime | None = None) -> HealthSnapshot:
        ordered_records = [
            HealthRecord(
                scope=self._scopes.get(scope_key) or self._scope_from_key(scope_key),
                state=self._states[scope_key],
            )
            for scope_key in sorted(self._states, key=lambda key: key)
        ]
        return HealthSnapshot(
            workspace_id=self.workspace_id,
            policy=self.policy,
            generated_at=_iso_now(now),
            records=tuple(ordered_records),
        )

    def snapshot(self, now: datetime | None = None) -> HealthSnapshot:
        with self._lock:
            return self._make_snapshot(now=now)

    def route_candidates(
        self,
        candidates: Sequence[str],
        *,
        session_id: str,
        task_family: str,
        model_id: str | None = None,
        probe_allowlist: Sequence[str] | None = None,
        now: datetime | None = None,
    ) -> HealthDecision:
        with self._lock:
            current_now = _utc_now(now)
            ordered_candidates = _unique_candidates(candidates)
            route_allowlist = tuple(_normalize_allowlist(probe_allowlist) or self.policy.probe_allowlist)

            records: list[HealthRecord] = []
            selected: list[str] = []
            suppressed: list[str] = []
            probe_candidate: str | None = None
            decision_state = "closed"
            decision_action = "allow"
            decision_reason = "healthy candidates available"
            failure_kind: str | None = None
            failure_message: str | None = None

            eligible_probe_records: list[HealthRecord] = []
            closed_candidates: list[str] = []

            for candidate in ordered_candidates:
                scope = _build_scope(
                    workspace_id=self.workspace_id,
                    session_id=session_id,
                    agent_id=candidate,
                    task_family=task_family,
                    model_id=model_id,
                )
                state = self._state_for(scope)
                if state.status == "half-open" and state.probe_reserved_until:
                    if _utc_now(datetime.fromisoformat(state.probe_reserved_until)) <= current_now:
                        state = replace(state, status="open", probe_reserved_until=None)
                        self._store(scope, state)

                record = HealthRecord(scope=scope, state=state)
                records.append(record)

                if state.status == "closed":
                    selected.append(candidate)
                    closed_candidates.append(candidate)
                    continue

                suppressed.append(candidate)

                if state.status == "open" and state.open_until:
                    try:
                        open_until = datetime.fromisoformat(state.open_until)
                    except Exception:
                        open_until = current_now
                    if open_until <= current_now and (
                        self.policy.allows_probe(candidate)
                        if not route_allowlist
                        else any(candidate.casefold() == entry.casefold() for entry in route_allowlist)
                    ):
                        eligible_probe_records.append(record)

            if not closed_candidates:
                if eligible_probe_records:
                    chosen = eligible_probe_records[0]
                    probe_candidate = chosen.scope.agent_id
                    selected = [probe_candidate]
                    suppressed = [candidate for candidate in ordered_candidates if candidate != probe_candidate]
                    reserved = self._reserve_probe(chosen.state, current_now)
                    self._store(chosen.scope, reserved)
                    records = [
                        HealthRecord(scope=record.scope, state=reserved if record.scope == chosen.scope else record.state)
                        if record.scope == chosen.scope
                        else record
                        for record in records
                    ]
                    decision_state = "half-open"
                    decision_action = "probe"
                    decision_reason = "probe candidate selected after all closed candidates were suppressed"
                    failure_kind = chosen.state.last_failure_kind
                    failure_message = chosen.state.last_failure_message
                else:
                    first_unhealthy = next((record for record in records if record.state.status != "closed"), None)
                    if first_unhealthy is not None:
                        failure_kind = first_unhealthy.state.last_failure_kind
                        failure_message = first_unhealthy.state.last_failure_message
                    decision_state = "open"
                    decision_action = "suppress"
                    decision_reason = "no closed candidates remain and no allow-listed probe candidate is available"
            elif suppressed:
                decision_reason = "healthy candidates available; unhealthy candidates suppressed"

            snapshot = HealthSnapshot(
                workspace_id=self.workspace_id,
                policy=self.policy,
                generated_at=_iso_now(current_now),
                records=tuple(records),
            )

            return HealthDecision(
                workspace_id=self.workspace_id,
                session_id=_text(session_id),
                task_family=_text(task_family),
                model_id=_optional_text(model_id),
                state=decision_state,
                action=decision_action,
                reason=decision_reason,
                selected_candidates=tuple(selected),
                suppressed_candidates=tuple(suppressed),
                probe_candidate=probe_candidate,
                failure_kind=failure_kind,
                failure_message=failure_message,
                snapshot=snapshot,
            )


_WORKSPACE_REGISTRIES: dict[str, WorkspaceHealthRegistry] = {}
_WORKSPACE_REGISTRY_LOCK = RLock()


def get_workspace_health_registry(
    workspace_id: str | None = None,
    *,
    policy: HealthPolicy | None = None,
) -> WorkspaceHealthRegistry:
    resolved_workspace_id = _resolve_workspace_id(workspace_id)
    with _WORKSPACE_REGISTRY_LOCK:
        registry = _WORKSPACE_REGISTRIES.get(resolved_workspace_id)
        if registry is None:
            registry = WorkspaceHealthRegistry(resolved_workspace_id, policy=policy)
            _WORKSPACE_REGISTRIES[resolved_workspace_id] = registry
        elif policy is not None:
            registry.policy = policy
        return registry


def reset_health_monitor_state(workspace_id: str | None = None) -> None:
    with _WORKSPACE_REGISTRY_LOCK:
        if workspace_id is None:
            _WORKSPACE_REGISTRIES.clear()
            return
        _WORKSPACE_REGISTRIES.pop(_resolve_workspace_id(workspace_id), None)


def build_health_scope(
    metadata: Mapping[str, Any] | None,
    agent_id: str,
    *,
    dispatch_type: str | None = None,
    workspace_id: str | None = None,
) -> HealthScope:
    source = metadata or {}
    return HealthScope(
        workspace_id=_resolve_workspace_id(workspace_id, source),
        session_id=_resolve_session_id(source),
        agent_id=_text(agent_id, default="unknown-agent"),
        task_family=_resolve_task_family(dispatch_type, source),
        model_id=_resolve_model_id(source),
    )


def build_health_policy(metadata: Mapping[str, Any] | None) -> HealthPolicy:
    return HealthPolicy.from_metadata(metadata or {})


def build_health_metadata(
    decision: HealthDecision,
    *,
    agent_id: str | None = None,
) -> dict[str, Any]:
    return decision.to_metadata(agent_id=agent_id)


def classify_health_observation(
    *,
    scope: HealthScope,
    result: Any = None,
    error: BaseException | None = None,
    source: str = "dispatch",
) -> HealthObservation:
    if error is not None:
        failure_kind = classify_execution_failure_kind(error=error)
        return HealthObservation.execution_failure(
            scope,
            failure_kind=failure_kind or "exception",
            message=_text(error),
            source=source,
        )

    failure_kind = classify_execution_failure_kind(payload=result)
    if failure_kind in HEALTH_FAILURE_KINDS:
        return HealthObservation.execution_failure(
            scope,
            failure_kind=failure_kind,
            message=_text(result.get("error") if isinstance(result, dict) else ""),
            source=source,
        )

    if failure_kind == "malformed_output":
        return HealthObservation.execution_failure(
            scope,
            failure_kind="malformed_output",
            message="non-dict result returned by agent callback",
            source=source,
        )

    return HealthObservation.success(scope, source=source)


__all__ = [
    "WorkspaceHealthRegistry",
    "build_health_metadata",
    "build_health_policy",
    "build_health_scope",
    "classify_execution_failure_kind",
    "classify_health_observation",
    "get_workspace_health_registry",
    "reset_health_monitor_state",
]