#!/usr/bin/env python3
"""Helper to capture a Copilot chat transcript and invoke the post-hook persist step.

This script accepts a transcript (file or stdin), optional metadata (skills, tags,
author, dispatch path, structured dispatch metadata), and a structured JSON wrapper
around the transcript body. It writes a temporary transcript file if needed and calls
`scripts/log_hook_runner.py --phase post` to persist logs.

Example:
    echo "conversation text" | python scripts/post_chat_hook.py --summary "Chat end" --skills "prompt-optimizer,contract-validator" --author "alice"

Structured wrapper example:
    echo '{"transcript":"conversation text","metadata":{"subagent":"Senior Developer","task_type":"implementation","criticality":"P1"}}' | python scripts/post_chat_hook.py

Or with an existing transcript file:
  python scripts/post_chat_hook.py --transcript-file ".wiki/orchestrator/transcripts/session-20260509.md" --summary "Chat end" --skills "..."
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

try:
    from src.trigger_test_prompt import extract_skill_usage as _extract_skill_usage
except Exception:  # pragma: no cover - fallback when package import is unavailable
    _extract_skill_usage = None

try:
    from hooks.log_hooks import normalize_checkpoint_metadata as _normalize_checkpoint_metadata
except Exception:  # pragma: no cover - fallback when package import is unavailable
    _normalize_checkpoint_metadata = None


def _score_transcript(text: str, subagent: str | None) -> str | None:
    """Run src/score.py against *text* and return the score string (e.g. '83/100').

    Returns None when the scorer is unavailable or the text is empty.
    Role is inferred from *subagent* name; falls back to auto-detect.
    """
    if not text or not text.strip():
        return None
    _ROLE_MAP = {
        "software architect": "architect",
        "architect": "architect",
        "senior developer": "developer",
        "developer": "developer",
        "code reviewer": "reviewer",
        "reviewer": "reviewer",
    }
    role: str | None = None
    if subagent:
        role = _ROLE_MAP.get(subagent.strip().lower())

    scorer = ORCHESTRATOR_ROOT / "src" / "score.py"
    if not scorer.exists():
        return None

    cmd = [sys.executable, str(scorer)]
    if role:
        cmd += ["--role", role]
    try:
        safe_text = _utf8_backslashreplace_text(text)
        result = subprocess.run(
            cmd,
            input=safe_text,
            capture_output=True,
            text=True,
            timeout=15,
        )
        score = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        if score and "/" in score:
            return score
    except Exception:
        pass
    return None


def _load_json_object(raw_value: Optional[str], label: str) -> Dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except Exception as exc:  # pragma: no cover - user input parsing
        raise ValueError(f"Failed to parse {label}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return parsed


def _coalesce_text(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _text_list_to_csv(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ",".join(items) if items else None
    text = str(value).strip()
    return text or None


def _unique_text_list(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            items = [str(item).strip() for item in value]
        else:
            items = [str(value).strip()]
        for item in items:
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _merge_unique_text_lists(*sources: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in _unique_text_list(source):
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _utf8_backslashreplace_text(text: str) -> str:
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


def _strip_role_prefix(line: str) -> str:
    lower = line.lower()
    for prefix in ("user:", "assistant:", "system:", "copilot:", "request:", "prompt:", "goal:", "summary:"):
        if lower.startswith(prefix):
            return line[len(prefix):].strip(" -:>")
    return line


def _infer_summary_from_text(text: str) -> Optional[str]:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if stripped.startswith(("```", "###", "##", "#", "- ", "* ", "> ")):
            continue
        if lowered.startswith((
            "timestamp",
            "tags:",
            "author:",
            "request type:",
            "routing path:",
            "subagent",
            "skills used",
            "invocation reason:",
            "outcome impact:",
            "reuse note:",
            "summary:",
            "completed:",
            "in progress:",
            "blockers/risks:",
            "next action:",
            "related:",
        )):
            continue
        candidate = _strip_role_prefix(stripped)
        candidate = _normalize_text(candidate)
        if candidate:
            return candidate[:240]
    compact = _normalize_text(text)
    return compact[:240] if compact else None


def _infer_subagents_from_text(text: str) -> list[str]:
    lowered = text.lower()
    candidates = [
        ("Software Architect", "software architect"),
        ("Senior Developer", "senior developer"),
        ("Code Reviewer", "code reviewer"),
        ("Orchestrator", "orchestrator"),
    ]
    found: list[tuple[int, str]] = []
    for label, needle in candidates:
        index = lowered.find(needle)
        if index != -1:
            found.append((index, label))
    ordered: list[str] = []
    for _, label in sorted(found, key=lambda item: item[0]):
        if label not in ordered:
            ordered.append(label)
    return ordered


def _infer_skills_from_text(text: str) -> list[str]:
    if _extract_skill_usage is None:
        return []
    try:
        usage = _extract_skill_usage(text)
    except Exception:
        return []
    skills = usage.get("skills")
    if isinstance(skills, (list, tuple, set)):
        return [str(item).strip() for item in skills if str(item).strip()]
    if isinstance(skills, str):
        return [item.strip() for item in skills.split(",") if item.strip()]
    return []


def _infer_dispatch_path(text: str, subagents: list[str]) -> str:
    lowered = text.lower()
    if "multi-agent" in lowered or len(subagents) > 1:
        return "multi-agent"
    if any(needle in lowered for needle in ("software architect", "senior developer", "code reviewer")):
        return "single-agent"
    return "direct"


def _looks_like_failure(text: str) -> bool:
    lowered = text.lower()
    failure_terms = ("failed", "failure", "error", "exception", "blocked", "rollback", "unable", "cannot", "issue", "problem", "bug")
    success_terms = ("passed", "pass", "success", "successful", "completed", "complete", "validated", "fixed", "resolved", "confirmed")
    return any(term in lowered for term in failure_terms) and not any(term in lowered for term in success_terms)


def _extract_conversation_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    current_role: Optional[str] = None
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^(User|Assistant|Copilot|System)\s*:\s*(.*)$", line, re.IGNORECASE)
        if match:
            if current_role and any(item.strip() for item in current_lines):
                blocks.append((current_role, "\n".join(current_lines).strip()))
            current_role = match.group(1).lower()
            current_lines = [match.group(2).strip()] if match.group(2).strip() else []
            continue

        if current_role:
            current_lines.append(line)

    if current_role and any(item.strip() for item in current_lines):
        blocks.append((current_role, "\n".join(current_lines).strip()))

    if not blocks and text.strip():
        blocks.append(("assistant", text.strip()))

    return blocks


CONTINUATION_REQUEST_RE = re.compile(
    r'^(?:please\s+)?(?:approve(?:d)?|proceed|go(?:\s+ahead)?|continue|carry\s+on|keep\s+going)(?:\s+please)?[.!?]*$',
    re.IGNORECASE,
)


def _is_continuation_request(value: str) -> bool:
    normalized = _normalize_text(_strip_role_prefix(value))
    if not normalized:
        return False
    return bool(CONTINUATION_REQUEST_RE.fullmatch(normalized))


def _unique_text_messages(*messages: str) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for message in messages:
        text = _normalize_text(_strip_role_prefix(message))
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return merged


def _select_project_request(user_messages: list[str]) -> Optional[str]:
    prompts = _unique_text_messages(*user_messages)
    if not prompts:
        return None

    substantive_prompts = [prompt for prompt in prompts if not _is_continuation_request(prompt)]
    if substantive_prompts:
        return substantive_prompts[-1]

    return prompts[-1]


def _build_session_evidence(
    turn_count: int,
    user_messages: list[str],
    assistant_checkpoint: str,
) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {
        "turn_count": turn_count,
    }

    prompts = _unique_text_messages(*user_messages)
    if prompts:
        evidence["user_prompt_count"] = len(prompts)
        if len(prompts) == 1:
            evidence["user_prompts"] = prompts
        else:
            evidence["user_prompts"] = [prompts[0], prompts[-1]]

    if assistant_checkpoint:
        evidence["assistant_checkpoint"] = assistant_checkpoint

    return evidence


def _extract_section_body(text: str, *heading_patterns: str) -> Optional[str]:
    lines = text.splitlines()
    normalized_patterns = tuple(pattern.lower() for pattern in heading_patterns)

    for index, raw_line in enumerate(lines):
        heading_match = re.match(r"^#{2,6}\s+(.*\S)\s*$", raw_line.strip())
        if not heading_match:
            continue
        heading_text = heading_match.group(1).strip().lower()
        if not any(pattern in heading_text for pattern in normalized_patterns):
            continue

        collected: list[str] = []
        for candidate in lines[index + 1:]:
            if re.match(r"^#{2,6}\s+", candidate.strip()):
                break
            collected.append(candidate)
        body = "\n".join(collected).strip()
        if body:
            return body

    return None


def _extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith(("- ", "* ")):
            bullets.append(_normalize_text(stripped[2:]))
    return bullets


def _summarize_lines(lines: list[str], limit: int = 4) -> Optional[str]:
    normalized = [_normalize_text(line).rstrip(".") for line in lines if _normalize_text(line)]
    if not normalized:
        return None
    return "; ".join(normalized[:limit])


def _first_paragraph(text: str) -> Optional[str]:
    collected: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if collected:
                break
            continue
        if stripped.startswith(("#", "- ", "* ", "> ")) and collected:
            break
        if stripped.startswith(("#", "- ", "* ", "> ")):
            continue
        collected.append(stripped)
    paragraph = _normalize_text(" ".join(collected))
    return paragraph or None


def _extract_file_references(text: str) -> list[str]:
    matches = re.findall(
        r"`([^`\n]+?\.(?:cs|xaml(?:\.cs)?|csproj|sln|md|json|xml|ya?ml|config|ps1|py|txt))`",
        text,
        flags=re.IGNORECASE,
    )
    unique: list[str] = []
    seen: set[str] = set()
    for match in matches:
        cleaned = match.strip()
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(cleaned)
    return unique


def _infer_decision(observed_result: Optional[str], stage: str, fallback_text: str) -> Optional[str]:
    evidence = _normalize_text(" ".join(part for part in (observed_result, fallback_text) if part))
    lowered = evidence.lower()
    if stage == "completed" and any(token in lowered for token in ("passed", "succeeded", "0 errors", "0 warnings / 0 errors")):
        return "keep"
    if stage == "blocked" or _looks_like_failure(evidence):
        return "revise"
    if stage in {"completed", "checkpoint"}:
        return "keep"
    return None


def _infer_checkpoint_metadata_from_transcript(text: str) -> Dict[str, Any]:
    blocks = _extract_conversation_blocks(text)
    user_messages = [content for role, content in blocks if role == "user" and content.strip()]
    assistant_messages = [content for role, content in blocks if role in {"assistant", "copilot"} and content.strip()]

    project_request = _select_project_request(user_messages)
    latest_assistant = assistant_messages[-1] if assistant_messages else text.strip()

    def _checkpoint_score(block: str) -> tuple[int, int]:
        lowered = block.lower()
        score = 0
        if "## verification" in lowered:
            score += 5
        if any(token in lowered for token in ("## done", "## what changed", "## what i changed")):
            score += 6
        if any(token in lowered for token in ("## proposed split", "## next", "## what's in it", "## what’s in it")):
            score += 3
        if _extract_file_references(block):
            score += 2
        if any(token in lowered for token in ("passed", "succeeded", "0 errors", "plan is saved", "implementation plan is saved")):
            score += 2
        return score, len(block)

    best_assistant = max(assistant_messages, key=_checkpoint_score, default=latest_assistant)
    lowered_best = best_assistant.lower()

    summary = _first_paragraph(best_assistant) or _infer_summary_from_text(best_assistant)
    verification_section = _extract_section_body(best_assistant, "verification")
    notes_section = _extract_section_body(best_assistant, "notes")
    next_section = _extract_section_body(best_assistant, "next")
    work_items_section = _extract_section_body(best_assistant, "new files", "updated files", "recommended approach", "what's in it", "what’s in it")

    files_touched = _merge_unique_text_lists(
        _extract_file_references(best_assistant),
        _extract_file_references(latest_assistant),
    )

    change_applied = _first_paragraph(
        _extract_section_body(best_assistant, "what changed", "what i changed", "done") or best_assistant
    )
    completed = _summarize_lines(_extract_bullets(work_items_section or best_assistant))
    observed_result = _summarize_lines(_extract_bullets(verification_section or ""))
    if not observed_result:
        observed_result = _first_paragraph(verification_section or "")

    next_action = _first_paragraph(next_section or "")
    if not next_action and notes_section:
        note_match = re.search(r"if you want, i can (.+?)(?:\.|$)", notes_section, re.IGNORECASE)
        if note_match:
            next_action = _normalize_text(note_match.group(1))
    if not next_action and best_assistant:
        next_match = re.search(r"if this looks good, i can (.+?)(?:\.|$)", best_assistant, re.IGNORECASE)
        if next_match:
            next_action = _normalize_text(next_match.group(1))

    stage = "in_progress"
    if any(token in lowered_best for token in ("## done", "## what changed", "## what i changed")):
        stage = "completed"
    elif _looks_like_failure(latest_assistant):
        stage = "blocked"
    elif any(token in lowered_best for token in ("## proposed split", "implementation plan is saved", "## next", "## what's in it", "## what’s in it")):
        stage = "checkpoint"

    blockers_risks = None
    if stage == "blocked" or _looks_like_failure(latest_assistant):
        blockers_risks = _infer_summary_from_text(latest_assistant)

    in_progress = None
    if stage != "completed":
        in_progress = _infer_summary_from_text(latest_assistant)

    decision = _infer_decision(observed_result, stage, latest_assistant)
    session_evidence = _build_session_evidence(
        turn_count=len(blocks),
        user_messages=user_messages,
        assistant_checkpoint=_first_paragraph(latest_assistant) or _infer_summary_from_text(latest_assistant),
    )

    inferred: Dict[str, Any] = {}
    if project_request:
        inferred["project_request"] = project_request
        inferred.setdefault("request_title", project_request)
    if summary:
        inferred["summary"] = summary
    if change_applied:
        inferred["change_applied"] = change_applied
    if completed:
        inferred["completed"] = completed
    if in_progress:
        inferred["in_progress"] = in_progress
    if blockers_risks:
        inferred["blockers_risks"] = blockers_risks
    if next_action:
        inferred["next_action"] = next_action
    if observed_result:
        inferred["observed_result"] = observed_result
    if files_touched:
        inferred["files_touched"] = files_touched
    if session_evidence:
        inferred["session_evidence"] = session_evidence
    if stage:
        inferred["stage"] = stage
    if decision:
        inferred["decision"] = decision

    return inferred


def _extract_structured_payload(raw_text: str) -> tuple[str, Dict[str, Any]]:
    stripped = raw_text.strip()
    if not stripped.startswith("{"):
        return raw_text, {}
    try:
        payload = json.loads(stripped)
    except Exception:
        return raw_text, {}
    if not isinstance(payload, dict):
        return raw_text, {}

    transcript_text = _coalesce_text(
        payload.get("transcript"),
        payload.get("conversation"),
        payload.get("message"),
        payload.get("body"),
        payload.get("text"),
        payload.get("content"),
        payload.get("prompt"),
        payload.get("input"),
        payload.get("selected_text"),
        payload.get("selectedText"),
        payload.get("selection"),
    )
    if transcript_text is None:
        return raw_text, {}
    return transcript_text, payload


def _merge_model_resolution_metadata(metadata: Dict[str, Any], model_resolution: Any) -> None:
    if not isinstance(model_resolution, dict):
        return
    metadata["model_resolution"] = dict(model_resolution)
    resolved_model = _coalesce_text(model_resolution.get("model"), model_resolution.get("selected_model"))
    if resolved_model:
        metadata["selected_model"] = resolved_model
        metadata["cycle_selected_model"] = resolved_model
        metadata["model"] = resolved_model
    resolved_source = _coalesce_text(model_resolution.get("source"))
    if resolved_source:
        metadata["selected_model_source"] = resolved_source
    if model_resolution.get("fallback_used") is not None:
        metadata["fallback_used"] = model_resolution["fallback_used"]
    if model_resolution.get("fallback_reason"):
        metadata["fallback_reason"] = model_resolution["fallback_reason"]


def _payload_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}

    for key in ("metadata", "dispatch_metadata"):
        value = payload.get(key)
        if isinstance(value, dict):
            metadata.update(value)

    parent_context = payload.get("parent_context")
    if isinstance(parent_context, dict):
        nested_dispatch_metadata = parent_context.get("dispatch_metadata")
        if isinstance(nested_dispatch_metadata, dict):
            metadata.update(nested_dispatch_metadata)
        nested_persistence = parent_context.get("persistence")
        if isinstance(nested_persistence, dict):
            nested_persistence_metadata = nested_persistence.get("metadata")
            if isinstance(nested_persistence_metadata, dict):
                metadata.update(nested_persistence_metadata)
        _merge_model_resolution_metadata(metadata, parent_context.get("model_resolution"))
        for key in (
            "curated_checkpoint",
            "subagent",
            "subagents",
            "selected_model",
            "cycle_selected_model",
            "model",
            "model_selection",
            "task_type",
            "criticality",
            "skills_used",
            "skills_used_ordered",
            "prompt_normalization",
            "routing_mode",
            "outcome",
            "fallback_used",
            "fallback_reason",
            "override_phrase",
            "normalized_request",
            "project_request",
            "session_id",
            "request_group_id",
            "cycle_id",
            "dedupe_key",
            "stage",
            "completed",
            "in_progress",
            "blockers_risks",
            "next_action",
            "files_touched",
            "session_evidence",
            "routing_policy_changes",
            "change_applied",
            "expected_effect",
            "validation_window",
            "observed_result",
            "decision",
            "contract_score",
            "request_title",
            "title",
            "overview",
            "work_done",
            "technical_details",
            "important_files",
            "next_steps",
            "health",
            "health_workspace_id",
            "health_session_id",
            "health_agent_id",
            "health_task_family",
            "health_model_id",
            "health_state",
            "health_action",
            "health_failure_kind",
            "health_reason",
            "health_selected_candidates",
            "health_suppressed_candidates",
            "health_probe_candidate",
        ):
            if key in parent_context and key not in metadata:
                metadata[key] = parent_context[key]

    for key in (
        "curated_checkpoint",
        "subagent",
        "subagents",
        "selected_model",
        "cycle_selected_model",
        "model",
        "model_selection",
        "task_type",
        "criticality",
        "skills_used",
        "skills_used_ordered",
        "prompt_normalization",
        "routing_mode",
        "outcome",
        "fallback_used",
        "fallback_reason",
        "override_phrase",
        "normalized_request",
        "project_request",
        "session_id",
        "request_group_id",
        "cycle_id",
        "dedupe_key",
        "stage",
        "completed",
        "in_progress",
        "blockers_risks",
        "next_action",
        "files_touched",
        "session_evidence",
        "routing_policy_changes",
        "change_applied",
        "expected_effect",
        "validation_window",
        "observed_result",
        "decision",
        "contract_score",
        "request_title",
        "title",
        "overview",
        "work_done",
        "technical_details",
        "important_files",
        "next_steps",
        "health",
        "health_workspace_id",
        "health_session_id",
        "health_agent_id",
        "health_task_family",
        "health_model_id",
        "health_state",
        "health_action",
        "health_failure_kind",
        "health_reason",
        "health_selected_candidates",
        "health_suppressed_candidates",
        "health_probe_candidate",
    ):
        if key in payload and key not in metadata:
            metadata[key] = payload[key]

    _merge_model_resolution_metadata(metadata, payload.get("model_resolution"))

    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture chat transcript and call post-hook to persist logs.")
    parser.add_argument("--transcript-file", help="Path to existing transcript file (optional)")
    parser.add_argument("--summary", help="Short summary for the log entry", default=None)
    parser.add_argument("--skills", help="Comma-separated skills list", default=None)
    parser.add_argument("--author", help="Author name", default=None)
    parser.add_argument("--tags", help="Comma-separated tags", default=None)
    parser.add_argument("--dispatch-path", help="Dispatch path (direct/single-agent/multi-agent)", default=None)
    parser.add_argument("--event-flags", help="JSON string of event flags to pass through", default=None)
    parser.add_argument("--metadata", help="JSON string of structured metadata to pass through", default=None)
    parser.add_argument("--subagent-name", help="Subagent name to persist in metadata", default=None)
    parser.add_argument("--spawn-payload", help="JSON string describing the dispatch spawn payload", default=None)
    parser.add_argument("--model-catalog", help="JSON string of allowed models and tiers", default=None)
    parser.add_argument("--global-default-model", help="Global default model to use for resolution", default=None)
    parser.add_argument("--minimum-tier", help="Minimum allowed model tier", default=None)
    parser.add_argument("--preview", action="store_true", help="Preview the generated log entries without writing files")
    parser.add_argument("--force-persist", action="store_true", help="Force persistence (adds --force-persist to the runner)")
    parser.add_argument("--prompt-command", help="Optional prompt command to run (e.g. /runbook)", default=None)
    args = parser.parse_args()

    transcript_path: Optional[Path] = None
    # If a transcript file provided, use it. Otherwise read stdin.
    if args.transcript_file:
        t = Path(args.transcript_file)
        if not t.exists():
            print(f"Transcript file not found: {t}", file=sys.stderr)
            return 2
        raw_transcript = t.read_text(encoding="utf-8", errors="surrogateescape")
    else:
        if sys.stdin.isatty():
            print("No transcript provided via stdin or --transcript-file", file=sys.stderr)
            return 3
        raw_transcript = sys.stdin.read()
        if not raw_transcript.strip():
            print("Empty transcript", file=sys.stderr)
            return 4

    transcript_text, transcript_payload = _extract_structured_payload(raw_transcript)

    inferred_summary = _infer_summary_from_text(transcript_text)
    inferred_subagents = _infer_subagents_from_text(transcript_text)
    inferred_skills = _infer_skills_from_text(transcript_text)
    inferred_dispatch_path = _infer_dispatch_path(transcript_text, inferred_subagents)
    inferred_failure = _looks_like_failure(transcript_text)

    if transcript_payload:
        summary = _coalesce_text(args.summary, transcript_payload.get("summary"), inferred_summary)
        skills = _text_list_to_csv(_unique_text_list(args.skills, transcript_payload.get("skills"), transcript_payload.get("skills_used"), transcript_payload.get("skills_used_ordered"), inferred_skills))
        author = _coalesce_text(args.author, transcript_payload.get("author"))
        tags = _text_list_to_csv(args.tags) or _text_list_to_csv(transcript_payload.get("tags"))
        dispatch_path = _coalesce_text(args.dispatch_path, transcript_payload.get("dispatch_path"), transcript_payload.get("dispatch"), inferred_dispatch_path)
        event_flags = _load_json_object(args.event_flags, "--event-flags") if args.event_flags else {}
        if not event_flags:
            nested_event_flags = transcript_payload.get("event_flags")
            if isinstance(nested_event_flags, dict):
                event_flags = nested_event_flags
        if inferred_failure and not event_flags.get("failure_detected"):
            event_flags["failure_detected"] = True
        metadata = _load_json_object(args.metadata, "--metadata") if args.metadata else {}
        if not metadata:
            metadata = _payload_metadata(transcript_payload)
        else:
            metadata.update(_payload_metadata(transcript_payload))
        inferred_subagent_name = inferred_subagents[0] if inferred_subagents else None
        subagent_name = _coalesce_text(args.subagent_name, transcript_payload.get("subagent_name"), transcript_payload.get("subagent"), metadata.get("subagent"), inferred_subagent_name)
        merged_subagents = _unique_text_list(transcript_payload.get("subagents"), metadata.get("subagents"), inferred_subagents)
        if merged_subagents:
            metadata["subagents"] = merged_subagents
            metadata.setdefault("subagent", merged_subagents[0])
        if inferred_skills:
            metadata["skills_used"] = _unique_text_list(metadata.get("skills_used"), metadata.get("skills_used_ordered"), inferred_skills)
            metadata["skills_used_ordered"] = metadata["skills_used"]
            metadata.setdefault("prompt_normalization", "performed" if any(skill.lower() == "prompt-optimizer" for skill in metadata["skills_used"]) else metadata.get("prompt_normalization", "not applicable"))
        transcript_checkpoint = _infer_checkpoint_metadata_from_transcript(transcript_text)
        for key, value in transcript_checkpoint.items():
            if key == "files_touched":
                metadata[key] = _unique_text_list(metadata.get(key), value)
            elif value and not metadata.get(key):
                metadata[key] = value
        spawn_payload = args.spawn_payload or (
            json.dumps(transcript_payload["spawn_payload"], ensure_ascii=False)
            if isinstance(transcript_payload.get("spawn_payload"), dict)
            else None
        )
        model_catalog = args.model_catalog or (
            json.dumps(transcript_payload["model_catalog"], ensure_ascii=False)
            if isinstance(transcript_payload.get("model_catalog"), dict)
            else None
        )
        global_default_model = _coalesce_text(args.global_default_model, transcript_payload.get("global_default_model"))
        minimum_tier = _coalesce_text(args.minimum_tier, transcript_payload.get("minimum_tier"))
        prompt_command = _coalesce_text(args.prompt_command, transcript_payload.get("prompt_command"))
    else:
        summary = _coalesce_text(args.summary, inferred_summary) or "Chat session end"
        skills = _text_list_to_csv(_unique_text_list(args.skills, inferred_skills))
        author = args.author
        tags = args.tags or "copilot-chat"
        dispatch_path = _coalesce_text(args.dispatch_path, inferred_dispatch_path) or "single-agent"
        event_flags = _load_json_object(args.event_flags, "--event-flags") if args.event_flags else {}
        if inferred_failure and not event_flags.get("failure_detected"):
            event_flags["failure_detected"] = True
        metadata = _load_json_object(args.metadata, "--metadata") if args.metadata else {}
        subagent_name = _coalesce_text(args.subagent_name, inferred_subagents[0] if inferred_subagents else None)
        if inferred_subagents:
            metadata["subagents"] = _unique_text_list(metadata.get("subagents"), inferred_subagents)
            metadata.setdefault("subagent", metadata["subagents"][0])
        if inferred_skills:
            metadata["skills_used"] = _unique_text_list(metadata.get("skills_used"), metadata.get("skills_used_ordered"), inferred_skills)
            metadata["skills_used_ordered"] = metadata["skills_used"]
            metadata.setdefault("prompt_normalization", "performed" if any(skill.lower() == "prompt-optimizer" for skill in metadata["skills_used"]) else "not applicable")
        transcript_checkpoint = _infer_checkpoint_metadata_from_transcript(transcript_text)
        for key, value in transcript_checkpoint.items():
            if key == "files_touched":
                metadata[key] = _unique_text_list(metadata.get(key), value)
            elif value and not metadata.get(key):
                metadata[key] = value
        spawn_payload = args.spawn_payload
        model_catalog = args.model_catalog
        global_default_model = args.global_default_model
        minimum_tier = args.minimum_tier
        prompt_command = args.prompt_command

    summary = summary or "Chat session end"
    tags = tags or "copilot-chat"
    dispatch_path = dispatch_path or "single-agent"
    if _normalize_checkpoint_metadata:
        metadata = _normalize_checkpoint_metadata(summary=summary, metadata=metadata, event_flags=event_flags, prompt_command=prompt_command)

    # Score the transcript against the contract-validator checklist and inject
    # the result into metadata before logging, but only when no upstream caller
    # already set a real score.
    if not metadata.get("contract_score"):
        _subagent_for_score = metadata.get("subagent") or subagent_name
        score_value = _score_transcript(transcript_text, _subagent_for_score)
        if score_value:
            metadata["contract_score"] = score_value

    transcript_path = None
    if transcript_payload:
        tf = tempfile.NamedTemporaryFile(prefix="copilot_transcript_", suffix=".md", delete=False)
        tf.write(_utf8_backslashreplace_text(transcript_text).encode("utf-8"))
        tf.flush()
        tf.close()
        transcript_path = Path(tf.name)
    elif args.transcript_file:
        transcript_path = t
    else:
        tf = tempfile.NamedTemporaryFile(prefix="copilot_transcript_", suffix=".md", delete=False)
        tf.write(_utf8_backslashreplace_text(raw_transcript).encode("utf-8"))
        tf.flush()
        tf.close()
        transcript_path = Path(tf.name)

    runner = ORCHESTRATOR_ROOT / "scripts" / "log_hook_runner.py"
    arg_lines = ["--phase", "post", "--summary", summary]
    if skills:
        arg_lines += ["--skills", skills]
    if author:
        arg_lines += ["--author", author]
    if tags:
        arg_lines += ["--tags", tags]
    if dispatch_path:
        arg_lines += ["--dispatch-path", dispatch_path]
    if event_flags:
        arg_lines += ["--event-flags", json.dumps(event_flags, ensure_ascii=False)]
    if metadata:
        arg_lines += ["--metadata", json.dumps(metadata, ensure_ascii=False)]
    if subagent_name:
        arg_lines += ["--subagent-name", subagent_name]
    if spawn_payload:
        arg_lines += ["--spawn-payload", spawn_payload]
    if model_catalog:
        arg_lines += ["--model-catalog", model_catalog]
    if global_default_model:
        arg_lines += ["--global-default-model", global_default_model]
    if minimum_tier:
        arg_lines += ["--minimum-tier", minimum_tier]
    if args.force_persist:
        arg_lines += ["--force-persist"]
    if prompt_command:
        arg_lines += ["--prompt-command", prompt_command]
    if args.preview:
        arg_lines += ["--preview"]
    if transcript_path:
        arg_lines += ["--transcript-file", str(transcript_path)]

    # Write args to a temp file to avoid Windows MAX_PATH (260-char) limit on
    # long command lines that embed large JSON payloads inline.  argparse
    # @-file syntax reads each line of the file as a separate argument.
    args_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", prefix="copilot_runner_args_", suffix=".txt",
            delete=False, encoding="utf-8",
        ) as af:
            af.write(_utf8_backslashreplace_text("\n".join(arg_lines)))
            args_file = af.name

        cmd = [sys.executable, str(runner), f"@{args_file}"]
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    finally:
        if args_file:
            try:
                Path(args_file).unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
