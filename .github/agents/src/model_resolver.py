"""Model resolver implementing per-subagent model precedence and policy checks.

Precedence (highest -> lowest):
 1. subagent_assigned_model (spawn payload `model`)
 2. parent_selected_model (parentContext.selected_model)
 3. cycle_selected_model (parentContext.cycle_selected_model)
 4. global_default_model

The resolver returns a dict with keys: model, source, fallback_used (bool), fallback_reason (optional).
"""
from typing import Dict, Any, Optional


TIERS_ORDER = {"economy": 0, "balanced": 1, "frontier": 2}


def is_allowed_model(model_id: str, model_catalog: Dict[str, Dict[str, Any]], minimum_tier: Optional[str]) -> bool:
    if model_id not in model_catalog:
        return False
    if minimum_tier is None:
        return True
    model_tier = model_catalog[model_id].get("tier")
    if model_tier not in TIERS_ORDER or minimum_tier not in TIERS_ORDER:
        return False
    return TIERS_ORDER[model_tier] >= TIERS_ORDER[minimum_tier]


def resolve_model_for_subagent(spawn_payload: Dict[str, Any], parent_context: Dict[str, Any],
                               model_catalog: Dict[str, Dict[str, Any]], global_default_model: str,
                               minimum_tier: Optional[str] = None) -> Dict[str, Any]:
    """Resolve model for a subagent using precedence and policy checks.

    spawn_payload: may contain `model` (string) as explicit override.
    parent_context: may contain `selected_model` and `cycle_selected_model`.
    model_catalog: mapping model_id -> properties (must include `tier`).
    global_default_model: fallback model id.
    minimum_tier: optional enforced minimum tier string.
    """

    result = {
        "model": None,
        "source": None,
        "fallback_used": False,
        "fallback_reason": None,
    }

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

    # 2. Parent selected model
    parent_selected = parent_context.get("selected_model")
    if parent_selected and is_allowed_model(parent_selected, model_catalog, minimum_tier):
        result.update({"model": parent_selected, "source": "parent_selected_model"})
        return result

    # 3. Cycle selected model
    cycle_model = parent_context.get("cycle_selected_model")
    if cycle_model and is_allowed_model(cycle_model, model_catalog, minimum_tier):
        result.update({"model": cycle_model, "source": "cycle_selected_model"})
        return result

    # 4. Global default
    if global_default_model and is_allowed_model(global_default_model, model_catalog, minimum_tier):
        result.update({"model": global_default_model, "source": "global_default_model"})
        return result

    # If we reach here, nothing was allowed — return blocked-style response
    result.update({
        "model": None,
        "source": "none_available",
    })
    if not result["fallback_reason"]:
        result["fallback_reason"] = "no eligible model met policy constraints"
    return result
