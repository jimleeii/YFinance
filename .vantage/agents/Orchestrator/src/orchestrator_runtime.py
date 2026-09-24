import json
import os
import argparse
import subprocess
import sys
import sqlite3
import uuid
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

try:
    # When running as part of the package tests, import via the package name
    from src.trigger_test_prompt import append_behavior_log, append_skill_usage_log, write_transcript, extract_skill_usage
except Exception:
    # Fallback for running the module directly from the repo root
    from trigger_test_prompt import append_behavior_log, append_skill_usage_log, write_transcript, extract_skill_usage
try:
    from src.health_monitor import (
        build_health_policy,
        build_health_scope,
        classify_execution_failure_kind,
        classify_health_observation,
        get_workspace_health_registry,
    )
except Exception:
    from health_monitor import (  # type: ignore
        build_health_policy,
        build_health_scope,
        classify_execution_failure_kind,
        classify_health_observation,
        get_workspace_health_registry,
    )
try:
    from scripts.search_wiki import search_wiki_pages
except Exception:
    try:
        from search_wiki import search_wiki_pages  # type: ignore
    except Exception:
        search_wiki_pages = None  # type: ignore[assignment]
try:
    from scripts.continuation_detector import detect_continuation
except Exception:
    try:
        from continuation_detector import detect_continuation  # type: ignore
    except Exception:
        detect_continuation = None  # type: ignore[assignment]
try:
    from scripts.continuation_planner import generate_next_steps_plan
except Exception:
    try:
        from continuation_planner import generate_next_steps_plan  # type: ignore
    except Exception:
        generate_next_steps_plan = None  # type: ignore[assignment]
from src.model_resolver import resolve_model_for_subagent
try:
    from src.model_discovery import load_model_catalog_bundle
except Exception:
    from model_discovery import load_model_catalog_bundle  # type: ignore
try:
    from src.orchestrator_memory import derive_continuity_key, resolve_continuity_db_path
except Exception:
    from orchestrator_memory import derive_continuity_key, resolve_continuity_db_path  # type: ignore
from src.skill_loader import discover_skills, save_manifest
from src.policy_reloader import PolicyReloader

logger = logging.getLogger(__name__)

# Global policy reloader instance (initialized on first use)
_policy_reloader: Optional[PolicyReloader] = None


def _init_policy_reloader(skills_dir: Optional[str] = None) -> PolicyReloader:
    """Initialize and return the global policy reloader.

    Args:
        skills_dir: Path to skills directory. If None, uses default location.

    Returns:
        PolicyReloader instance.
    """
    global _policy_reloader

    if _policy_reloader is not None:
        return _policy_reloader

    if skills_dir is None:
        # Default to relative path from this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        skills_dir = os.path.join(current_dir, "..", "..", "skills")
        skills_dir = os.path.normpath(skills_dir)

    try:
        _policy_reloader = PolicyReloader(skills_dir)
        logger.debug(f"Policy reloader initialized: {skills_dir}")
    except Exception as e:
        logger.warning(f"Failed to initialize policy reloader: {e}")
        _policy_reloader = None

    return _policy_reloader


def check_and_reload_policies() -> List[str]:
    """Check for policy changes and reload them.

    Returns:
        List of policy skill names that were reloaded, empty if none changed.

    This is safe to call frequently; it uses internal debouncing to avoid
    excessive file I/O.
    """
    reloader = _init_policy_reloader()
    if reloader is None:
        return []

    try:
        reloaded = reloader.check_and_reload()
        if reloaded:
            logger.info(f"Policies reloaded: {', '.join(reloaded)}")
        return reloaded
    except Exception as e:
        logger.warning(f"Error during policy reload check: {e}")
        return []


def generate_cycle_id() -> str:
    """Return a unique cycle identifier: CYC-YYYYMMDD-HHMMSS-XXXX.

    The 4-character hex suffix prevents collisions when two cycles start within
    the same second.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"CYC-{ts}-{suffix}"


def score_response(response_text: str, role: str, threshold: int = 70) -> Dict[str, Any]:
    """Score a subagent response using the contract-validator checklist.

    Returns a dict with keys:
      - ``score`` (int 0-100)
      - ``passed`` (int items passed)
      - ``total`` (int items checked)
      - ``below_threshold`` (bool)
      - ``role`` (str)
      - ``threshold`` (int)
    """
    try:
        from src.score import compute_score, auto_detect_role  # type: ignore
    except Exception:
        try:
            from score import compute_score, auto_detect_role  # type: ignore
        except Exception:
            return {"score": None, "error": "score module not available",
                    "below_threshold": False, "role": role, "threshold": threshold}

    if role not in ("architect", "developer", "reviewer"):
        detected = auto_detect_role(response_text)
        role = detected or "developer"

    passed, total, _role_results, _fmt_results = compute_score(response_text, role)
    pct = round(passed / total * 100) if total else 0
    return {
        "score": pct,
        "passed": passed,
        "total": total,
        "below_threshold": pct < threshold,
        "role": role,
        "threshold": threshold,
    }


def load_config(wiki_root: str):
    cfg_path = os.path.join(wiki_root, "config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"force_persist_all": False}


def choose_logging_level(dispatch_path: str, event_flags: dict, config: dict):
    if config.get("force_persist_all"):
        return "full"
    # fallback to simple rules
    if event_flags.get("persistent_mode_change") or event_flags.get("tier_override"):
        return "full"
    if event_flags.get("failure_detected"):
        return "full"
    if dispatch_path in ("multi-agent", "concurrent"):
        return "full"
    if dispatch_path == "single-agent":
        return "compact"
    return "minimal"


def classify_dispatch_type(
    subagents: Optional[List[str]] = None,
    task_flags: Optional[Dict[str, bool]] = None,
) -> str:
    """Recommend a dispatch path given the planned subagent list and task flags.

    Returns one of: ``"direct"``, ``"single-agent"``, ``"multi-agent"``, or ``"concurrent"``.

    ``"concurrent"`` is returned only when:
    - Two or more subagents are planned **and**
    - The task flag ``"independent_tracks"`` is ``True`` **and**
    - The task flag ``"shared_state"`` is **not** ``True``.

    For all other multi-subagent cases ``"multi-agent"`` (sequential) is returned.
    """
    task_flags = task_flags or {}
    subagents = subagents or []
    if not subagents:
        return "direct"
    if len(subagents) == 1:
        return "single-agent"
    if task_flags.get("independent_tracks") and not task_flags.get("shared_state"):
        return "concurrent"
    return "multi-agent"


def _result_score(result: Dict[str, Any]) -> int:
    score = result.get("contract_score")
    if isinstance(score, dict):
        score = score.get("score")
    try:
        return int(score)
    except Exception:
        return 0


def _artifact_weight(result: Dict[str, Any]) -> int:
    artifacts = result.get("artifacts")
    if isinstance(artifacts, str):
        return 1 if artifacts.strip() else 0
    if isinstance(artifacts, (list, tuple, set, dict)):
        return len(artifacts)
    return 0


def _as_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed if parsed > 0 else default


def _resolve_orchestration_cycle(metadata: Dict[str, Any]) -> int:
    for key in ("orchestration_cycle", "cycle_number", "attempt", "attempt_number"):
        if key in metadata:
            resolved = _as_positive_int(metadata.get(key), 0)
            if resolved > 0:
                return resolved

    if "retry_count" in metadata:
        retry_count = _as_positive_int(metadata.get("retry_count"), 0)
        return retry_count + 1

    return 1


def _resolve_dispatch_agents(subagents: Optional[List[str]], metadata: Dict[str, Any]) -> List[str]:
    return _merge_unique_text_lists(subagents, metadata.get("subagents"), metadata.get("subagent"))


def _normalize_agent_payload(payload: Any, agent_name: str, error: Exception | None = None) -> Dict[str, Any]:
    if error is not None:
        return {
            "agent": agent_name,
            "status": "failure",
            "error": str(error),
            "health_failure_kind": classify_execution_failure_kind(error=error) or "exception",
        }

    if payload is None:
        return {"agent": agent_name, "status": "success", "output": None}

    if not isinstance(payload, dict):
        return {
            "agent": agent_name,
            "status": "success",
            "output": str(payload),
            "health_failure_kind": "malformed_output",
        }

    normalized_payload = dict(payload)
    normalized_payload.setdefault("agent", agent_name)
    return normalized_payload


def dispatch_concurrent(
    agents: List[str],
    prompt: str,
    metadata: Optional[Dict[str, Any]] = None,
    run_agent: Optional[Callable[[str, str, Dict[str, Any]], Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Fan-out to multiple agents and return results sorted by quality.

    The sorter prefers higher ``contract_score``; ties are broken by artifact count.
    ``run_agent`` is caller-provided to keep runtime decoupled from actual agent I/O.
    """
    metadata = dict(metadata or {})
    if not agents:
        return []
    if run_agent is None:
        return [{"agent": name, "status": "not-run", "prompt": prompt} for name in agents]

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(agents), 8)) as pool:
        futures = {
            pool.submit(run_agent, agent, prompt, dict(metadata)): agent
            for agent in agents
        }
        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                payload = future.result() or {}
                payload = _normalize_agent_payload(payload, agent_name)
            except Exception as exc:
                payload = _normalize_agent_payload(None, agent_name, error=exc)
            results.append(payload)

    return sorted(results, key=lambda item: (_result_score(item), _artifact_weight(item)), reverse=True)


def execute_dispatch_by_type(
    dispatch_type: str,
    prompt: str,
    metadata: Optional[Dict[str, Any]] = None,
    subagents: Optional[List[str]] = None,
    run_agent: Optional[Callable[[str, str, Dict[str, Any]], Dict[str, Any]]] = None,
    max_orchestration_cycles: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute a dispatch path and return structured runtime results.

    Supported dispatch types: ``direct``, ``single-agent``, ``multi-agent``, ``concurrent``.
    The retry budget is enforced via ``max_orchestration_cycles`` and a deterministic
    hard-stop result is returned once the budget is exhausted.
    """
    metadata = dict(metadata or {})

    # Check for policy reloads before dispatch
    reloaded_policies = check_and_reload_policies()
    if reloaded_policies and "cycle_id" not in metadata:
        metadata.setdefault("policy_reloaded", reloaded_policies)
    normalized_dispatch = _normalize_text(dispatch_type)
    agents = _resolve_dispatch_agents(subagents, metadata)

    if normalized_dispatch not in {"direct", "single-agent", "multi-agent", "concurrent"}:
        normalized_dispatch = classify_dispatch_type(
            subagents=agents,
            task_flags=metadata.get("task_flags") if isinstance(metadata.get("task_flags"), dict) else {},
        )

    if normalized_dispatch == "single-agent" and agents:
        agents = agents[:1]

    max_cycles = _as_positive_int(
        max_orchestration_cycles,
        _as_positive_int(metadata.get("max_orchestration_cycles"), 3),
    )
    orchestration_cycle = _resolve_orchestration_cycle(metadata)
    health_policy = build_health_policy(metadata)
    health_registry = None
    health_route: Dict[str, Any] = {}

    if normalized_dispatch != "direct" and agents:
        health_scope = build_health_scope(metadata, agents[0], dispatch_type=normalized_dispatch)
        health_registry = get_workspace_health_registry(health_scope.workspace_id, policy=health_policy)
        health_decision = health_registry.route_candidates(
            agents,
            session_id=health_scope.session_id,
            task_family=health_scope.task_family,
            model_id=health_scope.model_id,
        )
        health_route = health_decision.to_metadata()
        metadata.update(health_route)
        agents = list(health_decision.selected_candidates)

    base_result: Dict[str, Any] = {
        "dispatch": normalized_dispatch,
        "cycle_id": metadata.get("cycle_id"),
        "orchestration_cycle": orchestration_cycle,
        "max_orchestration_cycles": max_cycles,
        "subagents": agents,
    }

    if health_route:
        base_result["health"] = health_route.get("health")
        base_result["health_state"] = health_route.get("health_state")
        base_result["health_action"] = health_route.get("health_action")
        base_result["health_reason"] = health_route.get("health_reason")
        base_result["health_failure_kind"] = health_route.get("health_failure_kind")

    if orchestration_cycle > max_cycles:
        return {
            **base_result,
            "status": "retry-budget-exhausted",
            "executed": False,
            "retry_budget_exhausted": True,
            "retries_remaining": 0,
            "results": [],
            "primary_result": None,
            "action": "hard-stop",
            "reason": f"max_orchestration_cycles={max_cycles} exhausted before cycle {orchestration_cycle}",
        }

    retries_remaining = max(0, max_cycles - orchestration_cycle)

    if normalized_dispatch == "direct":
        return {
            **base_result,
            "status": "direct-complete",
            "executed": True,
            "retry_budget_exhausted": False,
            "retries_remaining": retries_remaining,
            "results": [],
            "primary_result": None,
            "dispatch_metadata": {
                "aggregation_strategy": "none",
                "review_ready": False,
            },
        }

    if not agents:
        return {
            **base_result,
            "status": "not-run",
            "executed": False,
            "retry_budget_exhausted": False,
            "retries_remaining": retries_remaining,
            "results": [],
            "primary_result": None,
            "action": "health-suppressed" if health_route else "missing-subagents",
            "reason": health_route.get("health_reason") or "no subagents provided for dispatch type",
        }

    if run_agent is None:
        return {
            **base_result,
            "status": "not-run",
            "executed": False,
            "retry_budget_exhausted": False,
            "retries_remaining": retries_remaining,
            "results": [],
            "primary_result": None,
            "action": "missing-run-agent",
            "reason": "run_agent callback is required for agent dispatch",
        }

    aggregation_strategy = "sequential"
    ranking_fields: List[str] = []

    if normalized_dispatch == "concurrent":
        aggregation_strategy = "contract_score_then_artifact_count"
        ranking_fields = ["contract_score", "artifact_count"]
        concurrent_metadata = dict(metadata)
        concurrent_metadata.update(
            {
                "dispatch_type": "concurrent",
                "dispatch_path": "concurrent",
                "aggregation_strategy": aggregation_strategy,
                "fanout_total": len(agents),
                "orchestration_cycle": orchestration_cycle,
                "max_orchestration_cycles": max_cycles,
            }
        )
        results = dispatch_concurrent(
            agents=agents,
            prompt=prompt,
            metadata=concurrent_metadata,
            run_agent=run_agent,
        )
        if health_registry is not None:
            for payload in results:
                agent_name = _first_text(payload.get("agent"), payload.get("subagent"), payload.get("name"))
                if not agent_name:
                    continue
                scope = build_health_scope(metadata, agent_name, dispatch_type=normalized_dispatch)
                observation = classify_health_observation(
                    scope=scope,
                    result=payload,
                    source="dispatch",
                )
                health_registry.record_observation(observation)
    else:
        results = []
        remaining_agents = list(agents)
        while remaining_agents:
            if health_registry is not None:
                route_scope = build_health_scope(metadata, remaining_agents[0], dispatch_type=normalized_dispatch)
                health_decision = health_registry.route_candidates(
                    remaining_agents,
                    session_id=route_scope.session_id,
                    task_family=route_scope.task_family,
                    model_id=route_scope.model_id,
                )
                if not health_decision.selected_candidates:
                    if not results:
                        return {
                            **base_result,
                            "status": "not-run",
                            "executed": False,
                            "retry_budget_exhausted": False,
                            "retries_remaining": retries_remaining,
                            "results": [],
                            "primary_result": None,
                            "action": "health-suppressed",
                            "reason": health_decision.reason,
                        }
                    break
                step_agent = health_decision.selected_candidates[0]
                step_metadata = dict(metadata)
                step_metadata.update(health_decision.to_metadata(agent_id=step_agent))
            else:
                step_agent = remaining_agents[0]
                step_metadata = dict(metadata)

            step_metadata["dispatch_type"] = normalized_dispatch
            step_metadata["dispatch_order"] = len(results) + 1
            step_metadata["dispatch_total"] = len(agents)
            try:
                payload = run_agent(step_agent, prompt, step_metadata) or {}
                payload = _normalize_agent_payload(payload, step_agent)
            except Exception as exc:
                payload = _normalize_agent_payload(None, step_agent, error=exc)

            results.append(payload)

            if health_registry is not None:
                scope = build_health_scope(metadata, step_agent, dispatch_type=normalized_dispatch)
                observation = classify_health_observation(
                    scope=scope,
                    result=payload,
                    source="dispatch",
                )
                health_registry.record_observation(observation)

            if step_agent in remaining_agents:
                remaining_agents.remove(step_agent)

    return {
        **base_result,
        "status": "success",
        "executed": True,
        "retry_budget_exhausted": False,
        "retries_remaining": retries_remaining,
        "results": results,
        "primary_result": results[0] if results else None,
        "result_count": len(results),
        "dispatch_metadata": {
            "aggregation_strategy": aggregation_strategy,
            "ranking_fields": ranking_fields,
            "review_ready": normalized_dispatch == "concurrent",
            **health_route,
        },
    }


def execute_workflow_plan(
    plan: Any,
    context: Optional[Dict[str, Any]] = None,
    workflow_context: Optional[Dict[str, Any]] = None,
):
    """Execute a pure workflow plan through the dedicated workflow state machine."""

    from src.workflow_state_machine import execute_workflow_plan as _execute_workflow_plan

    return _execute_workflow_plan(plan, context=context, workflow_context=workflow_context)


_ARCHITECTURE_ESCALATION_KEYWORDS = (
    "architecture",
    "architecture gap",
    "design",
    "design undefined",
    "interface",
    "interface missing",
    "boundary",
    "boundary unclear",
    "schema",
    "schema conflict",
    "contract",
    "dependency",
    "component",
)


def detect_architecture_gap_escalation(response: Any, role: str = "developer") -> Dict[str, Any]:
    """Detect whether a developer partial response should escalate back to architect."""
    normalized_role = _normalize_text(role)
    if normalized_role and normalized_role != "developer":
        return {"escalation_required": False, "matched_keywords": [], "reason": None}

    status = ""
    uncertainties: List[str] = []

    if isinstance(response, dict):
        status = _normalize_text(response.get("status"))
        raw = response.get("uncertainties")
        if isinstance(raw, str):
            uncertainties = [raw]
        elif isinstance(raw, (list, tuple, set)):
            uncertainties = [str(item) for item in raw]
    else:
        text = str(response or "")
        m = re.search(r"\bstatus\s*[:=]\s*(success|partial|failure)\b", text, re.IGNORECASE)
        status = _normalize_text(m.group(1) if m else "")
        uncertainties = [text]

    if status != "partial":
        return {"escalation_required": False, "matched_keywords": [], "reason": None}

    joined = "\n".join(uncertainties).lower()
    matched = [kw for kw in _ARCHITECTURE_ESCALATION_KEYWORDS if kw in joined]
    if not matched:
        return {"escalation_required": False, "matched_keywords": [], "reason": None}

    return {
        "escalation_required": True,
        "matched_keywords": matched,
        "reason": f"developer returned partial with architecture uncertainty: {', '.join(sorted(set(matched)))}",
    }


def dispatch_peer_review(
    role: str,
    outputs: List[Dict[str, Any]],
    criticality: str = "p2",
) -> Dict[str, Any]:
    """Reconcile same-role peer review outputs for high-criticality flows.

    For P0/P1 Architect flows, require at least two outputs and pick the highest
    scored output as primary; the second highest is challenger.
    """
    normalized_role = _normalize_text(role)
    normalized_criticality = _normalize_text(criticality)
    required = normalized_role == "architect" and normalized_criticality in {"p0", "p1"}
    ranked = sorted(outputs or [], key=lambda item: (_result_score(item), _artifact_weight(item)), reverse=True)

    if not required:
        return {
            "peer_review_required": False,
            "primary": ranked[0] if ranked else None,
            "challenger": ranked[1] if len(ranked) > 1 else None,
            "reconcile_required": False,
            "reason": "criticality below p0/p1 or role not architect",
        }

    if len(ranked) < 2:
        return {
            "peer_review_required": True,
            "primary": ranked[0] if ranked else None,
            "challenger": None,
            "reconcile_required": True,
            "reason": "p0/p1 architect peer review requires two outputs",
        }

    primary, challenger = ranked[0], ranked[1]
    return {
        "peer_review_required": True,
        "primary": primary,
        "challenger": challenger,
        "reconcile_required": _result_score(challenger) >= _result_score(primary),
        "reason": "p0/p1 architect peer review complete",
    }


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = [str(value).strip()]
    return [item for item in items if item]


def _merge_unique_text_lists(*sources: Any) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in _as_text_list(source):
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _first_text(*sources: Any) -> Optional[str]:
    for source in sources:
        items = _as_text_list(source)
        if items:
            return items[0]
    return None


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _looks_like_json_text(value: str) -> bool:
    stripped = value.strip()
    return (
        (stripped.startswith("{") and stripped.endswith("}"))
        or (stripped.startswith("[") and stripped.endswith("]"))
    )


def _is_noise_summary(value: Any) -> bool:
    text = _first_text(value)
    if not text:
        return True
    normalized = text.strip().lower()
    if normalized in {
        "post-tool invocation",
        "hook-triggered logging",
        "hook-triggered template render",
        "full-log template verification",
        "structured full-log template rendering",
    }:
        return True
    return _looks_like_json_text(text)


def _select_cycle_summary(prompt: str, metadata: Dict[str, Any]) -> str:
    for candidate in (
        metadata.get("project_request"),
        metadata.get("normalized_request"),
        metadata.get("summary"),
        metadata.get("change_applied"),
        metadata.get("signal"),
        prompt,
    ):
        text = _first_text(candidate)
        if text and not _is_noise_summary(text):
            return text
    return ""


def _merge_dispatch_metadata(
    metadata: Optional[Dict[str, Any]] = None,
    subagent_name: Optional[str] = None,
    model_resolution: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged = dict(metadata or {})

    if subagent_name:
        merged["subagent"] = subagent_name
        merged["subagents"] = _merge_unique_text_lists(merged.get("subagents"), subagent_name)

    if isinstance(model_resolution, dict):
        normalized = dict(model_resolution)
        resolved_model = _first_text(normalized.get("model"), normalized.get("selected_model"))
        if resolved_model:
            merged["selected_model"] = resolved_model
            merged["cycle_selected_model"] = resolved_model
            merged["model"] = resolved_model

        resolved_source = _first_text(normalized.get("source"))
        if resolved_source:
            merged["selected_model_source"] = resolved_source

        if normalized.get("fallback_used") is not None:
            merged["fallback_used"] = normalized["fallback_used"]
        fallback_reason = _first_text(normalized.get("fallback_reason"))
        if fallback_reason:
            merged["fallback_reason"] = fallback_reason

        merged["model_resolution"] = normalized

    return merged


def _compact_context_text(value: Any, limit: int = 160) -> str:
    text = _first_text(value)
    if not text:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(0, limit - 1)].rstrip() + "…"


def _resolve_dispatch_workspace_root(metadata: Dict[str, Any], spawn_payload: Dict[str, Any]) -> Path:
    for source in (metadata, spawn_payload):
        if not isinstance(source, dict):
            continue

        for key in ("workspace_root", "project_root", "repo_root"):
            candidate = _compact_context_text(source.get(key), 256)
            if not candidate:
                continue
            try:
                resolved = Path(candidate).expanduser().resolve(strict=False)
            except Exception:
                continue
            parts = [part.lower() for part in resolved.parts[-2:]]
            if parts == [".wiki", "orchestrator"]:
                return resolved.parent.parent
            return resolved

        wiki_root = _compact_context_text(source.get("wiki_root"), 256)
        if not wiki_root:
            continue
        try:
            resolved = Path(wiki_root).expanduser().resolve(strict=False)
        except Exception:
            continue
        parts = [part.lower() for part in resolved.parts[-2:]]
        if parts == [".wiki", "orchestrator"]:
            return resolved.parent.parent
        if resolved.name == ".wiki" and resolved.parent != resolved:
            return resolved.parent
        return resolved

    return Path.cwd()


def _build_prior_context_query(
    prompt: str,
    metadata: Dict[str, Any],
    subagent_name: Optional[str] = None,
    model_resolution: Optional[Dict[str, Any]] = None,
) -> str:
    query_parts = [
        _compact_context_text(prompt, 120),
        _compact_context_text(metadata.get("project_request"), 120),
        _compact_context_text(metadata.get("request_title"), 80),
        _compact_context_text(metadata.get("normalized_request"), 120),
        _compact_context_text(metadata.get("summary"), 120),
        _compact_context_text(subagent_name, 40),
    ]
    if isinstance(model_resolution, dict):
        query_parts.append(_compact_context_text(model_resolution.get("model"), 40))
        query_parts.append(_compact_context_text(model_resolution.get("selected_model"), 40))
    query = " ".join(part for part in query_parts if part)
    return " ".join(query.split())[:280]


def _prior_context_item_identity(item: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        _normalize_text(item.get("title")),
        _normalize_text(item.get("detail")),
        _normalize_text(item.get("path")),
    )


def _prior_context_item_from_cache_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = _compact_context_text(
        _first_text(row.get("request_title"), row.get("project_request"), row.get("normalized_request"), row.get("summary")),
        96,
    )
    detail_bits: List[str] = []
    summary = _compact_context_text(row.get("summary"), 120)
    if summary and summary.casefold() != title.casefold():
        detail_bits.append(summary)
    for label, key, limit in (
        ("change", "change_applied", 120),
        ("result", "observed_result", 120),
        ("decision", "decision", 80),
        ("next", "next_action", 80),
    ):
        text = _compact_context_text(row.get(key), limit)
        if not text:
            continue
        detail_bits.append(f"{label}: {text}")

    detail = "; ".join(detail_bits[:3])
    if not title and not detail:
        return None

    return {
        "source": "continuity_cache",
        "title": title or "continuity checkpoint",
        "detail": detail,
        "path": "",
    }


def _prior_context_item_from_wiki_result(result: Any) -> Optional[Dict[str, Any]]:
    title = _compact_context_text(getattr(result, "title", None), 96)
    path = _compact_context_text(getattr(result, "path", None), 120)
    snippet = _compact_context_text(getattr(result, "snippet", None), 180)
    if not title and not path and not snippet:
        return None

    return {
        "source": "wiki_search",
        "title": title or path or "wiki result",
        "detail": snippet,
        "path": path,
    }


def _format_prior_context_block(items: List[Dict[str, Any]]) -> str:
    if not items:
        return ""

    lines = ["## Prior Context (Auto-Retrieved)"]
    for item in items[:3]:
        source = _normalize_text(item.get("source"))
        label = "cache" if source == "continuity_cache" else "wiki"
        title = _compact_context_text(item.get("title"), 96)
        detail = _compact_context_text(item.get("detail"), 180)
        path = _compact_context_text(item.get("path"), 120)

        line = f"- {label}"
        if title:
            line += f": `{title}`"
        if path and source == "wiki_search":
            line += f" ({path})"
        if detail:
            line += f" — {detail}"
        lines.append(line)

    return "\n".join(lines)


_PRIOR_CONTEXT_CACHE_SAMPLE_LIMIT = 48
_PRIOR_CONTEXT_CACHE_EXACT_LIMIT = 12
_PRIOR_CONTEXT_QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "available",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "here",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "may",
    "might",
    "must",
    "no",
    "not",
    "of",
    "on",
    "only",
    "or",
    "our",
    "please",
    "prior",
    "project",
    "context",
    "request",
    "summary",
    "title",
    "normalized",
    "should",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "this",
    "those",
    "to",
    "too",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "will",
    "with",
    "without",
    "would",
    "you",
    "your",
}


def _prior_context_query_terms(query: str) -> List[str]:
    terms: List[str] = []
    seen: set[str] = set()
    for raw_term in re.split(r"[^A-Za-z0-9]+", _normalize_text(query)):
        term = raw_term.strip()
        if not term or len(term) < 3 or term in _PRIOR_CONTEXT_QUERY_STOPWORDS:
            continue
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms[:24]


def _prior_context_row_text(row: Dict[str, Any], *keys: str) -> str:
    return " ".join(
        text
        for text in (_normalize_text(row.get(key)) for key in keys)
        if text
    )


def _score_prior_context_row(
    row: Dict[str, Any],
    query_terms: List[str],
    continuity_key: str,
    request_group_id: str,
) -> int:
    score = 0
    subject_text = _prior_context_row_text(row, "project_request", "request_title", "normalized_request")
    detail_texts = (
        (_prior_context_row_text(row, "summary"), 4),
        (_prior_context_row_text(row, "change_applied"), 4),
        (_prior_context_row_text(row, "observed_result"), 4),
        (_prior_context_row_text(row, "next_action"), 3),
        (_prior_context_row_text(row, "decision"), 2),
    )

    for term in query_terms:
        if term in subject_text:
            score += 6
        for text, weight in detail_texts:
            if term in text:
                score += weight

    if continuity_key and _normalize_text(row.get("continuity_key")) == _normalize_text(continuity_key):
        score += 30
    if request_group_id and _normalize_text(row.get("request_group_id")) == _normalize_text(request_group_id):
        score += 18

    return score


def _collect_prior_context_cache_rows(
    connection: sqlite3.Connection,
    continuity_key: str,
    request_group_id: str,
) -> List[Dict[str, Any]]:
    candidate_rows: Dict[int, Dict[str, Any]] = {}

    def _add_rows(rows: List[sqlite3.Row]) -> None:
        for row in rows:
            try:
                row_id = int(row["id"])
            except Exception:
                continue
            candidate_rows[row_id] = dict(row)

    try:
        sample_rows = connection.execute(
            f"""
            SELECT id, continuity_key, request_group_id, project_request, request_title,
                   normalized_request, summary, change_applied, observed_result,
                   decision, next_action, created_at_utc
            FROM continuity_checkpoints
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (_PRIOR_CONTEXT_CACHE_SAMPLE_LIMIT,),
        ).fetchall()
        _add_rows(sample_rows)
    except Exception:
        pass

    if continuity_key:
        try:
            exact_rows = connection.execute(
                f"""
                SELECT id, continuity_key, request_group_id, project_request, request_title,
                       normalized_request, summary, change_applied, observed_result,
                       decision, next_action, created_at_utc
                FROM continuity_checkpoints
                WHERE continuity_key = ?
                ORDER BY created_at_utc DESC, id DESC
                LIMIT ?
                """,
                (continuity_key, _PRIOR_CONTEXT_CACHE_EXACT_LIMIT),
            ).fetchall()
            _add_rows(exact_rows)
        except Exception:
            pass

    if request_group_id:
        try:
            request_group_rows = connection.execute(
                f"""
                SELECT id, continuity_key, request_group_id, project_request, request_title,
                       normalized_request, summary, change_applied, observed_result,
                       decision, next_action, created_at_utc
                FROM continuity_checkpoints
                WHERE request_group_id = ?
                ORDER BY created_at_utc DESC, id DESC
                LIMIT ?
                """,
                (request_group_id, _PRIOR_CONTEXT_CACHE_EXACT_LIMIT),
            ).fetchall()
            _add_rows(request_group_rows)
        except Exception:
            pass

    return list(candidate_rows.values())


def _collect_prior_context_payload(
    prompt: str,
    metadata: Dict[str, Any],
    spawn_payload: Dict[str, Any],
    subagent_name: Optional[str],
    model_resolution: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    workspace_root = _resolve_dispatch_workspace_root(metadata, spawn_payload)
    query = _build_prior_context_query(
        prompt,
        metadata,
        subagent_name=subagent_name,
        model_resolution=model_resolution,
    )
    query_terms = _prior_context_query_terms(query)
    request_group_id = _normalize_text(metadata.get("request_group_id"))

    items: List[Dict[str, Any]] = []
    cache_items: List[Dict[str, Any]] = []
    wiki_contributed = False

    try:
        continuity_key = derive_continuity_key(metadata)
    except Exception:
        continuity_key = ""

    if query_terms or continuity_key or request_group_id:
        try:
            db_path = resolve_continuity_db_path(root=workspace_root)
            if db_path.exists():
                with sqlite3.connect(db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    rows = _collect_prior_context_cache_rows(connection, continuity_key, request_group_id)
                scored_rows = sorted(
                    (
                        (
                            _score_prior_context_row(row, query_terms, continuity_key, request_group_id),
                            _normalize_text(row.get("created_at_utc")),
                            int(row.get("id") or 0),
                            row,
                        )
                        for row in rows
                    ),
                    key=lambda item: (item[0], item[1], item[2]),
                    reverse=True,
                )
                cache_seen = set()
                for score, _, _, row in scored_rows:
                    if score <= 0:
                        continue
                    item = _prior_context_item_from_cache_row(row)
                    if item is None:
                        continue
                    identity = _prior_context_item_identity(item)
                    if identity in cache_seen:
                        continue
                    cache_seen.add(identity)
                    cache_items.append(item)
                    if len(cache_items) >= 3:
                        break
        except Exception:
            cache_items = []

    items = list(cache_items)
    seen = {_prior_context_item_identity(item) for item in items}

    if len(items) < 3 and query and search_wiki_pages is not None:
        wiki_root = workspace_root / ".wiki" / "orchestrator"
        if wiki_root.exists():
            try:
                wiki_results = search_wiki_pages(wiki_root, query, limit=5, include_transcripts=False)
            except Exception:
                wiki_results = []

            for result in wiki_results:
                if len(items) >= 3:
                    break
                item = _prior_context_item_from_wiki_result(result)
                if item is None:
                    continue
                identity = _prior_context_item_identity(item)
                if identity in seen:
                    continue
                seen.add(identity)
                items.append(item)
                wiki_contributed = True

    if not items:
        source = "none"
    elif cache_items:
        source = "continuity_cache"
    elif wiki_contributed:
        source = "wiki_search"
    else:
        source = "none"

    bounded_items = items[:3]
    return {
        "items": bounded_items,
        "markdown": _format_prior_context_block(bounded_items),
        "context_retrieval_source": source,
        "context_fact_count": len(bounded_items),
    }


def _build_continuation_detection_summary(
    user: str,
    metadata: Dict[str, Any],
    prior_context: Dict[str, Any],
    dispatch: str,
    subagent_name: Optional[str],
) -> Dict[str, Any]:
    prior_items = [item for item in prior_context.get("items", []) if isinstance(item, dict)]
    project_candidates = _merge_unique_text_lists(
        metadata.get("prior_project_name"),
        metadata.get("prior_project_request"),
        metadata.get("prior_request_title"),
        *(item.get("title") for item in prior_items),
    )

    artifact_paths: List[str] = []
    artifact_stems: List[str] = []
    for item in prior_items:
        path = _compact_context_text(item.get("path"), 120)
        if not path:
            continue
        artifact_paths.append(path)
        try:
            artifact_stem = Path(path).stem
        except Exception:
            artifact_stem = ""
        if artifact_stem:
            artifact_stems.append(artifact_stem)

    prior_blockers = _merge_unique_text_lists(
        metadata.get("blockers_risks"),
        metadata.get("blockers"),
        metadata.get("risks"),
        metadata.get("open_blockers"),
        metadata.get("open_issues"),
        metadata.get("known_blockers"),
        metadata.get("prior_blockers"),
    )
    for item in prior_items:
        detail = _compact_context_text(item.get("detail"), 180)
        if detail and re.search(r"\b(blocked|blocking|wait(?:ing)?|pending|risk|issue|todo|to do)\b", detail, re.IGNORECASE):
            prior_blockers.append(detail)

    return {
        "current_user": _compact_context_text(user, 80),
        "prior_user": _compact_context_text(_first_text(metadata.get("prior_user"), metadata.get("session_user"), metadata.get("requested_by"), metadata.get("owner")), 80),
        "current_project_request": _compact_context_text(metadata.get("project_request"), 160),
        "current_request_title": _compact_context_text(metadata.get("request_title"), 120),
        "current_summary": _compact_context_text(metadata.get("summary"), 160),
        "request_group_id": _compact_context_text(metadata.get("request_group_id"), 80),
        "session_id": _compact_context_text(metadata.get("session_id"), 80),
        "cycle_id": _compact_context_text(metadata.get("cycle_id"), 80),
        "dispatch": _compact_context_text(dispatch, 40),
        "subagent": _compact_context_text(subagent_name, 80),
        "selected_model": _compact_context_text(metadata.get("selected_model"), 80),
        "cycle_selected_model": _compact_context_text(metadata.get("cycle_selected_model"), 80),
        "context_retrieval_source": _compact_context_text(prior_context.get("context_retrieval_source"), 40),
        "context_fact_count": prior_context.get("context_fact_count", 0),
        "prior_context_markdown": _compact_context_text(prior_context.get("markdown"), 1200),
        "prior_context_items": prior_items[:3],
        "project_name_candidates": project_candidates[:6],
        "prior_artifact_paths": artifact_paths[:6],
        "prior_artifact_stems": _merge_unique_text_lists(artifact_stems)[:6],
        "prior_blockers": _merge_unique_text_lists(prior_blockers)[:3],
    }


def _empty_continuation_detection_result() -> Dict[str, Any]:
    return {
        "is_continuation": False,
        "confidence": 0.0,
        "continuation_type": "none",
        "signals": [],
        "prior_blockers": [],
        "suggested_next_steps": [],
    }


def _continuation_plan_item_label(item: Any) -> str:
    if not isinstance(item, dict):
        return _compact_context_text(item, 96)

    for key in ("title", "label", "name", "path", "detail", "summary", "content", "file", "artifact"):
        label = _compact_context_text(item.get(key), 96)
        if not label:
            continue
        if key == "path":
            try:
                path = Path(label)
                path_label = _compact_context_text(path.name or path.stem, 96)
                if path_label:
                    return path_label
            except Exception:
                pass
        return label
    return ""


def _continuation_plan_artifacts(prior_context: Dict[str, Any], continuation_summary: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    seen: set[str] = set()
    for source in (prior_context.get("items", []), continuation_summary.get("prior_context_items", [])):
        for item in source if isinstance(source, list) else []:
            label = _continuation_plan_item_label(item)
            if not label:
                continue
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
            if len(labels) >= 3:
                return labels
    return labels


def _build_continuation_plan_inputs(
    prompt: str,
    prior_context: Dict[str, Any],
    continuation_summary: Dict[str, Any],
    continuation_detection: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    prior_items = [item for item in prior_context.get("items", []) if isinstance(item, dict)]
    prior_blockers = _merge_unique_text_lists(
        continuation_summary.get("prior_blockers"),
        continuation_detection.get("prior_blockers"),
    )
    prior_session = dict(continuation_summary)
    prior_session["items"] = prior_items[:3]
    prior_session["artifacts"] = _continuation_plan_artifacts(prior_context, continuation_summary)
    prior_session["blockers"] = prior_blockers[:2]
    prior_session["stage"] = "blocked" if prior_blockers else "in_progress"

    continuation_context = dict(continuation_summary)
    continuation_context["continuation_detection"] = continuation_detection
    continuation_context["prior_blockers"] = prior_blockers[:3]
    continuation_context["current_user_request"] = _compact_context_text(prompt, 160)
    return prior_session, continuation_context


def _should_generate_continuation_plan(
    continuation_detection: Dict[str, Any],
    prior_context: Dict[str, Any],
) -> bool:
    if generate_next_steps_plan is None:
        return False
    if not isinstance(continuation_detection, dict):
        return False
    if not bool(continuation_detection.get("is_continuation")):
        return False
    try:
        confidence = float(continuation_detection.get("confidence", 0.0) or 0.0)
    except Exception:
        confidence = 0.0
    if confidence < 0.80:
        return False
    try:
        context_fact_count = int(prior_context.get("context_fact_count", 0) or 0)
    except Exception:
        context_fact_count = 0
    return context_fact_count > 0


def _safe_continuation_plan(plan: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(plan, dict):
        return None
    try:
        return json.loads(json.dumps(plan, ensure_ascii=False))
    except Exception:
        return None


def _generate_continuation_plan(
    prompt: str,
    prior_context: Dict[str, Any],
    continuation_summary: Dict[str, Any],
    continuation_detection: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not _should_generate_continuation_plan(continuation_detection, prior_context):
        return None

    prior_session, planner_context = _build_continuation_plan_inputs(
        prompt=prompt,
        prior_context=prior_context,
        continuation_summary=continuation_summary,
        continuation_detection=continuation_detection,
    )
    try:
        plan = generate_next_steps_plan(
            prior_session=prior_session,
            current_user_request=prompt,
            continuation_context=planner_context,
        )
    except Exception:
        return None
    return _safe_continuation_plan(plan)


def persist_cycle(
    wiki_root: str,
    prompt: str,
    user: str,
    logging_level: str,
    output_text: str = "",
    dispatch_path: str = "single-agent",
    explicit_skill_names: Optional[List[str]] = None,
    event_flags: Optional[Dict[str, bool]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    # Use trigger_test_prompt.extract_skill_usage to compute structured skill usage
    # and delegate actual persistence to the centralized hooks (`hooks.log_hooks`)
    try:
        # dynamic import to avoid top-level dependency issues in some environments
        from hooks.log_hooks import log_cycle, normalize_checkpoint_metadata
    except Exception:
        # Best-effort: if hooks package isn't importable, fall back to previous behavior
        log_cycle = None
        normalize_checkpoint_metadata = None

    event_flags = dict(event_flags or {})
    metadata = dict(metadata or {})
    if normalize_checkpoint_metadata:
        metadata = normalize_checkpoint_metadata(summary=prompt, metadata=metadata, event_flags=event_flags)
    summary = _select_cycle_summary(prompt, metadata)

    # Parse skill usage from input/output without writing files
    skill_usage = extract_skill_usage(prompt, output_text or "", explicit_skill_names=explicit_skill_names or ())
    merged_skills = _merge_unique_text_lists(
        skill_usage.get("skills", []),
        metadata.get("skills_used"),
        metadata.get("skills_used_ordered"),
    )
    skill_usage = {
        **skill_usage,
        "skills": merged_skills,
    }
    sources = dict(skill_usage.get("sources", {}))
    for skill_name in merged_skills:
        sources.setdefault(skill_name, "metadata")
    skill_usage["sources"] = sources

    if logging_level == "minimal":
        print("Minimal logging: no persisted artifacts")
        return skill_usage

    # If hooks are available, use them to persist logs (they call the log CLI)
    if log_cycle:
        transcript_text = output_text if logging_level == "full" else None
        result = log_cycle(
            dispatch_path=dispatch_path,
            event_flags=event_flags,
            summary=summary,
            skills=merged_skills,
            metadata=metadata,
            transcript=transcript_text,
            force_persist_all=False,
            author=user,
            # `target_root` tells the log script where to write .wiki/orchestrator
            target_root=os.getcwd(),
        )
        # Report persistence result minimally for visibility
        print(f"log_cycle result: {result}")
        return skill_usage

    # Fallback behaviour: persist using legacy functions
    if logging_level == "full":
        append_behavior_log(wiki_root, prompt, user=user, metadata=metadata)
        skill_usage = append_skill_usage_log(
            wiki_root,
            prompt,
            output_text=output_text,
            user=user,
            routing_path=dispatch_path,
            explicit_skill_names=explicit_skill_names or (),
            metadata=metadata,
        )
        path = write_transcript(wiki_root, prompt, output_text=output_text, skill_usage=skill_usage)
        print(f"Persisted full artifacts (fallback): {path}")
        return skill_usage

    if logging_level == "compact":
        append_behavior_log(wiki_root, prompt, user=user, metadata=metadata)
        skill_usage = append_skill_usage_log(
            wiki_root,
            prompt,
            output_text=output_text,
            user=user,
            routing_path=dispatch_path,
            explicit_skill_names=explicit_skill_names or (),
            metadata=metadata,
        )
        print("Persisted compact behavior checkpoint (fallback)")
        return skill_usage

    print("Minimal logging: no persisted artifacts (fallback)")
    return skill_usage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", "-p", required=True)
    parser.add_argument("--wiki", "-w", default=".wiki/orchestrator")
    parser.add_argument("--user", "-u", default="runtime-user")
    parser.add_argument("--dispatch", "-d", default="single-agent")
    parser.add_argument("--event-flags", help="Structured JSON event flags to influence logging decisions")
    parser.add_argument("--metadata", help="Structured JSON metadata to carry into wiki log entries")
    parser.add_argument("--discover-skills", action="store_true", help="Scan and write skills manifest")
    parser.add_argument("--manifest-path", default="skills/skills_manifest.json", help="Manifest output path")
    parser.add_argument("--run-script", help="Run a repository script (relative path)")
    parser.add_argument("--run-skill", help="Run an executable script inside a skill folder (skill name)")
    parser.add_argument("--skill-script-name", help="Optional specific script filename inside the skill folder")
    args = parser.parse_args()

    config = load_config(args.wiki)
    try:
        event_flags = json.loads(args.event_flags) if args.event_flags else {}
        if not isinstance(event_flags, dict):
            raise ValueError("event flags must be a JSON object")
    except Exception as exc:
        parser.error(f"--event-flags must be a JSON object: {exc}")
    try:
        metadata = json.loads(args.metadata) if args.metadata else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
    except Exception as exc:
        parser.error(f"--metadata must be a JSON object: {exc}")
    level = choose_logging_level(args.dispatch, event_flags, config)
    print(f"Logging level chosen: {level}")
    os.makedirs(args.wiki, exist_ok=True)

    script_output = None
    skill_output = None

    # Optional operations: discover skills or run scripts inside the runtime
    if getattr(args, "discover_skills", False):
        manifest = discover_skills("skills")
        save_manifest(manifest, args.manifest_path)
        print(f"Saved skills manifest to {args.manifest_path} ({len(manifest)} skills)")

    if args.run_script:
        script_output = run_script(args.run_script)
        print(script_output)

    if args.run_skill:
        skill_output = run_skill_script(args.run_skill, script_name=args.skill_script_name)
        print(skill_output)

    output_text = "\n\n".join(part for part in [skill_output, script_output] if part)
    persist_cycle(
        args.wiki,
        args.prompt,
        args.user,
        level,
        output_text=output_text,
        dispatch_path=args.dispatch,
        explicit_skill_names=[args.run_skill] if args.run_skill else None,
        event_flags=event_flags,
        metadata=metadata,
    )


def init_orchestrator(skills_dir: Optional[str] = None, manifest_path: Optional[str] = None) -> dict:
    """Initialize orchestrator runtime by discovering skills and writing a manifest.

    By default this uses the package-relative `skills/` folder (adjacent to `src/`).
    The function will only write the manifest if one or more skills are discovered to
    avoid creating or overwriting a manifest with empty data in environments where
    the skills folder isn't present (for example when this package is imported from
    another project's working directory during deployment).

    Returns the discovered manifest dictionary.
    """
    if skills_dir is None or manifest_path is None:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(module_dir, ".."))
        skills_dir = skills_dir or os.path.join(repo_root, "skills")
        manifest_path = manifest_path or os.path.join(skills_dir, "skills_manifest.json")

    manifest = discover_skills(skills_dir)
    # Only persist when we found skills to avoid creating/truncating an empty manifest
    if manifest:
        save_manifest(manifest, manifest_path)
    return manifest


def run_script(path: str, args: Optional[List[str]] = None, timeout: int = 30) -> str:
    """Run a script file and return combined stdout/stderr output.

    Supports Python (`.py`), PowerShell (`.ps1`), and shell (`.sh`) scripts.
    """
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    if not os.path.exists(path):
        return f"Script not found: {path}"

    args = args or []
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        cmd = [sys.executable, path] + args
    elif ext == ".ps1":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path] + args
    elif ext == ".sh":
        cmd = ["bash", path] + args
    else:
        return f"Unsupported script type: {ext}"

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = proc.stdout or ""
        err = proc.stderr or ""
        return (out + err).strip()
    except Exception as e:
        return f"Script execution failed: {e}"


def run_skill_script(skill_name: str, script_name: Optional[str] = None) -> str:
    """Find an executable script inside `skills/<skill_name>/` and run it.

    If `script_name` is provided, run that file; otherwise choose the first
    `.py`, `.ps1`, or `.sh` file found.
    """
    base = os.path.join("skills", skill_name)
    if not os.path.isdir(base):
        return f"Skill not found: {skill_name}"

    if script_name:
        candidate = os.path.join(base, script_name)
        if os.path.exists(candidate):
            return run_script(candidate)
        return f"Script {script_name} not found in skill {skill_name}"

    # choose first supported script
    for fname in sorted(os.listdir(base)):
        if fname.lower().endswith(('.py', '.ps1', '.sh')):
            return run_script(os.path.join(base, fname))
    return f"No executable script found in skill {skill_name}"


# Auto-initialize skills manifest on import unless explicitly skipped.
try:
    if os.environ.get("ORCHESTRATOR_SKIP_AUTOINIT", "0") not in ("1", "true", "True"):
        # Best-effort: discover skills relative to this package and persist only if non-empty.
        try:
            module_dir = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(module_dir, ".."))
            default_skills_dir = os.path.join(repo_root, "skills")
            default_manifest_path = os.path.join(default_skills_dir, "skills_manifest.json")
            if os.path.isdir(default_skills_dir):
                _MANIFEST = init_orchestrator(skills_dir=default_skills_dir, manifest_path=default_manifest_path)
            else:
                # No package-relative skills folder; avoid creating files in caller CWD
                _MANIFEST = {}
        except Exception:
            _MANIFEST = {}
    else:
        _MANIFEST = {}
except Exception:
    _MANIFEST = {}


def handle_request(prompt: str, user: str = "runtime-user", dispatch: str = "single-agent",
                   run_skill: Optional[str] = None, skill_script_name: Optional[str] = None,
                   run_script_path: Optional[str] = None, event_flags: Optional[Dict[str, bool]] = None,
                   metadata: Optional[Dict[str, Any]] = None,
                   response_text: Optional[str] = None,
                   response_role: Optional[str] = None,
                   score_threshold: int = 70) -> dict:
    """Handle an incoming request: persist artifacts and optionally run scripts.

    This is a lightweight runtime entry that Orchestrator agents can call to
    persist behavior logs/transcripts and to execute local scripts or skill
    scripts. Returns a dict containing the persistence info and any script output.

    Optional scoring:
      response_text: subagent response text to score via score.py.
      response_role: role hint ('architect', 'developer', 'reviewer'); auto-detected
          from response_text when omitted.
      score_threshold: minimum passing score (default 70). When the response scores
          below this, ``event_flags['tier_override']`` is set to ``True`` so the
          next model-resolver call escalates to a frontier-tier model.
    """
    config = load_config('.wiki/orchestrator')
    event_flags = dict(event_flags or {})
    metadata = dict(metadata or {})

    # TODO-2: Ensure every request carries a unique cycle_id for cross-agent tracing
    if "cycle_id" not in metadata:
        metadata["cycle_id"] = generate_cycle_id()

    # TODO-1: Score the subagent response when provided; escalate tier on low score
    contract_score_result: Optional[Dict[str, Any]] = None
    if response_text:
        contract_score_result = score_response(
            response_text, response_role or "", threshold=score_threshold
        )
        metadata["contract_score"] = contract_score_result.get("score")
        metadata["contract_role"] = contract_score_result.get("role")
        if contract_score_result.get("below_threshold"):
            event_flags["tier_override"] = True
            metadata["tier_override_reason"] = (
                f"contract_score={contract_score_result['score']} "
                f"< threshold {score_threshold}; model escalated to frontier"
            )

        escalation_check = detect_architecture_gap_escalation(
            response_text,
            role=response_role or contract_score_result.get("role") or "developer",
        )
        if escalation_check.get("escalation_required"):
            event_flags["escalation_required"] = True
            metadata["escalation"] = "developer→architect"
            metadata["escalation_reason"] = escalation_check.get("reason")
            metadata["escalation_keywords"] = escalation_check.get("matched_keywords", [])

    try:
        from hooks.log_hooks import normalize_checkpoint_metadata
    except Exception:
        normalize_checkpoint_metadata = None
    if normalize_checkpoint_metadata:
        metadata = normalize_checkpoint_metadata(summary=prompt, metadata=metadata, event_flags=event_flags)
    level = choose_logging_level(dispatch, event_flags, config)
    os.makedirs('.wiki/orchestrator', exist_ok=True)
    skill_output = None
    script_output = None

    if run_skill:
        skill_output = run_skill_script(run_skill, script_name=skill_script_name)

    if run_script_path:
        script_output = run_script(run_script_path)

    output_text = "\n\n".join(part for part in [skill_output, script_output] if part)
    skill_usage = persist_cycle(
        '.wiki/orchestrator',
        prompt,
        user,
        level,
        output_text=output_text,
        dispatch_path=dispatch,
        explicit_skill_names=[run_skill] if run_skill else None,
        event_flags=event_flags,
        metadata=metadata,
    )

    result = {
        "logging_level": level,
        "manifest_summary": {"count": len(_MANIFEST)} if isinstance(_MANIFEST, dict) else {},
        "skill_output": skill_output,
        "script_output": script_output,
        "skill_usage": skill_usage,
        "event_flags": event_flags,
        "metadata": metadata,
        "cycle_id": metadata.get("cycle_id"),
        "contract_score": contract_score_result,
    }

    return result


def prepare_dispatch_payload(prompt: str, user: str = "runtime-user", dispatch: str = "single-agent",
                                                         run_skill: Optional[str] = None, skill_script_name: Optional[str] = None,
                                                         run_script_path: Optional[str] = None, event_flags: Optional[Dict[str, bool]] = None,
                                                         metadata: Optional[Dict[str, Any]] = None, subagent_name: Optional[str] = None,
                                                         model_resolution: Optional[Dict[str, Any]] = None,
                                                         spawn_payload: Optional[Dict[str, Any]] = None,
                                                         model_catalog: Optional[Dict[str, Dict[str, Any]]] = None,
                                                         global_default_model: Optional[str] = None,
                                                         minimum_tier: Optional[str] = None) -> dict:
        """Run persistence + optional skill/script and return a payload ready for dispatch.

        Returns a dict with keys:
            - `prompt`: the original prompt (normalized)
            - `parent_context`: dictionary with `persistence` (raw handle_request output)
            - `dispatch`: chosen dispatch path
            - `subagent`: chosen subagent name when supplied
            - `model_resolution`: resolved model metadata when supplied or auto-resolved
            - `spawn_payload`: original spawn payload when supplied

        This helper centralizes the pre-dispatch steps so callers (CLI or other
        orchestrator code) can call it and pass the resulting payload to their
        subagent dispatch mechanism (e.g., `agent/runSubagent`).
        """
        event_flags = dict(event_flags or {})
        metadata = dict(metadata or {})
        spawn_payload = dict(spawn_payload or {})

        if not subagent_name:
            subagent_name = _first_text(spawn_payload.get("name"), spawn_payload.get("subagent"), metadata.get("subagent"))

        model_catalog_bundle = None
        if model_catalog is None or global_default_model is None:
            try:
                model_catalog_bundle = load_model_catalog_bundle()
            except Exception as exc:
                logger.debug("Model catalog auto-discovery failed: %s", exc)
                model_catalog_bundle = None

        if model_catalog is None and model_catalog_bundle is not None:
            model_catalog = model_catalog_bundle.catalog

        if global_default_model is None and model_catalog_bundle is not None:
            global_default_model = model_catalog_bundle.default_model

        if model_resolution is None and spawn_payload and model_catalog and global_default_model:
            # Pass contract_score so a low-scoring previous response escalates the tier
            _contract_score = metadata.get("contract_score")
            _contract_score = int(_contract_score) if _contract_score is not None else None
            model_resolution = resolve_model_for_subagent(
                spawn_payload=spawn_payload,
                parent_context=dict(metadata or {}),
                model_catalog=model_catalog,
                global_default_model=global_default_model,
                minimum_tier=minimum_tier,
                contract_score=_contract_score,
            )

        if global_default_model and not metadata.get("selected_model"):
            metadata.setdefault("global_default_model", global_default_model)
            metadata.setdefault("selected_model", global_default_model)
            metadata.setdefault("cycle_selected_model", global_default_model)
            metadata.setdefault("model", global_default_model)

        metadata = _merge_dispatch_metadata(metadata, subagent_name=subagent_name, model_resolution=model_resolution)
        try:
            from hooks.log_hooks import normalize_checkpoint_metadata
        except Exception:
            normalize_checkpoint_metadata = None
        if normalize_checkpoint_metadata:
            metadata = normalize_checkpoint_metadata(summary=prompt, metadata=metadata, event_flags=event_flags)
        prior_context = _collect_prior_context_payload(
            prompt=prompt,
            metadata=metadata,
            spawn_payload=spawn_payload,
            subagent_name=subagent_name,
            model_resolution=model_resolution,
        )
        metadata["context_retrieval_source"] = prior_context["context_retrieval_source"]
        metadata["context_fact_count"] = prior_context["context_fact_count"]
        continuation_summary = _build_continuation_detection_summary(
            user=user,
            metadata=metadata,
            prior_context=prior_context,
            dispatch=dispatch,
            subagent_name=subagent_name,
        )
        continuation_detection = _empty_continuation_detection_result()
        if detect_continuation is not None:
            try:
                detected = detect_continuation(prompt, continuation_summary)
            except Exception:
                detected = None
            if isinstance(detected, dict):
                continuation_detection.update(detected)
        continuation_plan = _generate_continuation_plan(
            prompt=prompt,
            prior_context=prior_context,
            continuation_summary=continuation_summary,
            continuation_detection=continuation_detection,
        )
        if continuation_plan is not None:
            metadata["continuation_plan"] = continuation_plan
        continuation_detection["is_continuation"] = bool(continuation_detection.get("is_continuation"))
        try:
            continuation_detection["confidence"] = float(continuation_detection.get("confidence", 0.0) or 0.0)
        except Exception:
            continuation_detection["confidence"] = 0.0
        for key in ("signals", "prior_blockers", "suggested_next_steps"):
            value = continuation_detection.get(key)
            if isinstance(value, list):
                continue
            if isinstance(value, tuple):
                continuation_detection[key] = list(value)
            else:
                continuation_detection[key] = []
        metadata["continuation_detection"] = continuation_detection
        metadata["is_continuation"] = continuation_detection["is_continuation"]
        metadata["continuation_type"] = continuation_detection.get("continuation_type", "none")
        persistence = handle_request(prompt=prompt, user=user, dispatch=dispatch,
                                     run_skill=run_skill, skill_script_name=skill_script_name,
                                     run_script_path=run_script_path,
                                     event_flags=event_flags, metadata=metadata)

        parent_context = {
            "persistence": persistence,
            # include manifest path reference where applicable
            "skills_manifest": "skills/skills_manifest.json",
            "event_flags": event_flags,
            "dispatch_metadata": metadata,
            "context_retrieval_source": prior_context["context_retrieval_source"],
            "context_fact_count": prior_context["context_fact_count"],
            "prior_context": prior_context["markdown"],
            "prior_context_items": prior_context["items"],
            "continuation_detection": continuation_detection,
            "is_continuation": continuation_detection["is_continuation"],
            "continuation_type": continuation_detection.get("continuation_type", "none"),
        }

        if continuation_plan is not None:
            parent_context["continuation_plan"] = continuation_plan

        if subagent_name:
            parent_context["subagent"] = subagent_name
        elif metadata.get("subagent"):
            parent_context["subagent"] = metadata["subagent"]

        if metadata.get("subagents"):
            parent_context["subagents"] = metadata["subagents"]

        if metadata.get("selected_model"):
            parent_context["selected_model"] = metadata["selected_model"]

        if metadata.get("cycle_selected_model"):
            parent_context["cycle_selected_model"] = metadata["cycle_selected_model"]

        if model_resolution is not None:
            parent_context["model_resolution"] = model_resolution

        if spawn_payload:
            parent_context["spawn_payload"] = spawn_payload

        for key in (
            "selected_model",
            "cycle_selected_model",
            "subagent",
            "subagents",
            "skills_used",
            "skills_used_ordered",
            "task_type",
            "criticality",
            "prompt_normalization",
            "contract_score",
            "routing_mode",
            "outcome",
        ):
            if key in metadata and metadata[key] is not None:
                parent_context[key] = metadata[key]

        payload = {
                "prompt": prompt,
                "dispatch": dispatch,
                "subagent": parent_context.get("subagent"),
                "model_resolution": model_resolution,
                "spawn_payload": spawn_payload or None,
            "parent_context": parent_context,
        }
        return payload


if __name__ == "__main__":
    main()
