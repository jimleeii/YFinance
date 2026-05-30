"""Model resolver implementing per-subagent model precedence and policy checks.

Precedence (highest -> lowest):
 1. subagent_assigned_model (spawn payload `model`)
 2. explicit context override (`preferred_model` / `model_hint`)
 3. context best-fit model (subagent/task-aware tier selection)
 4. parent_selected_model (parentContext.selected_model)
 5. cycle_selected_model (parentContext.cycle_selected_model)
 6. global_default_model

The resolver returns a dict with keys: model, source, fallback_used (bool), fallback_reason (optional).
"""
from typing import Dict, Any, Optional


TIERS_ORDER = {"economy": 0, "balanced": 1, "frontier": 2}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return ""


def _normalize_tier(value: Any) -> Optional[str]:
    tier = _normalize_text(value)
    if tier in TIERS_ORDER:
        return tier
    if tier in {"high", "highest", "premium"}:
        return "frontier"
    if tier in {"medium", "mid", "default"}:
        return "balanced"
    if tier in {"low", "cheap", "cheapest"}:
        return "economy"
    return None


def is_allowed_model(model_id: str, model_catalog: Dict[str, Dict[str, Any]], minimum_tier: Optional[str]) -> bool:
    if model_id not in model_catalog:
        return False
    if minimum_tier is None:
        return True
    model_tier = model_catalog[model_id].get("tier")
    if model_tier not in TIERS_ORDER or minimum_tier not in TIERS_ORDER:
        return False
    return TIERS_ORDER[model_tier] >= TIERS_ORDER[minimum_tier]


def _preferred_tier_from_context(spawn_payload: Dict[str, Any], parent_context: Dict[str, Any]) -> Optional[str]:
    explicit_tier = _normalize_tier(
        _first_text(
            spawn_payload.get("desired_tier"),
            spawn_payload.get("preferred_tier"),
            parent_context.get("desired_tier"),
            parent_context.get("preferred_tier"),
        )
    )
    if explicit_tier:
        return explicit_tier

    subagent = _normalize_text(
        _first_text(
            spawn_payload.get("name"),
            spawn_payload.get("subagent"),
            parent_context.get("subagent"),
        )
    )
    task_type = _normalize_text(
        _first_text(
            spawn_payload.get("task_type"),
            parent_context.get("task_type"),
        )
    )
    criticality = _normalize_text(
        _first_text(
            spawn_payload.get("criticality"),
            parent_context.get("criticality"),
        )
    )

    if any(token in task_type for token in ("log", "conversion", "intake", "parsing", "extract")):
        return "economy"
    if criticality in {"p0", "p1"}:
        return "frontier"
    if subagent in {"software architect", "code reviewer"}:
        return "frontier"
    if criticality == "p2" or subagent == "senior developer" or any(
        token in task_type for token in ("implementation", "refactor", "optimization", "debug", "fix", "feature")
    ):
        return "balanced"
    if criticality == "p3":
        return "economy"
    return None


def _select_model_by_tier(
    model_catalog: Dict[str, Dict[str, Any]],
    preferred_tier: Optional[str],
    minimum_tier: Optional[str],
) -> Optional[str]:
    allowed_models = []
    for model_id, model_data in model_catalog.items():
        model_tier = model_data.get("tier")
        if model_tier not in TIERS_ORDER:
            continue
        if not is_allowed_model(model_id, model_catalog, minimum_tier):
            continue
        allowed_models.append((model_id, TIERS_ORDER[model_tier]))

    if not allowed_models:
        return None

    allowed_models.sort(key=lambda item: (item[1], item[0].lower()))

    if preferred_tier in TIERS_ORDER:
        preferred_rank = TIERS_ORDER[preferred_tier]
        matching = [item for item in allowed_models if item[1] >= preferred_rank]
        if matching:
            return matching[0][0]

    return allowed_models[-1][0]


def resolve_model_for_subagent(spawn_payload: Dict[str, Any], parent_context: Dict[str, Any],
                               model_catalog: Dict[str, Dict[str, Any]], global_default_model: str,
                               minimum_tier: Optional[str] = None,
                               contract_score: Optional[int] = None) -> Dict[str, Any]:
    """Resolve model for a subagent using precedence and policy checks.

    spawn_payload: may contain `model` (string) as explicit override.
    parent_context: may contain `selected_model` and `cycle_selected_model`.
    model_catalog: mapping model_id -> properties (must include `tier`).
    global_default_model: fallback model id.
    minimum_tier: optional enforced minimum tier string.
    contract_score: optional 0-100 score from score.py; if below 70 the minimum
        tier is escalated to 'frontier' to improve response quality on retry.
    """

    result = {
        "model": None,
        "source": None,
        "fallback_used": False,
        "fallback_reason": None,
        "contract_score": contract_score,
    }

    # Escalate minimum tier when the previous response scored below threshold
    _SCORE_THRESHOLD = 70
    if contract_score is not None and contract_score < _SCORE_THRESHOLD:
        frontier_rank = TIERS_ORDER["frontier"]
        current_rank = TIERS_ORDER.get(minimum_tier, -1)
        if current_rank < frontier_rank:
            minimum_tier = "frontier"
        result["fallback_used"] = True
        result["fallback_reason"] = (
            f"contract_score={contract_score} below threshold {_SCORE_THRESHOLD}; "
            "minimum_tier escalated to frontier"
        )

    requested = spawn_payload.get("model")

    # 1. Try explicit spawn payload model
    if requested:
        if is_allowed_model(requested, model_catalog, minimum_tier):
            result.update({"model": requested, "source": "subagent_assigned_model"})
            return result
        else:
            # requested model not allowed — record fallback and continue
            result["fallback_used"] = True
            result["fallback_reason"] = f"requested model '{requested}' unavailable or below minimum_tier"

    # 2. Explicit context override
    preferred_model = _first_text(
        spawn_payload.get("preferred_model"),
        spawn_payload.get("model_hint"),
        parent_context.get("preferred_model"),
        parent_context.get("model_hint"),
    )
    if preferred_model and is_allowed_model(preferred_model, model_catalog, minimum_tier):
        result.update({"model": preferred_model, "source": "preferred_model"})
        return result

    # 3. Parent selected model (inherits from parent context)
    parent_selected = parent_context.get("selected_model")
    if parent_selected and is_allowed_model(parent_selected, model_catalog, minimum_tier):
        result.update({"model": parent_selected, "source": "parent_selected_model"})
        return result

    # 4. Cycle selected model (per-cycle override)
    cycle_model = parent_context.get("cycle_selected_model")
    if cycle_model and is_allowed_model(cycle_model, model_catalog, minimum_tier):
        result.update({"model": cycle_model, "source": "cycle_selected_model"})
        return result

    # 5. Global default
    if global_default_model and is_allowed_model(global_default_model, model_catalog, minimum_tier):
        result.update({"model": global_default_model, "source": "global_default_model"})
        return result

    # 6. Subagent/task-aware best fit (fallback when no higher-priority model exists)
    preferred_tier = _preferred_tier_from_context(spawn_payload, parent_context)
    best_fit_model = _select_model_by_tier(model_catalog, preferred_tier, minimum_tier)
    if best_fit_model:
        result.update({"model": best_fit_model, "source": "context_best_fit_model"})
        if preferred_tier:
            result["preferred_tier"] = preferred_tier
        return result

    # If we reach here, nothing was allowed — return blocked-style response
    result.update({
        "model": None,
        "source": "none_available",
    })
    if not result["fallback_reason"]:
        result["fallback_reason"] = "no eligible model met policy constraints"
    return result
