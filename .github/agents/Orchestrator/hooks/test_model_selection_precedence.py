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


if __name__ == "__main__":
    unittest.main()