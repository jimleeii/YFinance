from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))


def _load_module(module_name: str, relative_path: Path):
    module_path = ORCHESTRATOR_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load module from {module_path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


analyze_logs = _load_module('orchestrator_analyze_logs_test', Path('scripts') / 'analyze_logs.py')
synthesize_wiki = _load_module('orchestrator_synthesize_wiki_test', Path('scripts') / 'synthesize_wiki.py')
search_wiki = _load_module('orchestrator_search_wiki_test', Path('scripts') / 'search_wiki.py')


BEHAVIOR_LOG = """# Behavior-Log.md

### OBS-20260524-101500

- Timestamp (UTC): 2026-05-24T10:15:00+00:00
- Project Request: Stabilize prompt mappings
- Model Selection: selected_model=gpt-5.4-mini | task_type=implementation | criticality=P1
- Contract Score: 92
- Outcome: pass
- Follow-up Action: Keep the explicit registry approach
- Failure Mode (if any):
- Root Cause Hypothesis: hard-coded mapping drift
- Related: [Behavior-Patterns](Behavior-Patterns.md#PAT-20260524-101500)
Cycle: CYC-20260524-101500-ABCD

### OBS-20260524-111500

- Timestamp (UTC): 2026-05-24T11:15:00+00:00
- Project Request: Improve routing quality
- Model Selection: selected_model=gpt-5.4 | task_type=analysis | criticality=P1
- Contract Score: 74
- Outcome: revise
- Failure Mode (if any): routing mismatch
- Root Cause Hypothesis: missing prompt registry validation
- Follow-up Action: tighten validator and knowledge synthesis
Cycle: CYC-20260524-111500-BCDE
"""

SKILL_LOG = """# Skill-Usage-Log.md

### SKL-20260524101500

- Timestamp (UTC): 2026-05-24T10:15:00+00:00
- Routing Path: single-agent
- Skills Used (ordered): prompt-optimizer, test-driven-development
- Invocation Reason: Stabilize prompt mappings
Cycle: CYC-20260524-101500-ABCD

### SKL-20260524111500

- Timestamp (UTC): 2026-05-24T11:15:00+00:00
- Routing Path: multi-agent
- Skills Used (ordered): prompt-optimizer, systematic-debugging
- Invocation Reason: Improve routing quality
Cycle: CYC-20260524-111500-BCDE
"""

PATTERNS_LOG = """# Behavior-Patterns.md

### PAT-20260524-101500

- Signal: prompt mapping drift
- Impact: high
- Status: candidate

### PAT-20260524-111500

- Signal: routing mismatch
- Impact: medium
- Status: applied
"""

BACKLOG_LOG = """# Learning-Backlog.md

### LRN-20260524-101500

- Priority: high
- Problem: prompt mapping drift
- Proposed Change: validate prompt mappings in CI
- Scope: routing
- Status: pending
- Linked Pattern: [Behavior-Patterns](Behavior-Patterns.md#PAT-20260524-101500)
- Date: 2026-05-24
"""

RUNBOOK_LOG = """# Runbook.md

### CHG-20260524-101500

- Date: 2026-05-24
- Change Applied: Introduced shared prompt registry
- Observed Result: Fewer mismatches during validation
- Decision: keep
"""

PROJECT_CONTEXT = """# Project-Context-Log.md

### CTX-20260524-101500

- Timestamp (UTC): 2026-05-24T10:15:00+00:00
- Project/Request: Stabilize prompt mappings
- Stage: checkpoint
"""

HOME = "# Home\n"

TELEMETRY_EVENTS = [
    {
        "schema_version": "orchestrator.telemetry.cycle.v1",
        "event_type": "cycle.persisted",
        "recorded_at_utc": "2026-05-26T12:34:56+00:00",
        "dispatch_path": "single-agent",
        "level": "compact",
        "command": "/info",
        "persisted": True,
        "preview": False,
        "cycle_id": "CYC-20260526-123456-ABCD",
        "session_id": "SESSION-001",
        "request_group_id": "GROUP-001",
        "dedupe_key": "dedupe-001",
        "curated_checkpoint": False,
        "summary": "Compact telemetry record one.",
        "skills_used": ["writing-plans"],
        "fingerprint": "sha1:1111111111111111111111111111111111111111",
    },
    {
        "schema_version": "orchestrator.telemetry.cycle.v1",
        "event_type": "cycle.persisted",
        "recorded_at_utc": "2026-05-26T12:35:56+00:00",
        "dispatch_path": "single-agent",
        "level": "compact",
        "command": "/info",
        "persisted": True,
        "preview": False,
        "cycle_id": "CYC-20260526-123456-ABCD",
        "session_id": "SESSION-001",
        "request_group_id": "GROUP-001",
        "dedupe_key": "dedupe-001",
        "curated_checkpoint": False,
        "summary": "Duplicate telemetry record one.",
        "skills_used": ["writing-plans"],
        "fingerprint": "sha1:1111111111111111111111111111111111111111",
    },
    {
        "schema_version": "orchestrator.telemetry.cycle.v1",
        "event_type": "cycle.persisted",
        "recorded_at_utc": "",
        "dispatch_path": "multi-agent",
        "level": "full",
        "command": "/full-log",
        "persisted": True,
        "preview": False,
        "cycle_id": "CYC-20260526-123457-BCDE",
        "session_id": "SESSION-002",
        "request_group_id": "GROUP-002",
        "dedupe_key": "dedupe-002",
        "curated_checkpoint": True,
        "summary": "Full telemetry record with missing timestamp.",
        "skills_used": ["systematic-debugging", "test-driven-development"],
        "fingerprint": "sha1:2222222222222222222222222222222222222222",
    },
]


def _telemetry_jsonl() -> str:
    return '\n'.join(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in TELEMETRY_EVENTS) + '\n'


def _refreshed_telemetry_jsonl() -> str:
    refreshed_events = TELEMETRY_EVENTS + [{
        "schema_version": "orchestrator.telemetry.cycle.v1",
        "event_type": "cycle.persisted",
        "recorded_at_utc": "2026-05-26T12:36:56+00:00",
        "dispatch_path": "direct",
        "level": "compact",
        "command": "/info",
        "persisted": True,
        "preview": False,
        "cycle_id": "CYC-20260526-123458-CDEF",
        "session_id": "SESSION-003",
        "request_group_id": "GROUP-003",
        "dedupe_key": "dedupe-003",
        "curated_checkpoint": False,
        "summary": "Additional telemetry record after cache refresh.",
        "skills_used": ["writing-plans"],
        "fingerprint": "sha1:3333333333333333333333333333333333333333",
    }]
    return '\n'.join(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in refreshed_events) + '\n'


BROKEN_TELEMETRY_JSONL = '\nnot json\n[]\nnull\n'


class WikiSynthesisTests(unittest.TestCase):
    def _build_wiki(self, root: Path, telemetry: str | None = None) -> Path:
        wiki = root / '.wiki' / 'orchestrator'
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / 'Behavior-Log.md').write_text(BEHAVIOR_LOG, encoding='utf-8')
        (wiki / 'Skill-Usage-Log.md').write_text(SKILL_LOG, encoding='utf-8')
        (wiki / 'Behavior-Patterns.md').write_text(PATTERNS_LOG, encoding='utf-8')
        (wiki / 'Learning-Backlog.md').write_text(BACKLOG_LOG, encoding='utf-8')
        (wiki / 'Runbook.md').write_text(RUNBOOK_LOG, encoding='utf-8')
        (wiki / 'Project-Context-Log.md').write_text(PROJECT_CONTEXT, encoding='utf-8')
        (wiki / 'Home.md').write_text(HOME, encoding='utf-8')
        if telemetry is not None:
            telemetry_dir = wiki / 'telemetry'
            telemetry_dir.mkdir(parents=True, exist_ok=True)
            (telemetry_dir / 'cycles.jsonl').write_text(telemetry, encoding='utf-8')
        return wiki

    def test_collect_metrics_summarizes_telemetry_jsonl_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir), telemetry=_telemetry_jsonl())
            metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)
            cache_path = wiki / 'telemetry' / 'summary-cache.json'
            cache_data = json.loads(cache_path.read_text(encoding='utf-8'))

        telemetry = metrics['telemetry_summary']
        self.assertEqual(telemetry['schema_version'], 'orchestrator.telemetry.index.v1')
        self.assertEqual(telemetry['source_path'], 'telemetry/cycles.jsonl')
        self.assertEqual(telemetry['source_state'], 'present_with_records')
        self.assertEqual(telemetry['record_count'], 3)
        self.assertEqual(telemetry['unique_cycle_count'], 2)
        self.assertEqual(telemetry['dispatch_counts'], {'single-agent': 2, 'multi-agent': 1})
        self.assertEqual(telemetry['level_counts'], {'compact': 2, 'full': 1})
        self.assertEqual(telemetry['command_counts'], {'/info': 2, '/full-log': 1})
        self.assertEqual(telemetry['duplicate_fingerprint_count'], 1)
        self.assertEqual(telemetry['incomplete_record_count'], 1)
        self.assertGreaterEqual(len(telemetry['anomaly_samples']), 2)
        duplicate_expected = {
            'type': 'duplicate_fingerprint',
            'fingerprint': 'sha1:1111111111111111111111111111111111111111',
            'occurrences': 2,
        }
        self.assertTrue(
            any(
                all(sample.get(key) == value for key, value in duplicate_expected.items())
                for sample in telemetry['anomaly_samples']
            )
        )
        self.assertTrue(
            any(
                sample.get('type') == 'duplicate_fingerprint' and sample.get('record_indices') == [1, 2]
                for sample in telemetry['anomaly_samples']
            )
        )
        incomplete_expected = {
            'type': 'incomplete_record',
            'record_index': 3,
        }
        self.assertTrue(
            any(
                all(sample.get(key) == value for key, value in incomplete_expected.items())
                for sample in telemetry['anomaly_samples']
            )
        )
        self.assertEqual(cache_data['schema_version'], 'orchestrator.telemetry.summary-cache.v1')
        self.assertEqual(cache_data['source_signature']['source_path'], 'telemetry/cycles.jsonl')
        self.assertEqual(cache_data['telemetry_summary']['record_count'], 3)
        self.assertEqual(cache_data['telemetry_summary']['source_state'], 'present_with_records')

    def test_collect_metrics_reuses_cached_telemetry_summary_when_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir), telemetry=_telemetry_jsonl())
            first_metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)

            with mock.patch.object(
                analyze_logs,
                '_collect_telemetry_summary',
                side_effect=AssertionError('telemetry rollup should have been served from cache'),
            ):
                second_metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)

        self.assertEqual(second_metrics['telemetry_summary']['record_count'], first_metrics['telemetry_summary']['record_count'])
        self.assertEqual(second_metrics['telemetry_summary']['source_state'], 'present_with_records')
        self.assertEqual(second_metrics['telemetry_summary']['dispatch_counts'], {'single-agent': 2, 'multi-agent': 1})

    def test_collect_metrics_refreshes_stale_cached_telemetry_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir), telemetry=_telemetry_jsonl())
            analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)
            cache_path = wiki / 'telemetry' / 'summary-cache.json'

            cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
            cache_data['cached_utc'] = '2000-01-01T00:00:00+00:00'
            cache_data['telemetry_summary'] = {
                'schema_version': 'orchestrator.telemetry.index.v1',
                'generated_utc': '2000-01-01T00:00:00+00:00',
                'source_path': 'telemetry/cycles.jsonl',
                'source_state': 'present_with_records',
                'record_count': 999,
            }
            cache_path.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

            with mock.patch.object(
                analyze_logs,
                '_collect_telemetry_summary',
                wraps=analyze_logs._collect_telemetry_summary,
            ) as rollup_helper:
                metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)

            refreshed_cache = json.loads(cache_path.read_text(encoding='utf-8'))

        self.assertEqual(rollup_helper.call_count, 1)
        self.assertEqual(metrics['telemetry_summary']['record_count'], 3)
        self.assertEqual(metrics['telemetry_summary']['source_state'], 'present_with_records')
        self.assertEqual(refreshed_cache['telemetry_summary']['record_count'], 3)
        self.assertNotEqual(refreshed_cache['telemetry_summary']['record_count'], 999)

    def test_collect_metrics_refreshes_cache_when_cached_utc_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir), telemetry=_telemetry_jsonl())
            analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)
            cache_path = wiki / 'telemetry' / 'summary-cache.json'

            with mock.patch.object(
                analyze_logs,
                '_collect_telemetry_summary',
                wraps=analyze_logs._collect_telemetry_summary,
            ) as rollup_helper:
                for invalid_cached_utc in (
                    '2026-05-26T12:34:56',
                    '2999-01-01T00:00:00+00:00',
                    '',
                    None,
                ):
                    cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
                    if invalid_cached_utc is None:
                        cache_data.pop('cached_utc', None)
                    else:
                        cache_data['cached_utc'] = invalid_cached_utc
                    cache_data['telemetry_summary']['record_count'] = 999
                    cache_path.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

                    metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)

                    self.assertEqual(metrics['telemetry_summary']['record_count'], 3)
                    self.assertEqual(metrics['telemetry_summary']['source_state'], 'present_with_records')

            refreshed_cache = json.loads(cache_path.read_text(encoding='utf-8'))

        self.assertEqual(rollup_helper.call_count, 4)
        self.assertEqual(refreshed_cache['telemetry_summary']['record_count'], 3)

    def test_collect_metrics_refreshes_cache_when_telemetry_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir), telemetry=_telemetry_jsonl())
            analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)
            cache_path = wiki / 'telemetry' / 'summary-cache.json'
            initial_cache = json.loads(cache_path.read_text(encoding='utf-8'))

            (wiki / 'telemetry' / 'cycles.jsonl').write_text(_refreshed_telemetry_jsonl(), encoding='utf-8')

            with mock.patch.object(
                analyze_logs,
                '_collect_telemetry_summary',
                wraps=analyze_logs._collect_telemetry_summary,
            ) as rollup_helper:
                metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)

            refreshed_cache = json.loads(cache_path.read_text(encoding='utf-8'))

        self.assertEqual(rollup_helper.call_count, 1)
        self.assertEqual(metrics['telemetry_summary']['record_count'], 4)
        self.assertEqual(metrics['telemetry_summary']['dispatch_counts'], {'single-agent': 2, 'multi-agent': 1, 'direct': 1})
        self.assertNotEqual(initial_cache['source_signature'], refreshed_cache['source_signature'])
        self.assertEqual(refreshed_cache['telemetry_summary']['record_count'], 4)

    def test_collect_metrics_without_telemetry_does_not_create_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir))
            metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)
            cache_path = wiki / 'telemetry' / 'summary-cache.json'

            self.assertFalse(cache_path.exists())

        telemetry = metrics['telemetry_summary']
        self.assertEqual(telemetry['record_count'], 0)
        self.assertEqual(telemetry['source_state'], 'missing')

    def test_collect_metrics_emits_richer_phase_two_and_three_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir))
            metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)

        self.assertEqual(metrics['cycle_count'], 2)
        self.assertIn('model_quality', metrics)
        self.assertIn('routing_quality', metrics)
        self.assertIn('contract_feedback', metrics)
        self.assertEqual({item['model'] for item in metrics['model_quality']}, {'gpt-5.4', 'gpt-5.4-mini'})

    def test_synthesize_wiki_generates_index_glossary_and_learned_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir), telemetry=_telemetry_jsonl())
            pages = synthesize_wiki.generate_knowledge_pages(wiki, cycles=10, stale_days=30)

            index_text = pages[wiki / 'knowledge' / 'Index.md']
            model_text = pages[wiki / 'knowledge' / 'Learned-Model-Selection.md']
            glossary_text = pages[wiki / 'knowledge' / 'Glossary.md']
            telemetry_text = pages[wiki / 'knowledge' / 'Learned-Telemetry.md']

        self.assertIn('Top Pattern Signals', index_text)
        self.assertIn('- [Learned Telemetry](Learned-Telemetry.md)', index_text)
        self.assertIn('gpt-5.4-mini', model_text)
        self.assertIn('Contract score', glossary_text)
        self.assertIn('duplicate_fingerprint', telemetry_text)
        self.assertIn('Dispatch Path', telemetry_text)
        self.assertIn('Source state: present_with_records', telemetry_text)

    def test_generate_knowledge_pages_distinguishes_present_but_invalid_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir), telemetry=BROKEN_TELEMETRY_JSONL)
            metrics = analyze_logs.collect_metrics(wiki, cycles=10, stale_days=30)
            pages = synthesize_wiki.generate_knowledge_pages(wiki, cycles=10, stale_days=30)
            telemetry_text = pages[wiki / 'knowledge' / 'Learned-Telemetry.md']

        telemetry = metrics['telemetry_summary']
        self.assertEqual(telemetry['record_count'], 0)
        self.assertEqual(telemetry['source_state'], 'present_no_valid_records')
        self.assertIn('Source state: present_no_valid_records', telemetry_text)
        self.assertNotIn('No telemetry JSONL stream was available', telemetry_text)

    def test_search_wiki_returns_relevant_knowledge_and_log_hits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir))
            synthesize_wiki.generate_knowledge_pages(wiki, cycles=10, stale_days=30)
            results = search_wiki.search_wiki_pages(wiki, 'routing quality', limit=5)

        self.assertTrue(results)
        self.assertIn('routing', results[0].title.lower())

    def test_search_wiki_finds_telemetry_knowledge_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki = self._build_wiki(Path(temp_dir), telemetry=_telemetry_jsonl())
            synthesize_wiki.generate_knowledge_pages(wiki, cycles=10, stale_days=30)
            results = search_wiki.search_wiki_pages(wiki, 'telemetry summary', limit=5)

        self.assertTrue(results)
        self.assertTrue(any(result.path.endswith('Learned-Telemetry.md') for result in results))


if __name__ == '__main__':
    unittest.main()
