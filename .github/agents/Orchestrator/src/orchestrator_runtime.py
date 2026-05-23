import json
import os
import argparse
import subprocess
import sys
from typing import Optional, List, Dict, Any

try:
    # When running as part of the package tests, import via the package name
    from src.trigger_test_prompt import append_behavior_log, append_skill_usage_log, write_transcript, extract_skill_usage
except Exception:
    # Fallback for running the module directly from the repo root
    from trigger_test_prompt import append_behavior_log, append_skill_usage_log, write_transcript, extract_skill_usage
from src.model_resolver import resolve_model_for_subagent
from src.skill_loader import discover_skills, save_manifest


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
    if dispatch_path == "multi-agent":
        return "full"
    if dispatch_path == "single-agent":
        return "compact"
    return "minimal"


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
        from hooks.log_hooks import log_cycle
    except Exception:
        # Best-effort: if hooks package isn't importable, fall back to previous behavior
        log_cycle = None

    event_flags = dict(event_flags or {})
    metadata = dict(metadata or {})

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
            summary=prompt,
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
                   metadata: Optional[Dict[str, Any]] = None) -> dict:
    """Handle an incoming request: persist artifacts and optionally run scripts.

    This is a lightweight runtime entry that Orchestrator agents can call to
    persist behavior logs/transcripts and to execute local scripts or skill
    scripts. Returns a dict containing the persistence info and any script output.
    """
    config = load_config('.wiki/orchestrator')
    event_flags = dict(event_flags or {})
    metadata = dict(metadata or {})
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

        if model_resolution is None and spawn_payload and model_catalog and global_default_model:
            model_resolution = resolve_model_for_subagent(
                spawn_payload=spawn_payload,
                parent_context=dict(metadata or {}),
                model_catalog=model_catalog,
                global_default_model=global_default_model,
                minimum_tier=minimum_tier,
            )

        if global_default_model and not metadata.get("selected_model"):
            metadata.setdefault("global_default_model", global_default_model)
            metadata.setdefault("selected_model", global_default_model)
            metadata.setdefault("cycle_selected_model", global_default_model)
            metadata.setdefault("model", global_default_model)

        metadata = _merge_dispatch_metadata(metadata, subagent_name=subagent_name, model_resolution=model_resolution)
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
        }

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
