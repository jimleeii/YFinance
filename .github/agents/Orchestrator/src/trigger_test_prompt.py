import argparse
import os
import re
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence, Any

from src.skill_loader import load_manifest
from pathlib import Path

# Prefer centralized hooks when available
try:
    from hooks.log_hooks import log_cycle as _log_cycle, write_transcript as _hooks_write_transcript
except Exception:
    _log_cycle = None
    _hooks_write_transcript = None


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _allow_legacy_curated_fallback() -> bool:
    return os.environ.get("ORCHESTRATOR_ALLOW_LEGACY_CURATED_FALLBACK", "0") in {"1", "true", "True"}


def _write_legacy_fallback_artifact(wiki_root: str, stem: str, content: str) -> str:
    artifacts_dir = os.path.join(wiki_root, "artifacts")
    ensure_dir(artifacts_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(artifacts_dir, f"{stem}-{ts}.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


DEFAULT_SKILL_HINTS = (
    "prompt-optimizer",
    "verification-before-completion",
    "requesting-code-review",
    "writing-plans",
    "brainstorming",
    "karpathy-guidelines",
    "proactive-recall",
    "self-improving-agent",
    "systematic-debugging",
    "test-driven-development",
    "agent-customization",
    "using-superpowers",
    "find-skills",
    "dispatching-parallel-agents",
    "subagent-driven-development",
    "proactivity",
    "create-agentsmd",
    "planning-with-files",
    "executing-plans",
    "finishing-a-development-branch",
    "simplify-code",
    "reviewing-dotnet-code",
    "writing-csharp-code",
    "dotnet-csharp-async-patterns",
    "csharp-pro",
    "dotnet-framework-4-8-expert",
    "dotnet-core-expert",
)


def _load_repo_skill_names() -> list[str]:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    manifest_paths = [
        os.path.join(repo_root, "skills", "skills_manifest.json"),
        os.path.join(repo_root, ".github", "agents", "Orchestrator", "skills", "skills_manifest.json"),
    ]
    names: list[str] = []
    for manifest_path in manifest_paths:
        if not os.path.exists(manifest_path):
            continue
        try:
            names.extend(load_manifest(manifest_path).keys())
        except Exception:
            continue
    return names


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(',')]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = [str(value).strip()]
    return [item for item in items if item]


def _merge_unique_text_lists(*sources: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in _as_text_list(source):
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _resolved_model_id(metadata: dict[str, Any]) -> Optional[str]:
    model_resolution = metadata.get("model_resolution")
    if isinstance(model_resolution, dict):
        resolved_model = model_resolution.get("model") or model_resolution.get("selected_model")
        if isinstance(resolved_model, str) and resolved_model.strip():
            return resolved_model.strip()

    for key in ("selected_model", "cycle_selected_model", "model"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _build_skill_catalog(explicit_skill_names: Iterable[str] = ()) -> list[str]:
    catalog: list[str] = []
    seen: set[str] = set()
    for source in (explicit_skill_names, _load_repo_skill_names(), DEFAULT_SKILL_HINTS):
        for skill_name in source:
            normalized = skill_name.strip().lower()
            if not normalized or normalized in seen:
                continue
            catalog.append(skill_name.strip())
            seen.add(normalized)
    return catalog


def _find_skill_match(text: str, skill_name: str) -> Optional[re.Match[str]]:
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(skill_name.lower())}(?![A-Za-z0-9])")
    return pattern.search(text.lower())


def extract_skill_usage(
    *texts: str,
    explicit_skill_names: Iterable[str] = (),
    known_skill_names: Sequence[str] | None = None,
) -> dict:
    """Extract ordered skill names and first-seen source labels from text snippets."""

    catalog = list(known_skill_names) if known_skill_names is not None else _build_skill_catalog(explicit_skill_names)
    ordered_hits: dict[str, tuple[int, int, str, str]] = {}

    for text_index, text in enumerate(texts):
        if not text:
            continue
        source_label = "input" if text_index == 0 else "output"
        for skill_name in catalog:
            match = _find_skill_match(text, skill_name)
            if not match:
                continue
            key = skill_name.lower()
            candidate = (text_index, match.start(), skill_name, source_label)
            previous = ordered_hits.get(key)
            if previous is None or candidate[:2] < previous[:2]:
                ordered_hits[key] = candidate

    ordered = sorted(ordered_hits.values(), key=lambda item: (item[0], item[1], item[2].lower()))
    skills = [item[2] for item in ordered]
    sources = {item[2]: item[3] for item in ordered}
    return {"skills": skills, "sources": sources}


def _skill_usage_log_path(wiki_root: str) -> str:
    return os.path.join(wiki_root, "Skill-Usage-Log.md")


def _ensure_skill_usage_log_header(wiki_root: str) -> str:
    ensure_dir(wiki_root)
    log_path = _skill_usage_log_path(wiki_root)
    if os.path.exists(log_path):
        return log_path

    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(
            "# Skill Usage Log\n\n"
            "Track which skills were used per orchestration cycle and what should be reused later.\n\n"
            "## Entry Template\n"
        )
    return log_path


def append_skill_usage_log(
    wiki_root: str,
    prompt: str,
    output_text: str = "",
    user: str = "test-user",
    routing_path: str = "single-agent",
    subagents: Optional[Sequence[str]] = None,
    explicit_skill_names: Iterable[str] = (),
    known_skill_names: Sequence[str] | None = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict:
    metadata = metadata or {}
    log_path = _ensure_skill_usage_log_header(wiki_root)
    usage = extract_skill_usage(
        prompt,
        output_text,
        explicit_skill_names=explicit_skill_names,
        known_skill_names=known_skill_names,
    )
    metadata_skills = _merge_unique_text_lists(metadata.get("skills_used"), metadata.get("skills_used_ordered"))
    usage["skills"] = _merge_unique_text_lists(usage.get("skills", []), metadata_skills)

    # If centralized hooks are available, prefer them to persist logs consistently.
    if _log_cycle:
        try:
            _log_cycle(
                dispatch_path=routing_path,
                event_flags={},
                summary=prompt + ("\n\n" + output_text if output_text else ""),
                skills=usage.get("skills", []),
                metadata=metadata,
                transcript=None,
                force_persist_all=False,
                author=user,
                target_root=Path(wiki_root).resolve(),
                preview=False,
            )
            # Return the parsed usage structure; the hook already wrote the files.
            return {"path": log_path, **usage, "entry_id": f"SKL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"}
        except Exception:
            # Fall back to local append behaviour on error
            pass

    if not _allow_legacy_curated_fallback():
        artifact_path = _write_legacy_fallback_artifact(
            wiki_root,
            "legacy-skill-usage",
            "\n".join(
                [
                    f"Timestamp (UTC): {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}",
                    f"Routing Path: {routing_path}",
                    f"Skills: {', '.join(usage.get('skills', [])) or '-'}",
                    f"Prompt: {prompt}",
                    f"Output: {output_text}",
                ]
            ) + "\n",
        )
        return {"path": artifact_path, **usage, "entry_id": None}

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entry_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    skills_text = ", ".join(usage["skills"]) if usage["skills"] else "-"
    subagents_text = ", ".join(_merge_unique_text_lists(subagents, metadata.get("subagents"), metadata.get("subagent"))) or "-"
    reason_bits = []
    if any(source == "input" for source in usage["sources"].values()):
        reason_bits.append("input transcript")
    if any(source == "output" for source in usage["sources"].values()):
        reason_bits.append("output transcript")
    if explicit_skill_names:
        reason_bits.append("explicit runtime invocation")
    if metadata.get("skills_used") or metadata.get("skills_used_ordered"):
        reason_bits.append("structured metadata")
    invocation_reason = metadata.get("invocation_reason") or ("parsed from " + ", ".join(reason_bits) if reason_bits else "no skill mentions detected")
    entry = [
        f"### SKL-{entry_id}",
        "",
        f"- Timestamp (UTC): {ts}",
        "- Request Type: chat-conversion",
        f"- Routing Path: {routing_path}",
        f"- Subagent(s): {subagents_text}",
        f"- Skills Used (ordered): {skills_text}",
        f"- Invocation Reason: {invocation_reason}",
        "- Outcome Impact: neutral",
        "- Reuse Note: Parsed from Copilot Chat input/output and runtime invocation events when available.",
        "",
    ]
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(entry))
    return {"path": log_path, **usage, "entry_id": f"SKL-{entry_id}"}


def append_behavior_log(wiki_root: str, prompt: str, user: str = "test-user", metadata: Optional[dict[str, Any]] = None):
    metadata = metadata or {}
    bl_path = os.path.join(wiki_root, "Behavior-Log.md")

    # Prefer centralized hooks when available
    if _log_cycle:
        try:
            _log_cycle(
                dispatch_path="single-agent",
                event_flags={},
                summary=prompt,
                skills=None,
                metadata=metadata,
                transcript=None,
                force_persist_all=False,
                author=user,
                target_root=Path(wiki_root).resolve(),
                preview=False,
            )
            return
        except Exception:
            # fallback to local append
            pass

    if not _allow_legacy_curated_fallback():
        _write_legacy_fallback_artifact(
            wiki_root,
            "legacy-behavior",
            "\n".join(
                [
                    f"Timestamp (UTC): {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}",
                    f"User: {user}",
                    f"Prompt: {prompt}",
                ]
            ) + "\n",
        )
        return

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entry_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    subagent_text = metadata.get("subagent") or metadata.get("subagents") or "Orchestrator"
    selected_model = _resolved_model_id(metadata)
    if not selected_model:
        selected_model = (
            metadata.get("global_default_model")
            or metadata.get("default_model")
            or metadata.get("runtime_model")
            or os.environ.get("ORCHESTRATOR_DEFAULT_MODEL")
            or "gpt-5.4-mini"
        )
    task_type = metadata.get("task_type") or "orchestration-cycle"
    criticality = metadata.get("criticality") or "P2"
    skills_text = ", ".join(_merge_unique_text_lists(metadata.get("skills_used"), metadata.get("skills_used_ordered"))) or "-"
    entry = [
        f"### OBS-{entry_id}",
        "",
        f"- Timestamp (UTC): {ts}",
        f"- Request Type: {metadata.get('request_type') or 'interactive-prompt'}",
        f"- Subagent: {subagent_text}",
        f"- Model Selection: selected_model={selected_model} | task_type={task_type} | criticality={criticality}",
        f"- User: {user}",
        f"- Skills Used: {skills_text}",
        f"- Prompt: |\n  {prompt}",
        "- Outcome: persisted-test",
        "",
    ]
    with open(bl_path, "a", encoding="utf-8") as f:
        f.write("\n".join(entry))


def write_transcript(wiki_root: str, prompt: str, output_text: str = "", skill_usage: Optional[dict] = None):
    # Prefer hooks-based transcript writer when available
    if _hooks_write_transcript:
        try:
            return _hooks_write_transcript(Path(wiki_root).resolve(), output_text or prompt)
        except Exception:
            pass

    artifacts_dir = os.path.join(wiki_root, "artifacts")
    ensure_dir(artifacts_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"transcript-{ts}.txt"
    path = os.path.join(artifacts_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}\n")
        f.write("Input Prompt:\n")
        f.write(prompt)
        f.write("\n\nOutput Text:\n")
        f.write(output_text or "")
        if skill_usage:
            f.write("\n\nParsed Skills:\n")
            f.write(", ".join(skill_usage.get("skills", [])) or "-")
    return path


def main():
    parser = argparse.ArgumentParser(description="Trigger a test prompt and persist logs to .wiki/orchestrator")
    parser.add_argument("--prompt", "-p", required=True, help="Prompt text to persist")
    parser.add_argument("--wiki", "-w", default=".wiki/orchestrator", help="Wiki root folder")
    parser.add_argument("--user", "-u", default="test-user", help="User name to record")
    args = parser.parse_args()

    wiki_root = args.wiki
    ensure_dir(wiki_root)
    append_behavior_log(wiki_root, args.prompt, user=args.user)
    transcript = write_transcript(wiki_root, args.prompt)
    print(f"Persisted prompt to Behavior-Log.md and transcript: {transcript}")


if __name__ == "__main__":
    main()
