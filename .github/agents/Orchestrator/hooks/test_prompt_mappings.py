from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ORCHESTRATOR_ROOT.parents[2]
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


prompt_registry = _load_module('orchestrator_prompt_registry_test', Path('scripts') / 'prompt_registry.py')
validate_prompt_mappings = _load_module('orchestrator_validate_prompt_mappings_test', Path('scripts') / 'validate_prompt_mappings.py')


class PromptMappingTests(unittest.TestCase):
    def test_cleanup_command_is_explicitly_registered(self) -> None:
        spec = prompt_registry.get_command_spec('/cleanup')
        self.assertIsNotNone(spec)
        self.assertEqual(spec.prompt_file, 'cleanup.prompt.md')
        self.assertFalse(spec.supports_log_append)
        self.assertEqual(spec.category, 'workflow')
        self.assertIn('audits/orchestrator-wiki-audit-<YYYY-MM-DD>.md', spec.targets)

    def test_refresh_model_catalog_command_is_explicitly_registered(self) -> None:
        spec = prompt_registry.get_command_spec('/refresh-model-catalog')
        self.assertIsNotNone(spec)
        self.assertEqual(spec.prompt_file, 'refresh-model-catalog.prompt.md')
        self.assertFalse(spec.supports_log_append)
        self.assertEqual(spec.category, 'workflow')
        self.assertIn('skills/model_catalog.json', spec.targets)
        self.assertIn('.github/agents/Orchestrator/skills/model_catalog.json', spec.targets)

    def test_refresh_model_alias_is_explicitly_registered(self) -> None:
        spec = prompt_registry.get_command_spec('/refresh-model')
        self.assertIsNotNone(spec)
        self.assertEqual(spec.prompt_file, 'refresh-model.prompt.md')
        self.assertFalse(spec.supports_log_append)
        self.assertEqual(spec.category, 'workflow')
        self.assertEqual(spec.alias_for, '/refresh-model-catalog')
        self.assertIn('skills/model_catalog.json', spec.targets)
        self.assertIn('.github/agents/Orchestrator/skills/model_catalog.json', spec.targets)

    def test_registry_covers_current_prompt_inventory(self) -> None:
        prompt_files = set(prompt_registry.discover_prompt_files(REPO_ROOT))
        mapped = {spec.prompt_file for spec in prompt_registry.PROMPT_COMMANDS.values() if spec.prompt_file}
        self.assertEqual(prompt_files, mapped)

    def test_prompt_mapping_validator_passes_for_repo(self) -> None:
        errors = validate_prompt_mappings.validate_manifest(REPO_ROOT)
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
