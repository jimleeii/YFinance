#!/usr/bin/env python3
"""Analyze orchestrator wiki logs and emit structured operational signals.

This script keeps the original summary metrics, but also produces richer outputs
for Phase 2/3 knowledge synthesis:
- pattern signal summaries
- backlog status and priority summaries
- routing quality
- model selection quality over time
- contract feedback candidates that can inform policy updates
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


_RE_CYCLE_ID = re.compile(r"\bCYC-\d{8}-\d{6}-[0-9A-F]{4}\b")
_RE_BEHAVIOR_ID = re.compile(r"^###\s+(OBS-\S+)", re.MULTILINE)
_RE_PATTERN_ID = re.compile(r"^###\s+(PAT-\S+)", re.MULTILINE)
_RE_BACKLOG_ID = re.compile(r"^###\s+(LRN-\S+)", re.MULTILINE)
_RE_CONTEXT_ID = re.compile(r"^###\s+(CTX-\S+)", re.MULTILINE)
_RE_RUNBOOK_ID = re.compile(r"^###\s+(CHG-\S+)", re.MULTILINE)
_RE_SKILL_ID = re.compile(r"^###\s+((?:SKL|SKILL)-\S+)", re.MULTILINE)
_RE_KEY_VALUE = re.compile(r"^\s*-\s+(?P<key>[^:]+):\s*(?P<value>.*)$")
_RE_DATE = re.compile(r"(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?)?)")
_RE_MODEL_SELECTION = re.compile(r"selected_model=([^|]+)")
_RE_CONTRACT_SCORE = re.compile(r"(\d+(?:\.\d+)?)")

_TELEMETRY_INDEX_SCHEMA_VERSION = 'orchestrator.telemetry.index.v1'
_TELEMETRY_SUMMARY_CACHE_SCHEMA_VERSION = 'orchestrator.telemetry.summary-cache.v1'
_TELEMETRY_SUMMARY_CACHE_NAME = 'summary-cache.json'
_TELEMETRY_SUMMARY_CACHE_TTL = timedelta(hours=24)
_TELEMETRY_REQUIRED_FIELDS = ('recorded_at_utc', 'dispatch_path', 'level', 'command', 'cycle_id', 'fingerprint')
_TELEMETRY_MAX_ANOMALY_SAMPLES = 5
_RE_CACHE_UTC = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$')


@dataclass
class EntryRecord:
    entry_id: str
    fields: dict[str, str]
    raw: str
    cycle_id: str
    timestamp: datetime | None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _find_default_wiki(start: Path | None = None) -> Path:
    cur = (start or Path(__file__)).resolve()
    cur = cur if cur.is_dir() else cur.parent
    for _ in range(20):
        if (cur / '.git').exists():
            return cur / '.wiki' / 'orchestrator'
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path('.wiki/orchestrator')


def _normalize_key(key: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', key.strip().lower()).strip('_')


def _parse_datetime(value: str) -> datetime | None:
    match = _RE_DATE.search(value)
    if not match:
        return None
    raw = match.group(1)
    if raw.endswith('Z'):
        raw = raw[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.strptime(raw, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_cached_utc(value: str) -> datetime | None:
    candidate = (value or '').strip()
    if not candidate or not _RE_CACHE_UTC.fullmatch(candidate):
        return None
    if candidate.endswith('Z'):
        candidate = candidate[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _split_entries(text: str, heading_re: re.Pattern[str]) -> list[tuple[str, str]]:
    matches = list(heading_re.finditer(text))
    if not matches:
        return []
    entries: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entries.append((match.group(1), text[start:end]))
    return entries


def _parse_fields(block: str) -> dict[str, str]:
    lines = block.splitlines()
    fields: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = _RE_KEY_VALUE.match(lines[index])
        if not match:
            index += 1
            continue
        key = _normalize_key(match.group('key'))
        value = match.group('value').rstrip()
        if value == '|':
            index += 1
            collected: list[str] = []
            while index < len(lines):
                next_line = lines[index]
                if _RE_KEY_VALUE.match(next_line):
                    index -= 1
                    break
                if next_line.startswith('  ') or next_line.startswith('\t'):
                    collected.append(next_line.strip())
                elif next_line.strip():
                    collected.append(next_line.strip())
                index += 1
            value = '\n'.join(collected).strip()
        fields[key] = value.strip()
        index += 1
    return fields


def _records(text: str, heading_re: re.Pattern[str]) -> list[EntryRecord]:
    records: list[EntryRecord] = []
    for entry_id, block in _split_entries(text, heading_re):
        fields = _parse_fields(block)
        timestamp = _parse_datetime(fields.get('timestamp_utc', '') or fields.get('date', ''))
        cycle_id_match = _RE_CYCLE_ID.search(block)
        records.append(
            EntryRecord(
                entry_id=entry_id,
                fields=fields,
                raw=block,
                cycle_id=cycle_id_match.group(0) if cycle_id_match else '',
                timestamp=timestamp,
            )
        )
    return records


def _trailing_window(records: list[EntryRecord], window: int) -> list[EntryRecord]:
    return records[-window:] if window > 0 else records


def _score_value(value: str) -> float | None:
    match = _RE_CONTRACT_SCORE.search(value or '')
    return float(match.group(1)) if match else None


def _model_name(fields: dict[str, str]) -> str:
    model_selection = fields.get('model_selection', '')
    match = _RE_MODEL_SELECTION.search(model_selection)
    if match:
        return match.group(1).strip()
    return 'unknown'


def _success_value(value: str) -> bool | None:
    normalized = (value or '').strip().lower()
    if normalized in {'pass', 'success', 'succeeded'}:
        return True
    if normalized in {'revise', 'block', 'failure', 'failed'}:
        return False
    return None


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(counter.most_common())


def _empty_telemetry_summary(source_path: str, source_state: str = 'missing') -> dict[str, Any]:
    return {
        'schema_version': _TELEMETRY_INDEX_SCHEMA_VERSION,
        'generated_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'source_path': source_path,
        'source_state': source_state,
        'record_count': 0,
        'unique_cycle_count': 0,
        'dispatch_counts': {},
        'level_counts': {},
        'command_counts': {},
        'duplicate_fingerprint_count': 0,
        'incomplete_record_count': 0,
        'anomaly_samples': [],
    }


def _telemetry_summary_cache_path(wiki: Path) -> Path:
    return wiki / 'telemetry' / _TELEMETRY_SUMMARY_CACHE_NAME


def _telemetry_source_signature(telemetry_path: Path, source_path: str) -> dict[str, Any]:
    stat_result = telemetry_path.stat()
    return {
        'source_path': source_path,
        'st_mtime_ns': stat_result.st_mtime_ns,
        'st_size': stat_result.st_size,
    }


def _load_cached_telemetry_summary(cache_path: Path, source_signature: dict[str, Any]) -> dict[str, Any] | None:
    try:
        cache_data = json.loads(cache_path.read_text(encoding='utf-8', errors='replace'))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(cache_data, dict):
        return None
    if cache_data.get('schema_version') != _TELEMETRY_SUMMARY_CACHE_SCHEMA_VERSION:
        return None
    if cache_data.get('source_signature') != source_signature:
        return None

    cached_utc = _parse_cached_utc(str(cache_data.get('cached_utc', '') or ''))
    if cached_utc is None:
        return None
    now = datetime.now(timezone.utc)
    if cached_utc > now:
        return None
    if now - cached_utc > _TELEMETRY_SUMMARY_CACHE_TTL:
        return None

    telemetry_summary = cache_data.get('telemetry_summary')
    return telemetry_summary if isinstance(telemetry_summary, dict) else None


def _write_cached_telemetry_summary(cache_path: Path, source_signature: dict[str, Any], telemetry_summary: dict[str, Any]) -> None:
    payload = {
        'schema_version': _TELEMETRY_SUMMARY_CACHE_SCHEMA_VERSION,
        'source_signature': source_signature,
        'cached_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'telemetry_summary': telemetry_summary,
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    except OSError:
        return


def _collect_telemetry_summary(telemetry_path: Path, source_path: str) -> dict[str, Any]:
    summary = _empty_telemetry_summary(source_path, 'present_no_valid_records')

    if not telemetry_path.is_file():
        return _empty_telemetry_summary(source_path)

    try:
        text = telemetry_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return summary

    dispatch_counts: Counter[str] = Counter()
    level_counts: Counter[str] = Counter()
    command_counts: Counter[str] = Counter()
    cycle_ids: set[str] = set()
    fingerprint_counts: Counter[str] = Counter()
    fingerprint_record_indices: dict[str, list[int]] = defaultdict(list)
    anomaly_samples: list[dict[str, Any]] = []

    for record_index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            summary['incomplete_record_count'] += 1
            if len(anomaly_samples) < _TELEMETRY_MAX_ANOMALY_SAMPLES:
                anomaly_samples.append({
                    'type': 'invalid_json',
                    'record_index': record_index,
                    'reason': getattr(exc, 'msg', 'invalid JSON'),
                })
            continue

        if not isinstance(payload, dict):
            summary['incomplete_record_count'] += 1
            if len(anomaly_samples) < _TELEMETRY_MAX_ANOMALY_SAMPLES:
                anomaly_samples.append({
                    'type': 'non_object_record',
                    'record_index': record_index,
                    'reason': 'expected JSON object',
                })
            continue

        summary['record_count'] += 1

        extracted: dict[str, str] = {}
        missing_fields: list[str] = []
        for field in _TELEMETRY_REQUIRED_FIELDS:
            value = payload.get(field, '')
            text_value = str(value).strip() if value is not None else ''
            extracted[field] = text_value
            if not text_value:
                missing_fields.append(field)

        dispatch_path = extracted['dispatch_path']
        level = extracted['level']
        command = extracted['command']
        cycle_id = extracted['cycle_id']
        fingerprint = extracted['fingerprint']

        if cycle_id:
            cycle_ids.add(cycle_id)
        if dispatch_path:
            dispatch_counts[dispatch_path] += 1
        if level:
            level_counts[level] += 1
        if command:
            command_counts[command] += 1
        if fingerprint:
            fingerprint_counts[fingerprint] += 1
            fingerprint_record_indices[fingerprint].append(record_index)

        if missing_fields:
            summary['incomplete_record_count'] += 1
            if len(anomaly_samples) < _TELEMETRY_MAX_ANOMALY_SAMPLES:
                anomaly: dict[str, Any] = {
                    'type': 'incomplete_record',
                    'record_index': record_index,
                    'missing_fields': missing_fields,
                }
                if cycle_id:
                    anomaly['cycle_id'] = cycle_id
                if fingerprint:
                    anomaly['fingerprint'] = fingerprint
                anomaly_samples.append(anomaly)

    duplicate_fingerprint_count = 0
    for fingerprint, occurrences in fingerprint_counts.items():
        if occurrences > 1:
            duplicate_fingerprint_count += 1
            if len(anomaly_samples) < _TELEMETRY_MAX_ANOMALY_SAMPLES:
                anomaly_samples.append({
                    'type': 'duplicate_fingerprint',
                    'fingerprint': fingerprint,
                    'occurrences': occurrences,
                    'record_indices': list(fingerprint_record_indices.get(fingerprint, [])),
                })

    summary['unique_cycle_count'] = len(cycle_ids)
    summary['dispatch_counts'] = _counter_dict(dispatch_counts)
    summary['level_counts'] = _counter_dict(level_counts)
    summary['command_counts'] = _counter_dict(command_counts)
    summary['duplicate_fingerprint_count'] = duplicate_fingerprint_count
    summary['anomaly_samples'] = anomaly_samples
    if summary['record_count'] > 0:
        summary['source_state'] = 'present_with_records'
    return summary


def _collect_cached_telemetry_summary(wiki: Path) -> dict[str, Any]:
    telemetry_path = wiki / 'telemetry' / 'cycles.jsonl'
    source_path = telemetry_path.relative_to(wiki).as_posix()

    if not telemetry_path.is_file():
        return _empty_telemetry_summary(source_path)

    try:
        source_signature = _telemetry_source_signature(telemetry_path, source_path)
    except OSError:
        return _empty_telemetry_summary(source_path, 'present_no_valid_records')

    cache_path = _telemetry_summary_cache_path(wiki)
    cached_summary = _load_cached_telemetry_summary(cache_path, source_signature)
    if cached_summary is not None:
        summary = dict(cached_summary)
        summary['generated_utc'] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return summary

    summary = _collect_telemetry_summary(telemetry_path, source_path)
    _write_cached_telemetry_summary(cache_path, source_signature, summary)
    return summary


def _pattern_signal_summary(pattern_records: Iterable[EntryRecord]) -> list[dict[str, Any]]:
    grouped: dict[str, list[EntryRecord]] = defaultdict(list)
    for record in pattern_records:
        signal = record.fields.get('signal', '').strip() or 'unspecified'
        grouped[signal].append(record)
    results: list[dict[str, Any]] = []
    for signal, records in grouped.items():
        latest = records[-1]
        results.append({
            'signal': signal,
            'count': len(records),
            'latest_status': latest.fields.get('status', ''),
            'impact': latest.fields.get('impact', ''),
        })
    results.sort(key=lambda item: (-item['count'], item['signal']))
    return results


def _backlog_summary(backlog_records: Iterable[EntryRecord]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    for record in backlog_records:
        status = record.fields.get('status', '').strip().lower()
        priority = record.fields.get('priority', '').strip().lower()
        scope = record.fields.get('scope', '').strip().lower()
        if status:
            status_counts[status] += 1
        if priority:
            priority_counts[priority] += 1
        if scope:
            scope_counts[scope] += 1
    return {
        'status_counts': _counter_dict(status_counts),
        'priority_counts': _counter_dict(priority_counts),
        'scope_counts': _counter_dict(scope_counts),
    }


def _skill_usage_summary(skill_records: Iterable[EntryRecord]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    counts: Counter[str] = Counter()
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for record in skill_records:
        raw = record.fields.get('skills_used_ordered') or record.fields.get('skills_used') or ''
        outcome_impact = record.fields.get('outcome_impact', '').strip().lower() or 'unknown'
        for skill in [item.strip() for item in raw.split(',') if item.strip()]:
            counts[skill] += 1
            grouped[skill][outcome_impact] += 1
    quality: list[dict[str, Any]] = []
    for skill, impact_counts in grouped.items():
        dominant_outcome = impact_counts.most_common(1)[0][0] if impact_counts else 'unknown'
        quality.append({'skill': skill, 'samples': sum(impact_counts.values()), 'dominant_outcome': dominant_outcome})
    quality.sort(key=lambda item: (-item['samples'], item['skill']))
    return _counter_dict(counts), quality


def _model_quality(behavior_records: Iterable[EntryRecord]) -> list[dict[str, Any]]:
    grouped: dict[str, list[EntryRecord]] = defaultdict(list)
    for record in behavior_records:
        grouped[_model_name(record.fields)].append(record)
    results: list[dict[str, Any]] = []
    for model, records in grouped.items():
        scores = [_score_value(record.fields.get('contract_score', '')) for record in records]
        numeric_scores = [score for score in scores if score is not None]
        success_values = [_success_value(record.fields.get('outcome', '')) for record in records]
        rated = [value for value in success_values if value is not None]
        results.append({
            'model': model,
            'samples': len(records),
            'avg_contract_score': round(sum(numeric_scores) / len(numeric_scores), 1) if numeric_scores else None,
            'success_rate': round(sum(1 for value in rated if value) / len(rated), 3) if rated else None,
            'low_score_count': sum(1 for score in numeric_scores if score < 80),
        })
    results.sort(key=lambda item: (item['avg_contract_score'] is None, -(item['avg_contract_score'] or -1), item['model']))
    return results


def _routing_quality(behavior_records: Iterable[EntryRecord], skill_records: Iterable[EntryRecord]) -> list[dict[str, Any]]:
    cycle_to_behavior = {record.cycle_id: record for record in behavior_records if record.cycle_id}
    grouped_scores: dict[str, list[float]] = defaultdict(list)
    grouped_outcomes: dict[str, list[bool]] = defaultdict(list)
    grouped_samples: Counter[str] = Counter()

    for record in skill_records:
        routing_path = record.fields.get('routing_path', '').strip() or 'unknown'
        grouped_samples[routing_path] += 1
        behavior = cycle_to_behavior.get(record.cycle_id)
        if behavior:
            score = _score_value(behavior.fields.get('contract_score', ''))
            success = _success_value(behavior.fields.get('outcome', ''))
            if score is not None:
                grouped_scores[routing_path].append(score)
            if success is not None:
                grouped_outcomes[routing_path].append(success)

    results: list[dict[str, Any]] = []
    for routing_path in grouped_samples:
        scores = grouped_scores[routing_path]
        outcomes = grouped_outcomes[routing_path]
        results.append({
            'routing_path': routing_path,
            'samples': grouped_samples[routing_path],
            'avg_contract_score': round(sum(scores) / len(scores), 1) if scores else None,
            'success_rate': round(sum(1 for outcome in outcomes if outcome) / len(outcomes), 3) if outcomes else None,
        })
    results.sort(key=lambda item: (-item['samples'], item['routing_path']))
    return results


def _contract_feedback(behavior_records: Iterable[EntryRecord]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in behavior_records:
        score = _score_value(record.fields.get('contract_score', ''))
        outcome = _success_value(record.fields.get('outcome', ''))
        failure_mode = record.fields.get('failure_mode_if_any') or record.fields.get('failure_mode') or ''
        root_cause = record.fields.get('root_cause_hypothesis', '')
        follow_up = record.fields.get('follow_up_action', '')
        if score is None and outcome is not False and not failure_mode:
            continue
        if score is not None and score >= 80 and outcome is not False and not failure_mode:
            continue
        label = follow_up or root_cause or failure_mode or 'manual-review'
        item = {
            'entry_id': record.entry_id,
            'cycle_id': record.cycle_id,
            'contract_score': score,
            'failure_mode': failure_mode,
            'root_cause_hypothesis': root_cause,
            'follow_up_action': follow_up,
            'label': label,
        }
        failures.append(item)
        grouped[label].append(item)

    policy_candidates: list[dict[str, Any]] = []
    for label, items in grouped.items():
        scores = [item['contract_score'] for item in items if item['contract_score'] is not None]
        policy_candidates.append({
            'label': label,
            'count': len(items),
            'avg_contract_score': round(sum(scores) / len(scores), 1) if scores else None,
            'recommended_action': 'update-policy' if len(items) > 1 else 'review',
        })
    policy_candidates.sort(key=lambda item: (-item['count'], item['label']))
    return {'failures': failures, 'policy_candidates': policy_candidates}


def _behavior_summary(behavior_records: list[EntryRecord]) -> dict[str, Any]:
    scores = [_score_value(record.fields.get('contract_score', '')) for record in behavior_records]
    numeric_scores = [score for score in scores if score is not None]
    outcomes = [_success_value(record.fields.get('outcome', '')) for record in behavior_records]
    rated_outcomes = [value for value in outcomes if value is not None]
    distribution = {'fail': 0, 'low': 0, 'ok': 0, 'good': 0}
    for score in numeric_scores:
        if score < 70:
            distribution['fail'] += 1
        elif score < 80:
            distribution['low'] += 1
        elif score < 90:
            distribution['ok'] += 1
        else:
            distribution['good'] += 1
    return {
        'cycle_count': len(behavior_records),
        'avg_contract_score': round(sum(numeric_scores) / len(numeric_scores), 1) if numeric_scores else None,
        'score_distribution': distribution,
        'scores_sampled': len(numeric_scores),
        'model_escalation_count': sum(1 for record in behavior_records if 'tier_override=true' in record.raw.lower()),
        'cycle_success_rate': round(sum(1 for value in rated_outcomes if value) / len(rated_outcomes), 3) if rated_outcomes else None,
        'status_counts': {
            'success': sum(1 for value in rated_outcomes if value),
            'failure': sum(1 for value in rated_outcomes if value is False),
        },
    }


def count_stale_backlog(text: str, stale_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stale = 0
    for record in _records(text, _RE_BACKLOG_ID):
        record_dt = record.timestamp or _parse_datetime(record.raw)
        if record_dt and record_dt < cutoff:
            stale += 1
    return stale


def collect_metrics(wiki: Path, cycles: int = 30, stale_days: int = 30) -> dict[str, Any]:
    behavior_records = _trailing_window(_records(_read(wiki / 'Behavior-Log.md'), _RE_BEHAVIOR_ID), cycles)
    skill_records = _trailing_window(_records(_read(wiki / 'Skill-Usage-Log.md'), _RE_SKILL_ID), cycles)
    pattern_records = _records(_read(wiki / 'Behavior-Patterns.md'), _RE_PATTERN_ID)
    backlog_text = _read(wiki / 'Learning-Backlog.md')
    backlog_records = _records(backlog_text, _RE_BACKLOG_ID)
    _records(_read(wiki / 'Project-Context-Log.md'), _RE_CONTEXT_ID)
    _records(_read(wiki / 'Runbook.md'), _RE_RUNBOOK_ID)

    behavior_summary = _behavior_summary(behavior_records)
    skill_counts, skill_quality = _skill_usage_summary(skill_records)
    contract_feedback = _contract_feedback(behavior_records)

    return {
        'generated_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'window_cycles': cycles,
        'stale_days': stale_days,
        **behavior_summary,
        'skill_usage_counts': skill_counts,
        'skill_quality': skill_quality,
        'stale_backlog_count': count_stale_backlog(backlog_text, stale_days),
        'pattern_signal_summary': _pattern_signal_summary(pattern_records),
        'backlog_summary': _backlog_summary(backlog_records),
        'model_quality': _model_quality(behavior_records),
        'routing_quality': _routing_quality(behavior_records, skill_records),
        'contract_feedback': contract_feedback,
        'telemetry_summary': _collect_cached_telemetry_summary(wiki),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Analyze orchestrator wiki logs and output metrics JSON')
    parser.add_argument('--wiki', default=str(_find_default_wiki()), help='Path to .wiki/orchestrator directory')
    parser.add_argument('--cycles', type=int, default=30, help='Number of trailing cycles to analyze')
    parser.add_argument('--stale-days', type=int, default=30, help='Backlog staleness threshold in days')
    parser.add_argument('--output', help='Write JSON to this file instead of stdout')
    args = parser.parse_args(argv)

    wiki = Path(args.wiki)
    if not wiki.is_dir():
        print(f'error: wiki directory not found: {wiki}', file=sys.stderr)
        return 1

    metrics = collect_metrics(wiki, cycles=args.cycles, stale_days=args.stale_days)
    output = json.dumps(metrics, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output + '\n', encoding='utf-8')
        print(f'Metrics written to {args.output}', file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
