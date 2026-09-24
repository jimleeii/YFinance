from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class WorkflowStepKind(str, Enum):
    NORMAL = "normal"
    RESULT = "result"


class WorkflowEffect(str, Enum):
    PURE = "pure"
    IDEMPOTENT = "idempotent"
    SIDE_EFFECTING = "side_effecting"


def freeze_json_value(value: Any) -> Any:
    """Convert a value into an immutable, JSON-safe structure."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Enum):
        return freeze_json_value(value.value)

    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): freeze_json_value(item)
                for key, item in value.items()
            }
        )

    if isinstance(value, (list, tuple)):
        return tuple(freeze_json_value(item) for item in value)

    if isinstance(value, (set, frozenset)):
        frozen_items = [freeze_json_value(item) for item in value]
        frozen_items.sort(key=repr)
        return tuple(frozen_items)

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        return freeze_json_value(value.to_dict())

    if is_dataclass(value):
        return freeze_json_value({name: getattr(value, name) for name in value.__dataclass_fields__})

    return str(value)


def to_jsonable_value(value: Any) -> Any:
    """Convert a frozen value into plain Python JSON data structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, MappingProxyType):
        return {key: to_jsonable_value(item) for key, item in value.items()}

    if isinstance(value, Mapping):
        return {str(key): to_jsonable_value(item) for key, item in value.items()}

    if isinstance(value, tuple):
        return [to_jsonable_value(item) for item in value]

    if isinstance(value, list):
        return [to_jsonable_value(item) for item in value]

    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        return value.to_dict()

    return str(value)


@dataclass(frozen=True)
class WorkflowPlan:
    """Validated workflow plan consumed by the state machine."""

    steps: tuple["WorkflowStep", ...] = field(default_factory=tuple)
    result_step_id: str = ""
    name: str = "workflow"

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "result_step_id", str(self.result_step_id).strip())
        object.__setattr__(self, "name", str(self.name).strip() or "workflow")


@dataclass(frozen=True)
class WorkflowStepSnapshot:
    """Immutable record describing a single step execution attempt group."""

    step_id: str
    attempts: int
    status: str
    output: Any = None
    error: Any = None
    selected_next_step_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", str(self.step_id))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "attempts", int(self.attempts))
        object.__setattr__(self, "output", freeze_json_value(self.output))
        object.__setattr__(self, "error", freeze_json_value(self.error))
        if self.selected_next_step_id is not None:
            object.__setattr__(self, "selected_next_step_id", str(self.selected_next_step_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "attempts": self.attempts,
            "status": self.status,
            "output": to_jsonable_value(self.output),
            "error": to_jsonable_value(self.error),
            "selected_next_step_id": self.selected_next_step_id,
        }


@dataclass(frozen=True)
class WorkflowExecutionSnapshot:
    """Immutable, JSON-safe summary of a workflow execution."""

    plan_name: str
    status: str
    result_step_id: str
    terminal_step_id: str | None
    result: Any = None
    workflow_context: Any = None
    step_snapshots: tuple[WorkflowStepSnapshot, ...] = field(default_factory=tuple)
    execution_order: tuple[str, ...] = field(default_factory=tuple)
    failed_step_id: str | None = None
    failure: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_name", str(self.plan_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "result_step_id", str(self.result_step_id))
        object.__setattr__(self, "terminal_step_id", str(self.terminal_step_id) if self.terminal_step_id is not None else None)
        object.__setattr__(self, "result", freeze_json_value(self.result))
        object.__setattr__(self, "workflow_context", freeze_json_value(self.workflow_context or {}))
        object.__setattr__(self, "step_snapshots", tuple(self.step_snapshots))
        object.__setattr__(self, "execution_order", tuple(str(step_id) for step_id in self.execution_order))
        if self.failed_step_id is not None:
            object.__setattr__(self, "failed_step_id", str(self.failed_step_id))
        object.__setattr__(self, "failure", freeze_json_value(self.failure))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_name": self.plan_name,
            "status": self.status,
            "result_step_id": self.result_step_id,
            "terminal_step_id": self.terminal_step_id,
            "result": to_jsonable_value(self.result),
            "workflow_context": to_jsonable_value(self.workflow_context),
            "step_snapshots": [snapshot.to_dict() for snapshot in self.step_snapshots],
            "execution_order": list(self.execution_order),
            "failed_step_id": self.failed_step_id,
            "failure": to_jsonable_value(self.failure),
        }