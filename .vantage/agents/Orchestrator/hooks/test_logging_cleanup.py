from __future__ import annotations

import io
import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from hooks import log_hooks
from hooks.log_hooks import _build_log_context, log_cycle


def _load_module(module_name: str, relative_path: Path):
    module_path = ORCHESTRATOR_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


log_prompt = _load_module("orchestrator_log_prompt_cleanup_test", Path("scripts") / "log_prompt.py")
post_chat_hook = _load_module("orchestrator_post_chat_hook_cleanup_test", Path("scripts") / "post_chat_hook.py")


class LoggingCleanupTests(unittest.TestCase):
    def test_format_entry_includes_cycle_id_when_provided(self) -> None:
        entry = log_prompt.format_entry(
            "/info",
            "tester",
            "checkpoint text",
            cycle_id="CYC-20260523-123000-ABCD",
        )

        self.assertIn("Cycle: CYC-20260523-123000-ABCD", entry)

    def test_build_log_context_does_not_invent_placeholder_fields(self) -> None:
        context = _build_log_context(
            dispatch_path="single-agent",
            event_flags={},
            summary="Post-tool invocation",
            skills=None,
            prompt_command=None,
            metadata={},
        )

        self.assertEqual(context["defaults"]["request_type"], "")
        self.assertEqual(context["targets"]["Behavior-Patterns.md"]["signal"], "")
        self.assertEqual(context["targets"]["Learning-Backlog.md"]["problem"], "")
        self.assertEqual(context["targets"]["Runbook.md"]["change_applied"], "")
        self.assertRegex(context["defaults"]["skl_id"], r"^SKL-\d{14}$")

    def test_log_cycle_skips_noise_event_without_running_log_command(self) -> None:
        with mock.patch("hooks.log_hooks._run_log_command") as run_log_command:
            result = log_cycle(
                dispatch_path="multi-agent",
                event_flags={"failure_detected": True},
                summary="Post-tool invocation",
                skills=None,
                metadata={},
                preview=False,
            )

        self.assertEqual(result["action"], "skipped-noise")
        run_log_command.assert_not_called()

    def test_log_cycle_skips_automatic_post_tool_hook_even_with_meaningful_summary(self) -> None:
        with mock.patch("hooks.log_hooks._run_log_command") as run_log_command:
            result = log_cycle(
                dispatch_path="single-agent",
                event_flags={"hook_phase": "post"},
                summary="I found the split shape and I am about to update compile includes.",
                skills=["prompt-optimizer"],
                metadata={
                    "hook_event_name": "PostToolUse",
                    "project_request": "Refactor this class and split sub-classes/interfaces to their own files",
                },
                preview=False,
            )

        self.assertEqual(result["action"], "skipped-auto-hook")
        run_log_command.assert_not_called()

    def test_log_cycle_downgrades_unstructured_full_log_to_compact(self) -> None:
        completed = subprocess.CompletedProcess(args=["python"], returncode=0)
        with mock.patch("hooks.log_hooks._run_log_command", return_value=completed) as run_log_command:
            result = log_cycle(
                dispatch_path="multi-agent",
                event_flags={"failure_detected": True},
                summary="Compare wiki logging against refactor source context",
                skills=["prompt-optimizer"],
                metadata={"project_request": "Compare wiki logging against refactor source context"},
                preview=True,
            )

        self.assertEqual(result["level"], "compact")
        self.assertEqual(result["command"], "/info")
        self.assertEqual(result["action"], "downgraded-full-log-to-compact")
        self.assertEqual(result["reason"], "missing cycle_id")
        run_log_command.assert_not_called()

    def test_log_cycle_allows_curated_full_log(self) -> None:
        completed = subprocess.CompletedProcess(args=["python"], returncode=0)
        with mock.patch("hooks.log_hooks._run_log_command", return_value=completed) as run_log_command:
            result = log_cycle(
                dispatch_path="multi-agent",
                event_flags={"failure_detected": True},
                summary="Remediate orchestrator logging noise and consolidate wiki state",
                skills=["prompt-optimizer", "systematic-debugging"],
                metadata={
                    "curated_log": True,
                    "cycle_id": "CYC-20260523-123000-ABCD",
                    "project_request": "Remediate orchestrator logging noise",
                    "change_applied": "Gate curated full-log writes behind meaningful structured metadata.",
                    "observed_result": "Preview output uses concrete IDs and omits placeholder lines.",
                    "decision": "keep",
                },
                preview=True,
            )

        self.assertEqual(result["level"], "full")
        self.assertEqual(result["command"], "/full-log")
        self.assertEqual(run_log_command.call_args.args[1], "/full-log")

    def test_log_cycle_downgrades_full_log_when_cycle_id_is_missing(self) -> None:
        completed = subprocess.CompletedProcess(args=["python"], returncode=0)
        with mock.patch("hooks.log_hooks._run_log_command", return_value=completed) as run_log_command:
            result = log_cycle(
                dispatch_path="multi-agent",
                event_flags={"failure_detected": True},
                summary="Remediate orchestrator logging noise and consolidate wiki state",
                skills=["prompt-optimizer", "systematic-debugging"],
                metadata={
                    "curated_log": True,
                    "project_request": "Remediate orchestrator logging noise",
                    "change_applied": "Gate curated full-log writes behind meaningful structured metadata.",
                    "observed_result": "Preview output uses concrete IDs and omits placeholder lines.",
                    "decision": "keep",
                },
                preview=False,
            )

        self.assertEqual(result["level"], "compact")
        self.assertEqual(result["command"], "/info")
        self.assertEqual(result["action"], "downgraded-full-log-to-compact")
        self.assertEqual(result["reason"], "missing cycle_id")
        run_log_command.assert_not_called()

    def test_log_cycle_downgrades_full_log_when_change_evidence_is_missing(self) -> None:
        completed = subprocess.CompletedProcess(args=["python"], returncode=0)
        with mock.patch("hooks.log_hooks._run_log_command", return_value=completed) as run_log_command:
            result = log_cycle(
                dispatch_path="multi-agent",
                event_flags={"failure_detected": True},
                summary="Remediate orchestrator logging noise and consolidate wiki state",
                skills=["prompt-optimizer", "systematic-debugging"],
                metadata={
                    "curated_log": True,
                    "cycle_id": "CYC-20260523-123000-ABCD",
                    "project_request": "Remediate orchestrator logging noise",
                },
                preview=False,
            )

        self.assertEqual(result["level"], "compact")
        self.assertEqual(result["command"], "/info")
        self.assertEqual(result["action"], "downgraded-full-log-to-compact")
        self.assertEqual(result["reason"], "missing meaningful change evidence")
        run_log_command.assert_not_called()

    def test_log_cycle_suppresses_duplicate_curated_checkpoint_writes(self) -> None:
        completed = subprocess.CompletedProcess(args=["python"], returncode=0)
        metadata = {
            "curated_log": True,
            "project_request": "Inventory FME system preferences and build the configuration page plan",
            "change_applied": "Persist a curated checkpoint after planning inventory coverage.",
            "completed": "Captured preference sources and page entry points.",
            "files_touched": ["docs/preferences.md", "progress.md"],
            "session_id": "8bfd517a-e8b3-4a65-95f8-e19dc1286155",
            "request_group_id": "grp-fme-pref-inventory",
            "cycle_id": "cycle-1",
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_root:
            with mock.patch("hooks.log_hooks._run_log_command", return_value=completed) as run_log_command:
                first = log_cycle(
                    dispatch_path="multi-agent",
                    event_flags={"failure_detected": True},
                    summary="Inventory checkpoint complete",
                    skills=["writing-plans"],
                    metadata=metadata,
                    target_root=Path(temp_root),
                    preview=False,
                )
                second = log_cycle(
                    dispatch_path="multi-agent",
                    event_flags={"failure_detected": True},
                    summary="Inventory checkpoint complete",
                    skills=["writing-plans"],
                    metadata=metadata,
                    target_root=Path(temp_root),
                    preview=False,
                )

        self.assertEqual(first["command"], "/full-log")
        self.assertEqual(second["action"], "skipped-duplicate")
        self.assertEqual(run_log_command.call_count, 1)

    def test_build_log_context_preserves_project_request_for_continuation_prompt(self) -> None:
        context = _build_log_context(
            dispatch_path="single-agent",
            event_flags={},
            summary="approved",
            skills=["writing-plans"],
            prompt_command="/info",
            metadata={
                "project_request": "Inventory all FME system preferences and outline the configuration-page implementation",
                "normalized_request": "approved",
                "change_applied": "Captured the next curated checkpoint without replacing the root request.",
            },
        )

        self.assertEqual(
            context["defaults"]["project_request"],
            "Inventory all FME system preferences and outline the configuration-page implementation",
        )
        self.assertEqual(
            context["targets"]["Skill-Usage-Log.md"]["invocation_reason"],
            "Inventory all FME system preferences and outline the configuration-page implementation",
        )
        self.assertEqual(
            context["targets"]["Behavior-Log.md"]["project_request"],
            "Inventory all FME system preferences and outline the configuration-page implementation",
        )

    def test_build_log_context_carries_structured_file_and_session_evidence(self) -> None:
        context = _build_log_context(
            dispatch_path="multi-agent",
            event_flags={"failure_detected": True},
            summary="Refactor checkpoint complete",
            skills=["comment-policy"],
            prompt_command="/full-log",
            metadata={
                "project_request": "Refactor this class and split sub-classes/interfaces to their own files. Make sure comments policy applied. Organize with a modern structure.",
                "change_applied": "Split FME Flow service dependencies into explicit contract and adapter types.",
                "files_touched": [
                    "FmeFlowService.cs",
                    "IFmeFlowHttpClient.cs",
                    "FmeFlowHttpClientAdapter.cs",
                    "FMEFlowSettingsViewModel.cs",
                    "FmePreferenceEditorKind.cs",
                    "FmePreferenceGroupViewModel.cs",
                    "DataExchange.csproj",
                ],
                "session_evidence": {
                    "session_id": "6f300dde-8b1d-4158-99b4-6a71e779b7d8",
                    "request_group_id": "grp-refactor-fme-http",
                    "cycle_id": "cycle-3",
                },
                "completed": "Extracted types and updated compile includes.",
            },
        )

        self.assertIn("FmeFlowService.cs", context["targets"]["Project-Context-Log.md"]["files_touched"])
        self.assertIn("session_id=6f300dde-8b1d-4158-99b4-6a71e779b7d8", context["targets"]["Runbook.md"]["session_evidence"])

    def test_normalize_checkpoint_metadata_maps_checkpoint_alias_fields(self) -> None:
        metadata = {
            "title": "FME system preferences list",
            "overview": "Captured the grouped preference inventory for the new configuration page.",
            "work_done": "Cataloged preference groups and mapped them to existing call sites.",
            "technical_details": "Verified the current UI only exposes the local executable path.",
            "important_files": [
                "DataExchange/DataExchange/FMEFlow/FMESystemPreferenceQuery.cs",
                "docs/superpowers/plans/2026-05-20-fme-flow-settings.md",
            ],
            "next_steps": "Implement the settings page wiring and persist new SystemPreferences values.",
        }

        normalized = log_cycle.__globals__["normalize_checkpoint_metadata"](
            summary="approved",
            metadata=metadata,
            event_flags={},
            prompt_command="/full-log",
        )

        self.assertEqual(normalized["project_request"], "FME system preferences list")
        self.assertEqual(normalized["request_title"], "FME system preferences list")
        self.assertEqual(normalized["summary"], "Captured the grouped preference inventory for the new configuration page.")
        self.assertEqual(normalized["completed"], "Cataloged preference groups and mapped them to existing call sites.")
        self.assertEqual(normalized["observed_result"], "Verified the current UI only exposes the local executable path.")
        self.assertEqual(normalized["next_action"], "Implement the settings page wiring and persist new SystemPreferences values.")
        self.assertIn("FMESystemPreferenceQuery.cs", normalized["files_touched"][0])

    def test_render_template_omits_empty_optional_lines_and_replaces_ids(self) -> None:
        template = """### OBS-YYYYMMDD-XXX\n\n- Timestamp (UTC): timestamp_utc\n- Request Type: request_type\n- Follow-up Action: follow_up_action\n- Related: [Behavior-Patterns](Behavior-Patterns.md#PAT-YYYYMMDD-XXX)\n"""
        rendered = log_prompt._render_template(
            template,
            message="",
            author="tester",
            context={
                "obs_id": "OBS-20260521-101500",
                "pat_id": "PAT-20260521-101500",
                "timestamp_utc": "2026-05-21T10:15:00Z",
            },
        )

        self.assertIn("### OBS-20260521-101500", rendered)
        self.assertIn("- Timestamp (UTC): 2026-05-21T10:15:00Z", rendered)
        self.assertNotIn("- Request Type:", rendered)
        self.assertNotIn("- Follow-up Action:", rendered)
        self.assertIn("Behavior-Patterns.md#pat-20260521-101500", rendered)
        self.assertNotIn("YYYYMMDD", rendered)
        self.assertNotIn("XXX", rendered)

    def test_render_template_formats_structured_evidence_without_placeholders(self) -> None:
        template = """### CTX-YYYYMMDD-XXX\n\n- Project/Request: project_request\n- Files Touched: files_touched\n- Session Evidence: session_evidence\n"""
        rendered = log_prompt._render_template(
            template,
            message="",
            author="tester",
            context={
                "ctx_id": "CTX-20260522-094500",
                "project_request": "Inventory all FME system preferences and outline the configuration-page implementation",
                "files_touched": ["FmeFlowService.cs", "DataExchange.csproj"],
                "session_evidence": {
                    "session_id": "8bfd517a-e8b3-4a65-95f8-e19dc1286155",
                    "request_group_id": "grp-pref-inventory",
                },
            },
        )

        self.assertIn("Files Touched: FmeFlowService.cs, DataExchange.csproj", rendered)
        self.assertIn('Session Evidence: |', rendered)
        self.assertIn('"session_id": "8bfd517a-e8b3-4a65-95f8-e19dc1286155"', rendered)
        self.assertNotIn("YYYYMMDD", rendered)

    def test_infer_checkpoint_metadata_uses_latest_substantive_refactor_request(self) -> None:
        transcript = """User: Refactor this class and split sub-classes/interfaces to their own files

Assistant: I’m going to inspect the current service class and its nearby types first, then I’ll split the nested pieces into separate files with the smallest safe surface change.

User: Refactor this class and split sub-classes/interfaces to their own files. Make sure comments policy applied. Organize with a modern structure.

Assistant: I’ve got the split shape now: interface to _Interfaces/Services, adapter to Services, and the service file stays functionally the same.
"""

        metadata = post_chat_hook._infer_checkpoint_metadata_from_transcript(transcript)

        self.assertEqual(
            metadata["project_request"],
            "Refactor this class and split sub-classes/interfaces to their own files. Make sure comments policy applied. Organize with a modern structure.",
        )
        self.assertEqual(metadata["request_title"], metadata["project_request"])
        self.assertEqual(metadata["session_evidence"]["turn_count"], 4)
        self.assertEqual(metadata["session_evidence"]["user_prompt_count"], 2)
        self.assertEqual(
            metadata["session_evidence"]["user_prompts"],
            [
                "Refactor this class and split sub-classes/interfaces to their own files",
                "Refactor this class and split sub-classes/interfaces to their own files. Make sure comments policy applied. Organize with a modern structure.",
            ],
        )
        self.assertIn("interface to _Interfaces/Services", metadata["session_evidence"]["assistant_checkpoint"])

    def test_infer_checkpoint_metadata_keeps_fme_inventory_prompt_context(self) -> None:
        transcript = """User: Help me collect all system preferences that required for FME run (upload, login, submit job, job log, job summary. etc.). Provide a list of the system preferences. My goal is to create a configuration page for FME that I can load those FME categorized preferences for user to set/modify values. A screenshot is attached to this prompt for reference. The pasted image is just reference, do NOT take it as is. If need re-generate image with the provided list.

Assistant: I’ve got the inventory direction. I’m now collecting the active FME Flow preferences and grouping them for the configuration page.
"""

        metadata = post_chat_hook._infer_checkpoint_metadata_from_transcript(transcript)

        self.assertTrue(metadata["project_request"].startswith("Help me collect all system preferences"))
        self.assertEqual(metadata["session_evidence"]["turn_count"], 2)
        self.assertEqual(metadata["session_evidence"]["user_prompt_count"], 1)
        self.assertEqual(
            metadata["session_evidence"]["user_prompts"],
            [
                "Help me collect all system preferences that required for FME run (upload, login, submit job, job log, job summary. etc.). Provide a list of the system preferences. My goal is to create a configuration page for FME that I can load those FME categorized preferences for user to set/modify values. A screenshot is attached to this prompt for reference. The pasted image is just reference, do NOT take it as is. If need re-generate image with the provided list.",
            ],
        )
        self.assertIn("inventory direction", metadata["session_evidence"]["assistant_checkpoint"])

    def test_main_preserves_surrogates_in_transcript_and_metadata(self) -> None:
        payload = {
            "transcript": "User: Lone surrogate in transcript \udc9d",
            "metadata": {
                "note": "metadata \udc9d",
            },
        }
        completed = subprocess.CompletedProcess(args=["python"], returncode=0, stdout="83/100")

        with tempfile.TemporaryDirectory() as temp_root:
            real_named_tempfile = post_chat_hook.tempfile.NamedTemporaryFile

            def _named_tempfile(*args, **kwargs):
                kwargs.setdefault("dir", temp_root)
                return real_named_tempfile(*args, **kwargs)

            def _fake_run(cmd, *args, **kwargs):
                script_name = Path(cmd[1]).name
                if script_name == "score.py":
                    self.assertEqual(kwargs["input"], "User: Lone surrogate in transcript \\udc9d")
                    self.assertNotIn("\udc9d", kwargs["input"])
                    return completed

                if script_name == "log_hook_runner.py":
                    args_file = Path(cmd[2][1:])
                    args_text = args_file.read_text(encoding="utf-8")
                    self.assertIn(r"\udc9d", args_text)
                    self.assertNotIn("\udc9d", args_text)
                    return subprocess.CompletedProcess(args=cmd, returncode=0)

                self.fail(f"Unexpected subprocess command: {cmd}")

            with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
                with mock.patch("sys.argv", ["post_chat_hook.py"]):
                    with mock.patch.object(post_chat_hook.tempfile, "NamedTemporaryFile", side_effect=_named_tempfile):
                        with mock.patch.object(post_chat_hook.subprocess, "run", side_effect=_fake_run):
                            result = post_chat_hook.main()

            self.assertEqual(result, 0)

            transcript_files = list(Path(temp_root).glob("copilot_transcript_*.md"))
            self.assertEqual(len(transcript_files), 1)

            transcript_text = transcript_files[0].read_text(encoding="utf-8")
            self.assertIn(r"\udc9d", transcript_text)
            self.assertNotIn("\udc9d", transcript_text)

    def test_write_transcript_escapes_surrogates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            transcript_path = log_hooks.write_transcript(Path(temp_root), "User: Lone surrogate in transcript \udc9d")

            transcript_text = transcript_path.read_text(encoding="utf-8")

        self.assertIn(r"\udc9d", transcript_text)
        self.assertNotIn("\udc9d", transcript_text)


if __name__ == "__main__":
    unittest.main()
