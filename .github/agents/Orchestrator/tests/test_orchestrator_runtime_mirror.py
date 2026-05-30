import os
import json
import unittest
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from src import orchestrator_runtime as rt
from src.orchestrator_memory import persist_continuity_checkpoint_from_normalized_metadata


@contextmanager
def chdir(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _write_markdown_page(root: Path, relative_path: str, title: str, body: str) -> None:
    page = root / relative_path
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"# {title}\n\n{body}\n", encoding="utf8")


class TestOrchestratorRuntime(unittest.TestCase):

    def test_init_orchestrator_writes_manifest(self):
        manifest_path = os.path.join(os.path.dirname(__file__), 'tmp_skills_manifest.json')
        if os.path.exists(manifest_path):
            os.remove(manifest_path)
        try:
            m = rt.init_orchestrator(skills_dir='skills', manifest_path=manifest_path)
            self.assertIsInstance(m, dict)
            self.assertTrue(os.path.exists(manifest_path))
            with open(manifest_path, encoding='utf8') as handle:
                loaded = json.loads(handle.read())
            self.assertEqual(m, loaded)
        finally:
            if os.path.exists(manifest_path):
                os.remove(manifest_path)

    def test_run_script_executes_python(self):
        # create a small python script
        tmp_dir = os.path.join(os.path.dirname(__file__), 'tmp_scripts')
        os.makedirs(tmp_dir, exist_ok=True)
        script = os.path.join(tmp_dir, 'echo.py')
        with open(script, 'w', encoding='utf8') as f:
            f.write('print("ORCH_TEST_HELLO")\n')
        try:
            out = rt.run_script(script)
            self.assertIn('ORCH_TEST_HELLO', out)
        finally:
            try:
                os.remove(script)
                os.rmdir(tmp_dir)
            except Exception:
                pass

    def test_handle_request_runs_skill_script(self):
        mirror_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        with chdir(mirror_root):
            skills_base = os.path.join(mirror_root, 'skills')
            tmp_skill = os.path.join(skills_base, 'tmp_skill')
            os.makedirs(tmp_skill, exist_ok=True)
            script = os.path.join(tmp_skill, 'run_me.py')
            try:
                with open(script, 'w', encoding='utf8') as f:
                    f.write('print("SKILL_SCRIPT_RAN")\n')

                out = rt.handle_request('test', user='u', run_skill='tmp_skill')
                self.assertIn('SKILL_SCRIPT_RAN', (out.get('skill_output') or ''))
            finally:
                try:
                    if os.path.exists(script):
                        os.remove(script)
                    if os.path.isdir(tmp_skill):
                        os.rmdir(tmp_skill)
                except Exception:
                    pass

    def test_prepare_dispatch_payload(self):
        payload = rt.prepare_dispatch_payload('prepare-prompt', user='u')
        self.assertIn('prompt', payload)
        self.assertIn('parent_context', payload)
        self.assertIn('persistence', payload['parent_context'])

    def test_prepare_dispatch_payload_detects_explicit_continuation_request(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            with chdir(temp_dir):
                payload = rt.prepare_dispatch_payload(
                    'Please continue where we left off on the telemetry dispatcher.',
                    user='u',
                    metadata={
                        'project_request': 'Telemetry dispatcher continuation.',
                        'request_title': 'Telemetry dispatcher continuation.',
                        'normalized_request': 'telemetry dispatcher continuation',
                    },
                )

        parent_context = payload['parent_context']
        detection = parent_context['continuation_detection']
        self.assertEqual(parent_context['context_retrieval_source'], 'none')
        self.assertEqual(parent_context['context_fact_count'], 0)
        self.assertTrue(detection['is_continuation'])
        self.assertEqual(detection['continuation_type'], 'explicit')
        self.assertGreaterEqual(detection['confidence'], 0.8)
        self.assertIn('explicit_continuation_request', [signal['name'] for signal in detection['signals']])
        self.assertTrue(parent_context['is_continuation'])
        self.assertTrue(parent_context['dispatch_metadata']['is_continuation'])

    def test_prepare_dispatch_payload_detects_prior_context_references(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            wiki_root = root / '.wiki' / 'orchestrator'
            _write_markdown_page(
                wiki_root,
                'plans/alpha-dispatch.md',
                'Alpha Dispatch Plan',
                'Update the alpha dispatch plan and keep the retrieval notes bounded.',
            )

            with chdir(temp_dir):
                payload = rt.prepare_dispatch_payload(
                    'Please revise the Alpha Dispatch Plan and update plans/alpha-dispatch.md with the latest notes.',
                    user='u',
                    metadata={
                        'project_request': 'Alpha Dispatch Plan',
                        'request_title': 'Alpha Dispatch Plan',
                        'normalized_request': 'alpha dispatch plan',
                    },
                )

        parent_context = payload['parent_context']
        detection = parent_context['continuation_detection']
        signal_names = [signal['name'] for signal in detection['signals']]
        self.assertEqual(parent_context['context_retrieval_source'], 'wiki_search')
        self.assertEqual(parent_context['context_fact_count'], 1)
        self.assertTrue(detection['is_continuation'])
        self.assertEqual(detection['continuation_type'], 'implicit')
        self.assertIn('project_reference', signal_names)
        self.assertIn('artifact_reference', signal_names)
        self.assertTrue(parent_context['is_continuation'])
        self.assertTrue(parent_context['dispatch_metadata']['is_continuation'])

    def test_prepare_dispatch_payload_does_not_self_match_current_request_metadata(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            with chdir(temp_dir):
                summary = rt._build_continuation_detection_summary(  # type: ignore[attr-defined]
                    user='u',
                    metadata={
                        'project_request': 'Please update the deployment scripts.',
                        'request_title': 'Please update the deployment scripts.',
                        'normalized_request': 'please update the deployment scripts',
                    },
                    prior_context={
                        'items': [
                            {
                                'source': 'continuity_cache',
                                'title': 'Telemetry Dispatcher',
                                'detail': 'Completed the earlier telemetry dispatcher changes.',
                                'path': '',
                            }
                        ],
                        'markdown': '## Prior Context (Auto-Retrieved)\n- cache: `Telemetry Dispatcher`',
                        'context_retrieval_source': 'continuity_cache',
                        'context_fact_count': 1,
                    },
                    dispatch='single-agent',
                    subagent_name=None,
                )
                detection = rt.detect_continuation('Please update the deployment scripts.', summary)

        self.assertFalse(detection['is_continuation'])
        self.assertEqual(detection['continuation_type'], 'none')
        self.assertEqual(detection['confidence'], 0.0)

    def test_prepare_dispatch_payload_uses_continuity_cache_when_available(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            base_metadata = {
                'request_group_id': 'grp-dispatch-001',
                'project_request': 'Continue the telemetry continuity work.',
                'request_title': 'Continue the telemetry continuity work.',
                'normalized_request': 'continue telemetry continuity work',
                'summary': 'Seed checkpoint for the dispatch continuity cache.',
                'change_applied': 'Prepared the dispatch payload seam.',
                'observed_result': 'Local SQLite cache recorded the work.',
                'decision': 'keep',
                'next_action': 'Continue with the prior-context seam.',
            }

            for index in range(3):
                persist_continuity_checkpoint_from_normalized_metadata(
                    {
                        **base_metadata,
                        'cycle_id': f'cycle-{index + 1}',
                        'summary': f"{base_metadata['summary']} #{index + 1}",
                        'change_applied': f"{base_metadata['change_applied']} #{index + 1}",
                        'observed_result': f"{base_metadata['observed_result']} #{index + 1}",
                        'next_action': f"{base_metadata['next_action']} #{index + 1}",
                    },
                    root=root,
                    source_kind='test',
                    source_identifier=f'unit-{index + 1}',
                )

            with chdir(temp_dir), mock.patch.object(rt, 'search_wiki_pages', side_effect=AssertionError('wiki fallback should not be needed')):
                payload = rt.prepare_dispatch_payload(
                    'Continue the telemetry continuity work.',
                    user='u',
                    metadata={
                        'request_group_id': 'grp-dispatch-001',
                        'project_request': 'Continue the telemetry continuity work.',
                        'request_title': 'Continue the telemetry continuity work.',
                        'normalized_request': 'continue telemetry continuity work',
                    },
                )

            parent_context = payload['parent_context']
            self.assertEqual(parent_context['context_retrieval_source'], 'continuity_cache')
            self.assertEqual(parent_context['context_fact_count'], 3)
            self.assertEqual(parent_context['dispatch_metadata']['context_retrieval_source'], 'continuity_cache')
            self.assertEqual(parent_context['dispatch_metadata']['context_fact_count'], 3)
            self.assertTrue(parent_context['prior_context'].startswith('## Prior Context (Auto-Retrieved)'))
            self.assertEqual(sum(line.startswith('- ') for line in parent_context['prior_context'].splitlines()), 3)
            self.assertIn('dispatch payload seam', parent_context['prior_context'])

    def test_prepare_dispatch_payload_uses_continuity_cache_for_prompt_only_requests_without_request_group_id(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            base_metadata = {
                'project_request': 'Continue the prompt-only continuity seam.',
                'request_title': 'Continue the prompt-only continuity seam.',
                'normalized_request': 'continue prompt-only continuity seam',
                'summary': 'Prompt-only continuity cache seed.',
                'change_applied': 'Seeded prompt-only continuity rows.',
                'observed_result': 'SQLite continuity cache stored prompt-only rows.',
                'decision': 'keep',
                'next_action': 'Retrieve prompt-only continuity rows without request_group_id.',
            }

            for index in range(3):
                persist_continuity_checkpoint_from_normalized_metadata(
                    {
                        **base_metadata,
                        'cycle_id': f'seed-cycle-{index + 1}',
                        'summary': f"{base_metadata['summary']} #{index + 1}",
                        'change_applied': f"{base_metadata['change_applied']} #{index + 1}",
                        'observed_result': f"{base_metadata['observed_result']} #{index + 1}",
                        'next_action': f"{base_metadata['next_action']} #{index + 1}",
                    },
                    root=root,
                    source_kind='test',
                    source_identifier=f'unit-prompt-only-{index + 1}',
                )

            with chdir(temp_dir), mock.patch.object(rt, 'search_wiki_pages', side_effect=AssertionError('wiki fallback should not be needed')):
                payload = rt.prepare_dispatch_payload(
                    'Continue the prompt-only continuity seam.',
                    user='u',
                    metadata={
                        'project_request': 'Continue the prompt-only continuity seam.',
                        'request_title': 'Continue the prompt-only continuity seam.',
                        'normalized_request': 'continue prompt-only continuity seam',
                    },
                )

            parent_context = payload['parent_context']
            self.assertEqual(parent_context['context_retrieval_source'], 'continuity_cache')
            self.assertEqual(parent_context['context_fact_count'], 3)
            self.assertTrue(parent_context['prior_context'].startswith('## Prior Context (Auto-Retrieved)'))
            self.assertEqual(sum(line.startswith('- ') for line in parent_context['prior_context'].splitlines()), 3)
            self.assertIn('prompt-only continuity cache seed', parent_context['prior_context'].casefold())

    def test_prepare_dispatch_payload_uses_wiki_fallback_when_cache_is_sparse(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            root = Path(temp_dir)
            wiki_root = root / '.wiki' / 'orchestrator'
            _write_markdown_page(
                wiki_root,
                'plans/alpha-dispatch.md',
                'Alpha Dispatch Plan',
                'Continue the alpha cache continuity work with dispatch payload retrieval and compact context.',
            )
            _write_markdown_page(
                wiki_root,
                'notes/alpha-continuity.md',
                'Alpha Continuity Notes',
                'The alpha cache continuity work should keep the payload small and reviewable.',
            )
            _write_markdown_page(
                wiki_root,
                'reviews/alpha-review.md',
                'Alpha Review Summary',
                'Review the alpha cache continuity work and keep the markdown block bounded.',
            )
            _write_markdown_page(
                wiki_root,
                'guides/alpha-facts.md',
                'Alpha Facts',
                'Miscellaneous archival notes that should rank below the continuity-specific pages.',
            )

            with chdir(temp_dir):
                payload = rt.prepare_dispatch_payload(
                    'Continue the alpha cache continuity work.',
                    user='u',
                    metadata={
                        'project_request': 'Continue the alpha cache continuity work.',
                        'request_title': 'Continue the alpha cache continuity work.',
                        'normalized_request': 'continue alpha cache continuity work',
                    },
                )

            parent_context = payload['parent_context']
            self.assertEqual(parent_context['context_retrieval_source'], 'wiki_search')
            self.assertEqual(parent_context['context_fact_count'], 3)
            self.assertTrue(parent_context['prior_context'].startswith('## Prior Context (Auto-Retrieved)'))
            self.assertEqual(sum(line.startswith('- ') for line in parent_context['prior_context'].splitlines()), 3)
            self.assertIn('Alpha Dispatch Plan', parent_context['prior_context'])

    def test_prepare_dispatch_payload_ignores_negated_blocker_text(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            with chdir(temp_dir):
                summary = rt._build_continuation_detection_summary(  # type: ignore[attr-defined]
                    user='u',
                    metadata={
                        'project_request': 'Continue the Alpha Dispatch Plan.',
                        'request_title': 'Continue the Alpha Dispatch Plan.',
                        'normalized_request': 'continue the alpha dispatch plan',
                    },
                    prior_context={
                        'items': [
                            {
                                'source': 'continuity_cache',
                                'title': 'Alpha Dispatch Plan',
                                'detail': 'No issue found in the previous run.',
                                'path': '',
                            }
                        ],
                        'markdown': '## Prior Context (Auto-Retrieved)\n- cache: `Alpha Dispatch Plan`',
                        'context_retrieval_source': 'continuity_cache',
                        'context_fact_count': 1,
                    },
                    dispatch='single-agent',
                    subagent_name=None,
                )
                detection = rt.detect_continuation('Please continue the Alpha Dispatch Plan.', summary)

        self.assertTrue(detection['is_continuation'])
        self.assertEqual(detection['continuation_type'], 'explicit')
        self.assertGreaterEqual(detection['confidence'], 0.8)
        self.assertEqual(detection['prior_blockers'], [])

    def test_prepare_dispatch_payload_handles_missing_prior_context_gracefully(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            with chdir(temp_dir):
                payload = rt.prepare_dispatch_payload(
                    'No prior context should be available here.',
                    user='u',
                    metadata={
                        'project_request': 'No prior context should be available here.',
                        'request_title': 'No prior context should be available here.',
                        'normalized_request': 'no prior context should be available here',
                    },
                )

            parent_context = payload['parent_context']
            self.assertEqual(parent_context['context_retrieval_source'], 'none')
            self.assertEqual(parent_context['context_fact_count'], 0)
            self.assertFalse(parent_context['prior_context'])
            self.assertFalse(parent_context['continuation_detection']['is_continuation'])
            self.assertEqual(parent_context['continuation_detection']['continuation_type'], 'none')
            self.assertEqual(parent_context['continuation_detection']['confidence'], 0.0)
            self.assertEqual(parent_context['dispatch_metadata']['context_retrieval_source'], 'none')
            self.assertEqual(parent_context['dispatch_metadata']['context_fact_count'], 0)

    def test_handle_request_logs_skills_from_prompt_and_output(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            skills_dir = os.path.join(temp_dir, 'skills', 'tmp_skill')
            os.makedirs(skills_dir, exist_ok=True)
            script = os.path.join(skills_dir, 'emit.py')
            with open(script, 'w', encoding='utf8') as handle:
                handle.write('print("output mentions contract-validator")\n')

            with chdir(temp_dir):
                result = rt.handle_request(
                    'Please use prompt-optimizer before you answer.',
                    user='u',
                    run_skill='tmp_skill',
                    skill_script_name='emit.py',
                )

                self.assertIn('skill_usage', result)
                self.assertEqual(result['skill_usage']['skills'], ['prompt-optimizer', 'contract-validator'])

                log_path = os.path.join(temp_dir, '.wiki', 'orchestrator', 'Skill-Usage-Log.md')
                self.assertTrue(os.path.exists(log_path))
                with open(log_path, encoding='utf8') as handle:
                    log_text = handle.read()
                self.assertIn('prompt-optimizer', log_text)
                self.assertIn('contract-validator', log_text)


if __name__ == '__main__':
    unittest.main()
