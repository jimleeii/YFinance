#!/usr/bin/env python3
"""Generate JAMES-style knowledge pages from the Orchestrator wiki layer."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_logs  # noqa: E402


GLOSSARY = {
    'Behavior log': 'The canonical observation stream for completed user-visible orchestration cycles.',
    'Compaction batch': 'A batch identifier used to connect compacted observations, patterns, and backlog items.',
    'Contract score': 'The acceptance-quality score assigned to a cycle or subagent result.',
    'Curated checkpoint': 'A high-signal checkpoint with enough evidence to justify multi-page wiki persistence.',
    'Cycle ID': 'The immutable orchestration identifier propagated across logs, transcripts, and follow-up actions.',
    'Dispatch path': 'The execution mode selected for a cycle such as direct, single-agent, multi-agent, or concurrent.',
    'Fallback': 'A runtime downgrade or alternate execution path taken when the preferred route is unavailable or low quality.',
    'Learning backlog': 'The actionable improvement queue derived from recurring patterns and operational pain.',
    'Routing quality': 'The quality signal for how well the selected path matched the work and produced successful outcomes.',
    'Skill usage': 'The ordered skill/tooling record that explains how a cycle was executed and what should be reused.',
}


def _find_repo_root(start: Path | None = None) -> Path:
    cur = (start or Path(__file__)).resolve()
    cur = cur if cur.is_dir() else cur.parent
    for _ in range(20):
        if (cur / '.git').exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(__file__).resolve().parents[3]


def _format_metric_rows(items: list[dict[str, Any]], headers: list[tuple[str, str]]) -> list[str]:
    if not items:
        return ['_No data available yet._']
    lines = ['| ' + ' | '.join(label for _, label in headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
    for item in items:
        lines.append('| ' + ' | '.join(str(item.get(key, '')) for key, _ in headers) + ' |')
    return lines


def _format_top_skills(skill_counts: dict[str, int]) -> list[str]:
    if not skill_counts:
        return ['- No skill usage data yet.']
    return [f'- `{name}` — {count} cycle(s)' for name, count in list(skill_counts.items())[:10]]


def _format_count_rows(counts: dict[str, int], key_name: str) -> list[dict[str, Any]]:
    return [{key_name: name, 'count': count} for name, count in counts.items()]


def _format_anomaly_samples(samples: list[dict[str, Any]]) -> list[str]:
    if not samples:
        return ['- No telemetry anomalies detected yet.']
    lines: list[str] = []
    for sample in samples:
        sample_type = sample.get('type', 'anomaly')
        if sample_type == 'duplicate_fingerprint':
            record_indices = sample.get('record_indices', [])
            provenance = f" at record indices {record_indices}" if record_indices else ''
            lines.append(
                f"- `duplicate_fingerprint` — `{sample.get('fingerprint', '')}` appeared {sample.get('occurrences', 0)} time(s){provenance}."
            )
        elif sample_type == 'incomplete_record':
            missing_fields = ', '.join(sample.get('missing_fields', []))
            cycle_id = sample.get('cycle_id')
            subject = f"cycle `{cycle_id}`" if cycle_id else f"record {sample.get('record_index', '?')}"
            lines.append(f"- `incomplete_record` — {subject} missing {missing_fields}.")
        else:
            lines.append(f"- `{sample_type}` — record {sample.get('record_index', '?')}")
    return lines


def _format_glossary() -> list[str]:
    return [f'- **{term}** — {definition}' for term, definition in sorted(GLOSSARY.items())]


def _knowledge_paths(wiki_root: Path) -> dict[str, Path]:
    knowledge_root = wiki_root / 'knowledge'
    return {
        'index': knowledge_root / 'Index.md',
        'glossary': knowledge_root / 'Glossary.md',
        'skills': knowledge_root / 'Learned-Skills.md',
        'routing': knowledge_root / 'Learned-Routing.md',
        'models': knowledge_root / 'Learned-Model-Selection.md',
        'telemetry': knowledge_root / 'Learned-Telemetry.md',
    }


def generate_knowledge_pages(wiki_root: Path, cycles: int = 30, stale_days: int = 30) -> dict[Path, str]:
    metrics = analyze_logs.collect_metrics(wiki_root, cycles=cycles, stale_days=stale_days)
    knowledge_paths = _knowledge_paths(wiki_root)
    knowledge_paths['index'].parent.mkdir(parents=True, exist_ok=True)

    pattern_rows = metrics.get('pattern_signal_summary', [])
    routing_rows = metrics.get('routing_quality', [])
    model_rows = metrics.get('model_quality', [])
    feedback_rows = metrics.get('contract_feedback', {}).get('policy_candidates', [])
    telemetry_summary = metrics.get('telemetry_summary', {})
    dispatch_rows = _format_count_rows(telemetry_summary.get('dispatch_counts', {}), 'dispatch_path')
    level_rows = _format_count_rows(telemetry_summary.get('level_counts', {}), 'level')
    command_rows = _format_count_rows(telemetry_summary.get('command_counts', {}), 'command')
    telemetry_source_state = telemetry_summary.get('source_state', 'missing')

    pages: dict[Path, str] = {}
    pages[knowledge_paths['index']] = '\n'.join([
        '# Orchestrator Knowledge Index',
        '',
        'This generated layer synthesizes the operational wiki into reusable knowledge pages.',
        '',
        '## Snapshot',
        '',
        f"- Generated: {metrics['generated_utc']}",
        f"- Cycles analyzed: {metrics['cycle_count']}",
        f"- Average contract score: {metrics.get('avg_contract_score')}",
        f"- Cycle success rate: {metrics.get('cycle_success_rate')}",
        f"- Stale backlog items: {metrics.get('stale_backlog_count')}",
        '',
        '## Knowledge Pages',
        '',
        '- [Glossary](Glossary.md)',
        '- [Learned Skills](Learned-Skills.md)',
        '- [Learned Routing](Learned-Routing.md)',
        '- [Learned Model Selection](Learned-Model-Selection.md)',
        '- [Learned Telemetry](Learned-Telemetry.md)',
        '',
        '## Telemetry Snapshot',
        '',
        f"- Records processed: {telemetry_summary.get('record_count', 0)}",
        f"- Unique cycles: {telemetry_summary.get('unique_cycle_count', 0)}",
        f"- Duplicate fingerprints: {telemetry_summary.get('duplicate_fingerprint_count', 0)}",
        f"- Incomplete records: {telemetry_summary.get('incomplete_record_count', 0)}",
        f"- Source state: {telemetry_source_state}",
        '',
        '## Top Pattern Signals',
        '',
        *_format_metric_rows(pattern_rows[:8], [('signal', 'Signal'), ('count', 'Count'), ('latest_status', 'Latest Status'), ('impact', 'Impact')]),
        '',
        '## Backlog + Policy Feed',
        '',
        *(
            [f"- `{item.get('label', 'manual-review')}` — {item.get('count', 0)} occurrence(s), avg score {item.get('avg_contract_score')}" for item in feedback_rows[:8]]
            if feedback_rows else
            ['- No policy feedback candidates yet.']
        ),
        '',
        '## Retrieval',
        '',
        '- Use `scripts/search_wiki.py <query>` to search the generated knowledge pages and the wiki layer together.',
        '',
    ]) + '\n'

    if telemetry_source_state == 'missing':
        telemetry_intro = 'No telemetry JSONL stream was available when this page was generated, so this page acts as a stable placeholder until telemetry arrives.'
    elif telemetry_source_state == 'present_no_valid_records':
        telemetry_intro = 'Telemetry JSONL was present, but no valid telemetry records were parsed yet, so this page reflects the source-state gap instead of a missing file.'
    else:
        telemetry_intro = 'This telemetry summary distills the Phase 1 telemetry JSONL lane into markdown-native knowledge.'

    pages[knowledge_paths['telemetry']] = '\n'.join([
        '# What We Learned — Telemetry',
        '',
        telemetry_intro,
        '',
        '## Snapshot',
        '',
        f"- Schema version: {telemetry_summary.get('schema_version', 'orchestrator.telemetry.index.v1')}",
        f"- Generated: {telemetry_summary.get('generated_utc')}",
        f"- Source path: `{telemetry_summary.get('source_path', 'telemetry/cycles.jsonl')}`",
        f"- Source state: {telemetry_summary.get('source_state', 'missing')}",
        f"- Records: {telemetry_summary.get('record_count', 0)}",
        f"- Unique cycles: {telemetry_summary.get('unique_cycle_count', 0)}",
        f"- Duplicate fingerprints: {telemetry_summary.get('duplicate_fingerprint_count', 0)}",
        f"- Incomplete records: {telemetry_summary.get('incomplete_record_count', 0)}",
        '',
        '## Dispatch Counts',
        '',
        *_format_metric_rows(dispatch_rows, [('dispatch_path', 'Dispatch Path'), ('count', 'Count')]),
        '',
        '## Level Counts',
        '',
        *_format_metric_rows(level_rows, [('level', 'Level'), ('count', 'Count')]),
        '',
        '## Command Counts',
        '',
        *_format_metric_rows(command_rows, [('command', 'Command'), ('count', 'Count')]),
        '',
        '## Anomaly Samples',
        '',
        *_format_anomaly_samples(telemetry_summary.get('anomaly_samples', [])),
        '',
    ]) + '\n'

    pages[knowledge_paths['glossary']] = '\n'.join([
        '# Orchestrator Glossary',
        '',
        'Generated glossary of recurring orchestration terms.',
        '',
        '## Terms',
        '',
        *_format_glossary(),
        '',
    ]) + '\n'

    pages[knowledge_paths['skills']] = '\n'.join([
        '# What We Learned — Skills',
        '',
        'This page summarizes reusable skill signals from recent cycles.',
        '',
        '## Top Skills',
        '',
        *_format_top_skills(metrics.get('skill_usage_counts', {})),
        '',
        '## Skill Reuse Guidance',
        '',
        *(
            [f"- `{item.get('skill')}` — impact `{item.get('dominant_outcome')}` across {item.get('samples')} sample(s)." for item in metrics.get('skill_quality', [])[:8]]
            if metrics.get('skill_quality') else
            ['- Not enough skill-usage evidence to infer reuse guidance yet.']
        ),
        '',
    ]) + '\n'

    pages[knowledge_paths['routing']] = '\n'.join([
        '# What We Learned — Routing',
        '',
        'Routing quality trends distilled from behavior + skill usage logs.',
        '',
        '## Routing Quality',
        '',
        *_format_metric_rows(routing_rows, [('routing_path', 'Routing Path'), ('samples', 'Samples'), ('avg_contract_score', 'Avg Score'), ('success_rate', 'Success Rate')]),
        '',
        '## Current Routing Signals',
        '',
        *(
            [f"- `{item.get('signal')}` appears {item.get('count')} time(s) and currently trends `{item.get('latest_status')}`." for item in pattern_rows[:8]]
            if pattern_rows else
            ['- No recurring routing-pattern signal detected yet.']
        ),
        '',
    ]) + '\n'

    pages[knowledge_paths['models']] = '\n'.join([
        '# What We Learned — Model Selection',
        '',
        'Model-quality tracking generated from recent behavior observations.',
        '',
        '## Model Quality Over Time',
        '',
        *_format_metric_rows(model_rows, [('model', 'Model'), ('samples', 'Samples'), ('avg_contract_score', 'Avg Score'), ('success_rate', 'Success Rate'), ('low_score_count', 'Low Scores')]),
        '',
        '## Contract Feedback',
        '',
        *(
            [f"- `{item.get('label', 'manual-review')}` — {item.get('count', 0)} occurrence(s), latest action: {item.get('recommended_action', 'review')}." for item in feedback_rows[:8]]
            if feedback_rows else
            ['- No contract-score feedback candidates yet.']
        ),
        '',
    ]) + '\n'

    for path, content in pages.items():
        path.write_text(content, encoding='utf-8')

    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generate knowledge pages from the Orchestrator wiki layer')
    parser.add_argument('--wiki', help='Path to .wiki/orchestrator; auto-detected when omitted')
    parser.add_argument('--cycles', type=int, default=30, help='Trailing cycle window to analyze')
    parser.add_argument('--stale-days', type=int, default=30, help='Backlog staleness threshold')
    args = parser.parse_args(argv)

    repo_root = _find_repo_root()
    wiki_root = Path(args.wiki).resolve() if args.wiki else repo_root / '.wiki' / 'orchestrator'
    pages = generate_knowledge_pages(wiki_root, cycles=args.cycles, stale_days=args.stale_days)
    for path in pages:
        print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
