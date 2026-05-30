#!/usr/bin/env python3
"""Deterministic continuation planner for Orchestrator dispatch preparation."""
from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_PLAN_NAMESPACE = uuid.UUID("6a4f3c8d-3c32-4a72-bb37-5a4f4d6b7f21")
_MAX_ITEM_LENGTH = 96
_MAX_COMPLETED_ITEMS = 3
_MAX_BLOCKERS = 2
_MAX_NEXT_STEPS = 4

_ARCHITECTURE_KEYWORDS = (
    "architecture",
    "architect",
    "design",
    "plan",
    "refine the design",
    "boundary",
    "workflow",
    "orchestrator",
)
_IMPLEMENTATION_KEYWORDS = (
    "implement",
    "build",
    "code",
    "fix",
    "patch",
    "change",
    "update",
    "refactor",
    "cleanup",
    "simplify",
)
_REVIEW_KEYWORDS = (
    "test",
    "tests",
    "verify",
    "review",
    "validate",
    "validation",
    "qa",
    "coverage",
    "regression",
)
_RELEASE_KEYWORDS = (
    "deploy",
    "release",
    "ship",
    "merge",
    "handoff",
    "complete",
    "done",
)
_BLOCKER_KEYWORDS = (
    "block",
    "blocked",
    "blocking",
    "risk",
    "issue",
    "pending",
    "waiting",
    "wait",
    "failure",
    "failing",
    "error",
)


def generate_next_steps_plan(
    prior_session: Dict[str, Any],
    current_user_request: str,
    continuation_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate a compact, deterministic next-steps plan for a continuation."""
    prior_session = _coerce_mapping(prior_session)
    continuation_context = _coerce_mapping(continuation_context)
    request_text = _clean_text(current_user_request)
    detection = _extract_detection_context(continuation_context)

    blockers_to_address = _derive_blockers(prior_session, detection, continuation_context)
    completed_in_prior_session = _derive_completed_items(prior_session, continuation_context)
    recommended_next_steps = _derive_next_steps(request_text, blockers_to_address, continuation_context)
    suggested_subagents = _suggest_subagents(request_text, blockers_to_address, recommended_next_steps)
    stage = _derive_stage(request_text, blockers_to_address)
    plan = {
        "plan_id": _build_plan_id(prior_session, request_text, continuation_context),
        "generated_at": _generated_at_iso(continuation_context, prior_session),
        "continuation_basis": _build_continuation_basis(detection),
        "stage": stage,
        "blockers_to_address": blockers_to_address[:_MAX_BLOCKERS],
        "completed_in_prior_session": completed_in_prior_session[:_MAX_COMPLETED_ITEMS],
        "recommended_next_steps": recommended_next_steps[:_MAX_NEXT_STEPS],
        "suggested_subagents": suggested_subagents[:_MAX_BLOCKERS + 1],
        "estimated_effort": _estimate_effort(blockers_to_address, recommended_next_steps, stage),
    }
    return plan


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _clean_text(value: Any, limit: int = _MAX_ITEM_LENGTH) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = " ".join(text.split()).strip()
    if not text:
        return ""
    if limit > 0 and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return default


def _coerce_float(*values: Any, default: float = 0.0) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            continue
    return default


def _coerce_int(*values: Any, default: int = 0) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return default


def _iter_items(value: Any) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return value
    return (value,)


def _merge_unique_text_items(*sources: Any) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in _iter_items(source):
            text = _clean_text(item)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
    return merged


def _item_to_label(item: Any) -> str:
    if isinstance(item, Mapping):
        for key in ("title", "label", "name", "path", "detail", "summary", "content", "file", "artifact"):
            value = _clean_text(item.get(key))
            if not value:
                continue
            if key == "path":
                try:
                    path = Path(value)
                    value = _clean_text(path.name or path.stem)
                except Exception:
                    value = _clean_text(value)
            return value
        return ""
    if isinstance(item, Path):
        return _clean_text(item.name or str(item))
    return _clean_text(item)


def _items_to_text_list(*sources: Any) -> List[str]:
    labels: List[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in _iter_items(source):
            label = _item_to_label(item)
            if not label:
                continue
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
    return labels


def _extract_detection_context(continuation_context: Dict[str, Any]) -> Dict[str, Any]:
    nested = continuation_context.get("continuation_detection")
    nested_mapping = nested if isinstance(nested, Mapping) else {}
    return {
        "continuation_type": _first_text(
            continuation_context.get("continuation_type"),
            nested_mapping.get("continuation_type"),
            default="none",
        ),
        "confidence": _coerce_float(
            continuation_context.get("confidence"),
            nested_mapping.get("confidence"),
            default=0.0,
        ),
        "context_fact_count": _coerce_int(
            continuation_context.get("context_fact_count"),
            nested_mapping.get("context_fact_count"),
            default=0,
        ),
        "context_retrieval_source": _first_text(
            continuation_context.get("context_retrieval_source"),
            nested_mapping.get("context_retrieval_source"),
            default="none",
        ),
        "prior_blockers": _merge_unique_text_items(
            continuation_context.get("prior_blockers"),
            nested_mapping.get("prior_blockers"),
        ),
        "suggested_next_steps": _merge_unique_text_items(
            continuation_context.get("suggested_next_steps"),
            nested_mapping.get("suggested_next_steps"),
        ),
    }


def _build_continuation_basis(detection: Dict[str, Any]) -> str:
    return f"{detection.get('continuation_type', 'none')}@{float(detection.get('confidence', 0.0) or 0.0):.2f}"


def _generated_at_iso(continuation_context: Dict[str, Any], prior_session: Dict[str, Any]) -> str:
    candidate = _first_text(continuation_context.get("generated_at"), prior_session.get("generated_at"))
    if candidate:
        return candidate
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _build_plan_id(prior_session: Dict[str, Any], request_text: str, continuation_context: Dict[str, Any]) -> str:
    normalized_context = dict(continuation_context)
    normalized_context.pop("generated_at", None)
    snapshot = {
        "prior_session": _freeze_for_hash(prior_session),
        "current_user_request": request_text,
        "continuation_context": _freeze_for_hash(normalized_context),
    }
    digest = json.dumps(snapshot, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return f"cont-plan-{uuid.uuid5(_PLAN_NAMESPACE, digest)}"


def _freeze_for_hash(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _freeze_for_hash(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_freeze_for_hash(item) for item in value]
    if isinstance(value, set):
        return sorted((_freeze_for_hash(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _clean_text(value)


def _derive_blockers(
    prior_session: Dict[str, Any],
    detection: Dict[str, Any],
    continuation_context: Dict[str, Any],
) -> List[str]:
    blockers = _merge_unique_text_items(
        detection.get("prior_blockers"),
        continuation_context.get("prior_blockers"),
        prior_session.get("prior_blockers"),
        prior_session.get("blockers"),
        prior_session.get("blockers_to_address"),
    )
    normalized: List[str] = []
    seen: set[str] = set()
    for blocker in blockers:
        compact = _clean_text(blocker)
        if not compact:
            continue
        if len(compact) > _MAX_ITEM_LENGTH:
            compact = _clean_text(compact, _MAX_ITEM_LENGTH)
        if any(keyword in compact.casefold() for keyword in ("no blocker", "nothing blocking", "without issue", "no issue")):
            continue
        key = compact.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(compact)
        if len(normalized) >= _MAX_BLOCKERS:
            break
    return normalized


def _derive_completed_items(prior_session: Dict[str, Any], continuation_context: Dict[str, Any]) -> List[str]:
    completed = _items_to_text_list(
        prior_session.get("completed_in_prior_session"),
        prior_session.get("completed"),
        prior_session.get("artifacts"),
        prior_session.get("items"),
        continuation_context.get("prior_context_items"),
        continuation_context.get("items"),
    )
    normalized: List[str] = []
    seen: set[str] = set()
    for item in completed:
        compact = _clean_text(item)
        if not compact:
            continue
        key = compact.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(compact)
        if len(normalized) >= _MAX_COMPLETED_ITEMS:
            break
    return normalized


def _derive_next_steps(
    request_text: str,
    blockers: List[str],
    continuation_context: Dict[str, Any],
) -> List[str]:
    steps: List[str] = []
    seen: set[str] = set()

    def add_step(value: Any) -> None:
        compact = _clean_text(value)
        if not compact:
            return
        key = compact.casefold()
        if key in seen:
            return
        seen.add(key)
        steps.append(compact)

    for blocker in blockers:
        add_step(f"Clear blocker: {blocker}")
        if len(steps) >= _MAX_NEXT_STEPS:
            return steps[:_MAX_NEXT_STEPS]

    for suggestion in _merge_unique_text_items(continuation_context.get("suggested_next_steps")):
        add_step(suggestion)
        if len(steps) >= _MAX_NEXT_STEPS:
            return steps[:_MAX_NEXT_STEPS]

    for hint in _request_step_hints(request_text):
        add_step(hint)
        if len(steps) >= _MAX_NEXT_STEPS:
            return steps[:_MAX_NEXT_STEPS]

    if len(steps) < _MAX_NEXT_STEPS:
        add_step(_validation_step(request_text))

    return steps[:_MAX_NEXT_STEPS]


def _request_step_hints(request_text: str) -> List[str]:
    lowered = request_text.casefold()
    if any(keyword in lowered for keyword in ("fix", "bug", "error", "failure", "broken")):
        return ["Reproduce the issue.", "Patch the failing path."]
    if any(keyword in lowered for keyword in ("test", "tests", "verify", "review", "validate", "qa")):
        return ["Run the targeted checks.", "Confirm the result."]
    if any(keyword in lowered for keyword in ("refactor", "cleanup", "simplify", "modernize")):
        return ["Refine the change.", "Check for regressions."]
    if any(keyword in lowered for keyword in ("design", "architecture", "architect", "plan")):
        return ["Confirm the design boundary.", "Document the decision."]
    if any(keyword in lowered for keyword in ("deploy", "release", "ship", "merge", "handoff")):
        return ["Prepare the handoff.", "Verify readiness."]
    return ["Resume the pending work.", "Finish the remaining change."]


def _validation_step(request_text: str) -> str:
    lowered = request_text.casefold()
    if any(keyword in lowered for keyword in ("test", "tests", "verify", "review", "validate", "qa")):
        return "Run the targeted checks."
    if any(keyword in lowered for keyword in ("deploy", "release", "ship", "merge", "handoff")):
        return "Verify readiness."
    return "Verify the result."


def _suggest_subagents(request_text: str, blockers: List[str], next_steps: List[str]) -> List[str]:
    corpus = " ".join([request_text, " ".join(blockers), " ".join(next_steps)]).casefold()
    suggested: List[str] = []

    if any(keyword in corpus for keyword in _ARCHITECTURE_KEYWORDS):
        suggested.append("Software Architect")
    if any(keyword in corpus for keyword in _IMPLEMENTATION_KEYWORDS):
        suggested.append("Senior Developer")
    if any(keyword in corpus for keyword in _REVIEW_KEYWORDS):
        suggested.append("Code Reviewer")
    if not suggested:
        suggested.append("Senior Developer")

    return _merge_unique_text_items(suggested)[: _MAX_BLOCKERS + 1]


def _derive_stage(request_text: str, blockers: List[str]) -> str:
    if blockers:
        return "blocked"
    lowered = request_text.casefold()
    if any(keyword in lowered for keyword in _RELEASE_KEYWORDS):
        return "ready_to_deploy"
    return "in_progress"


def _estimate_effort(blockers: List[str], next_steps: List[str], stage: str) -> str:
    work_units = len(blockers) * 2 + len(next_steps)
    if stage == "blocked":
        work_units += 1
    if work_units <= 1:
        return "<1h"
    if work_units <= 3:
        return "1-2h"
    if work_units <= 5:
        return "2-4h"
    return ">4h"


__all__ = ["generate_next_steps_plan"]
