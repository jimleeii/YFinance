from __future__ import annotations

import ast
import json
import os
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

os.environ.setdefault("ORCHESTRATOR_SKIP_AUTOINIT", "1")

from src.orchestrator_runtime import classify_dispatch_type, execute_dispatch_by_type, execute_workflow_plan
from src.workflow_state_machine import WorkflowStateMachine, WorkflowValidationError
from src.workflow_step import WorkflowEffect, WorkflowRetryPolicy, WorkflowStep, WorkflowStepContext, WorkflowStepKind, WorkflowTransition
from src.workflow_types import WorkflowPlan


class WorkflowEngineTests(unittest.TestCase):
    def _result_step(self, step_id: str = "result") -> WorkflowStep:
        return WorkflowStep(
            step_id=step_id,
            kind=WorkflowStepKind.RESULT,
            run=lambda _context: {"result": step_id},
        )

    def _plan(self, *steps: WorkflowStep, result_step_id: str = "result", name: str = "workflow-test") -> WorkflowPlan:
        return WorkflowPlan(steps=steps, result_step_id=result_step_id, name=name)

    def test_validation_rejects_duplicate_step_ids(self) -> None:
        plan = self._plan(
            WorkflowStep(step_id="start", run=lambda _context: "first"),
            WorkflowStep(step_id="start", run=lambda _context: "second"),
            self._result_step(),
        )

        with self.assertRaises(WorkflowValidationError) as cm:
            WorkflowStateMachine(plan)

        self.assertIn("duplicate", str(cm.exception).lower())

    def test_validation_rejects_unknown_transition_target(self) -> None:
        plan = self._plan(
            WorkflowStep(
                step_id="start",
                run=lambda _context: "start",
                transitions=(WorkflowTransition(target_step_id="missing"),),
            ),
            self._result_step(),
        )

        with self.assertRaises(WorkflowValidationError) as cm:
            WorkflowStateMachine(plan)

        self.assertIn("missing", str(cm.exception).lower())

    def test_validation_rejects_cycle(self) -> None:
        plan = self._plan(
            WorkflowStep(
                step_id="alpha",
                run=lambda _context: "alpha",
                transitions=(WorkflowTransition(target_step_id="beta"),),
            ),
            WorkflowStep(
                step_id="beta",
                run=lambda _context: "beta",
                transitions=(WorkflowTransition(target_step_id="alpha"),),
            ),
            self._result_step(),
        )

        with self.assertRaises(WorkflowValidationError) as cm:
            WorkflowStateMachine(plan)

        self.assertIn("cycle", str(cm.exception).lower())

    def test_validation_rejects_missing_result_sink(self) -> None:
        plan = self._plan(
            WorkflowStep(step_id="start", run=lambda _context: "start"),
            WorkflowStep(step_id="finish", run=lambda _context: "finish"),
            result_step_id="result",
        )

        with self.assertRaises(WorkflowValidationError) as cm:
            WorkflowStateMachine(plan)

        self.assertIn("result", str(cm.exception).lower())

    def test_validation_rejects_duplicate_result_sink(self) -> None:
        plan = self._plan(
            WorkflowStep(step_id="start", run=lambda _context: "start"),
            WorkflowStep(step_id="result", kind=WorkflowStepKind.RESULT, run=lambda _context: "first result"),
            WorkflowStep(step_id="final", kind=WorkflowStepKind.RESULT, run=lambda _context: "second result"),
            result_step_id="result",
        )

        with self.assertRaises(WorkflowValidationError) as cm:
            WorkflowStateMachine(plan)

        self.assertIn("result", str(cm.exception).lower())
        self.assertIn("duplicate", str(cm.exception).lower())

    def test_validation_rejects_retry_on_side_effecting_step(self) -> None:
        plan = self._plan(
            WorkflowStep(
                step_id="start",
                effect=WorkflowEffect.SIDE_EFFECTING,
                retry=WorkflowRetryPolicy(max_attempts=2, retry_on=(RuntimeError,)),
                run=lambda _context: "start",
                transitions=(WorkflowTransition(target_step_id="result"),),
            ),
            self._result_step(),
        )

        with self.assertRaises(WorkflowValidationError) as cm:
            WorkflowStateMachine(plan)

        self.assertIn("effect", str(cm.exception).lower())
        self.assertIn("retry", str(cm.exception).lower())

    def test_execute_plan_runs_root_steps_in_definition_order(self) -> None:
        observed: list[str] = []

        def make_step(step_id: str, *, depend_on_join: bool = False) -> WorkflowStep:
            dependencies = ("join",) if depend_on_join else ()
            transitions = (WorkflowTransition(target_step_id="join"),) if not depend_on_join else (WorkflowTransition(target_step_id="result"),)

            return WorkflowStep(
                step_id=step_id,
                depends_on=dependencies,
                transitions=transitions,
                run=lambda _context, label=step_id: observed.append(label) or {"step": label},
            )

        plan = self._plan(
            make_step("beta"),
            make_step("alpha"),
            WorkflowStep(
                step_id="join",
                depends_on=("beta", "alpha"),
                transitions=(WorkflowTransition(target_step_id="result"),),
                run=lambda context: observed.append("join") or {"inputs": sorted(context.inputs.keys())},
            ),
            WorkflowStep(
                step_id="result",
                kind=WorkflowStepKind.RESULT,
                depends_on=("join",),
                run=lambda context: observed.append("result") or {"final": context.inputs["join"]},
            ),
        )

        snapshot = execute_workflow_plan(plan, context={"request_id": "req-1"})

        self.assertEqual(snapshot.execution_order, ("beta", "alpha", "join", "result"))
        self.assertEqual(observed, ["beta", "alpha", "join", "result"])
        self.assertEqual(snapshot.status, "success")
        self.assertEqual(snapshot.result_step_id, "result")

    def test_execute_plan_honours_branch_precedence(self) -> None:
        observed: list[str] = []

        plan = self._plan(
            WorkflowStep(
                step_id="router",
                run=lambda _context: observed.append("router") or {"route": "special"},
                transitions=(
                    WorkflowTransition(target_step_id="special", predicate=lambda _context, output: output["route"] == "special"),
                    WorkflowTransition(target_step_id="fallback", predicate=lambda _context, _output: True),
                ),
            ),
            WorkflowStep(
                step_id="special",
                depends_on=("router",),
                transitions=(WorkflowTransition(target_step_id="result"),),
                run=lambda _context: observed.append("special") or {"branch": "special"},
            ),
            WorkflowStep(
                step_id="fallback",
                depends_on=("router",),
                transitions=(WorkflowTransition(target_step_id="result"),),
                run=lambda _context: observed.append("fallback") or {"branch": "fallback"},
            ),
            WorkflowStep(
                step_id="result",
                kind=WorkflowStepKind.RESULT,
                depends_on=("special",),
                run=lambda _context: observed.append("result") or {"selected": "special"},
            ),
        )

        snapshot = WorkflowStateMachine(plan).execute(context={"request_id": "req-2"})

        self.assertEqual(observed, ["router", "special", "result"])
        self.assertEqual(snapshot.execution_order, ("router", "special", "result"))
        self.assertEqual(snapshot.result["selected"], "special")

    def test_execute_plan_captures_branch_predicate_exception_as_structured_failure(self) -> None:
        class PredicateError(RuntimeError):
            pass

        def bad_predicate(_context: WorkflowStepContext, _output: object) -> bool:
            raise PredicateError("bad branch")

        plan = self._plan(
            WorkflowStep(
                step_id="router",
                run=lambda _context: {"route": "special"},
                transitions=(
                    WorkflowTransition(target_step_id="special", predicate=bad_predicate),
                    WorkflowTransition(target_step_id="fallback", predicate=lambda _context, _output: True),
                ),
            ),
            WorkflowStep(
                step_id="special",
                depends_on=("router",),
                transitions=(WorkflowTransition(target_step_id="result"),),
                run=lambda _context: {"branch": "special"},
            ),
            WorkflowStep(
                step_id="fallback",
                depends_on=("router",),
                transitions=(WorkflowTransition(target_step_id="result"),),
                run=lambda _context: {"branch": "fallback"},
            ),
            self._result_step(),
        )

        snapshot = WorkflowStateMachine(plan).execute()

        self.assertEqual(snapshot.status, "failed")
        self.assertEqual(snapshot.failed_step_id, "router")
        self.assertEqual(snapshot.terminal_step_id, "router")
        self.assertEqual(snapshot.execution_order, ())
        self.assertEqual(snapshot.step_snapshots[0].status, "failed")
        self.assertEqual(snapshot.step_snapshots[0].attempts, 1)
        self.assertEqual(snapshot.step_snapshots[0].error["type"], "PredicateError")
        self.assertFalse(snapshot.step_snapshots[0].error["retryable"])
        self.assertEqual(snapshot.failure["type"], "PredicateError")
        self.assertFalse(snapshot.failure["retryable"])

    def test_execute_plan_retries_safe_step_and_succeeds(self) -> None:
        attempts: list[int] = []

        class TransientError(RuntimeError):
            pass

        def flaky_step(_context: WorkflowStepContext) -> dict:
            attempts.append(len(attempts) + 1)
            if len(attempts) < 2:
                raise TransientError("try again")
            return {"attempt": len(attempts)}

        plan = self._plan(
            WorkflowStep(
                step_id="start",
                effect=WorkflowEffect.IDEMPOTENT,
                retry=WorkflowRetryPolicy(max_attempts=3, retry_on=(TransientError,)),
                transitions=(WorkflowTransition(target_step_id="result"),),
                run=flaky_step,
            ),
            self._result_step(),
        )

        snapshot = WorkflowStateMachine(plan).execute()

        self.assertEqual(snapshot.status, "success")
        self.assertEqual(attempts, [1, 2])
        self.assertEqual(snapshot.step_snapshots[0].attempts, 2)
        self.assertEqual(snapshot.result["result"], "result")

    def test_execute_plan_fails_terminally_on_non_retryable_error(self) -> None:
        attempts: list[int] = []

        class TransientError(RuntimeError):
            pass

        class FatalError(RuntimeError):
            pass

        def failing_step(_context: WorkflowStepContext) -> dict:
            attempts.append(len(attempts) + 1)
            raise FatalError("stop")

        plan = self._plan(
            WorkflowStep(
                step_id="start",
                effect=WorkflowEffect.IDEMPOTENT,
                retry=WorkflowRetryPolicy(max_attempts=3, retry_on=(TransientError,)),
                transitions=(WorkflowTransition(target_step_id="result"),),
                run=failing_step,
            ),
            self._result_step(),
        )

        snapshot = WorkflowStateMachine(plan).execute()

        self.assertEqual(snapshot.status, "failed")
        self.assertEqual(attempts, [1])
        self.assertEqual(snapshot.terminal_step_id, "start")
        self.assertEqual(snapshot.step_snapshots[0].attempts, 1)
        self.assertEqual(snapshot.step_snapshots[0].error["type"], "FatalError")

    def test_execute_plan_marks_retry_exhaustion_as_terminal(self) -> None:
        attempts: list[int] = []

        class TransientError(RuntimeError):
            pass

        def flaky_step(_context: WorkflowStepContext) -> dict:
            attempts.append(len(attempts) + 1)
            raise TransientError("still bad")

        plan = self._plan(
            WorkflowStep(
                step_id="start",
                effect=WorkflowEffect.IDEMPOTENT,
                retry=WorkflowRetryPolicy(max_attempts=2, retry_on=(TransientError,)),
                transitions=(WorkflowTransition(target_step_id="result"),),
                run=flaky_step,
            ),
            self._result_step(),
        )

        snapshot = WorkflowStateMachine(plan).execute()

        self.assertEqual(snapshot.status, "failed")
        self.assertEqual(attempts, [1, 2])
        self.assertEqual(snapshot.step_snapshots[0].attempts, 2)
        self.assertEqual(snapshot.failure["type"], "TransientError")
        self.assertFalse(snapshot.failure["retryable"])
        self.assertFalse(snapshot.step_snapshots[0].error["retryable"])

    def test_snapshot_is_frozen_and_json_round_trips(self) -> None:
        plan = self._plan(
            WorkflowStep(
                step_id="start",
                run=lambda _context: {"nested": {"items": [1, 2, 3]}, "label": "alpha"},
                transitions=(WorkflowTransition(target_step_id="result"),),
            ),
            WorkflowStep(
                step_id="result",
                kind=WorkflowStepKind.RESULT,
                depends_on=("start",),
                run=lambda context: {"echo": context.inputs["start"]},
            ),
        )

        snapshot = WorkflowStateMachine(plan).execute(context={"request_id": "req-3"})

        with self.assertRaises(FrozenInstanceError):
            snapshot.status = "mutated"  # type: ignore[misc]

        with self.assertRaises(TypeError):
            snapshot.step_snapshots[0].output["nested"]["items"] = [4, 5]  # type: ignore[index]

        payload = snapshot.to_dict()
        encoded = json.dumps(payload)
        decoded = json.loads(encoded)

        self.assertEqual(decoded, payload)
        self.assertEqual(payload["workflow_context"]["request_id"], "req-3")

    def test_workflow_modules_are_import_safe(self) -> None:
        for relative in (
            "src/workflow_step.py",
            "src/workflow_types.py",
            "src/workflow_state_machine.py",
        ):
            module_path = ORCHESTRATOR_ROOT / relative
            source = module_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(module_path))

            for node in tree.body:
                self.assertIn(
                    type(node).__name__,
                    {"Expr", "Import", "ImportFrom", "Assign", "AnnAssign", "ClassDef", "FunctionDef", "If"},
                    f"unexpected top-level statement in {relative}: {type(node).__name__}",
                )

    def test_runtime_helper_and_dispatch_boundary_coexist(self) -> None:
        plan = self._plan(
            WorkflowStep(
                step_id="start",
                run=lambda _context: {"ok": True},
                transitions=(WorkflowTransition(target_step_id="result"),),
            ),
            self._result_step(),
        )

        snapshot = execute_workflow_plan(plan, context={"request_id": "req-4"})
        self.assertEqual(snapshot.status, "success")
        self.assertEqual(snapshot.result["result"], "result")

        dispatch_result = execute_dispatch_by_type(
            "direct",
            "dispatch remains direct",
            metadata={"workflow_plan": {"name": "sample"}},
            max_orchestration_cycles=3,
        )

        self.assertEqual(dispatch_result["dispatch"], "direct")
        self.assertEqual(dispatch_result["status"], "direct-complete")
        self.assertTrue(dispatch_result["executed"])
        self.assertEqual(dispatch_result["results"], [])
        self.assertIsNone(dispatch_result["primary_result"])
        self.assertEqual(classify_dispatch_type([], {}), "direct")


if __name__ == "__main__":
    unittest.main()
