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
import hashlib
import sys
import subprocess
from time import perf_counter
from pathlib import Path
from datetime import datetime, timezone
import re
from typing import Optional, List, Dict, Any

try:
    from src.orchestrator_memory import persist_continuity_checkpoint_from_normalized_metadata as _persist_continuity_checkpoint_from_normalized_metadata
except Exception:  # pragma: no cover - import/runtime guard
    _persist_continuity_checkpoint_from_normalized_metadata = None

TEMPLATES_DIR_NAME = ".wiki/orchestrator"
DEFAULT_MODEL_ID = "gpt-5.4-mini"
AUTOMATIC_HOOK_EVENT_NAMES = {
    "PreToolUse",
    "PostToolUse",
}
NOISE_TEXT_VALUES = {
    "",
    "-",
    "none",
    "unknown",
    "n/a",
    "not applicable",
    "hook-triggered logging",
    "hook-triggered template render",
    "post-tool invocation",
    "full-log template verification",
    "structured full-log template rendering",
}
CURATED_METADATA_KEYS = (
    'project_request',
    'normalized_request',
    'summary',
    'change_applied',
    'signal',
    'problem',
    'proposed_change',
    'likely_cause',
    'completed',
    'in_progress',
    'blockers_risks',
    'next_action',
    'invocation_reason',
    'observed_result',
    'decision',
    'health',
    'health_workspace_id',
    'health_session_id',
    'health_agent_id',
    'health_task_family',
    'health_model_id',
    'health_state',
    'health_action',
    'health_failure_kind',
    'health_reason',
    'health_selected_candidates',
    'health_suppressed_candidates',
    'health_probe_candidate',
)
CURATED_CHECKPOINT_FIELDS = (
    'completed',
    'in_progress',
    'blockers_risks',
    'next_action',
    'change_applied',
    'expected_effect',
    'validation_window',
    'observed_result',
    'decision',
    'problem',
    'proposed_change',
    'likely_cause',
    'summary',
)
FILES_TOUCHED_KEYS = (
    'files_touched',
    'important_files',
    'intended_files',
    'target_files',
    'planned_files',
    'components_touched',
    'components_intended',
    'intended_components',
)
ANCHORED_REQUEST_KEYS = (
    'project_request',
    'anchored_request',
    'request_anchor',
    'original_request',
    'root_request',
    'request_title',
    'title',
)
REQUEST_TEXT_KEYS = (
    'normalized_request',
    'request',
    'prompt',
    'user_request',
    'request_title',
    'title',
    'overview',
    'history',
    'summary',
)
FULL_LOG_COMMANDS = {'/full-log', '/all-log'}
TELEMETRY_CYCLE_FILENAME = 'cycles.jsonl'
CONTINUATION_REQUEST_RE = re.compile(
    r'^(?:please\s+)?(?:approve(?:d)?|perceed|proceed|go(?:\s+ahead)?|continue|carry\s+on|keep\s+going)(?:\s+please)?[.!?]*$',
    re.IGNORECASE,
)


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


def _looks_like_json(value: str) -> bool:
    stripped = value.strip()
    return (
        (stripped.startswith('{') and stripped.endswith('}'))
        or (stripped.startswith('[') and stripped.endswith(']'))
    )


def _is_noise_text(value: Any) -> bool:
    text = _first_text(value)
    if not text:
        return True
    normalized = text.strip().lower()
    if normalized in NOISE_TEXT_VALUES:
        return True
    return _looks_like_json(text)


def _first_meaningful_text(*values: Any, default: str = "") -> str:
    for value in values:
        text = _first_text(value)
        if text and not _is_noise_text(text):
            return text
    return default


def _normalize_inline_text(value: Any) -> str:
    text = _first_text(value)
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def _collect_files_touched(metadata: Dict[str, Any]) -> List[str]:
    return _merge_unique_text_lists(*(metadata.get(key) for key in FILES_TOUCHED_KEYS))


def _build_health_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    health = metadata.get('health') if isinstance(metadata.get('health'), dict) else {}
    health = dict(health) if isinstance(health, dict) else {}
    selected_candidates = _merge_unique_text_lists(metadata.get('health_selected_candidates'), health.get('selected_candidates'))
    suppressed_candidates = _merge_unique_text_lists(metadata.get('health_suppressed_candidates'), health.get('suppressed_candidates'))
    return {
        'health': health,
        'health_workspace_id': _first_meaningful_text(metadata.get('health_workspace_id'), health.get('workspace_id')),
        'health_session_id': _first_meaningful_text(metadata.get('health_session_id'), health.get('session_id')),
        'health_agent_id': _first_meaningful_text(metadata.get('health_agent_id'), health.get('agent_id')),
        'health_task_family': _first_meaningful_text(metadata.get('health_task_family'), health.get('task_family')),
        'health_model_id': _first_meaningful_text(metadata.get('health_model_id'), health.get('model_id')),
        'health_state': _first_meaningful_text(metadata.get('health_state'), health.get('state')),
        'health_action': _first_meaningful_text(metadata.get('health_action'), health.get('action')),
        'health_failure_kind': _first_meaningful_text(metadata.get('health_failure_kind'), health.get('failure_kind')),
        'health_reason': _first_meaningful_text(metadata.get('health_reason'), health.get('reason')),
        'health_selected_candidates': ", ".join(selected_candidates),
        'health_suppressed_candidates': ", ".join(suppressed_candidates),
        'health_probe_candidate': _first_meaningful_text(metadata.get('health_probe_candidate'), health.get('probe_candidate')),
    }


def _apply_checkpoint_aliases(metadata: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(metadata)

    request_title = _normalize_inline_text(
        _first_meaningful_text(normalized.get('request_title'), normalized.get('title'))
    )
    if request_title:
        normalized.setdefault('request_title', request_title)

    summary_alias = _first_meaningful_text(normalized.get('overview'), normalized.get('history'))
    if summary_alias and not _first_meaningful_text(normalized.get('summary')):
        normalized['summary'] = summary_alias

    if not _first_meaningful_text(normalized.get('completed')):
        completed_alias = _first_meaningful_text(normalized.get('work_done'))
        if completed_alias:
            normalized['completed'] = completed_alias

    if not _first_meaningful_text(normalized.get('change_applied')):
        change_alias = _first_meaningful_text(normalized.get('work_done'), normalized.get('overview'))
        if change_alias:
            normalized['change_applied'] = change_alias

    if not _first_meaningful_text(normalized.get('observed_result')):
        observed_alias = _first_meaningful_text(normalized.get('technical_details'))
        if observed_alias:
            normalized['observed_result'] = observed_alias

    if not _first_meaningful_text(normalized.get('next_action')):
        next_alias = _first_meaningful_text(normalized.get('next_steps'))
        if next_alias:
            normalized['next_action'] = next_alias

    files_touched = _collect_files_touched(normalized)
    if files_touched:
        normalized['files_touched'] = files_touched

    return normalized


def _is_continuation_request(value: Any) -> bool:
    text = _normalize_inline_text(value)
    if not text:
        return False
    return bool(CONTINUATION_REQUEST_RE.fullmatch(text))


def _has_meaningful_curated_content(metadata: Dict[str, Any], summary: str = "") -> bool:
    if _collect_files_touched(metadata):
        return True
    if _first_meaningful_text(metadata.get('session_evidence')):
        return True

    health_metadata = _build_health_metadata(metadata)
    for key in (
        'health_workspace_id',
        'health_session_id',
        'health_agent_id',
        'health_task_family',
        'health_model_id',
        'health_state',
        'health_action',
        'health_failure_kind',
        'health_reason',
        'health_selected_candidates',
        'health_suppressed_candidates',
        'health_probe_candidate',
    ):
        if not _is_noise_text(health_metadata.get(key)):
            return True

    for key in CURATED_CHECKPOINT_FIELDS:
        if not _is_noise_text(metadata.get(key)):
            return True

    project_request = _first_meaningful_text(metadata.get('project_request'), metadata.get('anchored_request'))
    if project_request:
        normalized_summary = _normalize_inline_text(summary)
        if normalized_summary and normalized_summary.lower() != project_request.lower():
            return True

    return False


def _has_full_log_evidence(metadata: Dict[str, Any], summary: str = "") -> tuple[bool, str]:
    cycle_id = _first_meaningful_text(metadata.get('cycle_id'))
    if not cycle_id:
        return False, "missing cycle_id"

    health_metadata = _build_health_metadata(metadata)

    request_evidence = _first_meaningful_text(
        metadata.get('project_request'),
        metadata.get('normalized_request'),
        metadata.get('request_title'),
        metadata.get('title'),
        summary,
        health_metadata.get('health_reason'),
        health_metadata.get('health_action'),
        health_metadata.get('health_state'),
        health_metadata.get('health_failure_kind'),
        health_metadata.get('health_selected_candidates'),
        health_metadata.get('health_suppressed_candidates'),
        health_metadata.get('health_probe_candidate'),
    )
    change_evidence = _first_meaningful_text(
        metadata.get('change_applied'),
        metadata.get('completed'),
        metadata.get('observed_result'),
        metadata.get('decision'),
        metadata.get('next_action'),
        health_metadata.get('health_reason'),
        health_metadata.get('health_action'),
        health_metadata.get('health_state'),
        health_metadata.get('health_failure_kind'),
    )

    if not request_evidence:
        return False, "missing meaningful request evidence"
    if not change_evidence:
        return False, "missing meaningful change evidence"
    return True, ""


def _build_curated_dedupe_key(
    metadata: Dict[str, Any],
    summary: str = "",
    prompt_command: Optional[str] = None,
) -> str:
    health_metadata = _build_health_metadata(metadata)
    payload = {
        'session_id': _first_text(metadata.get('session_id')),
        'request_group_id': _first_text(metadata.get('request_group_id')),
        'cycle_id': _first_text(metadata.get('cycle_id')),
        'request_title': _first_text(metadata.get('request_title'), metadata.get('title')),
        'project_request': _first_text(metadata.get('project_request'), metadata.get('anchored_request')),
        'normalized_request': _first_text(metadata.get('normalized_request')),
        'summary': _normalize_inline_text(_first_meaningful_text(metadata.get('summary'), summary)),
        'completed': _first_text(metadata.get('completed')),
        'in_progress': _first_text(metadata.get('in_progress')),
        'blockers_risks': _first_text(metadata.get('blockers_risks')),
        'next_action': _first_text(metadata.get('next_action')),
        'change_applied': _first_text(metadata.get('change_applied')),
        'observed_result': _first_text(metadata.get('observed_result')),
        'decision': _first_text(metadata.get('decision')),
        'health_workspace_id': _first_text(health_metadata.get('health_workspace_id')),
        'health_session_id': _first_text(health_metadata.get('health_session_id')),
        'health_agent_id': _first_text(health_metadata.get('health_agent_id')),
        'health_task_family': _first_text(health_metadata.get('health_task_family')),
        'health_model_id': _first_text(health_metadata.get('health_model_id')),
        'health_state': _first_text(health_metadata.get('health_state')),
        'health_action': _first_text(health_metadata.get('health_action')),
        'health_failure_kind': _first_text(health_metadata.get('health_failure_kind')),
        'health_reason': _first_text(health_metadata.get('health_reason')),
        'health_selected_candidates': _first_text(health_metadata.get('health_selected_candidates')),
        'health_suppressed_candidates': _first_text(health_metadata.get('health_suppressed_candidates')),
        'health_probe_candidate': _first_text(health_metadata.get('health_probe_candidate')),
        'files_touched': _collect_files_touched(metadata),
        'prompt_command': prompt_command or '',
    }
    # Safely encode JSON payload for hashing. Some inputs (from external prompts or
    # transcripts) may include lone surrogate code points which raise on
    # `.encode('utf-8')` when `ensure_ascii=False` is used. Try the preferred
    # non-escaped JSON form first, but fall back to an ASCII-escaped JSON
    # representation if encoding fails to ensure we never raise here.
    try:
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        payload_bytes = payload_str.encode('utf-8')
    except UnicodeEncodeError:
        # Fallback: escape non-ASCII characters to \uXXXX sequences so the
        # resulting bytes are always encodable to UTF-8. This keeps the
        # dedupe key deterministic while avoiding exceptions from lone
        # surrogates in input data.
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        payload_bytes = payload_str.encode('utf-8')

    digest = hashlib.sha1(payload_bytes).hexdigest()
    return f"curated:{digest[:20]}"


def normalize_checkpoint_metadata(
    summary: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    event_flags: Optional[Dict[str, Any]] = None,
    prompt_command: Optional[str] = None,
) -> Dict[str, Any]:
    normalized = _apply_checkpoint_aliases(metadata or {})

    anchored_request = _first_meaningful_text(*(normalized.get(key) for key in ANCHORED_REQUEST_KEYS))
    candidate_request = _first_meaningful_text(*(normalized.get(key) for key in REQUEST_TEXT_KEYS), summary)
    if _is_continuation_request(candidate_request):
        continuation_prompt = _normalize_inline_text(candidate_request)
        if continuation_prompt:
            normalized['continuation_prompt'] = continuation_prompt
        candidate_request = anchored_request

    normalized_request = _normalize_inline_text(candidate_request)
    anchored_request = _normalize_inline_text(anchored_request or normalized_request)
    if normalized_request:
        normalized['normalized_request'] = normalized_request
    if anchored_request:
        normalized['project_request'] = anchored_request
        normalized.setdefault('anchored_request', anchored_request)

    files_touched = _collect_files_touched(normalized)
    if files_touched:
        normalized['files_touched'] = files_touched

    curated_requested = bool(
        normalized.get('curated_checkpoint')
        or normalized.get('curated_log')
        or normalized.get('persist_full_log')
        or prompt_command in FULL_LOG_COMMANDS
    )
    curated_meaningful = _has_meaningful_curated_content(normalized, summary)
    normalized['curated_checkpoint'] = bool(curated_meaningful or curated_requested and curated_meaningful)

    if normalized.get('curated_checkpoint') and not normalized.get('dedupe_key'):
        normalized['dedupe_key'] = _build_curated_dedupe_key(normalized, summary=summary, prompt_command=prompt_command)

    if normalized.get('curated_checkpoint') and prompt_command in FULL_LOG_COMMANDS:
        normalized['curated_log'] = True

    return normalized


def _resolve_wiki_root(base_root: Path) -> Path:
    if (base_root / 'Behavior-Log.md').exists() or (base_root / 'Home.md').exists():
        return base_root
    if base_root.name == 'orchestrator' and base_root.parent.name == '.wiki':
        return base_root
    return base_root / TEMPLATES_DIR_NAME


def _utf8_backslashreplace_text(text: str) -> str:
    return text.encode('utf-8', errors='backslashreplace').decode('utf-8')


def _dedupe_store_path(base_root: Path) -> Path:
    return _resolve_wiki_root(base_root) / '.curated-checkpoint-dedupe.json'


def _telemetry_cycle_path(base_root: Path) -> Path:
    return _resolve_wiki_root(base_root) / 'telemetry' / TELEMETRY_CYCLE_FILENAME


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(float(str(value).strip()))
    except Exception:
        return default
    return parsed if parsed >= 0 else default


def _build_cycle_telemetry_metadata(
    summary: str,
    body: str,
    skills: List[str],
    metadata: Dict[str, Any],
    transcript: Optional[str],
    started_at: float,
) -> Dict[str, Any]:
    telemetry_metadata = dict(metadata)
    telemetry_metadata.setdefault(
        'selected_model',
        _first_meaningful_text(metadata.get('selected_model'), metadata.get('cycle_selected_model'), metadata.get('model')),
    )
    telemetry_metadata.setdefault('selected_model_source', _first_meaningful_text(metadata.get('selected_model_source')))
    telemetry_metadata.setdefault(
        'model_resolution',
        metadata.get('model_resolution') if isinstance(metadata.get('model_resolution'), dict) else None,
    )
    telemetry_metadata['summary_chars'] = len(_normalize_inline_text(summary))
    telemetry_metadata['body_chars'] = len(body)
    telemetry_metadata['transcript_chars'] = len(transcript or '')
    telemetry_metadata['skills_count'] = len(skills)
    telemetry_metadata['files_touched_count'] = len(_collect_files_touched(metadata))
    telemetry_metadata['elapsed_ms'] = max(0, int((perf_counter() - started_at) * 1000))
    telemetry_metadata['failure_detected'] = bool(metadata.get('failure_detected') or metadata.get('health_failure_kind'))
    return telemetry_metadata


def _build_cycle_telemetry_fingerprint(payload: Dict[str, Any]) -> str:
    fingerprint_payload = {
        'dispatch_path': _first_text(payload.get('dispatch_path')),
        'level': _first_text(payload.get('level')),
        'command': _first_text(payload.get('command')),
        'cycle_id': _first_text(payload.get('cycle_id')),
        'session_id': _first_text(payload.get('session_id')),
        'request_group_id': _first_text(payload.get('request_group_id')),
        'dedupe_key': _first_text(payload.get('dedupe_key')),
    }
    digest = hashlib.sha1(json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=True).encode('utf-8')).hexdigest()
    return f"sha1:{digest}"


def _append_cycle_telemetry_event(
    base_root: Path,
    dispatch_path: str,
    level: str,
    command: str,
    summary: str,
    skills: List[str],
    metadata: Dict[str, Any],
    preview: bool,
) -> None:
    if preview:
        return

    payload: Dict[str, Any] = {
        'schema_version': 'orchestrator.telemetry.cycle.v1',
        'event_type': 'cycle.persisted',
        'recorded_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'dispatch_path': dispatch_path,
        'level': level,
        'command': command,
        'persisted': True,
        'preview': bool(preview),
        'cycle_id': _first_text(metadata.get('cycle_id')),
        'session_id': _first_text(metadata.get('session_id')),
        'request_group_id': _first_text(metadata.get('request_group_id')),
        'dedupe_key': _first_text(metadata.get('dedupe_key')),
        'curated_checkpoint': bool(metadata.get('curated_checkpoint')),
        'summary': _normalize_inline_text(summary),
        'skills_used': list(skills),
        'selected_model': _first_meaningful_text(metadata.get('selected_model'), metadata.get('cycle_selected_model'), metadata.get('model')),
        'selected_model_source': _first_meaningful_text(metadata.get('selected_model_source')),
        'contract_score': metadata.get('contract_score'),
        'elapsed_ms': _coerce_non_negative_int(metadata.get('elapsed_ms')),
        'summary_chars': _coerce_non_negative_int(metadata.get('summary_chars')),
        'body_chars': _coerce_non_negative_int(metadata.get('body_chars')),
        'transcript_chars': _coerce_non_negative_int(metadata.get('transcript_chars')),
        'skills_count': _coerce_non_negative_int(metadata.get('skills_count')),
        'files_touched_count': _coerce_non_negative_int(metadata.get('files_touched_count')),
        'failure_detected': bool(metadata.get('failure_detected')),
        'model_resolution': metadata.get('model_resolution') if isinstance(metadata.get('model_resolution'), dict) else None,
    }
    payload['fingerprint'] = _build_cycle_telemetry_fingerprint(payload)

    path = _telemetry_cycle_path(base_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = _utf8_backslashreplace_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    with path.open('a', encoding='utf-8') as handle:
        handle.write(line + '\n')


def _persist_continuity_checkpoint(
    base_root: Path,
    metadata: Dict[str, Any],
    dispatch_path: str,
    command: str,
) -> None:
    if _persist_continuity_checkpoint_from_normalized_metadata is None:
        return
    try:
        _persist_continuity_checkpoint_from_normalized_metadata(
            metadata,
            root=base_root,
            source_kind='log_cycle',
            source_identifier=f'{dispatch_path}:{command}' if dispatch_path or command else '',
        )
    except Exception:
        return


def _load_dedupe_store(base_root: Path) -> Dict[str, str]:
    path = _dedupe_store_path(base_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    entries = payload.get('entries')
    return dict(entries) if isinstance(entries, dict) else {}


def _record_dedupe_key(base_root: Path, dedupe_key: str) -> None:
    if not dedupe_key:
        return
    path = _dedupe_store_path(base_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_dedupe_store(base_root)
    entries[dedupe_key] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if len(entries) > 256:
        items = list(entries.items())[-256:]
        entries = {key: value for key, value in items}
    path.write_text(json.dumps({'entries': entries}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _is_duplicate_curated_checkpoint(base_root: Path, metadata: Dict[str, Any]) -> bool:
    dedupe_key = _first_text(metadata.get('dedupe_key'))
    if not metadata.get('curated_checkpoint') or not dedupe_key:
        return False
    return dedupe_key in _load_dedupe_store(base_root)


def _format_session_evidence(metadata: Dict[str, Any]) -> str:
    explicit = metadata.get('session_evidence')
    if isinstance(explicit, dict):
        parts = []
        for key, value in explicit.items():
            text = _first_meaningful_text(value)
            if text:
                parts.append(f"{key}={text}")
        return ' | '.join(parts)
    if isinstance(explicit, (list, tuple, set)):
        return '\n'.join(f"- {item}" for item in _as_text_list(explicit))
    explicit_text = _first_meaningful_text(explicit)
    if explicit_text:
        return explicit_text

    parts = []
    for key in ('session_id', 'request_group_id', 'cycle_id'):
        value = _first_meaningful_text(metadata.get(key))
        if value:
            parts.append(f"{key}={value}")
    return ' | '.join(parts)


def _build_entry_ids(now: datetime) -> Dict[str, str]:
    date = now.strftime('%Y%m%d')
    time = now.strftime('%H%M%S')
    suffix = f"{date}-{time}"
    return {
        'obs_id': f"OBS-{suffix}",
        'pat_id': f"PAT-{suffix}",
        'lrn_id': f"LRN-{suffix}",
        'ctx_id': f"CTX-{suffix}",
        'chg_id': f"CHG-{suffix}",
        'skl_id': f"SKL-{date}{time}",
        'compaction_batch': f"CB-{date}-01",
    }


def _build_related_links(ids: Dict[str, str]) -> Dict[str, str]:
    return {
        'behavior_related': (
            f"[Behavior-Patterns](Behavior-Patterns.md#{ids['pat_id']}), "
            f"[Learning-Backlog](Learning-Backlog.md#{ids['lrn_id']})"
        ),
        'pattern_evidence': f"[Behavior-Log](Behavior-Log.md#{ids['obs_id']})",
        'learning_linked_pattern': f"[Behavior-Patterns](Behavior-Patterns.md#{ids['pat_id']})",
        'context_related': (
            f"[Behavior-Log](Behavior-Log.md#{ids['obs_id']}), "
            f"[Learning-Backlog](Learning-Backlog.md#{ids['lrn_id']}), "
            f"[Runbook](Runbook.md#{ids['chg_id']})"
        ),
        'runbook_related_entries': (
            f"[Behavior-Patterns](Behavior-Patterns.md#{ids['pat_id']}), "
            f"[Learning-Backlog](Learning-Backlog.md#{ids['lrn_id']})"
        ),
    }


def _hook_event_name(metadata: Dict[str, Any], event_flags: Optional[Dict[str, Any]] = None) -> str:
    event_flags = event_flags or {}
    return _first_text(
        metadata.get('hook_event_name'),
        event_flags.get('hook_event_name'),
        default='',
    )


def _is_automatic_hook_event(metadata: Dict[str, Any], event_flags: Optional[Dict[str, Any]] = None) -> bool:
    event_flags = event_flags or {}
    hook_event_name = _hook_event_name(metadata, event_flags)
    hook_phase = _first_text(metadata.get('hook_phase'), event_flags.get('hook_phase'), default='')
    return hook_event_name in AUTOMATIC_HOOK_EVENT_NAMES or hook_phase in {'pre', 'mid'}


def _should_persist_entry(
    level: str,
    summary: str,
    metadata: Dict[str, Any],
    skills: List[str],
    prompt_command: Optional[str] = None,
) -> bool:
    if bool(metadata.get('curated_checkpoint') or metadata.get('curated_log') or metadata.get('persist_full_log')):
        return _has_meaningful_curated_content(metadata, summary)
    if prompt_command:
        return True
    if not _is_noise_text(summary):
        return True
    if skills:
        return True
    for key in CURATED_METADATA_KEYS:
        if not _is_noise_text(metadata.get(key)):
            return True
    return False


def _build_model_selection(metadata: Dict[str, Any]) -> str:
    resolved_model = _first_meaningful_text(
        metadata.get('selected_model'),
        metadata.get('cycle_selected_model'),
        metadata.get('model'),
    )
    model_resolution = metadata.get('model_resolution')
    if isinstance(model_resolution, dict):
        resolved_model = _first_meaningful_text(
            model_resolution.get('model'),
            model_resolution.get('selected_model'),
            resolved_model,
        )
    explicit_selection = _first_meaningful_text(metadata.get('model_selection'))
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
        resolved_model = _first_meaningful_text(
            metadata.get('global_default_model'),
            metadata.get('default_model'),
            metadata.get('runtime_model'),
        )
    task_type = _first_meaningful_text(metadata.get('task_type'), explicit_task_type)
    criticality = _first_meaningful_text(metadata.get('criticality'), explicit_criticality)

    parts: List[str] = []
    if resolved_model:
        parts.append(f"selected_model={resolved_model}")
    if task_type:
        parts.append(f"task_type={task_type}")
    if criticality:
        parts.append(f"criticality={criticality}")
    if parts:
        return " | ".join(parts)
    if explicit_selection:
        return explicit_selection
    return ""


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


def _run_synthesize_wiki(repo_root: Path, target_root: Optional[Path] = None, preview: bool = False) -> None:
    """Fire-and-forget run of scripts/synthesize_wiki.py to regenerate knowledge pages.
    Does nothing in preview mode or when the script is absent.
    """
    if preview:
        return
    candidates = [
        repo_root / 'scripts' / 'synthesize_wiki.py',
        repo_root / '.github' / 'agents' / 'Orchestrator' / 'scripts' / 'synthesize_wiki.py',
        Path(__file__).resolve().parents[1] / 'scripts' / 'synthesize_wiki.py',
    ]
    wiki_base = Path(target_root) if target_root else repo_root
    wiki_dir = wiki_base / '.wiki' / 'orchestrator'
    for candidate in candidates:
        try:
            if candidate.exists():
                # Start the synthesize_wiki script asynchronously and don't block the caller.
                subprocess.Popen([sys.executable, str(candidate), '--wiki', str(wiki_dir)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        except Exception:
            # Fail silently; synthesis is a best-effort background task.
            return


def _build_log_context(
    dispatch_path: str,
    event_flags: Optional[Dict[str, bool]] = None,
    summary: str = "",
    skills: Optional[List[str]] = None,
    prompt_command: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_flags = event_flags or {}
    metadata = normalize_checkpoint_metadata(
        summary=summary,
        metadata=metadata or {},
        event_flags=event_flags,
        prompt_command=prompt_command,
    )
    now = datetime.now(timezone.utc).astimezone()
    timestamp_utc = now.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    date = now.strftime('%Y-%m-%d')
    ids = _build_entry_ids(now)
    related_links = _build_related_links(ids)
    metadata_skills = _merge_unique_text_lists(
        metadata.get('skills_used'),
        metadata.get('skills_used_ordered'),
        metadata.get('skills'),
    )
    skills = _merge_unique_text_lists(skills or [], metadata_skills)
    skills_text = ", ".join(skills)
    subagents = _merge_unique_text_lists(metadata.get('subagents'), metadata.get('subagent'))
    if not subagents:
        subagents = ["Orchestrator"]
    subagents_text = ", ".join(subagents)
    subagent_text = _first_meaningful_text(metadata.get('subagent'), subagents_text, default='Orchestrator')
    invocation_reason = _first_meaningful_text(
        metadata.get('invocation_reason'),
        metadata.get('normalized_request'),
        metadata.get('project_request'),
        summary,
        prompt_command,
    )
    prompt_normalization = _first_meaningful_text(
        metadata.get('prompt_normalization'),
        default="performed" if any(skill.lower() == 'prompt-optimizer' for skill in skills) else "",
    )
    failure_detected = bool(event_flags.get('failure_detected'))
    outcome = _first_meaningful_text(metadata.get('outcome'), default="revise" if failure_detected else "")
    compaction_batch = ids['compaction_batch']
    fallback_used_value = metadata.get('fallback_used')
    if fallback_used_value is None:
        fallback_used_value = event_flags.get('fallback_used')
    fallback_reason_value = _first_meaningful_text(
        metadata.get('fallback_reason'),
        event_flags.get('fallback_reason'),
    )
    override_phrase_value = _first_meaningful_text(
        metadata.get('override_phrase'),
        event_flags.get('override_phrase'),
    )
    model_selection = _build_model_selection(metadata)
    routing_mode = _first_meaningful_text(metadata.get('routing_mode'))
    contract_score = _first_meaningful_text(metadata.get('contract_score'))
    failure_mode = _first_meaningful_text(metadata.get('failure_mode'))
    root_cause_hypothesis = _first_meaningful_text(metadata.get('root_cause_hypothesis'))
    follow_up_action = _first_meaningful_text(metadata.get('follow_up_action'))
    request_title = _first_meaningful_text(metadata.get('request_title'), metadata.get('title'))
    project_request = _first_meaningful_text(metadata.get('project_request'), metadata.get('anchored_request'), request_title, metadata.get('normalized_request'), summary)
    stage = _first_meaningful_text(metadata.get('stage'))
    summary_completed = _first_meaningful_text(metadata.get('completed'), metadata.get('summary_completed'))
    summary_in_progress = _first_meaningful_text(metadata.get('in_progress'), metadata.get('summary_in_progress'))
    summary_blockers_risks = _first_meaningful_text(metadata.get('blockers_risks'), metadata.get('summary_blockers_risks'))
    summary_next_action = _first_meaningful_text(metadata.get('next_action'), metadata.get('summary_next_action'))
    files_touched_text = ", ".join(_collect_files_touched(metadata))
    session_evidence_text = _format_session_evidence(metadata)
    routing_policy_changes = _first_meaningful_text(metadata.get('routing_policy_changes'))
    change_applied = _first_meaningful_text(metadata.get('change_applied'), summary)
    expected_effect = _first_meaningful_text(metadata.get('expected_effect'))
    validation_window = _first_meaningful_text(metadata.get('validation_window'))
    observed_result = _first_meaningful_text(metadata.get('observed_result'))
    decision = _first_meaningful_text(metadata.get('decision'), default='revise' if failure_detected else '')
    request_type = _first_meaningful_text(metadata.get('request_type'))
    health_metadata = _build_health_metadata(metadata)
    fallback_override = ""
    if fallback_used_value is not None or fallback_reason_value or override_phrase_value:
        fallback_override = (
            f"fallback_used={'yes' if bool(fallback_used_value) else 'no'}"
            f" | fallback_reason={fallback_reason_value or 'none'}"
            f" | override_phrase={override_phrase_value or 'none'}"
        )

    defaults: Dict[str, Any] = {
        **ids,
        'timestamp_utc': timestamp_utc,
        'date': date,
        'request_type': request_type,
        'request_title': request_title,
        'routing_path': dispatch_path,
        'subagents': subagents_text,
        'subagent': subagent_text,
        'skills_used_ordered': skills_text,
        'skills_used': skills_text,
        'invocation_reason': invocation_reason,
        'outcome_impact': _first_meaningful_text(metadata.get('outcome_impact'), default='positive' if skills else ''),
        'reuse_note': _first_meaningful_text(metadata.get('reuse_note')),
        'prompt_normalization': prompt_normalization,
        'model_selection': model_selection,
        'routing_mode': routing_mode,
        'fallback_override': fallback_override,
        'health': health_metadata.get('health'),
        'health_workspace_id': health_metadata.get('health_workspace_id'),
        'health_session_id': health_metadata.get('health_session_id'),
        'health_agent_id': health_metadata.get('health_agent_id'),
        'health_task_family': health_metadata.get('health_task_family'),
        'health_model_id': health_metadata.get('health_model_id'),
        'health_state': health_metadata.get('health_state'),
        'health_action': health_metadata.get('health_action'),
        'health_failure_kind': health_metadata.get('health_failure_kind'),
        'health_reason': health_metadata.get('health_reason'),
        'health_selected_candidates': health_metadata.get('health_selected_candidates'),
        'health_suppressed_candidates': health_metadata.get('health_suppressed_candidates'),
        'health_probe_candidate': health_metadata.get('health_probe_candidate'),
        'contract_score': contract_score,
        'outcome': outcome,
        'failure_mode': failure_mode,
        'failure_mode_if_any': failure_mode,
        'root_cause_hypothesis': root_cause_hypothesis,
        'follow_up_action': follow_up_action,
        'signal': _first_meaningful_text(metadata.get('signal'), summary),
        'frequency': _first_meaningful_text(metadata.get('frequency')),
        'impact': _first_meaningful_text(metadata.get('impact')),
        'affected_subagents': subagents_text,
        'likely_cause': _first_meaningful_text(metadata.get('likely_cause')),
        'proposed_policy_change': _first_meaningful_text(metadata.get('proposed_policy_change')),
        'priority': _first_meaningful_text(metadata.get('priority')),
        'problem': _first_meaningful_text(metadata.get('problem')),
        'proposed_change': _first_meaningful_text(metadata.get('proposed_change')),
        'scope': _first_meaningful_text(metadata.get('scope')),
        'safety_check': _first_meaningful_text(metadata.get('safety_check')),
        'owner': _first_meaningful_text(metadata.get('owner'), default='Orchestrator'),
        'project_request': project_request,
        'normalized_request': _first_meaningful_text(metadata.get('normalized_request'), project_request),
        'stage': stage,
        'summary': _first_meaningful_text(metadata.get('summary'), summary),
        'completed': summary_completed,
        'in_progress': summary_in_progress,
        'blockers_risks': summary_blockers_risks,
        'next_action': summary_next_action,
        'files_touched': files_touched_text,
        'session_evidence': session_evidence_text,
        'routing_policy_changes': routing_policy_changes,
        'change_applied': change_applied,
        'expected_effect': expected_effect,
        'validation_window': validation_window,
        'observed_result': observed_result,
        'decision': decision,
        'compaction_batch': compaction_batch,
        'session_id': _first_meaningful_text(metadata.get('session_id')),
        'request_group_id': _first_meaningful_text(metadata.get('request_group_id')),
        'cycle_id': _first_meaningful_text(metadata.get('cycle_id')),
        'dedupe_key': _first_meaningful_text(metadata.get('dedupe_key')),
        'curated_checkpoint': 'yes' if metadata.get('curated_checkpoint') else 'no',
    }

    return {
        'defaults': defaults,
        'targets': {
            'Behavior-Log.md': {
                'request_type': request_type,
                'project_request': defaults['project_request'],
                'subagent': subagent_text,
                'model_selection': defaults['model_selection'],
                'routing_mode': defaults['routing_mode'],
                'fallback_override': defaults['fallback_override'],
                'health': defaults['health'],
                'health_workspace_id': defaults['health_workspace_id'],
                'health_session_id': defaults['health_session_id'],
                'health_agent_id': defaults['health_agent_id'],
                'health_task_family': defaults['health_task_family'],
                'health_model_id': defaults['health_model_id'],
                'health_state': defaults['health_state'],
                'health_action': defaults['health_action'],
                'health_failure_kind': defaults['health_failure_kind'],
                'health_reason': defaults['health_reason'],
                'health_selected_candidates': defaults['health_selected_candidates'],
                'health_suppressed_candidates': defaults['health_suppressed_candidates'],
                'health_probe_candidate': defaults['health_probe_candidate'],
                'skills_used': skills_text,
                'prompt_normalization': prompt_normalization,
                'contract_score': defaults['contract_score'],
                'outcome': outcome,
                'failure_mode': defaults['failure_mode'],
                'failure_mode_if_any': defaults['failure_mode_if_any'],
                'root_cause_hypothesis': defaults['root_cause_hypothesis'],
                'follow_up_action': defaults['follow_up_action'],
                'related': related_links['behavior_related'],
                'compaction_batch': compaction_batch,
            },
            'Behavior-Patterns.md': {
                'signal': defaults['signal'],
                'frequency': defaults['frequency'],
                'impact': defaults['impact'],
                'affected_subagents': defaults['affected_subagents'],
                'likely_cause': defaults['likely_cause'],
                'proposed_policy_change': defaults['proposed_policy_change'],
                'status': _first_meaningful_text(metadata.get('pattern_status')),
                'compaction_batch': compaction_batch,
                'evidence': related_links['pattern_evidence'],
            },
            'Learning-Backlog.md': {
                'priority': defaults['priority'],
                'problem': defaults['problem'],
                'proposed_change': defaults['proposed_change'],
                'scope': defaults['scope'],
                'safety_check': defaults['safety_check'],
                'owner': defaults['owner'],
                'status': _first_meaningful_text(metadata.get('learning_status')),
                'linked_pattern': related_links['learning_linked_pattern'],
            },
            'Project-Context-Log.md': {
                'project_request': defaults['project_request'],
                'stage': defaults['stage'],
                'summary': defaults['summary'],
                'completed': defaults['completed'],
                'in_progress': defaults['in_progress'],
                'blockers_risks': defaults['blockers_risks'],
                'next_action': defaults['next_action'],
                'files_touched': defaults['files_touched'],
                'session_evidence': defaults['session_evidence'],
                'routing_policy_changes': defaults['routing_policy_changes'],
                'related': related_links['context_related'],
            },
            'Runbook.md': {
                'date': date,
                'trigger_pattern': _first_meaningful_text(metadata.get('trigger_pattern'), prompt_command),
                'change_applied': defaults['change_applied'],
                'expected_effect': defaults['expected_effect'],
                'validation_window': defaults['validation_window'],
                'observed_result': defaults['observed_result'],
                'decision': defaults['decision'],
                'files_touched': defaults['files_touched'],
                'session_evidence': defaults['session_evidence'],
                'related_entries': related_links['runbook_related_entries'],
            },
            'Skill-Usage-Log.md': {
                'request_type': request_type,
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
    path.write_text(_utf8_backslashreplace_text(header + transcript + "\n"), encoding='utf-8')
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
) -> Dict[str, Any]:
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
    started_at = perf_counter()
    metadata = normalize_checkpoint_metadata(
        summary=summary,
        metadata=metadata or {},
        event_flags=event_flags,
        prompt_command=prompt_command,
    )
    effective_skills = _merge_unique_text_lists(skills or [], metadata.get('skills_used'), metadata.get('skills_used_ordered'))
    initial_full_level = level == 'full'
    requested_full_log = prompt_command in FULL_LOG_COMMANDS
    full_log_allowed, full_log_reason = _has_full_log_evidence(metadata, summary)
    curated_full_log = bool(metadata.get('curated_checkpoint') and (metadata.get('curated_log') or metadata.get('persist_full_log') or requested_full_log))

    if level == 'full' and not curated_full_log:
        level = 'compact'

    if level == 'minimal':
        return {"level": "minimal", "action": "none"}

    if _is_automatic_hook_event(metadata, event_flags) and not bool(prompt_command or curated_full_log):
        return {"level": level, "action": "skipped-auto-hook"}

    if not _should_persist_entry(level, summary, metadata, effective_skills, prompt_command=prompt_command):
        return {"level": level, "action": "skipped-noise"}

    if (requested_full_log or initial_full_level) and not full_log_allowed:
        return {
            "level": 'compact',
            "command": '/info',
            "action": "downgraded-full-log-to-compact",
            "reason": full_log_reason,
        }

    dedupe_root = Path(target_root) if target_root else repo_root
    if not preview and _is_duplicate_curated_checkpoint(dedupe_root, metadata):
        return {"level": level, "action": "skipped-duplicate", "dedupe_key": _first_text(metadata.get('dedupe_key'))}

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
        if not preview and metadata.get('curated_checkpoint'):
            _record_dedupe_key(dedupe_root, _first_text(metadata.get('dedupe_key')))
        telemetry_metadata = _build_cycle_telemetry_metadata(summary, body, effective_skills, metadata, transcript, started_at)
        _append_cycle_telemetry_event(
            base_root=dedupe_root,
            dispatch_path=dispatch_path,
            level=level,
            command=prompt_command,
            summary=summary,
            skills=effective_skills,
            metadata=telemetry_metadata,
            preview=preview,
        )
        if not preview:
            _persist_continuity_checkpoint(dedupe_root, metadata, dispatch_path, prompt_command)
        # After persisting telemetry and curated checkpoint, regenerate knowledge pages (non-blocking)
        _run_synthesize_wiki(repo_root, Path(target_root) if target_root else None, preview)
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
        if not preview and metadata.get('curated_checkpoint'):
            _record_dedupe_key(dedupe_root, _first_text(metadata.get('dedupe_key')))
        telemetry_metadata = _build_cycle_telemetry_metadata(summary, body, effective_skills, metadata, transcript, started_at)
        _append_cycle_telemetry_event(
            base_root=dedupe_root,
            dispatch_path=dispatch_path,
            level='compact',
            command='/info',
            summary=summary,
            skills=effective_skills,
            metadata=telemetry_metadata,
            preview=preview,
        )
        if not preview:
            _persist_continuity_checkpoint(dedupe_root, metadata, dispatch_path, '/info')
        # Trigger background knowledge generation for workspace wiki
        _run_synthesize_wiki(repo_root, Path(target_root) if target_root else None, preview)
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
        if not preview and metadata.get('curated_checkpoint'):
            _record_dedupe_key(dedupe_root, _first_text(metadata.get('dedupe_key')))
        telemetry_metadata = _build_cycle_telemetry_metadata(summary, body, effective_skills, metadata, transcript, started_at)
        _append_cycle_telemetry_event(
            base_root=dedupe_root,
            dispatch_path=dispatch_path,
            level='full',
            command='/full-log',
            summary=summary,
            skills=effective_skills,
            metadata=telemetry_metadata,
            preview=preview,
        )
        if not preview:
            _persist_continuity_checkpoint(dedupe_root, metadata, dispatch_path, '/full-log')
        # Trigger background knowledge generation for workspace wiki
        _run_synthesize_wiki(repo_root, Path(target_root) if target_root else None, preview)
        return {
            "level": "full",
            "command": "/full-log",
            "returncode": str(proc.returncode),
            "transcript": str(transcript_path) if transcript_path else None,
        }

    return {"level": level, "action": "unhandled"}


__all__ = ["choose_logging_level", "log_cycle", "normalize_checkpoint_metadata", "write_transcript"]
