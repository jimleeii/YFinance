"""Programmatic model discovery for the Orchestrator.

This module consolidates model sources from:

- GitHub Copilot Chat / Copilot CLI help output
- Local Copilot session-state logs (selected/current model history)
- Optional provider SDKs (OpenAI, Anthropic, Hugging Face)
- Orchestrator cycle telemetry (quality / latency / cost)

The result is a ``model_catalog`` mapping per ``rules/Model.Policy.md``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.model_telemetry import collect_cycle_model_telemetry


DEFAULT_MODEL_ID = "gpt-5.4-mini"

_TIER_PRIORS: Dict[str, Dict[str, int]] = {
    "frontier": {"quality_score": 90, "latency_score": 65, "cost_score": 35},
    "balanced": {"quality_score": 75, "latency_score": 75, "cost_score": 60},
    "economy": {"quality_score": 60, "latency_score": 85, "cost_score": 85},
}


@dataclass(frozen=True)
class ModelCatalogBundle:
    catalog: Dict[str, Dict[str, Any]]
    default_model: Optional[str]
    sources: Dict[str, Any]


def _normalize_model_id(name: Any) -> str:
    return str(name).strip().replace(" ", "-").lower()


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


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _heuristic_tier(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("opus", "sonnet-4.6", "sonnet-4.5", "sonnet-4", "gpt-5.4", "gpt-5.3", "gpt-5.2", "gpt-5.1", "gemini-3-pro")):
        return "frontier"
    if any(k in n for k in ("mini", "haiku", "flash", "4o", "4.1", "4.0")):
        return "balanced"
    if any(k in n for k in ("econ", "economy", "small", "tiny", "nano")):
        return "economy"
    return "balanced"


def _tier_prior_scores(tier: str) -> Dict[str, int]:
    return dict(_TIER_PRIORS.get(tier, _TIER_PRIORS["balanced"]))


def _new_model_entry(
    model_id: str,
    *,
    tier: Optional[str] = None,
    source: Optional[str] = None,
    context_window: Optional[int] = None,
    tool_calling: Optional[bool] = None,
) -> Dict[str, Any]:
    resolved_tier = tier or _heuristic_tier(model_id)
    prior_scores = _tier_prior_scores(resolved_tier)
    entry: Dict[str, Any] = {
        "tier": resolved_tier,
        "quality_score": prior_scores["quality_score"],
        "latency_score": prior_scores["latency_score"],
        "cost_score": prior_scores["cost_score"],
        "quality_score_source": "tier-prior",
        "latency_score_source": "tier-prior",
        "cost_score_source": "tier-prior",
        "context_window": context_window,
        "tool_calling": bool(tool_calling) if tool_calling is not None else False,
        "telemetry_partial": True,
        "sources": [],
        "observed_in_copilot_chat": False,
    }
    if source:
        entry["sources"].append(source)
    return entry


def _merge_text_list(*sources: Any) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for source in sources:
        if source is None:
            continue
        if isinstance(source, str):
            items = [item.strip() for item in source.split(",")]
        elif isinstance(source, (list, tuple, set)):
            items = [str(item).strip() for item in source]
        else:
            items = [str(source).strip()]
        for item in items:
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _merge_entry(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in update.items():
        if key == "sources":
            merged[key] = _merge_text_list(merged.get(key), value)
            continue
        if key == "observed_in_copilot_chat":
            merged[key] = bool(merged.get(key)) or bool(value)
            continue
        if key.endswith("_score") and value is not None:
            merged[key] = value
            continue
        if key.endswith("_source") and value is not None:
            merged[key] = value
            continue
        if merged.get(key) is None and value is not None:
            merged[key] = value
    return merged


def merge_catalogs(*cats: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for catalog in cats:
        if not catalog:
            continue
        for model_id, entry in catalog.items():
            if model_id in out:
                out[model_id] = _merge_entry(out[model_id], entry)
            else:
                out[model_id] = dict(entry or {})
    return out


def _discover_openai_models() -> Dict[str, Dict[str, Any]]:
    try:
        import openai  # type: ignore
    except Exception:
        return {}

    catalog: Dict[str, Dict[str, Any]] = {}
    try:
        models: Iterable[Any] = []
        if hasattr(openai, "Model") and hasattr(openai.Model, "list"):
            res = openai.Model.list()
            models = getattr(res, "data", res)
        elif hasattr(openai, "models") and hasattr(openai.models, "list"):
            res = openai.models.list()
            models = getattr(res, "data", res)

        for model in models:
            name = model.get("id") if isinstance(model, dict) else getattr(model, "id", str(model))
            model_id = _normalize_model_id(name)
            if not model_id:
                continue
            catalog[model_id] = _new_model_entry(
                model_id,
                tier=_heuristic_tier(model_id),
                source="openai-sdk",
                context_window=_coerce_int(
                    model.get("context_window") if isinstance(model, dict) else getattr(model, "context_window", None)
                ),
                tool_calling=False,
            )
    except Exception:
        return {}
    return catalog


def _discover_huggingface_models() -> Dict[str, Dict[str, Any]]:
    try:
        from huggingface_hub import list_models  # type: ignore
    except Exception:
        return {}

    catalog: Dict[str, Dict[str, Any]] = {}
    try:
        for model in list_models(batch_size=100):
            name = model.modelId if hasattr(model, "modelId") else model.get("modelId") if isinstance(model, dict) else str(model)
            model_id = _normalize_model_id(name)
            if not model_id:
                continue
            catalog[model_id] = _new_model_entry(
                model_id,
                tier=_heuristic_tier(model_id),
                source="huggingface-hub",
                tool_calling=False,
            )
    except Exception:
        return {}
    return catalog


def _discover_anthropic_models() -> Dict[str, Dict[str, Any]]:
    try:
        import anthropic  # type: ignore
    except Exception:
        return {}

    catalog: Dict[str, Dict[str, Any]] = {}
    try:
        client = None
        if hasattr(anthropic, "Anthropic"):
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                client = anthropic.Anthropic(api_key=api_key)

        if client and hasattr(client, "models") and hasattr(client.models, "list"):
            res = client.models.list()
            for model in getattr(res, "data", res):
                name = model.get("id") if isinstance(model, dict) else getattr(model, "id", str(model))
                model_id = _normalize_model_id(name)
                if not model_id:
                    continue
                catalog[model_id] = _new_model_entry(
                    model_id,
                    tier=_heuristic_tier(model_id),
                    source="anthropic-sdk",
                    tool_calling=False,
                )
    except Exception:
        return {}
    return catalog


def _find_copilot_cli_script(copilot_root: Optional[Path | str] = None) -> Optional[Path]:
    candidates: List[Path] = []
    if copilot_root is not None:
        base = Path(copilot_root).expanduser().resolve(strict=False)
        candidates.extend(
            [
                base / "copilotCli" / "copilot.ps1",
                base / "copilot.ps1",
                base / "copilot",
            ]
        )

    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    candidates.extend(
        [
            appdata / "Code" / "User" / "globalStorage" / "github.copilot-chat" / "copilotCli" / "copilot.ps1",
            Path.home() / ".copilot" / "copilotCli" / "copilot.ps1",
            Path.home() / ".copilot" / "copilot.ps1",
            Path.home() / ".copilot" / "bin" / "copilot",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _run_copilot_help_config(copilot_root: Optional[Path | str] = None) -> str:
    script = _find_copilot_cli_script(copilot_root)
    if script is None:
        return ""

    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        return ""

    if script.suffix.lower() == ".ps1":
        command = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "help", "config"]
    else:
        command = [str(script), "help", "config"]

    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except Exception:
        return ""

    output = completed.stdout or completed.stderr or ""
    return output.strip()


def _parse_copilot_help_config(help_text: str) -> List[str]:
    models: List[str] = []
    in_model_section = False

    for raw_line in help_text.splitlines():
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        lower = stripped.lower()

        if not in_model_section:
            if lower.startswith("model:"):
                in_model_section = True
            continue

        if stripped and re.match(r"^[a-z0-9_.-]+:\s*$", stripped, flags=re.IGNORECASE) and not lower.startswith("\""):
            break

        match = re.match(r'^\s*-\s*"([^"]+)"\s*$', line)
        if match:
            model_id = _normalize_model_id(match.group(1))
            if model_id and model_id != "auto":
                models.append(model_id)

    return models


def _discover_copilot_session_models(copilot_root: Optional[Path | str] = None) -> Tuple[List[str], Dict[str, Any]]:
    session_roots: List[Path] = []
    if copilot_root is not None:
        base = Path(copilot_root).expanduser().resolve(strict=False)
        session_roots.append(base / "session-state")

    session_roots.append(Path.home() / ".copilot" / "session-state")
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    session_roots.append(appdata / "Code" / "User" / "globalStorage" / "github.copilot-chat" / "session-state")

    observed: set[str] = set()
    selected_models: Counter[str] = Counter()
    current_models: Counter[str] = Counter()
    session_count = 0
    latest_selected_model = ""
    latest_current_model = ""
    latest_timestamp: Optional[str] = None

    for root in session_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("events.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
            except Exception:
                continue

            for raw_line in lines:
                text = raw_line.strip()
                if not text:
                    continue

                try:
                    event = json.loads(text)
                except Exception:
                    continue

                if not isinstance(event, dict):
                    continue

                event_type = _coerce_text(event.get("type"))
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                timestamp = _coerce_text(event.get("timestamp"))
                if timestamp and (latest_timestamp is None or timestamp >= latest_timestamp):
                    latest_timestamp = timestamp

                if event_type == "session.start":
                    session_count += 1
                    selected = _normalize_model_id(_first_text(data.get("selectedModel"), data.get("currentModel")))
                    if selected:
                        observed.add(selected)
                        selected_models[selected] += 1
                        latest_selected_model = selected
                elif event_type == "session.resume":
                    selected = _normalize_model_id(_first_text(data.get("selectedModel"), data.get("currentModel")))
                    if selected:
                        observed.add(selected)
                        selected_models[selected] += 1
                        latest_selected_model = selected
                elif event_type == "session.model_change":
                    changed = _normalize_model_id(_first_text(data.get("newModel")))
                    if changed:
                        observed.add(changed)
                        selected_models[changed] += 1
                        latest_selected_model = changed
                elif event_type == "session.shutdown":
                    current = _normalize_model_id(_first_text(data.get("currentModel")))
                    if current:
                        observed.add(current)
                        current_models[current] += 1
                        latest_current_model = current
                    metrics = data.get("modelMetrics") if isinstance(data.get("modelMetrics"), dict) else {}
                    for model_name in metrics.keys():
                        normalized = _normalize_model_id(model_name)
                        if normalized:
                            observed.add(normalized)

    source_summary = {
        "session_count": session_count,
        "observed_models": sorted(observed),
        "selected_model": latest_selected_model or None,
        "current_model": latest_current_model or None,
        "selected_model_counts": dict(selected_models),
        "current_model_counts": dict(current_models),
        "last_event_timestamp": latest_timestamp,
    }
    return sorted(observed), source_summary


def _apply_telemetry(catalog: Dict[str, Dict[str, Any]], telemetry: Dict[str, Dict[str, Any]]) -> None:
    for model_id, metrics in telemetry.items():
        entry = catalog.get(model_id)
        if entry is None:
            entry = _new_model_entry(model_id, source="orchestrator-telemetry")
            catalog[model_id] = entry
        else:
            entry["sources"] = _merge_text_list(entry.get("sources"), "orchestrator-telemetry")

        for score_key, source_key in (
            ("quality_score", "quality_score_source"),
            ("latency_score", "latency_score_source"),
            ("cost_score", "cost_score_source"),
        ):
            value = metrics.get(score_key)
            if value is not None:
                entry[score_key] = value
                entry[source_key] = metrics.get(source_key) or "orchestrator-telemetry"

        for key in (
            "quality_sample_count",
            "latency_sample_count",
            "cost_sample_count",
            "sample_count",
            "raw_latency_ms",
            "raw_cost_units",
            "tool_call_success_rate",
            "tool_call_reliability",
            "telemetry_partial",
        ):
            if key in metrics and metrics[key] is not None:
                entry[key] = metrics[key]


def _finalize_catalog(catalog: Dict[str, Dict[str, Any]]) -> None:
    for model_id, entry in catalog.items():
        tier = _coerce_text(entry.get("tier")) or _heuristic_tier(model_id)
        prior_scores = _tier_prior_scores(tier)
        for score_key, source_key in (
            ("quality_score", "quality_score_source"),
            ("latency_score", "latency_score_source"),
            ("cost_score", "cost_score_source"),
        ):
            if entry.get(score_key) is None:
                entry[score_key] = prior_scores[score_key]
                entry[source_key] = "tier-prior"
            elif entry.get(source_key) is None:
                entry[source_key] = "computed"

        entry["telemetry_partial"] = any(
            entry.get(source_key) in {None, "tier-prior", "provider-heuristic"}
            for source_key in ("quality_score_source", "latency_score_source", "cost_score_source")
        )
        entry["sources"] = _merge_text_list(entry.get("sources"))


def _default_model_from_catalog(catalog: Dict[str, Dict[str, Any]], sources: Dict[str, Any]) -> Optional[str]:
    env_model = _normalize_model_id(os.environ.get("COPILOT_MODEL")) if os.environ.get("COPILOT_MODEL") else ""
    if env_model and env_model in catalog:
        return env_model

    copilot_sources = sources.get("copilot") if isinstance(sources.get("copilot"), dict) else {}
    for candidate in _merge_text_list(
        copilot_sources.get("current_model"),
        copilot_sources.get("selected_model"),
    ):
        normalized = _normalize_model_id(candidate)
        if normalized in catalog:
            return normalized

    if DEFAULT_MODEL_ID in catalog:
        return DEFAULT_MODEL_ID

    if not catalog:
        return None

    tier_priority = {"frontier": 3, "balanced": 2, "economy": 1}

    def sort_key(item: Tuple[str, Dict[str, Any]]) -> Tuple[int, int, int, int, str]:
        model_id, entry = item
        tier_score = tier_priority.get(_coerce_text(entry.get("tier")), 0)
        quality = _coerce_int(entry.get("quality_score")) or 0
        latency = _coerce_int(entry.get("latency_score")) or 0
        cost = _coerce_int(entry.get("cost_score")) or 0
        return (tier_score, quality, latency, cost, model_id)

    return max(catalog.items(), key=sort_key)[0]


def discover_model_catalog_bundle(
    *,
    repo_root: Optional[Path | str] = None,
    copilot_root: Optional[Path | str] = None,
    providers: Optional[Sequence[str]] = None,
    telemetry_window_days: int = 14,
    help_config_text: Optional[str] = None,
) -> ModelCatalogBundle:
    """Discover a full model catalog bundle.

    The returned bundle includes the catalog itself, the chosen default model,
    and a small source summary for debugging and tests.
    """

    selected_providers = [provider.strip().lower() for provider in (providers or ("copilot", "openai", "anthropic", "huggingface")) if provider and provider.strip()]

    catalog: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, Any] = {}

    if "copilot" in selected_providers:
        copilot_catalog, copilot_sources = discover_copilot_models(
            copilot_root=copilot_root,
            help_config_text=help_config_text,
        )
        catalog = merge_catalogs(catalog, copilot_catalog)
        sources["copilot"] = copilot_sources

    if "openai" in selected_providers:
        openai_catalog = _discover_openai_models()
        catalog = merge_catalogs(catalog, openai_catalog)
        sources["openai"] = {"model_count": len(openai_catalog)}

    if "anthropic" in selected_providers:
        anthropic_catalog = _discover_anthropic_models()
        catalog = merge_catalogs(catalog, anthropic_catalog)
        sources["anthropic"] = {"model_count": len(anthropic_catalog)}

    if "huggingface" in selected_providers:
        hf_catalog = _discover_huggingface_models()
        catalog = merge_catalogs(catalog, hf_catalog)
        sources["huggingface"] = {"model_count": len(hf_catalog)}

    telemetry = collect_cycle_model_telemetry(repo_root=repo_root, window_days=telemetry_window_days)
    if telemetry:
        _apply_telemetry(catalog, telemetry)
        sources["orchestrator_telemetry"] = {
            "model_count": len(telemetry),
            "sample_count": sum(int(entry.get("sample_count") or 0) for entry in telemetry.values()),
        }

    if not catalog:
        fallback = _new_model_entry(DEFAULT_MODEL_ID, source="fallback")
        fallback["telemetry_partial"] = True
        catalog[DEFAULT_MODEL_ID] = fallback

    _finalize_catalog(catalog)
    default_model = _default_model_from_catalog(catalog, sources)

    return ModelCatalogBundle(catalog=catalog, default_model=default_model, sources=sources)


def discover_copilot_models(
    *,
    copilot_root: Optional[Path | str] = None,
    help_config_text: Optional[str] = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Discover Copilot Chat models from CLI help and session-state logs."""

    text = help_config_text if help_config_text is not None else _run_copilot_help_config(copilot_root)
    cli_models = _parse_copilot_help_config(text)
    session_models, session_sources = _discover_copilot_session_models(copilot_root)

    catalog: Dict[str, Dict[str, Any]] = {}
    for model_id in sorted(set(cli_models) | set(session_models)):
        if not model_id:
            continue
        observed = model_id in session_models
        entry = _new_model_entry(
            model_id,
            tier=_heuristic_tier(model_id),
            source="copilot-cli" if model_id in cli_models else "copilot-session-state",
            tool_calling=True,
        )
        entry["observed_in_copilot_chat"] = observed
        if observed:
            entry["sources"] = _merge_text_list(entry.get("sources"), "copilot-session-state")
        catalog[model_id] = entry

    source_summary = {
        "cli_model_count": len(cli_models),
        "cli_models": cli_models,
        "observed_models": session_sources.get("observed_models", []),
        "session_count": session_sources.get("session_count", 0),
        "selected_model": session_sources.get("selected_model"),
        "current_model": session_sources.get("current_model"),
        "selected_model_counts": session_sources.get("selected_model_counts", {}),
        "current_model_counts": session_sources.get("current_model_counts", {}),
        "last_event_timestamp": session_sources.get("last_event_timestamp"),
    }
    return catalog, source_summary


def discover_model_catalog(
    *,
    repo_root: Optional[Path | str] = None,
    copilot_root: Optional[Path | str] = None,
    providers: Optional[Sequence[str]] = None,
    telemetry_window_days: int = 14,
    help_config_text: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    return discover_model_catalog_bundle(
        repo_root=repo_root,
        copilot_root=copilot_root,
        providers=providers,
        telemetry_window_days=telemetry_window_days,
        help_config_text=help_config_text,
    ).catalog


def load_model_catalog_bundle(
    *,
    repo_root: Optional[Path | str] = None,
    copilot_root: Optional[Path | str] = None,
    providers: Optional[Sequence[str]] = None,
    telemetry_window_days: int = 14,
    help_config_text: Optional[str] = None,
    refresh: bool = False,
) -> ModelCatalogBundle:
    # The bundle is cheap enough to build on demand; refresh is kept for API
    # symmetry and future caching hooks.
    return discover_model_catalog_bundle(
        repo_root=repo_root,
        copilot_root=copilot_root,
        providers=providers,
        telemetry_window_days=telemetry_window_days,
        help_config_text=help_config_text,
    )


def load_model_catalog(
    *,
    repo_root: Optional[Path | str] = None,
    copilot_root: Optional[Path | str] = None,
    providers: Optional[Sequence[str]] = None,
    telemetry_window_days: int = 14,
    help_config_text: Optional[str] = None,
    refresh: bool = False,
) -> Dict[str, Dict[str, Any]]:
    return load_model_catalog_bundle(
        repo_root=repo_root,
        copilot_root=copilot_root,
        providers=providers,
        telemetry_window_days=telemetry_window_days,
        help_config_text=help_config_text,
        refresh=refresh,
    ).catalog


def save_model_catalog(catalog: Dict[str, Dict[str, Any]], out_path: Path | str) -> Path:
    path = Path(out_path).expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def discover_models(
    providers: Optional[Sequence[str]] = None,
    repo_root: Optional[Path | str] = None,
    copilot_root: Optional[Path | str] = None,
    telemetry_window_days: int = 14,
    help_config_text: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Backward-compatible alias for the original discovery entry point."""

    return discover_model_catalog(
        repo_root=repo_root,
        copilot_root=copilot_root,
        providers=providers,
        telemetry_window_days=telemetry_window_days,
        help_config_text=help_config_text,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Discover available LLM models and emit a model_catalog JSON")
    parser.add_argument("--out", help="Write model_catalog JSON to this path", default=None)
    parser.add_argument(
        "--providers",
        help="Comma-separated providers to probe (copilot,openai,anthropic,huggingface)",
        default=None,
    )
    parser.add_argument("--repo-root", help="Workspace or repo root for telemetry discovery", default=None)
    parser.add_argument("--copilot-root", help="Copilot config root", default=None)
    parser.add_argument("--telemetry-window-days", type=int, default=14)
    args = parser.parse_args(argv)

    providers = [provider.strip() for provider in args.providers.split(",")] if args.providers else None
    catalog = discover_model_catalog(
        repo_root=args.repo_root,
        copilot_root=args.copilot_root,
        providers=providers,
        telemetry_window_days=args.telemetry_window_days,
    )

    if args.out:
        path = save_model_catalog(catalog, args.out)
        print(f"Wrote model_catalog to {path}")
        return 0

    print(json.dumps(catalog, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ModelCatalogBundle",
    "discover_copilot_models",
    "discover_model_catalog",
    "discover_model_catalog_bundle",
    "discover_models",
    "load_model_catalog",
    "load_model_catalog_bundle",
    "merge_catalogs",
    "main",
    "save_model_catalog",
]
