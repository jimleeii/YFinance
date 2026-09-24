from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path


ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from hooks.log_hooks import _build_model_selection
from src.trigger_test_prompt import _resolved_model_id


def _load_module(module_name: str, relative_path: Path):
    module_path = ORCHESTRATOR_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


log_hook_runner = _load_module("orchestrator_log_hook_runner_test", Path("scripts") / "log_hook_runner.py")
post_chat_hook = _load_module("orchestrator_post_chat_hook_test", Path("scripts") / "post_chat_hook.py")
os.environ.setdefault("ORCHESTRATOR_SKIP_AUTOINIT", "1")
orchestrator_runtime = _load_module("orchestrator_runtime_test", Path("src") / "orchestrator_runtime.py")


class ModelSelectionPrecedenceTests(unittest.TestCase):
    def test_build_model_selection_prefers_canonical_model_resolution(self) -> None:
        metadata = {
            "model_selection": "selected_model=gpt-5 | task_type=chat-conversion | criticality=P1",
            "model_resolution": {"model": "gpt-5.4", "source": "auto"},
            "task_type": "chat-conversion",
            "criticality": "P1",
        }

        self.assertEqual(
            _build_model_selection(metadata),
            "selected_model=gpt-5.4 | task_type=chat-conversion | criticality=P1",
        )

    def test_build_dispatch_metadata_promotes_supplied_model_resolution(self) -> None:
        metadata = {
            "model_selection": "selected_model=gpt-5 | task_type=chat-conversion | criticality=P1",
            "model_resolution": {"model": "gpt-5.4", "source": "auto"},
        }

        merged, model_resolution = log_hook_runner._build_dispatch_metadata(metadata=metadata)

        self.assertEqual(model_resolution, {"model": "gpt-5.4", "source": "auto"})
        self.assertEqual(merged["selected_model"], "gpt-5.4")
        self.assertEqual(merged["cycle_selected_model"], "gpt-5.4")
        self.assertEqual(merged["model"], "gpt-5.4")
        self.assertEqual(merged["model_resolution"], {"model": "gpt-5.4", "source": "auto"})

    def test_payload_metadata_overrides_stale_selected_model(self) -> None:
        payload = {
            "transcript": "User: verify auto model conversion",
            "metadata": {
                "selected_model": "gpt-5",
                "cycle_selected_model": "gpt-5",
                "model": "gpt-5",
                "model_selection": "selected_model=gpt-5 | task_type=chat-conversion | criticality=P1",
                "task_type": "chat-conversion",
                "criticality": "P1",
            },
            "model_resolution": {"model": "gpt-5.4", "source": "auto"},
        }

        metadata = post_chat_hook._payload_metadata(payload)

        self.assertEqual(metadata["selected_model"], "gpt-5.4")
        self.assertEqual(metadata["cycle_selected_model"], "gpt-5.4")
        self.assertEqual(metadata["model"], "gpt-5.4")
        self.assertEqual(metadata["model_resolution"], {"model": "gpt-5.4", "source": "auto"})

    def test_payload_metadata_preserves_anchored_project_request_for_follow_up_approval(self) -> None:
        payload = {
            "transcript": "approved",
            "metadata": {
                "normalized_request": "approved",
            },
            "parent_context": {
                "project_request": "Inventory all FME system preferences and outline the configuration-page implementation",
                "dispatch_metadata": {
                    "project_request": "Inventory all FME system preferences and outline the configuration-page implementation",
                    "request_group_id": "grp-pref-inventory",
                },
            },
        }

        metadata = post_chat_hook._payload_metadata(payload)
        metadata = post_chat_hook._normalize_checkpoint_metadata(summary="approved", metadata=metadata)

        self.assertEqual(
            metadata["project_request"],
            "Inventory all FME system preferences and outline the configuration-page implementation",
        )
        self.assertEqual(
            metadata["normalized_request"],
            "Inventory all FME system preferences and outline the configuration-page implementation",
        )
        self.assertEqual(metadata["request_group_id"], "grp-pref-inventory")

    def test_transcript_checkpoint_inference_extracts_curated_refactor_fields(self) -> None:
        transcript = """User: Refactor this class and split sub-classes/interfaces to their own files
Assistant: ## What changed

I split the FME Flow HTTP client contract and adapter out of `FmeFlowService` and kept the service behavior the same.

- `DataExchange/DataExchange/FMEFlow/Core/_Interfaces/Services/IFmeFlowHttpClient.cs`
- `DataExchange/DataExchange/FMEFlow/Core/Services/FmeFlowHttpClientAdapter.cs`
- `DataExchange/DataExchange/FMEFlow/Core/Services/FmeFlowService.cs`
- `DataExchange/DataExchange/DataExchange.csproj`

## Verification

- Solution build: succeeded with **0 warnings / 0 errors**
- Targeted tests: `DataExchangeTest.FMEFlow.FmeFlowServiceTests`
  - **34 passed / 34 total**

## Notes

If you want, I can do a second pass and break the large `FmeFlowService` itself into partial classes or smaller helper services next.
"""

        inferred = post_chat_hook._infer_checkpoint_metadata_from_transcript(transcript)

        self.assertEqual(
            inferred["project_request"],
            "Refactor this class and split sub-classes/interfaces to their own files",
        )
        self.assertEqual(
            inferred["change_applied"],
            "I split the FME Flow HTTP client contract and adapter out of `FmeFlowService` and kept the service behavior the same.",
        )
        self.assertEqual(inferred["decision"], "keep")
        self.assertEqual(inferred["stage"], "completed")
        self.assertIn("DataExchange/DataExchange/FMEFlow/Core/Services/FmeFlowService.cs", inferred["files_touched"])
        self.assertIn("34 passed / 34 total", inferred["observed_result"])
        self.assertIn("break the large `FmeFlowService` itself into partial classes", inferred["next_action"])

    def test_transcript_checkpoint_inference_extracts_plan_checkpoint_fields(self) -> None:
        transcript = """User: Help me collect all system preferences that required for FME run.
Assistant: The implementation plan is saved at `docs/superpowers/plans/2026-05-20-fme-flow-settings.md`.

## what’s in it

It breaks the work into four small chunks:

- preference catalog and `SystemPreferences` upsert support
- a dedicated FME Flow settings view model and view
- wiring the new page into the existing configuration dialog
- focused MSTest coverage plus build verification

## next

If this looks good, I can start the implementation next and work through it in the planned order.
"""

        inferred = post_chat_hook._infer_checkpoint_metadata_from_transcript(transcript)

        self.assertEqual(inferred["stage"], "checkpoint")
        self.assertEqual(
            inferred["project_request"],
            "Help me collect all system preferences that required for FME run.",
        )
        self.assertIn("docs/superpowers/plans/2026-05-20-fme-flow-settings.md", inferred["files_touched"])
        self.assertIn("preference catalog and `SystemPreferences` upsert support", inferred["completed"])
        self.assertIn("start the implementation next", inferred["next_action"])

    def test_legacy_fallback_prefers_model_resolution_over_stale_top_level_model(self) -> None:
        metadata = {
            "selected_model": "gpt-5",
            "cycle_selected_model": "gpt-5",
            "model": "gpt-5",
            "model_resolution": {"model": "gpt-5.4", "source": "auto"},
        }

        self.assertEqual(_resolved_model_id(metadata), "gpt-5.4")

    def test_runtime_merge_dispatch_metadata_preserves_model_resolution_selected_model_fallback(self) -> None:
        metadata = {
            "selected_model": "gpt-5",
            "cycle_selected_model": "gpt-5",
            "model": "gpt-5",
        }
        model_resolution = {
            "selected_model": "gpt-5.4",
            "source": "auto",
            "fallback_used": True,
            "fallback_reason": "policy fallback",
        }

        merged = orchestrator_runtime._merge_dispatch_metadata(metadata, model_resolution=model_resolution)

        self.assertEqual(merged["selected_model"], "gpt-5.4")
        self.assertEqual(merged["cycle_selected_model"], "gpt-5.4")
        self.assertEqual(merged["model"], "gpt-5.4")
        self.assertEqual(merged["selected_model_source"], "auto")
        self.assertIs(merged["fallback_used"], True)
        self.assertEqual(merged["fallback_reason"], "policy fallback")
        self.assertEqual(merged["model_resolution"], model_resolution)

    def test_runtime_merge_dispatch_metadata_prefers_model_over_selected_model(self) -> None:
        model_resolution = {
            "model": "gpt-5.4",
            "selected_model": "gpt-5.3",
            "source": "auto",
        }

        merged = orchestrator_runtime._merge_dispatch_metadata({}, model_resolution=model_resolution)

        self.assertEqual(merged["selected_model"], "gpt-5.4")
        self.assertEqual(merged["cycle_selected_model"], "gpt-5.4")
        self.assertEqual(merged["model"], "gpt-5.4")
        self.assertEqual(merged["model_resolution"], model_resolution)

    def test_dispatch_concurrent_sorts_by_contract_score_descending(self) -> None:
        def fake_runner(agent: str, _prompt: str, _metadata: dict) -> dict:
            score_map = {
                "Senior Developer A": 72,
                "Senior Developer B": 91,
            }
            return {"agent": agent, "contract_score": score_map[agent], "artifacts": ["a.cs"]}

        results = orchestrator_runtime.dispatch_concurrent(
            ["Senior Developer A", "Senior Developer B"],
            "implement feature",
            run_agent=fake_runner,
        )

        self.assertEqual(results[0]["agent"], "Senior Developer B")
        self.assertEqual(results[1]["agent"], "Senior Developer A")

    def test_execute_dispatch_by_type_runs_concurrent_path_and_returns_structured_results(self) -> None:
        calls = []

        def fake_runner(agent: str, _prompt: str, metadata: dict) -> dict:
            calls.append((agent, metadata.get("dispatch_type"), metadata.get("aggregation_strategy"), metadata.get("fanout_total")))
            score_map = {
                "Senior Developer A": 72,
                "Senior Developer B": 91,
            }
            return {"agent": agent, "contract_score": score_map[agent], "artifacts": ["a.cs"]}

        result = orchestrator_runtime.execute_dispatch_by_type(
            "concurrent",
            "implement feature",
            metadata={
                "cycle_id": "CYC-20260523-123000-ABCD",
                "subagents": ["Senior Developer A", "Senior Developer B"],
                "task_flags": {"independent_tracks": True},
            },
            subagents=["Senior Developer A", "Senior Developer B"],
            run_agent=fake_runner,
            max_orchestration_cycles=3,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["dispatch"], "concurrent")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result_count"], 2)
        self.assertEqual(result["results"][0]["agent"], "Senior Developer B")
        self.assertEqual(result["dispatch_metadata"]["aggregation_strategy"], "contract_score_then_artifact_count")
        self.assertEqual(result["dispatch_metadata"]["ranking_fields"], ["contract_score", "artifact_count"])
        self.assertTrue(result["dispatch_metadata"]["review_ready"])
        self.assertEqual(result["retries_remaining"], 2)
        self.assertEqual({call[0] for call in calls}, {"Senior Developer A", "Senior Developer B"})
        self.assertTrue(all(call[1] == "concurrent" for call in calls))
        self.assertTrue(all(call[2] == "contract_score_then_artifact_count" for call in calls))
        self.assertTrue(all(call[3] == 2 for call in calls))

    def test_execute_dispatch_by_type_hard_stops_when_retry_budget_exhausted(self) -> None:
        called = []

        def fail_runner(*_args, **_kwargs) -> dict:
            called.append(True)
            raise AssertionError("run_agent should not be called after the retry budget is exhausted")

        result = orchestrator_runtime.execute_dispatch_by_type(
            "single-agent",
            "retry budget test",
            metadata={
                "cycle_id": "CYC-20260523-123000-ABCD",
                "retry_count": 3,
                "subagent": "Senior Developer",
            },
            subagents=["Senior Developer"],
            run_agent=fail_runner,
            max_orchestration_cycles=3,
        )

        self.assertEqual(result["status"], "retry-budget-exhausted")
        self.assertTrue(result["retry_budget_exhausted"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["retries_remaining"], 0)
        self.assertEqual(result["results"], [])
        self.assertEqual(result["action"], "hard-stop")
        self.assertIn("max_orchestration_cycles=3 exhausted before cycle 4", result["reason"])
        self.assertEqual(called, [])

    def test_detect_architecture_gap_escalation_from_partial_response(self) -> None:
        text = """
Status: partial
Uncertainties:
- Architecture gap: interface missing between job client and orchestrator
"""
        result = orchestrator_runtime.detect_architecture_gap_escalation(text, role="developer")

        self.assertTrue(result["escalation_required"])
        self.assertIn("architecture gap", result["reason"])

    def test_dispatch_peer_review_requires_two_outputs_for_p1_architect(self) -> None:
        result = orchestrator_runtime.dispatch_peer_review(
            role="architect",
            outputs=[{"contract_score": 88, "artifacts": ["design-a"]}],
            criticality="p1",
        )

        self.assertTrue(result["peer_review_required"])
        self.assertTrue(result["reconcile_required"])
        self.assertIsNone(result["challenger"])


if __name__ == "__main__":
    unittest.main()