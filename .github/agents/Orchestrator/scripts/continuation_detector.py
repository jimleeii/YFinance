#!/usr/bin/env python3
"""Continuation detection heuristics for Orchestrator dispatch preparation."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_EXPLICIT_CONTINUATION_PATTERNS = (
    re.compile(r"\bpick up where (?:we|i) left off\b", re.IGNORECASE),
    re.compile(r"\bpick up from here\b", re.IGNORECASE),
    re.compile(r"\bpick up the thread\b", re.IGNORECASE),
    re.compile(r"\bcontinue\s+(?:the|this|that|with|from|work|task|project|where|working(?:\s+on)?)\b", re.IGNORECASE),
    re.compile(r"\bresume\s+(?:the|this|that|from|work|task|project|where|working(?:\s+on)?)\b", re.IGNORECASE),
    re.compile(r"\bkeep going\s+(?:with|on)\b", re.IGNORECASE),
    re.compile(r"\bcarry on\s+(?:with|on)\b", re.IGNORECASE),
    re.compile(r"\bkeep working on\b", re.IGNORECASE),
    re.compile(r"\bgo ahead and continue\b", re.IGNORECASE),
)

_BLOCKER_RE = re.compile(r"\b(blocked|blocking|wait(?:ing)?|pending|risk|issue|todo|to do)\b", re.IGNORECASE)
_NEGATED_BLOCKER_PATTERNS = (
    re.compile(r"\b(?:no|without)\s+(?:known\s+)?(?:issue|issues|blocker|blockers|problem|problems|risk|risks|todo|to do)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+a\s+blocker\b", re.IGNORECASE),
    re.compile(r"\bnothing\s+blocking\b", re.IGNORECASE),
)


def _default_result() -> Dict[str, Any]:
    return {
        "is_continuation": False,
        "confidence": 0.0,
        "continuation_type": "none",
        "signals": [],
        "prior_blockers": [],
        "suggested_next_steps": [],
    }


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    return " ".join(str(value).split()).strip()


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = [str(value).strip()]
    return [_coerce_text(item) for item in items if _coerce_text(item)]


def _merge_unique_text_lists(*sources: Any) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in _as_text_list(source):
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _normalize_for_match(value: Any) -> str:
    text = _coerce_text(value).casefold()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _first_matching_candidate(transcript_norm: str, candidates: List[str]) -> Optional[str]:
    for candidate in candidates:
        candidate_norm = _normalize_for_match(candidate)
        if not candidate_norm:
            continue
        if candidate_norm in transcript_norm:
            return _coerce_text(candidate)
    return None


def _extract_project_candidates(summary: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    candidates.extend(_as_text_list(summary.get("project_name_candidates")))

    for item in summary.get("prior_context_items") if isinstance(summary.get("prior_context_items"), list) else []:
        if not isinstance(item, dict):
            continue
        candidates.extend(_as_text_list(item.get("title")))

    return _merge_unique_text_lists(candidates)


def _extract_artifact_candidates(summary: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    candidates.extend(_as_text_list(summary.get("prior_artifact_paths")))
    candidates.extend(_as_text_list(summary.get("prior_artifact_stems")))
    candidates.extend(_as_text_list(summary.get("artifact_paths")))
    candidates.extend(_as_text_list(summary.get("artifact_names")))
    candidates.extend(_as_text_list(summary.get("prior_artifacts")))

    for item in summary.get("prior_context_items") if isinstance(summary.get("prior_context_items"), list) else []:
        if not isinstance(item, dict):
            continue
        path = _coerce_text(item.get("path"))
        if path:
            candidates.append(path)
            try:
                candidates.append(Path(path).stem)
            except Exception:
                pass

    return _merge_unique_text_lists(candidates)


def _extract_prior_blockers(summary: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    for key in (
        "prior_blockers",
        "blockers",
        "blockers_risks",
        "risks",
        "open_blockers",
        "open_issues",
        "known_blockers",
    ):
        for item in _as_text_list(summary.get(key)):
            if any(pattern.search(item) for pattern in _NEGATED_BLOCKER_PATTERNS):
                continue
            candidates.append(item)

    for item in summary.get("prior_context_items") if isinstance(summary.get("prior_context_items"), list) else []:
        if not isinstance(item, dict):
            continue
        detail = _coerce_text(item.get("detail"))
        if detail and any(pattern.search(detail) for pattern in _NEGATED_BLOCKER_PATTERNS):
            continue
        if detail and _BLOCKER_RE.search(detail):
            candidates.append(detail)

    return _merge_unique_text_lists(candidates)[:3]


def _extract_prior_user_candidates(summary: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    for key in ("prior_user", "session_user", "requested_by", "owner"):
        candidates.extend(_as_text_list(summary.get(key)))
    return _merge_unique_text_lists(candidates)


def detect_continuation(current_transcript: str, prior_session_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        transcript = _coerce_text(current_transcript)
        transcript_norm = _normalize_for_match(transcript)
        summary = dict(prior_session_summary or {}) if isinstance(prior_session_summary, dict) else {}
        prior_context_available = bool(
            summary.get("prior_context_items")
            or _coerce_text(summary.get("prior_context_markdown"))
            or int(_coerce_text(summary.get("context_fact_count") or 0) or 0)
        )

        signals: List[Dict[str, Any]] = []
        seen_evidence: set[str] = set()

        def add_signal(name: str, evidence: str, weight: float) -> None:
            evidence_text = _coerce_text(evidence)
            evidence_norm = _normalize_for_match(evidence_text)
            if not evidence_norm or evidence_norm in seen_evidence:
                return
            signals.append({"name": name, "evidence": evidence_text[:120], "weight": round(weight, 2)})
            seen_evidence.add(evidence_norm)

        explicit_match = None
        for pattern in _EXPLICIT_CONTINUATION_PATTERNS:
            match = pattern.search(transcript)
            if match:
                explicit_match = match.group(0)
                add_signal("explicit_continuation_request", explicit_match, 0.8)
                break

        project_match = None
        artifact_match = None
        if prior_context_available:
            project_match = _first_matching_candidate(transcript_norm, _extract_project_candidates(summary))
            if project_match:
                add_signal("project_reference", project_match, 0.65)

            artifact_match = _first_matching_candidate(transcript_norm, _extract_artifact_candidates(summary))
            if artifact_match:
                add_signal("artifact_reference", artifact_match, 0.65)

            current_user = _normalize_for_match(summary.get("current_user"))
            if current_user:
                prior_user_match = _first_matching_candidate(current_user, _extract_prior_user_candidates(summary))
                if prior_user_match:
                    add_signal("same_user", prior_user_match, 0.0)

        strong_signal = bool(explicit_match or project_match or artifact_match)
        if explicit_match:
            continuation_type = "explicit"
        elif project_match or artifact_match:
            continuation_type = "implicit"
        else:
            continuation_type = "none"

        confidence = round(min(1.0, sum(signal["weight"] for signal in signals)), 2)
        prior_blockers = _extract_prior_blockers(summary)
        suggested_next_steps = (
            [
                "Review the retrieved prior context before making changes.",
                "Resume from the latest checkpoint before introducing new work.",
            ]
            if strong_signal
            else []
        )

        return {
            "is_continuation": strong_signal,
            "confidence": confidence,
            "continuation_type": continuation_type,
            "signals": signals[:4],
            "prior_blockers": prior_blockers,
            "suggested_next_steps": suggested_next_steps[:2],
        }
    except Exception:
        return _default_result()
