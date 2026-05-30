#!/usr/bin/env python3
"""Run `hooks.log_hooks.log_cycle` from hook runner JSON configs.

This small CLI is intended to be invoked by repository hook runners
(e.g. `.github/hooks/*.json`) as a command. It maps simple arguments,
structured metadata, and optional model-resolution inputs to `log_cycle()`
so hooks can persist logs at pre/mid/post phases without shelling out to
the markdown CLI directly.
"""
from __future__ import annotations

import argparse
import logging
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


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


def _apply_model_resolution(metadata: Dict[str, Any], model_resolution: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(model_resolution, dict):
        return None

    normalized = dict(model_resolution)
    resolved_model = _first_text(normalized.get("model"), normalized.get("selected_model"))
    if resolved_model:
        metadata["selected_model"] = resolved_model
        metadata["cycle_selected_model"] = resolved_model
        metadata["model"] = resolved_model

    resolved_source = _first_text(normalized.get("source"))
    if resolved_source:
        metadata["selected_model_source"] = resolved_source

    if normalized.get("fallback_used") is not None:
        metadata["fallback_used"] = normalized["fallback_used"]

    fallback_reason = _first_text(normalized.get("fallback_reason"))
    if fallback_reason:
        metadata["fallback_reason"] = fallback_reason

    metadata["model_resolution"] = normalized
    return normalized


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


def _build_dispatch_metadata(
    metadata: Optional[Dict[str, Any]] = None,
    subagent_name: Optional[str] = None,
    spawn_payload: Optional[Dict[str, Any]] = None,
    model_catalog: Optional[Dict[str, Dict[str, Any]]] = None,
    global_default_model: Optional[str] = None,
    minimum_tier: Optional[str] = None,
) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    merged = dict(metadata or {})

    if global_default_model:
        merged.setdefault("global_default_model", global_default_model)

    inferred_subagent = _first_text(
        subagent_name,
        merged.get("subagent"),
        merged.get("subagents"),
        spawn_payload.get("name") if spawn_payload else None,
        spawn_payload.get("subagent") if spawn_payload else None,
    )
    if inferred_subagent:
        merged["subagent"] = inferred_subagent
        merged["subagents"] = _merge_unique_text_lists(merged.get("subagents"), inferred_subagent)

    model_resolution = _apply_model_resolution(merged, merged.get("model_resolution"))
    if spawn_payload and model_catalog:
        try:
            from src.model_resolver import resolve_model_for_subagent
        except Exception:
            resolve_model_for_subagent = None

        if resolve_model_for_subagent:
            model_resolution = resolve_model_for_subagent(
                spawn_payload=spawn_payload,
                parent_context=merged,
                model_catalog=model_catalog,
                global_default_model=global_default_model or "",
                minimum_tier=minimum_tier,
            )
            model_resolution = _apply_model_resolution(merged, model_resolution)

    if global_default_model and not merged.get("selected_model"):
        merged.setdefault("selected_model", global_default_model)
        merged.setdefault("cycle_selected_model", global_default_model)
        merged.setdefault("model", global_default_model)

    return merged, model_resolution


def find_repo_root(start: Optional[Path] = None) -> Path:
    p = Path(start or __file__).resolve()
    cur = p if p.is_dir() else p.parent
    markers = ("AGENTS.md", ".git")
    for _ in range(20):
        for m in markers:
            if (cur / m).exists():
                return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run orchestrator log hook runner.",
        fromfile_prefix_chars="@",
    )
    parser.add_argument("--phase", choices=["pre", "mid", "post"], default="pre", help="Hook phase")
    parser.add_argument("--dispatch-path", default="direct", help="Dispatch path (direct/single-agent/multi-agent)")
    parser.add_argument("--summary", default="", help="Short summary message")
    parser.add_argument("--skills", help="Comma-separated skills list", default=None)
    parser.add_argument("--transcript-file", help="Path to transcript file to include", default=None)
    parser.add_argument("--author", help="Author name", default=None)
    parser.add_argument("--preview", action="store_true", help="Run in preview mode (no writes)")
    parser.add_argument("--force-persist", action="store_true", help="Force full persist")
    parser.add_argument("--tags", help="Comma-separated tags", default=None)
    parser.add_argument("--event-flags", help="JSON string of event flags (e.g. '{\"failure_detected\": true}')", default=None)
    parser.add_argument("--event-flags-file", help="Path to a JSON file containing event flags", default=None)
    parser.add_argument("--metadata", help="JSON string of structured metadata to carry into logs", default=None)
    parser.add_argument("--subagent-name", help="Subagent name to record in metadata", default=None)
    parser.add_argument("--spawn-payload", help="JSON string describing the dispatch spawn payload", default=None)
    parser.add_argument("--model-catalog", help="JSON string of allowed models and tiers", default=None)
    parser.add_argument("--global-default-model", help="Global default model to use for resolution", default=None)
    parser.add_argument("--minimum-tier", help="Minimum allowed model tier", default=None)
    parser.add_argument("--prompt-command", help="Optional prompt command to run (e.g. /runbook)", default=None)
    parser.add_argument("--root", help="Repository root (for testing)", default=None)
    args = parser.parse_args()

    workspace_root = Path(args.root) if args.root else find_repo_root(Path(__file__))
    orchestrator_root = workspace_root / ".github" / "agents" / "Orchestrator"
    # Ensure the Orchestrator package root is on sys.path so `hooks` can be imported reliably
    sys.path.insert(0, str(orchestrator_root))

    try:
        from hooks.log_hooks import log_cycle, normalize_checkpoint_metadata
    except Exception as e:  # pragma: no cover - import/runtime guard
        print("Failed to import hooks.log_hooks:", e, file=sys.stderr)
        return 2

    skills = [s for s in (args.skills.split(",") if args.skills else []) if s]
    transcript = None
    if args.transcript_file:
        tf = Path(args.transcript_file)
        if tf.exists():
            transcript = tf.read_text(encoding="utf-8")
        else:
            print(f"Transcript file not found: {tf}", file=sys.stderr)

    # Base event flags always include the hook phase. Additional flags can be supplied
    # via `--event-flags` (JSON string) or `--event-flags-file` (JSON file).
    event_flags = {"hook_phase": args.phase}
    if args.event_flags:
        try:
            parsed = json.loads(args.event_flags)
            if isinstance(parsed, dict):
                event_flags.update(parsed)
        except Exception as e:  # pragma: no cover - user input parsing
            print("Failed to parse --event-flags JSON:", e, file=sys.stderr)
            return 4
    if args.event_flags_file:
        try:
            p = Path(args.event_flags_file)
            if p.exists():
                parsed = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    event_flags.update(parsed)
            else:
                print(f"Event flags file not found: {p}", file=sys.stderr)
        except Exception as e:  # pragma: no cover - user input parsing
            print("Failed to read/parse --event-flags-file:", e, file=sys.stderr)
            return 5

    try:
        metadata = _load_json_object(args.metadata, "--metadata")
        spawn_payload = _load_json_object(args.spawn_payload, "--spawn-payload")
        model_catalog = _load_json_object(args.model_catalog, "--model-catalog")
        # If no catalog supplied, attempt to load a persisted discovery result
        if not model_catalog:
            try:
                default_catalog = workspace_root / "skills" / "model_catalog.json"
                if default_catalog.exists():
                    model_catalog = json.loads(default_catalog.read_text(encoding="utf-8"))
                    logger.debug("Loaded model_catalog from %s", default_catalog)
                else:
                    try:
                        from src.model_discovery import load_model_catalog_bundle
                    except Exception:
                        from model_discovery import load_model_catalog_bundle  # type: ignore

                    bundle = load_model_catalog_bundle(repo_root=workspace_root)
                    model_catalog = bundle.catalog
                    if not args.global_default_model and bundle.default_model:
                        args.global_default_model = bundle.default_model
            except Exception:
                # best-effort only
                model_catalog = {}
    except ValueError as e:  # pragma: no cover - user input parsing
        print(e, file=sys.stderr)
        return 6

    metadata, model_resolution = _build_dispatch_metadata(
        metadata=metadata,
        subagent_name=args.subagent_name,
        spawn_payload=spawn_payload,
        model_catalog=model_catalog,
        global_default_model=args.global_default_model,
        minimum_tier=args.minimum_tier,
    )

    if model_resolution:
        metadata["model_resolution"] = model_resolution

    metadata = normalize_checkpoint_metadata(
        summary=args.summary,
        metadata=metadata,
        event_flags=event_flags,
        prompt_command=args.prompt_command,
    )

    try:
        res = log_cycle(
            dispatch_path=args.dispatch_path,
            event_flags=event_flags,
            summary=args.summary,
            skills=skills or None,
            metadata=metadata,
            transcript=transcript,
            force_persist_all=bool(args.force_persist),
            author=args.author,
            root=orchestrator_root,
            target_root=workspace_root,
            tags=args.tags,
            preview=args.preview,
            prompt_command=args.prompt_command,
        )
    except Exception as e:  # pragma: no cover - runtime exception reporting
        print("log_cycle raised an exception:", e, file=sys.stderr)
        return 3

    # Print a compact result for hook runner visibility
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
