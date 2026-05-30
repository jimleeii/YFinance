from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.workflow_step import WorkflowEffect, WorkflowStep, WorkflowStepContext
from src.workflow_types import WorkflowExecutionSnapshot, WorkflowPlan, WorkflowStepKind, WorkflowStepSnapshot, freeze_json_value


class WorkflowValidationError(ValueError):
    """Raised when a workflow plan is structurally invalid."""


class WorkflowStateMachine:
    """Pure deterministic DAG executor for a validated workflow plan."""

    def __init__(self, plan: WorkflowPlan):
        self.plan = plan
        self._steps = tuple(plan.steps)
        self._step_by_id = {step.step_id: step for step in self._steps}
        self._step_order = {step.step_id: index for index, step in enumerate(self._steps)}
        self._incoming_transition_sources: Dict[str, tuple[str, ...]] = {}
        self._dependents: Dict[str, tuple[str, ...]] = {}
        self._validate_and_index_plan()

    def _validate_and_index_plan(self) -> None:
        if not self._steps:
            raise WorkflowValidationError("workflow plan must contain at least one step")

        if not self.plan.result_step_id:
            raise WorkflowValidationError("workflow plan must define a result_step_id")

        duplicate_ids = self._find_duplicate_step_ids()
        if duplicate_ids:
            raise WorkflowValidationError(f"duplicate workflow step id(s): {', '.join(duplicate_ids)}")

        result_steps = [step.step_id for step in self._steps if step.kind == WorkflowStepKind.RESULT]
        if not result_steps:
            raise WorkflowValidationError(f"workflow plan is missing required result sink: {self.plan.result_step_id}")
        if len(result_steps) > 1:
            raise WorkflowValidationError(f"workflow plan defines duplicate result sinks: {', '.join(result_steps)}")

        result_step = self._step_by_id.get(self.plan.result_step_id)
        if result_step is None:
            raise WorkflowValidationError(f"workflow plan is missing required result sink: {self.plan.result_step_id}")
        if result_step.kind != WorkflowStepKind.RESULT:
            raise WorkflowValidationError(
                f"result_step_id '{self.plan.result_step_id}' must reference the step marked as WorkflowStepKind.RESULT"
            )

        incoming_transition_sources: Dict[str, List[str]] = {step.step_id: [] for step in self._steps}
        dependents: Dict[str, List[str]] = {step.step_id: [] for step in self._steps}
        adjacency: Dict[str, List[str]] = {step.step_id: [] for step in self._steps}

        for step in self._steps:
            for dependency_id in step.depends_on:
                if dependency_id not in self._step_by_id:
                    raise WorkflowValidationError(
                        f"step '{step.step_id}' depends on unknown step '{dependency_id}'"
                    )
                dependents[dependency_id].append(step.step_id)
                adjacency[dependency_id].append(step.step_id)

            for transition in step.transitions:
                if transition.target_step_id not in self._step_by_id:
                    raise WorkflowValidationError(
                        f"step '{step.step_id}' targets unknown step '{transition.target_step_id}'"
                    )
                incoming_transition_sources[transition.target_step_id].append(step.step_id)
                adjacency[step.step_id].append(transition.target_step_id)

        if dependents[self.plan.result_step_id]:
            raise WorkflowValidationError(
                f"result step '{self.plan.result_step_id}' cannot be a dependency source for other steps"
            )

        if result_step.transitions:
            raise WorkflowValidationError(
                f"result step '{self.plan.result_step_id}' must not define outgoing transitions"
            )

        for step in self._steps:
            if step.step_id != self.plan.result_step_id and not step.transitions and not dependents[step.step_id]:
                raise WorkflowValidationError(
                    f"step '{step.step_id}' is a terminal sink; only '{self.plan.result_step_id}' may terminate the workflow"
                )

            if step.retry.max_attempts > 1 and step.effect == WorkflowEffect.SIDE_EFFECTING:
                raise WorkflowValidationError(
                    f"step '{step.step_id}' is side-effecting and cannot retry under the workflow contract"
                )

        self._detect_cycles(adjacency)
        self._incoming_transition_sources = {
            step_id: tuple(sorted(sources, key=self._plan_sort_key))
            for step_id, sources in incoming_transition_sources.items()
        }
        self._dependents = {
            step_id: tuple(sorted(children, key=self._plan_sort_key))
            for step_id, children in dependents.items()
        }

    def _find_duplicate_step_ids(self) -> list[str]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for step in self._steps:
            if step.step_id in seen and step.step_id not in duplicates:
                duplicates.append(step.step_id)
            seen.add(step.step_id)
        return duplicates

    def _detect_cycles(self, adjacency: Mapping[str, Sequence[str]]) -> None:
        temporary: set[str] = set()
        permanent: set[str] = set()
        trail: list[str] = []

        def visit(node_id: str) -> None:
            if node_id in permanent:
                return
            if node_id in temporary:
                cycle_start = trail.index(node_id) if node_id in trail else 0
                cycle_path = trail[cycle_start:] + [node_id]
                raise WorkflowValidationError(
                    f"workflow plan contains a cycle: {' -> '.join(cycle_path)}"
                )

            temporary.add(node_id)
            trail.append(node_id)
            for next_node in adjacency.get(node_id, ()):
                visit(next_node)
            trail.pop()
            temporary.remove(node_id)
            permanent.add(node_id)

        for step in self._steps:
            visit(step.step_id)

    def _plan_sort_key(self, step_id: str) -> int:
        return self._step_order[step_id]

    def _step_inputs(self, completed_outputs: Mapping[str, Any], step: WorkflowStep) -> Mapping[str, Any]:
        return {dependency_id: completed_outputs[dependency_id] for dependency_id in step.depends_on}

    def _is_step_ready(
        self,
        step: WorkflowStep,
        completed_step_ids: set[str],
        activated_step_ids: set[str],
    ) -> bool:
        if step.step_id in completed_step_ids:
            return False

        if any(dependency_id not in completed_step_ids for dependency_id in step.depends_on):
            return False

        incoming_sources = self._incoming_transition_sources.get(step.step_id, ())
        if incoming_sources:
            return step.step_id in activated_step_ids

        return True

    def _evaluate_transition(
        self,
        step: WorkflowStep,
        context: WorkflowStepContext,
        output: Any,
    ) -> str | None:
        for transition in step.transitions:
            if transition.predicate(context, output):
                return transition.target_step_id
        return None

    def _should_retry(self, step: WorkflowStep, error: BaseException, attempts: int) -> bool:
        if attempts >= step.retry.max_attempts:
            return False
        if step.effect not in {WorkflowEffect.PURE, WorkflowEffect.IDEMPOTENT}:
            return False
        if not step.retry.retry_on:
            return False
        return any(isinstance(error, error_type) for error_type in step.retry.retry_on)

    def _failure_payload(
        self,
        *,
        step_id: str,
        error: BaseException,
        attempts: int,
        retryable: bool,
    ) -> dict[str, Any]:
        return {
            "step_id": step_id,
            "type": error.__class__.__name__,
            "message": str(error),
            "attempts": attempts,
            "retryable": retryable,
        }

    def execute(
        self,
        context: Optional[Mapping[str, Any]] = None,
        workflow_context: Optional[Mapping[str, Any]] = None,
    ) -> WorkflowExecutionSnapshot:
        runtime_context = workflow_context if workflow_context is not None else context
        frozen_runtime_context = freeze_json_value(runtime_context or {})
        completed_outputs: Dict[str, Any] = {}
        completed_step_ids: set[str] = set()
        activated_step_ids: set[str] = {
            step.step_id for step in self._steps if not self._incoming_transition_sources.get(step.step_id)
        }
        step_snapshots: list[WorkflowStepSnapshot] = []
        execution_order: list[str] = []

        while True:
            ready_steps = [
                step
                for step in self._steps
                if self._is_step_ready(step, completed_step_ids, activated_step_ids)
            ]

            if not ready_steps:
                if self.plan.result_step_id in completed_step_ids:
                    result_snapshot = next(
                        (snapshot for snapshot in step_snapshots if snapshot.step_id == self.plan.result_step_id),
                        None,
                    )
                    return WorkflowExecutionSnapshot(
                        plan_name=self.plan.name,
                        status="success",
                        result_step_id=self.plan.result_step_id,
                        terminal_step_id=self.plan.result_step_id,
                        result=result_snapshot.output if result_snapshot is not None else None,
                        workflow_context=frozen_runtime_context,
                        step_snapshots=tuple(step_snapshots),
                        execution_order=tuple(execution_order),
                    )

                failure = {
                    "type": "WorkflowDeadEnd",
                    "message": f"workflow dead-ended before reaching result step '{self.plan.result_step_id}'",
                    "result_step_id": self.plan.result_step_id,
                }
                return WorkflowExecutionSnapshot(
                    plan_name=self.plan.name,
                    status="failed",
                    result_step_id=self.plan.result_step_id,
                    terminal_step_id=execution_order[-1] if execution_order else None,
                    workflow_context=frozen_runtime_context,
                    step_snapshots=tuple(step_snapshots),
                    execution_order=tuple(execution_order),
                    failed_step_id=execution_order[-1] if execution_order else None,
                    failure=failure,
                )

            ready_steps.sort(key=lambda step: self._plan_sort_key(step.step_id))
            step = ready_steps[0]
            context_inputs = freeze_json_value(self._step_inputs(completed_outputs, step))
            completed_snapshot = freeze_json_value(completed_outputs)
            step_context = WorkflowStepContext(
                plan=self.plan,
                step=step,
                attempt=1,
                workflow_context=frozen_runtime_context,
                inputs=context_inputs,
                completed_outputs=completed_snapshot,
                execution_order=tuple(execution_order),
            )

            attempts = 0
            output: Any = None
            selected_next_step_id: str | None = None
            failure_payload: dict[str, Any] | None = None

            while True:
                attempts += 1
                attempt_context = replace(step_context, attempt=attempts)
                try:
                    raw_output = step.run(attempt_context)
                    output = freeze_json_value(raw_output)
                except BaseException as exc:  # pragma: no cover - deliberate broad capture for workflow safety
                    retryable = self._should_retry(step, exc, attempts)
                    if retryable:
                        continue
                    failure_payload = self._failure_payload(
                        step_id=step.step_id,
                        error=exc,
                        attempts=attempts,
                        retryable=False,
                    )
                    break

                try:
                    selected_next_step_id = self._evaluate_transition(step, attempt_context, output)
                    failure_payload = None
                    break
                except BaseException as exc:  # pragma: no cover - deliberate broad capture for workflow safety
                    failure_payload = self._failure_payload(
                        step_id=step.step_id,
                        error=exc,
                        attempts=attempts,
                        retryable=False,
                    )
                    break

            if failure_payload is not None:
                step_snapshots.append(
                    WorkflowStepSnapshot(
                        step_id=step.step_id,
                        attempts=attempts,
                        status="failed",
                        output=None,
                        error=failure_payload,
                        selected_next_step_id=None,
                    )
                )
                return WorkflowExecutionSnapshot(
                    plan_name=self.plan.name,
                    status="failed",
                    result_step_id=self.plan.result_step_id,
                    terminal_step_id=step.step_id,
                    workflow_context=frozen_runtime_context,
                    step_snapshots=tuple(step_snapshots),
                    execution_order=tuple(execution_order),
                    failed_step_id=step.step_id,
                    failure=failure_payload,
                )

            completed_step_ids.add(step.step_id)
            completed_outputs[step.step_id] = output
            execution_order.append(step.step_id)

            if selected_next_step_id is not None:
                activated_step_ids.add(selected_next_step_id)

            step_snapshots.append(
                WorkflowStepSnapshot(
                    step_id=step.step_id,
                    attempts=attempts,
                    status="completed",
                    output=output,
                    error=None,
                    selected_next_step_id=selected_next_step_id,
                )
            )

            if step.step_id == self.plan.result_step_id:
                return WorkflowExecutionSnapshot(
                    plan_name=self.plan.name,
                    status="success",
                    result_step_id=self.plan.result_step_id,
                    terminal_step_id=step.step_id,
                    result=output,
                    workflow_context=frozen_runtime_context,
                    step_snapshots=tuple(step_snapshots),
                    execution_order=tuple(execution_order),
                )


def execute_workflow_plan(
    plan: WorkflowPlan,
    context: Optional[Mapping[str, Any]] = None,
    workflow_context: Optional[Mapping[str, Any]] = None,
) -> WorkflowExecutionSnapshot:
    """Execute a validated workflow plan and return an immutable execution snapshot."""

    return WorkflowStateMachine(plan).execute(context=context, workflow_context=workflow_context)