from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from src.workflow_types import freeze_json_value, to_jsonable_value


HEALTH_FAILURE_KINDS = ("exception", "timeout", "transport", "malformed_output")
HEALTH_STATE_VALUES = ("closed", "open", "half-open")
HEALTH_ACTION_VALUES = ("allow", "probe", "suppress")


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


def _sequence_text(*values: Any) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()

    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple, set, frozenset)):
            items = [str(item).strip() for item in value]
        else:
            items = [str(value).strip()]

        for item in items:
            if not item:
                continue
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

    return tuple(merged)


def _utc_now_iso(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_failure_kind(value: Any) -> str:
    kind = _text(value).replace("-", "_").replace(" ", "_").lower()
    return kind


def _normalize_state(value: Any) -> str:
    state = _text(value, default="closed").replace("_", "-").lower()
    if state not in HEALTH_STATE_VALUES:
        return "closed"
    return state


def _normalize_action(value: Any) -> str:
    action = _text(value, default="allow").lower()
    if action not in HEALTH_ACTION_VALUES:
        return "allow"
    return action


@dataclass(frozen=True)
class HealthPolicy:
    """Circuit-breaker policy for a single workspace registry."""

    failure_threshold: int = 1
    open_cooldown_seconds: int = 30
    probe_cooldown_seconds: int = 60
    probe_allowlist: tuple[str, ...] = field(default_factory=tuple)
    backoff_factor: float = 2.0
    max_backoff_seconds: int = 300

    def __post_init__(self) -> None:
        object.__setattr__(self, "failure_threshold", _positive_int(self.failure_threshold, 1))
        object.__setattr__(self, "open_cooldown_seconds", _non_negative_int(self.open_cooldown_seconds, 30))
        object.__setattr__(self, "probe_cooldown_seconds", _non_negative_int(self.probe_cooldown_seconds, 60))
        object.__setattr__(self, "probe_allowlist", _sequence_text(self.probe_allowlist))
        try:
            backoff_factor = float(self.backoff_factor)
        except Exception:
            backoff_factor = 2.0
        if backoff_factor < 1.0:
            backoff_factor = 1.0
        object.__setattr__(self, "backoff_factor", backoff_factor)
        object.__setattr__(self, "max_backoff_seconds", _non_negative_int(self.max_backoff_seconds, 300))

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any] | None = None) -> "HealthPolicy":
        source = metadata or {}
        allowlist = source.get("health_probe_allowlist")
        if allowlist is None:
            allowlist = source.get("probe_allowlist")
        if allowlist is None:
            allowlist = source.get("health_probe_candidates")
        return cls(
            failure_threshold=_positive_int(source.get("health_failure_threshold"), 1),
            open_cooldown_seconds=_non_negative_int(source.get("health_open_cooldown_seconds"), 30),
            probe_cooldown_seconds=_non_negative_int(source.get("health_probe_cooldown_seconds"), 60),
            probe_allowlist=_sequence_text(allowlist),
            backoff_factor=float(source.get("health_backoff_factor") or 2.0),
            max_backoff_seconds=_non_negative_int(source.get("health_max_backoff_seconds"), 300),
        )

    def allows_probe(self, agent_id: Any) -> bool:
        agent_text = _text(agent_id)
        if not agent_text:
            return False
        if not self.probe_allowlist:
            return True
        agent_key = agent_text.casefold()
        return any(candidate.casefold() == agent_key for candidate in self.probe_allowlist)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_threshold": self.failure_threshold,
            "open_cooldown_seconds": self.open_cooldown_seconds,
            "probe_cooldown_seconds": self.probe_cooldown_seconds,
            "probe_allowlist": list(self.probe_allowlist),
            "backoff_factor": self.backoff_factor,
            "max_backoff_seconds": self.max_backoff_seconds,
        }


@dataclass(frozen=True)
class HealthScope:
    """Hierarchical identity for one agent under one workspace/session/task family."""

    workspace_id: str
    session_id: str
    agent_id: str
    task_family: str
    model_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _text(self.workspace_id))
        object.__setattr__(self, "session_id", _text(self.session_id))
        object.__setattr__(self, "agent_id", _text(self.agent_id))
        object.__setattr__(self, "task_family", _text(self.task_family))
        object.__setattr__(self, "model_id", _optional_text(self.model_id))

    def to_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.workspace_id,
            self.session_id,
            self.agent_id,
            self.task_family,
            self.model_id or "",
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "task_family": self.task_family,
        }
        if self.model_id:
            data["model_id"] = self.model_id
        return data


@dataclass(frozen=True)
class HealthObservation:
    """Execution-health observation for one scope."""

    scope: HealthScope
    outcome: str = "success"
    failure_kind: str | None = None
    message: str = ""
    counts_toward_health: bool = False
    source: str = "dispatch"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    observed_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", _text(self.outcome, default="success").lower())
        object.__setattr__(self, "failure_kind", _optional_text(self.failure_kind))
        object.__setattr__(self, "message", _text(self.message))
        object.__setattr__(self, "source", _text(self.source, default="dispatch"))
        object.__setattr__(self, "metadata", freeze_json_value(dict(self.metadata or {})))
        object.__setattr__(self, "observed_at", _optional_text(self.observed_at))

    @classmethod
    def success(
        cls,
        scope: HealthScope,
        *,
        message: str = "",
        source: str = "dispatch",
        metadata: Mapping[str, Any] | None = None,
        observed_at: str | None = None,
    ) -> "HealthObservation":
        return cls(
            scope=scope,
            outcome="success",
            message=message,
            counts_toward_health=False,
            source=source,
            metadata=metadata or {},
            observed_at=observed_at,
        )

    @classmethod
    def execution_failure(
        cls,
        scope: HealthScope,
        *,
        failure_kind: str,
        message: str = "",
        source: str = "dispatch",
        metadata: Mapping[str, Any] | None = None,
        observed_at: str | None = None,
    ) -> "HealthObservation":
        normalized_kind = _normalize_failure_kind(failure_kind)
        if normalized_kind not in HEALTH_FAILURE_KINDS:
            raise ValueError(f"unsupported execution-health failure kind: {failure_kind!r}")
        return cls(
            scope=scope,
            outcome="failure",
            failure_kind=normalized_kind,
            message=message,
            counts_toward_health=True,
            source=source,
            metadata=metadata or {},
            observed_at=observed_at,
        )

    @classmethod
    def quality_failure(
        cls,
        scope: HealthScope,
        *,
        message: str = "",
        source: str = "dispatch",
        metadata: Mapping[str, Any] | None = None,
        observed_at: str | None = None,
    ) -> "HealthObservation":
        return cls(
            scope=scope,
            outcome="failure",
            failure_kind="quality",
            message=message,
            counts_toward_health=False,
            source=source,
            metadata=metadata or {},
            observed_at=observed_at,
        )

    @classmethod
    def ignored(
        cls,
        scope: HealthScope,
        *,
        message: str = "",
        source: str = "dispatch",
        metadata: Mapping[str, Any] | None = None,
        observed_at: str | None = None,
    ) -> "HealthObservation":
        return cls(
            scope=scope,
            outcome="ignored",
            message=message,
            counts_toward_health=False,
            source=source,
            metadata=metadata or {},
            observed_at=observed_at,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "scope": self.scope.to_dict(),
            "outcome": self.outcome,
            "counts_toward_health": self.counts_toward_health,
            "source": self.source,
        }
        if self.failure_kind:
            data["failure_kind"] = self.failure_kind
        if self.message:
            data["message"] = self.message
        if self.observed_at:
            data["observed_at"] = self.observed_at
        if self.metadata:
            data["metadata"] = to_jsonable_value(self.metadata)
        return data


@dataclass(frozen=True)
class HealthState:
    """Immutable circuit-breaker state for one health scope."""

    status: str = "closed"
    failure_count: int = 0
    success_count: int = 0
    open_until: str | None = None
    probe_reserved_until: str | None = None
    last_observed_at: str | None = None
    last_failure_at: str | None = None
    last_success_at: str | None = None
    last_probe_at: str | None = None
    probe_count: int = 0
    reopen_count: int = 0
    last_failure_kind: str | None = None
    last_failure_message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _normalize_state(self.status))
        object.__setattr__(self, "failure_count", max(0, int(self.failure_count)))
        object.__setattr__(self, "success_count", max(0, int(self.success_count)))
        object.__setattr__(self, "probe_count", max(0, int(self.probe_count)))
        object.__setattr__(self, "reopen_count", max(0, int(self.reopen_count)))
        object.__setattr__(self, "open_until", _optional_text(self.open_until))
        object.__setattr__(self, "probe_reserved_until", _optional_text(self.probe_reserved_until))
        object.__setattr__(self, "last_observed_at", _optional_text(self.last_observed_at))
        object.__setattr__(self, "last_failure_at", _optional_text(self.last_failure_at))
        object.__setattr__(self, "last_success_at", _optional_text(self.last_success_at))
        object.__setattr__(self, "last_probe_at", _optional_text(self.last_probe_at))
        object.__setattr__(self, "last_failure_kind", _optional_text(self.last_failure_kind))
        object.__setattr__(self, "last_failure_message", _optional_text(self.last_failure_message))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "open_until": self.open_until,
            "probe_reserved_until": self.probe_reserved_until,
            "last_observed_at": self.last_observed_at,
            "last_failure_at": self.last_failure_at,
            "last_success_at": self.last_success_at,
            "last_probe_at": self.last_probe_at,
            "probe_count": self.probe_count,
            "reopen_count": self.reopen_count,
            "last_failure_kind": self.last_failure_kind,
            "last_failure_message": self.last_failure_message,
        }


@dataclass(frozen=True)
class HealthRecord:
    """Immutable record for a scope/state pair in a snapshot."""

    scope: HealthScope
    state: HealthState

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.to_dict(),
            "state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class HealthSnapshot:
    """Immutable, deterministic snapshot of one workspace registry."""

    workspace_id: str
    policy: HealthPolicy
    generated_at: str
    records: tuple[HealthRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _text(self.workspace_id))
        object.__setattr__(self, "generated_at", _text(self.generated_at))
        object.__setattr__(self, "records", tuple(self.records))

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "generated_at": self.generated_at,
            "policy": self.policy.to_dict(),
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(frozen=True)
class HealthDecision:
    """Pre-invocation routing decision for a candidate list."""

    workspace_id: str
    session_id: str
    task_family: str
    model_id: str | None
    state: str
    action: str
    reason: str
    selected_candidates: tuple[str, ...] = field(default_factory=tuple)
    suppressed_candidates: tuple[str, ...] = field(default_factory=tuple)
    probe_candidate: str | None = None
    failure_kind: str | None = None
    failure_message: str | None = None
    snapshot: HealthSnapshot | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _text(self.workspace_id))
        object.__setattr__(self, "session_id", _text(self.session_id))
        object.__setattr__(self, "task_family", _text(self.task_family))
        object.__setattr__(self, "model_id", _optional_text(self.model_id))
        object.__setattr__(self, "state", _normalize_state(self.state))
        object.__setattr__(self, "action", _normalize_action(self.action))
        object.__setattr__(self, "reason", _text(self.reason))
        object.__setattr__(self, "selected_candidates", _sequence_text(self.selected_candidates))
        object.__setattr__(self, "suppressed_candidates", _sequence_text(self.suppressed_candidates))
        object.__setattr__(self, "probe_candidate", _optional_text(self.probe_candidate))
        object.__setattr__(self, "failure_kind", _optional_text(self.failure_kind))
        object.__setattr__(self, "failure_message", _optional_text(self.failure_message))

    @property
    def effective_candidates(self) -> tuple[str, ...]:
        return self.selected_candidates

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "task_family": self.task_family,
            "state": self.state,
            "action": self.action,
            "reason": self.reason,
            "selected_candidates": list(self.selected_candidates),
            "suppressed_candidates": list(self.suppressed_candidates),
            "probe_candidate": self.probe_candidate,
        }
        if self.model_id:
            data["model_id"] = self.model_id
        if self.failure_kind:
            data["failure_kind"] = self.failure_kind
        if self.failure_message:
            data["failure_message"] = self.failure_message
        if self.snapshot is not None:
            data["snapshot"] = self.snapshot.to_dict()
        return data

    def to_metadata(self, agent_id: str | None = None) -> dict[str, Any]:
        health_payload = self.to_dict()
        if agent_id:
            health_payload["agent_id"] = _text(agent_id)

        metadata: dict[str, Any] = {
            "health": health_payload,
            "health_workspace_id": self.workspace_id,
            "health_session_id": self.session_id,
            "health_task_family": self.task_family,
            "health_state": self.state,
            "health_action": self.action,
            "health_reason": self.reason,
            "health_selected_candidates": list(self.selected_candidates),
            "health_suppressed_candidates": list(self.suppressed_candidates),
            "health_probe_candidate": self.probe_candidate or "",
        }
        if self.model_id:
            metadata["health_model_id"] = self.model_id
        if self.failure_kind:
            metadata["health_failure_kind"] = self.failure_kind
        if self.failure_message:
            metadata["health_failure_message"] = self.failure_message
        if self.snapshot is not None:
            metadata["health_snapshot"] = self.snapshot.to_dict()
        if agent_id:
            metadata["health_agent_id"] = _text(agent_id)
        return metadata
