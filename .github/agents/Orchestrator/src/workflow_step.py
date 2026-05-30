from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping

from src.workflow_types import WorkflowEffect, WorkflowPlan, WorkflowStepKind, freeze_json_value


def _always_true(*_args: Any, **_kwargs: Any) -> bool:
    return True


@dataclass(frozen=True)
class WorkflowRetryPolicy:
    """Local retry policy for a single workflow step."""

    max_attempts: int = 1
    retry_on: tuple[type[BaseException], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_attempts", int(self.max_attempts))
        object.__setattr__(self, "retry_on", tuple(self.retry_on))
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")


@dataclass(frozen=True)
class WorkflowTransition:
    """Deterministic transition to a downstream step."""

    target_step_id: str
    predicate: Callable[["WorkflowStepContext", Any], bool] = field(default=_always_true)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_step_id", str(self.target_step_id).strip())
        if not callable(self.predicate):
            raise TypeError("predicate must be callable")


@dataclass(frozen=True)
class WorkflowStepContext:
    """Read-only context passed to a workflow step at execution time."""

    plan: WorkflowPlan
    step: "WorkflowStep"
    attempt: int = 1
    workflow_context: Mapping[str, Any] = field(default_factory=dict)
    inputs: Mapping[str, Any] = field(default_factory=dict)
    completed_outputs: Mapping[str, Any] = field(default_factory=dict)
    execution_order: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempt", int(self.attempt))
        object.__setattr__(self, "workflow_context", freeze_json_value(self.workflow_context or {}))
        object.__setattr__(self, "inputs", freeze_json_value(self.inputs or {}))
        object.__setattr__(self, "completed_outputs", freeze_json_value(self.completed_outputs or {}))
        object.__setattr__(self, "execution_order", tuple(str(step_id) for step_id in self.execution_order))


@dataclass(frozen=True)
class WorkflowStep:
    """A single deterministic workflow node."""

    step_id: str
    run: Callable[[WorkflowStepContext], Any]
    kind: WorkflowStepKind = WorkflowStepKind.NORMAL
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    transitions: tuple[WorkflowTransition, ...] = field(default_factory=tuple)
    retry: WorkflowRetryPolicy = field(default_factory=WorkflowRetryPolicy)
    effect: WorkflowEffect = WorkflowEffect.PURE

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", str(self.step_id).strip())
        object.__setattr__(self, "depends_on", tuple(str(step_id).strip() for step_id in self.depends_on))
        object.__setattr__(self, "transitions", tuple(self.transitions))
        if not callable(self.run):
            raise TypeError("run must be callable")
        if not isinstance(self.kind, WorkflowStepKind):
            object.__setattr__(self, "kind", WorkflowStepKind(str(self.kind)))
        if not isinstance(self.effect, WorkflowEffect):
            object.__setattr__(self, "effect", WorkflowEffect(str(self.effect)))

    def with_retry_policy(self, retry: WorkflowRetryPolicy) -> "WorkflowStep":
        return replace(self, retry=retry)