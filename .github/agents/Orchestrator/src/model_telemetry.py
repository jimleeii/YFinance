"""Aggregate model telemetry from Orchestrator cycle logs.

The Orchestrator writes compact cycle telemetry to
``.wiki/orchestrator/telemetry/cycles.jsonl``.  This module turns those raw
events into per-model quality/latency/cost signals that can be merged into the
model catalog during discovery.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, Optional


def _normalize_model_id(name: Any) -> str:
    return str(name).strip().replace(" ", "-").lower()


def _coerce_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("score", "value", "count", "elapsed_ms", "cost", "total"):
            nested = value.get(key)
            parsed = _coerce_number(nested)
            if parsed is not None:
                return parsed
        return None
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _coerce_int(value: Any) -> Optional[int]:
    parsed = _coerce_number(value)
    if parsed is None:
        return None
    try:
        return int(round(parsed))
    except Exception:
        return None


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _coerce_text(value)
        if text:
            return text
    return ""


def _parse_timestamp(value: Any) -> Optional[datetime]:
    text = _coerce_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_workspace_root(repo_root: Optional[Path | str]) -> Path:
    candidate = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
    candidate = candidate.expanduser().resolve(strict=False)
    if candidate.name == "orchestrator" and candidate.parent.name == ".wiki":
        return candidate.parent.parent
    if (candidate / ".wiki" / "orchestrator").exists():
        return candidate
    return candidate


def _telemetry_path(repo_root: Optional[Path | str]) -> Path:
    workspace_root = _resolve_workspace_root(repo_root)
    return workspace_root / ".wiki" / "orchestrator" / "telemetry" / "cycles.jsonl"


def _record_cost_units(record: Dict[str, Any]) -> float:
    explicit = _coerce_number(record.get("cost_units"))
    if explicit is not None:
        return explicit

    transcript_chars = _coerce_int(record.get("transcript_chars")) or 0
    body_chars = _coerce_int(record.get("body_chars")) or 0
    summary_chars = _coerce_int(record.get("summary_chars")) or 0
    skills_count = _coerce_int(record.get("skills_count")) or 0
    files_count = _coerce_int(record.get("files_touched_count")) or 0
    elapsed_ms = _coerce_int(record.get("elapsed_ms")) or 0

    return (
        transcript_chars
        + (body_chars * 0.5)
        + (summary_chars * 0.25)
        + (skills_count * 120)
        + (files_count * 75)
        + (elapsed_ms * 0.1)
    )


def _extract_model_id(record: Dict[str, Any]) -> str:
    model_resolution = record.get("model_resolution") if isinstance(record.get("model_resolution"), dict) else {}
    return _normalize_model_id(
        _first_text(
            record.get("selected_model"),
            record.get("cycle_selected_model"),
            record.get("model"),
            model_resolution.get("model") if isinstance(model_resolution, dict) else None,
            model_resolution.get("selected_model") if isinstance(model_resolution, dict) else None,
        )
    )


def _is_failure(record: Dict[str, Any]) -> bool:
    for key in ("failure_detected", "failed", "is_failure"):
        if bool(record.get(key)):
            return True

    status = _coerce_text(record.get("status")).lower()
    if status in {"failure", "error"}:
        return True

    action = _coerce_text(record.get("action")).lower()
    if action in {"hard-stop", "retry-budget-exhausted"}:
        return True

    return False


def _normalize_inverse_score(value: Optional[float], values: Iterable[float]) -> Optional[int]:
    if value is None:
        return None

    samples = [sample for sample in values if sample is not None]
    if len(samples) < 2:
        return 50

    minimum = min(samples)
    maximum = max(samples)
    if maximum <= minimum:
        return 50

    normalized = 1.0 - ((value - minimum) / (maximum - minimum))
    return max(0, min(100, int(round(normalized * 100))))


def collect_cycle_model_telemetry(
    repo_root: Optional[Path | str] = None,
    window_days: int = 14,
    telemetry_path: Optional[Path | str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Dict[str, Any]]:
    """Aggregate telemetry from the Orchestrator cycle log.

    The return value is keyed by normalized model id.  Each entry contains
    aggregated quality/latency/cost scores plus raw sample counts so discovery
    can distinguish actual telemetry from priors.
    """

    path = Path(telemetry_path) if telemetry_path else _telemetry_path(repo_root)
    if not path.exists():
        return {}

    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=max(0, int(window_days)))

    samples: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "quality_samples": [],
        "latency_samples": [],
        "cost_samples": [],
        "sample_count": 0,
        "success_count": 0,
        "failure_count": 0,
    })

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}

    for line in lines:
        text = line.strip()
        if not text:
            continue

        try:
            record = json.loads(text)
        except Exception:
            continue

        if not isinstance(record, dict):
            continue

        recorded_at = _parse_timestamp(record.get("recorded_at_utc"))
        if recorded_at is not None and recorded_at < cutoff:
            continue

        model_id = _extract_model_id(record)
        if not model_id:
            continue

        entry = samples[model_id]
        entry["sample_count"] += 1

        quality = _coerce_number(record.get("contract_score"))
        if quality is None and isinstance(record.get("contract_score"), dict):
            quality = _coerce_number(record.get("contract_score", {}).get("score"))
        if quality is not None:
            entry["quality_samples"].append(max(0.0, min(100.0, quality)))

        latency = _coerce_number(
            record.get("elapsed_ms")
            or record.get("duration_ms")
            or record.get("runtime_ms")
            or record.get("api_duration_ms")
        )
        if latency is not None:
            entry["latency_samples"].append(max(0.0, latency))

        cost_units = _record_cost_units(record)
        if cost_units is not None:
            entry["cost_samples"].append(max(0.0, cost_units))

        if _is_failure(record):
            entry["failure_count"] += 1
        else:
            entry["success_count"] += 1

    if not samples:
        return {}

    latency_pool = [mean(entry["latency_samples"]) for entry in samples.values() if entry["latency_samples"]]
    cost_pool = [mean(entry["cost_samples"]) for entry in samples.values() if entry["cost_samples"]]

    result: Dict[str, Dict[str, Any]] = {}
    for model_id, entry in samples.items():
        quality_samples = entry["quality_samples"]
        latency_samples = entry["latency_samples"]
        cost_samples = entry["cost_samples"]

        quality_score = int(round(mean(quality_samples))) if quality_samples else None
        raw_latency = mean(latency_samples) if latency_samples else None
        raw_cost = mean(cost_samples) if cost_samples else None

        latency_score = _normalize_inverse_score(raw_latency, latency_pool)
        cost_score = _normalize_inverse_score(raw_cost, cost_pool)

        total = entry["success_count"] + entry["failure_count"]
        failure_rate = (entry["failure_count"] / total) if total else 0.0
        if total == 0:
            reliability = "unknown"
        elif failure_rate <= 0.05:
            reliability = "pass"
        elif failure_rate < 0.20:
            reliability = "mixed"
        else:
            reliability = "fail"

        result[model_id] = {
            "quality_score": quality_score,
            "latency_score": latency_score,
            "cost_score": cost_score,
            "quality_score_source": "orchestrator-telemetry" if quality_score is not None else None,
            "latency_score_source": "orchestrator-telemetry" if latency_score is not None else None,
            "cost_score_source": "orchestrator-telemetry" if cost_score is not None else None,
            "quality_sample_count": len(quality_samples),
            "latency_sample_count": len(latency_samples),
            "cost_sample_count": len(cost_samples),
            "sample_count": entry["sample_count"],
            "raw_latency_ms": round(raw_latency, 2) if raw_latency is not None else None,
            "raw_cost_units": round(raw_cost, 2) if raw_cost is not None else None,
            "tool_call_success_rate": round(entry["success_count"] / total, 4) if total else None,
            "tool_call_reliability": reliability,
            "telemetry_partial": any(value is None for value in (quality_score, latency_score, cost_score)),
        }

    return result


__all__ = ["collect_cycle_model_telemetry"]
