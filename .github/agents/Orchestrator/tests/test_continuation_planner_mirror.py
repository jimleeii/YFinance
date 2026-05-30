import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from scripts.continuation_planner import generate_next_steps_plan
from src import orchestrator_runtime as rt
from src.orchestrator_memory import persist_continuity_checkpoint_from_normalized_metadata


@contextmanager
def chdir(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _write_markdown_page(root: Path, relative_path: str, title: str, body: str) -> None:
    page = root / relative_path
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"# {title}\n\n{body}\n", encoding="utf8")


def _seed_continuity_cache(root: Path, *, request_group_id: str, project_request: str, request_title: str, normalized_request: str) -> None:
    base_metadata = {
        "request_group_id": request_group_id,
        "project_request": project_request,
        "request_title": request_title,
        "normalized_request": normalized_request,
        "summary": "Seed checkpoint for the continuity cache.",
        "change_applied": "Prepared the dispatch payload seam.",
        "observed_result": "Local SQLite cache recorded the work.",
        "decision": "keep",
        "next_action": "Continue with the prior-context seam.",
    }

    for index in range(3):
        persist_continuity_checkpoint_from_normalized_metadata(
            {
                **base_metadata,
                "cycle_id": f"cycle-{index + 1}",
                "summary": f"{base_metadata['summary']} #{index + 1}",
                "change_applied": f"{base_metadata['change_applied']} #{index + 1}",
                "observed_result": f"{base_metadata['observed_result']} #{index + 1}",
                "next_action": f"{base_metadata['next_action']} #{index + 1}",
            },
            root=root,
            source_kind="test",
            source_identifier=f"unit-{index + 1}",
        )


class TestContinuationPlanner(unittest.TestCase):
    def test_generate_next_steps_plan_is_json_serializable_and_bounded(self):
        plan = generate_next_steps_plan(
            prior_session={
                "stage": "in_progress",
                "artifacts": [
                    {"title": "Alpha Dispatch Plan", "path": "plans/alpha-dispatch.md"},
                    {"title": "Telemetry Logger", "path": "src/logger.py"},
                    {"title": "Metric Bridge", "path": "src/metrics.py"},
                    {"title": "Extra Item", "path": "src/extra.py"},
                ],
                "completed": ["Alpha Dispatch Plan"],
                "blockers": [
                    "retry loop is failing in CI",
                    "cache invalidation is pending",
                    "ignored blocker",
                ],
            },
            current_user_request="Please continue the telemetry dispatcher, fix the failing tests, and review the architecture.",
            continuation_context={
                "continuation_type": "explicit",
                "confidence": 0.95,
                "context_fact_count": 3,
                "context_retrieval_source": "continuity_cache",
                "prior_blockers": [
                    "retry loop is failing in CI",
                    "cache invalidation is pending",
                    "ignored blocker",
                ],
                "suggested_next_steps": [
                    "Review the retrieved prior context before making changes.",
                    "Resume from the latest checkpoint before introducing new work.",
                ],
                "continuation_detection": {
                    "continuation_type": "explicit",
                    "confidence": 0.95,
                    "context_fact_count": 3,
                    "prior_blockers": ["retry loop is failing in CI"],
                    "suggested_next_steps": ["Review the retrieved prior context before making changes."],
                },
                "prior_context_items": [
                    {"title": "Alpha Dispatch Plan", "detail": "Updated the alpha dispatch plan."},
                    {"title": "Telemetry Logger", "detail": "Added the telemetry logger seam."},
                    {"title": "Metric Bridge", "detail": "Connected the metric bridge."},
                    {"title": "Extra Item", "detail": "Should be dropped by the planner."},
                ],
            },
        )

        json.dumps(plan, sort_keys=True, ensure_ascii=False)

        self.assertTrue(plan["plan_id"].startswith("cont-plan-"))
        self.assertEqual(plan["continuation_basis"], "explicit@0.95")
        self.assertIn(plan["stage"], {"blocked", "in_progress", "ready_to_deploy"})
        self.assertLessEqual(len(plan["blockers_to_address"]), 2)
        self.assertLessEqual(len(plan["completed_in_prior_session"]), 3)
        self.assertLessEqual(len(plan["recommended_next_steps"]), 4)
        self.assertLessEqual(len(plan["suggested_subagents"]), 3)
        self.assertIn("Alpha Dispatch Plan", " ".join(plan["completed_in_prior_session"]))
        self.assertIn("retry loop", " ".join(plan["blockers_to_address"]).casefold())
        self.assertIn("Software Architect", plan["suggested_subagents"])
        self.assertIn("Senior Developer", plan["suggested_subagents"])
        self.assertIn("Code Reviewer", plan["suggested_subagents"])
        self.assertIn(plan["estimated_effort"], {"<1h", "1-2h", "2-4h", ">4h"})
        self.assertTrue(all(isinstance(item, str) and len(item) <= 96 for item in plan["blockers_to_address"]))
        self.assertTrue(all(isinstance(item, str) and len(item) <= 96 for item in plan["completed_in_prior_session"]))
        self.assertTrue(all(isinstance(item, str) and len(item) <= 96 for item in plan["recommended_next_steps"]))
        self.assertTrue(all(isinstance(item, str) and len(item) <= 96 for item in plan["suggested_subagents"]))

    def test_explicit_continuation_with_prior_context_generates_plan_and_attaches_it(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            _seed_continuity_cache(
                root,
                request_group_id="grp-plan-001",
                project_request="Telemetry dispatcher continuation.",
                request_title="Telemetry dispatcher continuation.",
                normalized_request="telemetry dispatcher continuation",
            )

            with chdir(temp_dir), mock.patch.object(rt, "search_wiki_pages", side_effect=AssertionError("wiki fallback should not be needed")):
                payload = rt.prepare_dispatch_payload(
                    "Please continue where we left off on the telemetry dispatcher.",
                    user="u",
                    metadata={
                        "request_group_id": "grp-plan-001",
                        "project_request": "Telemetry dispatcher continuation.",
                        "request_title": "Telemetry dispatcher continuation.",
                        "normalized_request": "telemetry dispatcher continuation",
                    },
                )

            parent_context = payload["parent_context"]
            detection = parent_context["continuation_detection"]
            plan = parent_context["continuation_plan"]
            self.assertTrue(detection["is_continuation"])
            self.assertGreaterEqual(detection["confidence"], 0.8)
            self.assertEqual(parent_context["context_fact_count"], 3)
            self.assertEqual(plan, parent_context["dispatch_metadata"]["continuation_plan"])
            self.assertEqual(plan, parent_context["persistence"]["metadata"]["continuation_plan"])
            self.assertLessEqual(len(plan["blockers_to_address"]), 2)
            self.assertLessEqual(len(plan["recommended_next_steps"]), 4)
            self.assertLessEqual(len(plan["completed_in_prior_session"]), 3)
            self.assertLessEqual(len(plan["suggested_subagents"]), 3)
            self.assertTrue(all(isinstance(item, str) for item in plan["recommended_next_steps"]))

    def test_single_signal_continuation_with_low_confidence_skips_plan(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            wiki_root = root / ".wiki" / "orchestrator"
            _write_markdown_page(
                wiki_root,
                "plans/alpha-plan.md",
                "Alpha Dispatch Plan",
                "Keep the retrieval notes bounded and review the checkpoint history.",
            )

            with chdir(temp_dir):
                payload = rt.prepare_dispatch_payload(
                    "Please revise the Alpha Dispatch Plan.",
                    user="u",
                    metadata={
                        "project_request": "Alpha Dispatch Plan",
                        "request_title": "Alpha Dispatch Plan",
                        "normalized_request": "alpha dispatch plan",
                    },
                )

            parent_context = payload["parent_context"]
            detection = parent_context["continuation_detection"]
            self.assertTrue(detection["is_continuation"])
            self.assertAlmostEqual(detection["confidence"], 0.65, places=2)
            self.assertEqual(parent_context["context_fact_count"], 1)
            self.assertNotIn("continuation_plan", parent_context)
            self.assertNotIn("continuation_plan", parent_context["dispatch_metadata"])
            self.assertNotIn("continuation_plan", parent_context["persistence"]["metadata"])

    def test_empty_prior_context_skips_plan_even_when_request_is_explicit(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            with chdir(temp_dir):
                payload = rt.prepare_dispatch_payload(
                    "Please continue where we left off on the telemetry dispatcher.",
                    user="u",
                    metadata={
                        "project_request": "Telemetry dispatcher continuation.",
                        "request_title": "Telemetry dispatcher continuation.",
                        "normalized_request": "telemetry dispatcher continuation",
                    },
                )

            parent_context = payload["parent_context"]
            detection = parent_context["continuation_detection"]
            self.assertTrue(detection["is_continuation"])
            self.assertGreaterEqual(detection["confidence"], 0.8)
            self.assertEqual(parent_context["context_fact_count"], 0)
            self.assertNotIn("continuation_plan", parent_context)
            self.assertNotIn("continuation_plan", parent_context["dispatch_metadata"])
            self.assertNotIn("continuation_plan", parent_context["persistence"]["metadata"])

    def test_runtime_passes_through_when_planner_raises(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            _seed_continuity_cache(
                root,
                request_group_id="grp-plan-002",
                project_request="Telemetry dispatcher continuation.",
                request_title="Telemetry dispatcher continuation.",
                normalized_request="telemetry dispatcher continuation",
            )

            with chdir(temp_dir), mock.patch.object(rt, "search_wiki_pages", side_effect=AssertionError("wiki fallback should not be needed")), mock.patch.object(rt, "generate_next_steps_plan", side_effect=RuntimeError("planner boom")):
                payload = rt.prepare_dispatch_payload(
                    "Please continue where we left off on the telemetry dispatcher.",
                    user="u",
                    metadata={
                        "request_group_id": "grp-plan-002",
                        "project_request": "Telemetry dispatcher continuation.",
                        "request_title": "Telemetry dispatcher continuation.",
                        "normalized_request": "telemetry dispatcher continuation",
                    },
                )

            parent_context = payload["parent_context"]
            self.assertTrue(parent_context["continuation_detection"]["is_continuation"])
            self.assertGreaterEqual(parent_context["continuation_detection"]["confidence"], 0.8)
            self.assertEqual(parent_context["context_fact_count"], 3)
            self.assertNotIn("continuation_plan", parent_context)
            self.assertNotIn("continuation_plan", parent_context["dispatch_metadata"])
            self.assertNotIn("continuation_plan", parent_context["persistence"]["metadata"])


if __name__ == "__main__":
    unittest.main()
