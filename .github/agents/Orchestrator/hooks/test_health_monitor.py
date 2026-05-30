from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path


ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

os.environ.setdefault("ORCHESTRATOR_SKIP_AUTOINIT", "1")

from hooks import log_hooks
from src.health_monitor import get_workspace_health_registry, reset_health_monitor_state
from src.health_types import HealthObservation, HealthPolicy, HealthScope
from src.orchestrator_runtime import execute_dispatch_by_type


def _load_module(module_name: str, relative_path: Path):
    module_path = ORCHESTRATOR_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


post_chat_hook = _load_module("orchestrator_post_chat_hook_health_test", Path("scripts") / "post_chat_hook.py")


class HealthMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_health_monitor_state()

    def _scope(
        self,
        workspace_id: str,
        session_id: str,
        agent_id: str,
        task_family: str,
        model_id: str | None = None,
    ) -> HealthScope:
        return HealthScope(
            workspace_id=workspace_id,
            session_id=session_id,
            agent_id=agent_id,
            task_family=task_family,
            model_id=model_id,
        )

    def test_closed_open_half_open_closed_cycle(self) -> None:
        policy = HealthPolicy(
            failure_threshold=1,
            open_cooldown_seconds=5,
            probe_cooldown_seconds=10,
            probe_allowlist=("Agent A",),
        )
        registry = get_workspace_health_registry("workspace-cycle", policy=policy)
        scope = self._scope("workspace-cycle", "session-1", "Agent A", "feature", "model-1")
        base = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

        registry.record_observation(
            HealthObservation.execution_failure(scope, failure_kind="exception", message="boom"),
            now=base,
        )

        state = registry.snapshot().records[0].state
        self.assertEqual(state.status, "open")
        self.assertEqual(state.failure_count, 1)
        self.assertEqual(state.last_failure_kind, "exception")

        decision = registry.route_candidates(
            ["Agent A"],
            session_id="session-1",
            task_family="feature",
            model_id="model-1",
            now=base + timedelta(seconds=6),
        )

        self.assertEqual(decision.action, "probe")
        self.assertEqual(decision.state, "half-open")
        self.assertEqual(decision.probe_candidate, "Agent A")
        self.assertEqual(decision.selected_candidates, ("Agent A",))

        state = registry.snapshot().records[0].state
        self.assertEqual(state.status, "half-open")

        registry.record_observation(HealthObservation.success(scope), now=base + timedelta(seconds=7))

        state = registry.snapshot().records[0].state
        self.assertEqual(state.status, "closed")
        self.assertEqual(state.failure_count, 0)

    def test_quality_failure_does_not_count_toward_execution_health(self) -> None:
        registry = get_workspace_health_registry("workspace-taxonomy")
        scope = self._scope("workspace-taxonomy", "session-1", "Agent A", "feature", "model-1")

        registry.record_observation(
            HealthObservation.quality_failure(scope, message="reviewer rejected the response"),
            now=datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(registry.snapshot().records, ())

    def test_task_family_isolation_keeps_unrelated_family_closed(self) -> None:
        registry = get_workspace_health_registry("workspace-task-family")
        base = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

        hot_scope = self._scope("workspace-task-family", "session-1", "Agent A", "family-a", "model-1")
        cold_scope = self._scope("workspace-task-family", "session-1", "Agent A", "family-b", "model-1")

        registry.record_observation(
            HealthObservation.execution_failure(hot_scope, failure_kind="exception", message="boom"),
            now=base,
        )
        registry.record_observation(
            HealthObservation.success(cold_scope),
            now=base + timedelta(seconds=1),
        )

        decision = registry.route_candidates(
            ["Agent A"],
            session_id="session-1",
            task_family="family-b",
            model_id="model-1",
            now=base + timedelta(seconds=1),
        )

        self.assertEqual(decision.action, "allow")
        self.assertEqual(decision.selected_candidates, ("Agent A",))
        self.assertEqual(decision.suppressed_candidates, ())

        records = registry.snapshot().records
        self.assertEqual(len(records), 2)
        self.assertEqual({record.scope.task_family for record in records}, {"family-a", "family-b"})
        cold_state = next(record.state for record in records if record.scope.task_family == "family-b")
        self.assertEqual(cold_state.status, "closed")

    def test_workspace_registries_do_not_share_state(self) -> None:
        registry_a = get_workspace_health_registry("workspace-a")
        registry_b = get_workspace_health_registry("workspace-b")
        base = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

        scope_a = self._scope("workspace-a", "session-1", "Agent A", "feature", "model-1")
        registry_a.record_observation(
            HealthObservation.execution_failure(scope_a, failure_kind="exception", message="boom"),
            now=base,
        )

        self.assertEqual(registry_b.snapshot().records, ())

    def test_updates_are_thread_safe_under_lock(self) -> None:
        registry = get_workspace_health_registry("workspace-lock")
        scope = self._scope("workspace-lock", "session-1", "Agent A", "feature", "model-1")
        now = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

        def record_success(_index: int) -> None:
            registry.record_observation(HealthObservation.success(scope), now=now)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(record_success, range(100)))

        state = registry.snapshot().records[0].state
        self.assertEqual(state.success_count, 100)
        self.assertEqual(state.status, "closed")

    def test_probe_allowlist_and_cooldown_selects_single_probe_candidate(self) -> None:
        policy = HealthPolicy(
            failure_threshold=1,
            open_cooldown_seconds=1,
            probe_cooldown_seconds=30,
            probe_allowlist=("Allowed Agent",),
        )
        registry = get_workspace_health_registry("workspace-probe", policy=policy)
        base = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

        allowed_scope = self._scope("workspace-probe", "session-1", "Allowed Agent", "routing", "model-1")
        blocked_scope = self._scope("workspace-probe", "session-1", "Blocked Agent", "routing", "model-1")

        registry.record_observation(
            HealthObservation.execution_failure(allowed_scope, failure_kind="exception", message="boom"),
            now=base,
        )
        registry.record_observation(
            HealthObservation.execution_failure(blocked_scope, failure_kind="exception", message="boom"),
            now=base,
        )

        decision = registry.route_candidates(
            ["Allowed Agent", "Blocked Agent"],
            session_id="session-1",
            task_family="routing",
            model_id="model-1",
            now=base + timedelta(seconds=2),
        )

        self.assertEqual(decision.action, "probe")
        self.assertEqual(decision.probe_candidate, "Allowed Agent")
        self.assertEqual(decision.selected_candidates, ("Allowed Agent",))
        self.assertEqual(decision.suppressed_candidates, ("Blocked Agent",))

        second = registry.route_candidates(
            ["Allowed Agent", "Blocked Agent"],
            session_id="session-1",
            task_family="routing",
            model_id="model-1",
            now=base + timedelta(seconds=2),
        )

        self.assertEqual(second.action, "suppress")
        self.assertEqual(second.selected_candidates, ())
        self.assertIsNone(second.probe_candidate)

    def test_snapshot_is_deterministic_and_immutable(self) -> None:
        workspace_id = "workspace-snapshot"
        scope_a = self._scope(workspace_id, "session-1", "Agent A", "family-a", "model-1")
        scope_b = self._scope(workspace_id, "session-1", "Agent B", "family-b", "model-1")
        now = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

        registry = get_workspace_health_registry(workspace_id)
        registry.record_observation(HealthObservation.success(scope_a), now=now)
        registry.record_observation(
            HealthObservation.execution_failure(scope_b, failure_kind="exception", message="boom"),
            now=now,
        )
        first = registry.snapshot()

        reset_health_monitor_state(workspace_id)
        registry = get_workspace_health_registry(workspace_id)
        registry.record_observation(
            HealthObservation.execution_failure(scope_b, failure_kind="exception", message="boom"),
            now=now,
        )
        registry.record_observation(HealthObservation.success(scope_a), now=now)
        second = registry.snapshot()

        self.assertEqual(first.to_dict(), second.to_dict())

        with self.assertRaises(FrozenInstanceError):
            first.records[0].state.status = "mutated"  # type: ignore[misc]

        with self.assertRaises(TypeError):
            first.records[0] = first.records[0]  # type: ignore[misc]

    def test_execute_dispatch_by_type_respects_open_state_and_passes_health_metadata(self) -> None:
        workspace_id = "workspace-runtime"
        policy = HealthPolicy(failure_threshold=1, open_cooldown_seconds=3600, probe_cooldown_seconds=30)
        registry = get_workspace_health_registry(workspace_id, policy=policy)
        base = datetime.now(timezone.utc)

        open_scope = self._scope(workspace_id, "session-runtime", "Agent A", "feature", "model-1")
        registry.record_observation(
            HealthObservation.execution_failure(open_scope, failure_kind="exception", message="boom"),
            now=base,
        )

        calls: list[tuple[str, str | None, str | None, str | None]] = []

        def fake_runner(agent: str, _prompt: str, metadata: dict) -> dict:
            health = metadata.get("health") if isinstance(metadata.get("health"), dict) else {}
            calls.append(
                (
                    agent,
                    metadata.get("health_state"),
                    metadata.get("health_action"),
                    metadata.get("health_failure_kind"),
                )
            )
            self.assertEqual(health.get("workspace_id"), workspace_id)
            self.assertEqual(health.get("session_id"), "session-runtime")
            self.assertEqual(health.get("task_family"), "feature")
            return {"agent": agent, "contract_score": 82, "artifacts": [f"{agent}.txt"]}

        result = execute_dispatch_by_type(
            "multi-agent",
            "implement feature",
            metadata={
                "workspace_id": workspace_id,
                "session_id": "session-runtime",
                "task_type": "feature",
                "model": "model-1",
                "subagents": ["Agent A", "Agent B"],
            },
            subagents=["Agent A", "Agent B"],
            run_agent=fake_runner,
            max_orchestration_cycles=3,
        )

        self.assertEqual([call[0] for call in calls], ["Agent B"])
        self.assertEqual(calls[0][1], "closed")
        self.assertEqual(calls[0][2], "allow")
        self.assertIsNone(calls[0][3])
        self.assertEqual(result["dispatch"], "multi-agent")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["agent"], "Agent B")
        self.assertEqual(result["dispatch_metadata"]["health_state"], "closed")
        self.assertEqual(result["dispatch_metadata"]["health_action"], "allow")

    def test_payload_metadata_preserves_health_namespace(self) -> None:
        payload = {
            "metadata": {
                "health": {
                    "workspace_id": "workspace-logging",
                    "session_id": "session-logging",
                    "task_family": "feature",
                    "state": "open",
                    "action": "probe",
                    "failure_kind": "exception",
                    "reason": "open circuit",
                    "selected_candidates": ["Agent A"],
                    "suppressed_candidates": ["Agent B"],
                },
                "health_workspace_id": "workspace-logging",
                "health_session_id": "session-logging",
                "health_task_family": "feature",
                "health_state": "open",
                "health_action": "probe",
                "health_failure_kind": "exception",
                "health_reason": "open circuit",
                "health_selected_candidates": ["Agent A"],
                "health_suppressed_candidates": ["Agent B"],
            },
            "model_resolution": {"model": "gpt-5.4", "source": "auto"},
        }

        metadata = post_chat_hook._payload_metadata(payload)

        self.assertEqual(metadata["health"]["state"], "open")
        self.assertEqual(metadata["health_workspace_id"], "workspace-logging")
        self.assertEqual(metadata["health_action"], "probe")
        self.assertEqual(metadata["health_failure_kind"], "exception")
        self.assertEqual(metadata["health_selected_candidates"], ["Agent A"])
        self.assertEqual(metadata["model_resolution"], {"model": "gpt-5.4", "source": "auto"})
        self.assertNotIn("fallback_used", metadata)
        self.assertNotIn("fallback_reason", metadata)

    def test_build_log_context_renders_health_fields_separately_from_model_selection(self) -> None:
        context = log_hooks._build_log_context(
            dispatch_path="multi-agent",
            event_flags={"failure_detected": True},
            summary="Circuit breaker probe",
            skills=["systematic-debugging"],
            prompt_command="/full-log",
            metadata={
                "cycle_id": "CYC-20260523-123000-ABCD",
                "project_request": "Probe orchestrator health routing",
                "change_applied": "Added workspace-scoped health routing.",
                "health": {
                    "workspace_id": "workspace-logging",
                    "session_id": "session-logging",
                    "agent_id": "Agent A",
                    "task_family": "feature",
                    "model_id": "model-1",
                    "state": "open",
                    "action": "probe",
                    "failure_kind": "exception",
                    "reason": "open circuit",
                    "selected_candidates": ["Agent A"],
                    "suppressed_candidates": ["Agent B"],
                    "probe_candidate": "Agent A",
                },
                "health_workspace_id": "workspace-logging",
                "health_session_id": "session-logging",
                "health_agent_id": "Agent A",
                "health_task_family": "feature",
                "health_model_id": "model-1",
                "health_state": "open",
                "health_action": "probe",
                "health_failure_kind": "exception",
                "health_reason": "open circuit",
                "health_selected_candidates": ["Agent A"],
                "health_suppressed_candidates": ["Agent B"],
                "health_probe_candidate": "Agent A",
                "model_resolution": {"model": "gpt-5.4", "source": "auto"},
            },
        )

        behavior = context["targets"]["Behavior-Log.md"]

        self.assertEqual(behavior["model_selection"], "selected_model=gpt-5.4")
        self.assertEqual(behavior["health_workspace_id"], "workspace-logging")
        self.assertEqual(behavior["health_session_id"], "session-logging")
        self.assertEqual(behavior["health_agent_id"], "Agent A")
        self.assertEqual(behavior["health_task_family"], "feature")
        self.assertEqual(behavior["health_model_id"], "model-1")
        self.assertEqual(behavior["health_state"], "open")
        self.assertEqual(behavior["health_action"], "probe")
        self.assertEqual(behavior["health_failure_kind"], "exception")
        self.assertEqual(behavior["health_reason"], "open circuit")
        self.assertEqual(behavior["health_selected_candidates"], "Agent A")
        self.assertEqual(behavior["health_suppressed_candidates"], "Agent B")
        self.assertEqual(behavior["health_probe_candidate"], "Agent A")


if __name__ == "__main__":
    unittest.main()