import json
import os
import argparse
import subprocess
import sys
from typing import Optional, List

try:
    # When running as part of the package tests, import via the package name
    from src.trigger_test_prompt import append_behavior_log, write_transcript
except Exception:
    # Fallback for running the module directly from the repo root
    from trigger_test_prompt import append_behavior_log, write_transcript
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


def persist_cycle(wiki_root: str, prompt: str, user: str, logging_level: str):
    # For 'full' persist behavior, write Behavior-Log and transcript
    if logging_level == "full":
        append_behavior_log(wiki_root, prompt, user=user)
        path = write_transcript(wiki_root, prompt)
        print(f"Persisted full artifacts: {path}")
    elif logging_level == "compact":
        append_behavior_log(wiki_root, prompt, user=user)
        print("Persisted compact behavior checkpoint")
    else:
        print("Minimal logging: no persisted artifacts")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", "-p", required=True)
    parser.add_argument("--wiki", "-w", default=".wiki/orchestrator")
    parser.add_argument("--user", "-u", default="runtime-user")
    parser.add_argument("--dispatch", "-d", default="single-agent")
    parser.add_argument("--discover-skills", action="store_true", help="Scan and write skills manifest")
    parser.add_argument("--manifest-path", default="skills/skills_manifest.json", help="Manifest output path")
    parser.add_argument("--run-script", help="Run a repository script (relative path)")
    parser.add_argument("--run-skill", help="Run an executable script inside a skill folder (skill name)")
    parser.add_argument("--skill-script-name", help="Optional specific script filename inside the skill folder")
    args = parser.parse_args()

    config = load_config(args.wiki)
    level = choose_logging_level(args.dispatch, {}, config)
    print(f"Logging level chosen: {level}")
    os.makedirs(args.wiki, exist_ok=True)
    persist_cycle(args.wiki, args.prompt, args.user, level)

    # Optional operations: discover skills or run scripts inside the runtime
    if getattr(args, "discover_skills", False):
        manifest = discover_skills("skills")
        save_manifest(manifest, args.manifest_path)
        print(f"Saved skills manifest to {args.manifest_path} ({len(manifest)} skills)")

    if args.run_script:
        out = run_script(args.run_script)
        print(out)

    if args.run_skill:
        out = run_skill_script(args.run_skill, script_name=args.skill_script_name)
        print(out)


def init_orchestrator(skills_dir: str = "skills", manifest_path: str = "skills/skills_manifest.json") -> dict:
    """Initialize orchestrator runtime by discovering skills and writing a manifest.

    Returns the discovered manifest dictionary.
    """
    manifest = discover_skills(skills_dir)
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
        # Best-effort discover and persist manifest; don't fail import on error.
        try:
            _MANIFEST = init_orchestrator()
        except Exception:
            _MANIFEST = {}
    else:
        _MANIFEST = {}
except Exception:
    _MANIFEST = {}


def handle_request(prompt: str, user: str = "runtime-user", dispatch: str = "single-agent",
                   run_skill: Optional[str] = None, skill_script_name: Optional[str] = None,
                   run_script_path: Optional[str] = None) -> dict:
    """Handle an incoming request: persist artifacts and optionally run scripts.

    This is a lightweight runtime entry that Orchestrator agents can call to
    persist behavior logs/transcripts and to execute local scripts or skill
    scripts. Returns a dict containing the persistence info and any script output.
    """
    config = load_config('.wiki/orchestrator')
    level = choose_logging_level(dispatch, {}, config)
    os.makedirs('.wiki/orchestrator', exist_ok=True)
    persist_cycle('.wiki/orchestrator', prompt, user, level)

    result = {
        "logging_level": level,
        "manifest_summary": {"count": len(_MANIFEST)} if isinstance(_MANIFEST, dict) else {},
        "skill_output": None,
        "script_output": None,
    }

    if run_skill:
        result["skill_output"] = run_skill_script(run_skill, script_name=skill_script_name)

    if run_script_path:
        result["script_output"] = run_script(run_script_path)

    return result


def prepare_dispatch_payload(prompt: str, user: str = "runtime-user", dispatch: str = "single-agent",
                                                         run_skill: Optional[str] = None, skill_script_name: Optional[str] = None,
                                                         run_script_path: Optional[str] = None) -> dict:
        """Run persistence + optional skill/script and return a payload ready for dispatch.

        Returns a dict with keys:
            - `prompt`: the original prompt (normalized)
            - `parent_context`: dictionary with `persistence` (raw handle_request output)
            - `dispatch`: chosen dispatch path

        This helper centralizes the pre-dispatch steps so callers (CLI or other
        orchestrator code) can call it and pass the resulting payload to their
        subagent dispatch mechanism (e.g., `agent/runSubagent`).
        """
        persistence = handle_request(prompt=prompt, user=user, dispatch=dispatch,
                                                                 run_skill=run_skill, skill_script_name=skill_script_name,
                                                                 run_script_path=run_script_path)

        payload = {
                "prompt": prompt,
                "dispatch": dispatch,
                "parent_context": {
                        "persistence": persistence,
                        # include manifest path reference where applicable
                        "skills_manifest": "skills/skills_manifest.json",
                },
        }
        return payload


if __name__ == "__main__":
    main()
