from __future__ import annotations

import io
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from src import model_discovery
from src.model_telemetry import collect_cycle_model_telemetry


def _load_module(module_name: str, relative_path: Path):
    module_path = ORCHESTRATOR_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


os.environ.setdefault("ORCHESTRATOR_SKIP_AUTOINIT", "1")
log_hook_runner = _load_module("orchestrator_log_hook_runner_model_discovery_test", Path("scripts") / "log_hook_runner.py")
orchestrator_runtime = _load_module("orchestrator_runtime_model_discovery_test", Path("src") / "orchestrator_runtime.py")


class ModelDiscoveryTests(unittest.TestCase):
    def test_parse_copilot_help_config_extracts_models(self) -> None:
        help_text = """
model: AI model to use for Copilot CLI

  - "claude-sonnet-4.6"
  - "gpt-5.4-mini"
  - "claude-haiku-4.5"

edit: Other Copilot setting
"""

        self.assertEqual(
            model_discovery._parse_copilot_help_config(help_text),
            ["claude-sonnet-4.6", "gpt-5.4-mini", "claude-haiku-4.5"],
        )

    def test_discover_copilot_models_includes_session_state_models(self) -> None:
        help_text = """
model: AI model to use for Copilot CLI

  - "gpt-5.4-mini"
  - "gpt-5-mini"
"""

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            session_dir = root / "session-state" / "session-1"
            session_dir.mkdir(parents=True, exist_ok=True)
            events_path = session_dir / "events.jsonl"
            events = [
                {
                    "type": "session.start",
                    "timestamp": "2026-05-20T12:00:00.000Z",
                    "data": {"selectedModel": "claude-sonnet-4.6"},
                },
                {
                    "type": "session.shutdown",
                    "timestamp": "2026-05-20T12:01:00.000Z",
                    "data": {
                        "currentModel": "claude-sonnet-4.6",
                        "modelMetrics": {
                            "claude-sonnet-4.6": {"requests": {"count": 2, "cost": 1}}
                        },
                    },
                },
            ]
            events_path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

            catalog, sources = model_discovery.discover_copilot_models(copilot_root=root, help_config_text=help_text)

            self.assertIn("gpt-5.4-mini", catalog)
            self.assertIn("claude-sonnet-4.6", catalog)
            self.assertTrue(catalog["claude-sonnet-4.6"]["observed_in_copilot_chat"])
            self.assertEqual(sources["selected_model"], "claude-sonnet-4.6")
            self.assertEqual(sources["current_model"], "claude-sonnet-4.6")

    def test_collect_cycle_model_telemetry_aggregates_scores(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            telemetry_path = Path(temp_dir) / ".wiki" / "orchestrator" / "telemetry" / "cycles.jsonl"
            telemetry_path.parent.mkdir(parents=True, exist_ok=True)

            records = [
                {
                    "recorded_at_utc": "2026-05-20T12:00:00+00:00",
                    "selected_model": "gpt-5.4-mini",
                    "contract_score": 92,
                    "elapsed_ms": 120,
                    "summary_chars": 100,
                    "body_chars": 180,
                    "transcript_chars": 900,
                    "skills_count": 2,
                    "files_touched_count": 1,
                    "failure_detected": False,
                },
                {
                    "recorded_at_utc": "2026-05-20T12:05:00+00:00",
                    "selected_model": "gpt-5.4-mini",
                    "contract_score": 88,
                    "elapsed_ms": 140,
                    "summary_chars": 120,
                    "body_chars": 210,
                    "transcript_chars": 1100,
                    "skills_count": 3,
                    "files_touched_count": 2,
                    "failure_detected": False,
                },
                {
                    "recorded_at_utc": "2026-05-20T12:10:00+00:00",
                    "selected_model": "claude-haiku-4.5",
                    "contract_score": 70,
                    "elapsed_ms": 420,
                    "summary_chars": 80,
                    "body_chars": 260,
                    "transcript_chars": 2000,
                    "skills_count": 5,
                    "files_touched_count": 4,
                    "failure_detected": False,
                },
            ]
            telemetry_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

            telemetry = collect_cycle_model_telemetry(
                telemetry_path=telemetry_path,
                now=datetime(2026, 5, 21, tzinfo=timezone.utc),
                window_days=7,
            )

            self.assertIn("gpt-5.4-mini", telemetry)
            self.assertIn("claude-haiku-4.5", telemetry)
            self.assertGreater(telemetry["gpt-5.4-mini"]["quality_score"], telemetry["claude-haiku-4.5"]["quality_score"])
            self.assertGreater(telemetry["gpt-5.4-mini"]["latency_score"], telemetry["claude-haiku-4.5"]["latency_score"])
            self.assertGreater(telemetry["gpt-5.4-mini"]["cost_score"], telemetry["claude-haiku-4.5"]["cost_score"])
            self.assertEqual(telemetry["gpt-5.4-mini"]["tool_call_reliability"], "pass")

    def test_prepare_dispatch_payload_auto_loads_model_catalog(self) -> None:
        fake_bundle = SimpleNamespace(
            catalog={
                "gpt-5.4-mini": {
                    "tier": "balanced",
                    "quality_score": 75,
                    "latency_score": 75,
                    "cost_score": 60,
                    "quality_score_source": "tier-prior",
                    "latency_score_source": "tier-prior",
                    "cost_score_source": "tier-prior",
                    "context_window": None,
                    "tool_calling": True,
                    "telemetry_partial": True,
                    "sources": ["copilot-cli"],
                }
            },
            default_model="gpt-5.4-mini",
            sources={"copilot": {"selected_model": "gpt-5.4-mini"}},
        )

        with (
            patch.object(orchestrator_runtime, "load_model_catalog_bundle", return_value=fake_bundle) as load_mock,
            patch.object(
                orchestrator_runtime,
                "resolve_model_for_subagent",
                return_value={"model": "gpt-5.4-mini", "source": "copilot-cli"},
            ) as resolve_mock,
            patch.object(orchestrator_runtime, "handle_request", return_value={"logging_level": "compact", "skill_usage": {}}),
            patch.object(orchestrator_runtime, "detect_continuation", None),
            patch.object(orchestrator_runtime, "generate_next_steps_plan", None),
            patch.object(
                orchestrator_runtime,
                "_collect_prior_context_payload",
                return_value={"context_retrieval_source": "none", "context_fact_count": 0, "markdown": "", "items": []},
            ),
        ):
            payload = orchestrator_runtime.prepare_dispatch_payload(
                "build the thing",
                spawn_payload={"name": "Senior Developer"},
                subagent_name="Senior Developer",
            )

        load_mock.assert_called_once()
        resolve_mock.assert_called_once()
        self.assertEqual(payload["model_resolution"], {"model": "gpt-5.4-mini", "source": "copilot-cli"})
        self.assertEqual(payload["parent_context"]["selected_model"], "gpt-5.4-mini")
        self.assertEqual(payload["parent_context"]["cycle_selected_model"], "gpt-5.4-mini")
        self.assertEqual(payload["parent_context"]["model_resolution"], {"model": "gpt-5.4-mini", "source": "copilot-cli"})

    def test_log_hook_runner_live_discovery_populates_catalog_without_stderr_noise(self) -> None:
        fake_bundle = SimpleNamespace(
            catalog={
                "gpt-5.4-mini": {
                    "tier": "balanced",
                    "quality_score": 75,
                    "latency_score": 75,
                    "cost_score": 60,
                    "quality_score_source": "tier-prior",
                    "latency_score_source": "tier-prior",
                    "cost_score_source": "tier-prior",
                    "context_window": None,
                    "tool_calling": True,
                    "telemetry_partial": True,
                    "sources": ["copilot-cli"],
                }
            },
            default_model="gpt-5.4-mini",
            sources={"copilot": {"selected_model": "gpt-5.4-mini"}},
        )

        with (
            patch.object(model_discovery, "load_model_catalog_bundle", return_value=fake_bundle) as load_mock,
            patch("hooks.log_hooks.log_cycle", return_value={"logging_level": "compact", "skill_usage": {}}),
            patch("hooks.log_hooks.normalize_checkpoint_metadata", side_effect=lambda **kwargs: kwargs["metadata"]),
            patch("src.model_resolver.resolve_model_for_subagent", return_value={"model": "gpt-5.4-mini", "source": "copilot-cli"}) as resolve_mock,
            patch.object(sys, "argv", [
                "log_hook_runner.py",
                "--root",
                str(ORCHESTRATOR_ROOT),
                "--subagent-name",
                "Senior Developer",
                "--spawn-payload",
                json.dumps({"name": "Senior Developer"}),
            ]),
        ):
            stderr = io.StringIO()
            stdout = io.StringIO()
            with redirect_stderr(stderr), redirect_stdout(stdout):
                result = log_hook_runner.main()

        self.assertEqual(result, 0)
        self.assertNotIn("Loaded model_catalog from live discovery", stderr.getvalue())
        load_mock.assert_called_once_with(repo_root=ORCHESTRATOR_ROOT)
        self.assertEqual(resolve_mock.call_args.kwargs["model_catalog"], fake_bundle.catalog)


if __name__ == "__main__":
    unittest.main()
