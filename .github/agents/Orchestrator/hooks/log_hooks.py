"""Logging hooks for the Orchestrator.

These helpers follow `rules/Logging.Policy.md` to choose a logging verbosity
(`minimal` | `compact` | `full`) and persist entries by invoking the
`scripts/log_prompt.py` CLI. They also provide a small helper to write
cycle transcripts under `.wiki/orchestrator/transcripts/` when available.

Usage:
  from hooks.log_hooks import log_cycle
  res = log_cycle(
      dispatch_path='single-agent',
      event_flags={'failure_detected': False},
      summary='Completed single-agent task',
      skills=['skillA','skillB'],
      transcript=None,
      force_persist_all=False,
      author='Wei Li',
  )

The implementation intentionally calls the existing `scripts/log_prompt.py`
so the project keeps a single mapping of prompt-commands -> template files.
"""
from __future__ import annotations

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timezone
import re
from typing import Optional, List, Dict, Any

TEMPLATES_DIR_NAME = ".wiki/orchestrator"
DEFAULT_MODEL_ID = "gpt-5.4-mini"


def find_repo_root(start: Optional[Path] = None) -> Path:
    p = Path(start or __file__).resolve()
    cur = p if p.is_dir() else p.parent
    markers = (TEMPLATES_DIR_NAME, 'orchestrator.agent.md', '.git')
    for _ in range(20):
        for m in markers:
            if (cur / m).exists():
                return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(__file__).resolve().parents[1]


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(',')]
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


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = value.strip() if isinstance(value, str) else str(value).strip()
        if text:
            return text
    return default


def _build_model_selection(metadata: Dict[str, Any]) -> str:
    resolved_model = _first_text(
        metadata.get('selected_model'),
        metadata.get('cycle_selected_model'),
        metadata.get('model'),
    )
    model_resolution = metadata.get('model_resolution')
    if isinstance(model_resolution, dict):
        resolved_model = _first_text(
            model_resolution.get('model'),
            model_resolution.get('selected_model'),
            resolved_model,
        )
    explicit_selection = _first_text(metadata.get('model_selection'))
    if explicit_selection and not resolved_model:
        return explicit_selection

    explicit_task_type = ""
    explicit_criticality = ""
    if explicit_selection:
        task_match = re.search(r"task_type=([^|]+)", explicit_selection)
        if task_match:
            explicit_task_type = task_match.group(1).strip()
        criticality_match = re.search(r"criticality=([^|]+)", explicit_selection)
        if criticality_match:
            explicit_criticality = criticality_match.group(1).strip()

    if not resolved_model:
        resolved_model = _first_text(
            metadata.get('global_default_model'),
            metadata.get('default_model'),
            metadata.get('runtime_model'),
            default=DEFAULT_MODEL_ID,
        )
    task_type = _first_text(metadata.get('task_type'), explicit_task_type, default='orchestration-cycle')
    criticality = _first_text(metadata.get('criticality'), explicit_criticality, default='P2')
    return f"selected_model={resolved_model} | task_type={task_type} | criticality={criticality}"


def choose_logging_level(dispatch_path: str, event_flags: Optional[Dict[str, bool]] = None, config: Optional[Dict[str, bool]] = None) -> str:
    """Choose logging level per `rules/Logging.Policy.md` pseudocode.

    dispatch_path: 'direct' | 'single-agent' | 'multi-agent' (or similar)
    event_flags: keys may include: 'persistent_mode_change', 'tier_override', 'failure_detected'
    config: supported keys: 'force_persist_all'

    Returns: 'minimal' | 'compact' | 'full'
    """
    event_flags = event_flags or {}
    config = config or {}
    if config.get('force_persist_all'):
        return 'full'
    if event_flags.get('persistent_mode_change') or event_flags.get('tier_override') or event_flags.get('failure_detected'):
        return 'full'
    if dispatch_path == 'multi-agent':
        return 'full'
    if dispatch_path == 'single-agent':
        return 'compact'
    return 'minimal'


def _run_log_command(
    repo_root: Path,
    command: str,
    message: str = "",
    author: Optional[str] = None,
    tags: Optional[str] = None,
    preview: bool = False,
    script_root: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
):
    script = repo_root / 'scripts' / 'log_prompt.py'
    if not script.exists():
        raise FileNotFoundError(f"log_prompt.py not found at expected location: {script}")
    payload = json.dumps(context, ensure_ascii=False) if context is not None else message
    cmd = [sys.executable, str(script), command, payload]
    if author:
        cmd += ['--author', str(author)]
    if tags:
        cmd += ['--tags', str(tags)]
    if script_root:
        cmd += ['--root', str(script_root)]
    if preview:
        cmd += ['--preview']
    # Use run so exceptions propagate to callers for the orchestrator to handle
    return subprocess.run(cmd, check=True)


def _build_log_context(
    dispatch_path: str,
    event_flags: Optional[Dict[str, bool]] = None,
    summary: str = "",
    skills: Optional[List[str]] = None,
    prompt_command: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_flags = event_flags or {}
    metadata = metadata or {}
    now = datetime.now(timezone.utc).astimezone()
    timestamp_utc = now.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    date = now.strftime('%Y-%m-%d')
    metadata_skills = _merge_unique_text_lists(
        metadata.get('skills_used'),
        metadata.get('skills_used_ordered'),
        metadata.get('skills'),
    )
    skills = _merge_unique_text_lists(skills or [], metadata_skills)
    skills_text = ", ".join(skills) if skills else "-"
    subagents = _merge_unique_text_lists(metadata.get('subagents'), metadata.get('subagent'))
    if not subagents:
        subagents = ["Orchestrator"]
    subagents_text = ", ".join(subagents)
    subagent_text = _first_text(metadata.get('subagent'), subagents_text, default='Orchestrator')
    invocation_reason = summary.strip() if summary.strip() else (prompt_command or "hook-triggered logging")
    prompt_normalization = _first_text(
        metadata.get('prompt_normalization'),
        default="performed" if any(skill.lower() == 'prompt-optimizer' for skill in skills) else "not applicable",
    )
    failure_detected = bool(event_flags.get('failure_detected'))
    outcome = _first_text(metadata.get('outcome'), default="revise" if failure_detected else "pass")
    compaction_batch = f"CB-{now.strftime('%Y%m%d')}-01"
    fallback_used_value = metadata.get('fallback_used')
    if fallback_used_value is None:
        fallback_used_value = event_flags.get('fallback_used')
    fallback_reason_value = _first_text(
        metadata.get('fallback_reason'),
        event_flags.get('fallback_reason'),
        default='none',
    )
    override_phrase_value = _first_text(
        metadata.get('override_phrase'),
        event_flags.get('override_phrase'),
        default='none',
    )
    model_selection = _build_model_selection(metadata)
    routing_mode = _first_text(
        metadata.get('routing_mode'),
        default='persistent=adaptive-score-based | effective=adaptive-score-based | source=default',
    )
    contract_score = _first_text(metadata.get('contract_score'), default='n/a')
    failure_mode = _first_text(metadata.get('failure_mode'), default='hook reported failure' if failure_detected else 'none')
    root_cause_hypothesis = _first_text(metadata.get('root_cause_hypothesis'), default='template field mapping was incomplete')
    follow_up_action = _first_text(metadata.get('follow_up_action'), default='Verify all template fields are populated from structured metadata.')
    project_request = _first_text(metadata.get('project_request'), default=summary or 'full-log template verification')
    stage = _first_text(metadata.get('stage'), default='checkpoint')
    summary_completed = _first_text(metadata.get('completed'), metadata.get('summary_completed'), default='Structured fields are now available to the renderer.')
    summary_in_progress = _first_text(metadata.get('in_progress'), metadata.get('summary_in_progress'), default='Verifying hook-driven log output.')
    summary_blockers_risks = _first_text(metadata.get('blockers_risks'), metadata.get('summary_blockers_risks'), default='No blockers')
    summary_next_action = _first_text(metadata.get('next_action'), metadata.get('summary_next_action'), default='Run the hook preview and confirm field population.')
    routing_policy_changes = _first_text(metadata.get('routing_policy_changes'), default='mode_change=no | override=no | fallback=no')
    change_applied = _first_text(metadata.get('change_applied'), default=summary or 'Structured full-log template rendering')
    expected_effect = _first_text(metadata.get('expected_effect'), default='Log templates receive populated field values.')
    validation_window = _first_text(metadata.get('validation_window'), default='preview render and hook invocation')
    observed_result = _first_text(metadata.get('observed_result'), default='Preview render should show populated fields.')
    decision = _first_text(metadata.get('decision'), default='keep' if not failure_detected else 'revise')

    defaults: Dict[str, Any] = {
        'timestamp_utc': timestamp_utc,
        'date': date,
        'request_type': 'chat-conversion',
        'routing_path': dispatch_path,
        'subagents': subagents_text,
        'subagent': subagent_text,
        'skills_used_ordered': skills_text,
        'skills_used': skills_text,
        'invocation_reason': invocation_reason,
        'outcome_impact': 'positive' if skills else 'neutral',
        'reuse_note': 'Use structured metadata payload for hook-driven logs.',
        'prompt_normalization': prompt_normalization,
        'model_selection': model_selection,
        'routing_mode': routing_mode,
        'fallback_override': f"fallback_used={'yes' if bool(fallback_used_value) else 'no'} | fallback_reason={fallback_reason_value} | override_phrase={override_phrase_value}",
        'contract_score': contract_score,
        'outcome': outcome,
        'failure_mode': failure_mode,
        'failure_mode_if_any': failure_mode,
        'root_cause_hypothesis': root_cause_hypothesis,
        'follow_up_action': follow_up_action,
        'signal': summary or prompt_command or 'hook-triggered template render',
        'frequency': '1',
        'impact': 'logging fields populated',
        'affected_subagents': subagents_text,
        'likely_cause': 'missing structured metadata path',
        'proposed_policy_change': 'Render log templates from structured metadata payloads.',
        'priority': 'medium',
        'problem': 'blank template fields',
        'proposed_change': 'Populate log templates from hook metadata.',
        'scope': 'output-format',
        'safety_check': 'preview render and hook-runner invocation',
        'owner': 'Orchestrator',
        'project_request': project_request,
        'stage': stage,
        'summary': summary or 'Hook-triggered logging cycle',
        'completed': summary_completed,
        'in_progress': summary_in_progress,
        'blockers_risks': summary_blockers_risks,
        'next_action': summary_next_action,
        'routing_policy_changes': routing_policy_changes,
        'change_applied': change_applied,
        'expected_effect': expected_effect,
        'validation_window': validation_window,
        'observed_result': observed_result,
        'decision': decision,
        'request_type_skill': 'chat-conversion',
        'compaction_batch': compaction_batch,
    }

    return {
        'defaults': defaults,
        'targets': {
            'Behavior-Log.md': {
                'request_type': 'chat-conversion',
                'subagent': subagents_text,
                'model_selection': defaults['model_selection'],
                'routing_mode': defaults['routing_mode'],
                'fallback_override': defaults['fallback_override'],
                'skills_used': skills_text,
                'prompt_normalization': prompt_normalization,
                'contract_score': defaults['contract_score'],
                'outcome': outcome,
                'failure_mode': defaults['failure_mode'],
                'failure_mode_if_any': defaults['failure_mode_if_any'],
                'root_cause_hypothesis': defaults['root_cause_hypothesis'],
                'follow_up_action': defaults['follow_up_action'],
                'compaction_batch': compaction_batch,
            },
            'Behavior-Patterns.md': {
                'signal': defaults['signal'],
                'frequency': defaults['frequency'],
                'impact': defaults['impact'],
                'affected_subagents': defaults['affected_subagents'],
                'likely_cause': defaults['likely_cause'],
                'proposed_policy_change': defaults['proposed_policy_change'],
                'status': 'candidate',
                'compaction_batch': compaction_batch,
            },
            'Learning-Backlog.md': {
                'priority': defaults['priority'],
                'problem': defaults['problem'],
                'proposed_change': defaults['proposed_change'],
                'scope': defaults['scope'],
                'safety_check': defaults['safety_check'],
                'owner': defaults['owner'],
                'status': 'in_progress',
            },
            'Project-Context-Log.md': {
                'project_request': defaults['project_request'],
                'stage': defaults['stage'],
                'summary': defaults['summary'],
                'completed': defaults['completed'],
                'in_progress': defaults['in_progress'],
                'blockers_risks': defaults['blockers_risks'],
                'next_action': defaults['next_action'],
                'routing_policy_changes': defaults['routing_policy_changes'],
            },
            'Runbook.md': {
                'date': date,
                'trigger_pattern': prompt_command or 'hook-triggered logging',
                'change_applied': defaults['change_applied'],
                'expected_effect': defaults['expected_effect'],
                'validation_window': defaults['validation_window'],
                'observed_result': defaults['observed_result'],
                'decision': defaults['decision'],
            },
            'Skill-Usage-Log.md': {
                'request_type': 'chat-conversion',
                'routing_path': dispatch_path,
                'subagents': subagents_text,
                'skills_used_ordered': skills_text,
                'invocation_reason': invocation_reason,
                'outcome_impact': defaults['outcome_impact'],
                'reuse_note': defaults['reuse_note'],
            },
        },
    }


def write_transcript(repo_root: Path, transcript: str, prefix: str = 'transcript') -> Path:
    base_root = Path(repo_root)
    if (base_root / 'Behavior-Log.md').exists() or (base_root / 'Home.md').exists():
        transcripts_dir = base_root / 'transcripts'
    else:
        transcripts_dir = base_root / TEMPLATES_DIR_NAME / 'transcripts'
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone()
    ts = now.strftime('%Y%m%dT%H%M%S-%f%z')
    filename = f"{prefix}-{ts}.md"
    path = transcripts_dir / filename
    header = f"# Transcript {now.isoformat(timespec='seconds')}\n\n"
    path.write_text(header + transcript + "\n", encoding='utf-8')
    return path


def log_cycle(
    dispatch_path: str,
    event_flags: Optional[Dict[str, bool]] = None,
    summary: str = "",
    skills: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    transcript: Optional[str] = None,
    force_persist_all: bool = False,
    author: Optional[str] = None,
    root: Optional[Path] = None,
    target_root: Optional[Path] = None,
    tags: Optional[str] = None,
    preview: bool = False,
    prompt_command: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """High-level orchestrator hook to persist logs according to policy.

    - Decides level via `choose_logging_level`.
    - For `minimal`: performs no persistent writes and returns quickly.
    - For `compact`: invokes `/info` (writes `Skill-Usage-Log.md` and `Behavior-Log.md`).
    - For `full`: invokes `/full-log` (writes across logs) and optionally writes a transcript.

    Returns a dict with keys describing what was done.
    """
    config = {"force_persist_all": bool(force_persist_all)}
    level = choose_logging_level(dispatch_path, event_flags or {}, config)
    repo_root = Path(root) if root else find_repo_root(None)
    metadata = metadata or {}
    effective_skills = _merge_unique_text_lists(skills or [], metadata.get('skills_used'), metadata.get('skills_used_ordered'))

    if level == 'minimal':
        return {"level": "minimal", "action": "none"}

    # Build a compact message body used for both compact and full
    body = summary or ("(no summary provided)")
    if effective_skills:
        body += "\n\nSkills: " + ", ".join(effective_skills)

    context = _build_log_context(
        dispatch_path=dispatch_path,
        event_flags=event_flags,
        summary=summary,
        skills=effective_skills,
        prompt_command=prompt_command,
        metadata=metadata,
    )

    # If a specific prompt command was requested, run it directly.
    if prompt_command:
        proc = _run_log_command(
            repo_root,
            prompt_command,
            body,
            author=author,
            tags=tags,
            preview=preview,
            script_root=target_root,
            context=context,
        )
        transcript_path = None
        if transcript and not preview:
            transcript_path = write_transcript(Path(target_root) if target_root else repo_root, transcript)
        return {
            "level": level,
            "command": prompt_command,
            "returncode": str(proc.returncode),
            "transcript": str(transcript_path) if transcript_path else None,
        }

    if level == 'compact':
        # single-agent flows: record behavior + skill usage via `/info`
        proc = _run_log_command(
            repo_root,
            '/info',
            body,
            author=author,
            tags=tags,
            preview=preview,
            script_root=target_root,
            context=context,
        )
        return {"level": "compact", "command": "/info", "returncode": str(proc.returncode)}

    if level == 'full':
        proc = _run_log_command(
            repo_root,
            '/full-log',
            body,
            author=author,
            tags=tags,
            preview=preview,
            script_root=target_root,
            context=context,
        )
        transcript_path = None
        # Only write transcript when not in preview mode
        if transcript and not preview:
            transcript_path = write_transcript(Path(target_root) if target_root else repo_root, transcript)
        return {
            "level": "full",
            "command": "/full-log",
            "returncode": str(proc.returncode),
            "transcript": str(transcript_path) if transcript_path else None,
        }

    return {"level": level, "action": "unhandled"}


__all__ = ["choose_logging_level", "log_cycle", "write_transcript"]
