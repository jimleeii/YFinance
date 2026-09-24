#!/usr/bin/env python3
"""Explicit prompt/command registry for the mirrored Orchestrator package.

This module is the single source of truth for:
- prompt-backed slash commands under `.github/prompts/`
- append-capable commands supported by `scripts/log_prompt.py`
- internal aliases that intentionally do not expose a prompt file
- maintenance/workflow commands (for example `/cleanup`) that are prompt-backed
  but are not simple append operations
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path('.github/prompts')


@dataclass(frozen=True)
class PromptCommandSpec:
    command: str
    description: str
    prompt_file: str | None
    targets: tuple[str, ...]
    supports_log_append: bool
    category: str = 'append'
    alias_for: str | None = None
    notes: str = ''

    def to_manifest_record(self, repo_root: Path | None = None) -> dict[str, Any]:
        prompt_path = repo_root / PROMPTS_DIR / self.prompt_file if repo_root and self.prompt_file else None
        record = asdict(self)
        record['prompt_path'] = str(prompt_path.relative_to(repo_root)) if prompt_path and repo_root else (
            str(PROMPTS_DIR / self.prompt_file) if self.prompt_file else None
        )
        record['prompt_exists'] = bool(prompt_path and prompt_path.exists()) if prompt_path else False
        record['target_count'] = len(self.targets)
        return record


PROMPT_COMMANDS: dict[str, PromptCommandSpec] = {
    '/full-log': PromptCommandSpec(
        command='/full-log',
        description='Append a curated full checkpoint across the six primary wiki logs.',
        prompt_file='full-log.prompt.md',
        targets=(
            'Behavior-Log.md',
            'Behavior-Patterns.md',
            'Learning-Backlog.md',
            'Project-Context-Log.md',
            'Runbook.md',
            'Skill-Usage-Log.md',
        ),
        supports_log_append=True,
    ),
    '/info': PromptCommandSpec(
        command='/info',
        description='Append a compact behavior + skill checkpoint.',
        prompt_file='info.prompt.md',
        targets=('Behavior-Log.md', 'Skill-Usage-Log.md'),
        supports_log_append=True,
    ),
    '/error': PromptCommandSpec(
        command='/error',
        description='Append an error-focused checkpoint.',
        prompt_file='error.prompt.md',
        targets=('Behavior-Log.md', 'Project-Context-Log.md'),
        supports_log_append=True,
    ),
    '/warning': PromptCommandSpec(
        command='/warning',
        description='Append a warning observation and matching pattern signal.',
        prompt_file='warning.prompt.md',
        targets=('Behavior-Log.md', 'Behavior-Patterns.md'),
        supports_log_append=True,
    ),
    '/warn': PromptCommandSpec(
        command='/warn',
        description='Short-form warning command with the same targets as `/warning`.',
        prompt_file='warn.prompt.md',
        targets=('Behavior-Log.md', 'Behavior-Patterns.md'),
        supports_log_append=True,
        alias_for='/warning',
        notes='Prompt-backed shorthand kept for slash-command ergonomics.',
    ),
    '/debug': PromptCommandSpec(
        command='/debug',
        description='Append a debug checkpoint to runbook + backlog.',
        prompt_file='debug.prompt.md',
        targets=('Runbook.md', 'Learning-Backlog.md'),
        supports_log_append=True,
    ),
    '/trace': PromptCommandSpec(
        command='/trace',
        description='Append a trace/learning item to the backlog.',
        prompt_file='trace.prompt.md',
        targets=('Learning-Backlog.md',),
        supports_log_append=True,
    ),
    '/behavior': PromptCommandSpec(
        command='/behavior',
        description='Append a single behavior observation entry.',
        prompt_file='behavior.prompt.md',
        targets=('Behavior-Log.md',),
        supports_log_append=True,
    ),
    '/patterns-log': PromptCommandSpec(
        command='/patterns-log',
        description='Append a single behavior-pattern entry.',
        prompt_file='patterns-log.prompt.md',
        targets=('Behavior-Patterns.md',),
        supports_log_append=True,
    ),
    '/learning-backlog': PromptCommandSpec(
        command='/learning-backlog',
        description='Append a single learning-backlog item.',
        prompt_file='learning-backlog.prompt.md',
        targets=('Learning-Backlog.md',),
        supports_log_append=True,
    ),
    '/project-context': PromptCommandSpec(
        command='/project-context',
        description='Append a project-context checkpoint.',
        prompt_file='project-context.prompt.md',
        targets=('Project-Context-Log.md',),
        supports_log_append=True,
    ),
    '/runbook': PromptCommandSpec(
        command='/runbook',
        description='Append a runbook change entry.',
        prompt_file='runbook.prompt.md',
        targets=('Runbook.md',),
        supports_log_append=True,
    ),
    '/skill-usage': PromptCommandSpec(
        command='/skill-usage',
        description='Append a standalone skill-usage entry.',
        prompt_file='skill-usage.prompt.md',
        targets=('Skill-Usage-Log.md',),
        supports_log_append=True,
    ),
    '/cleanup': PromptCommandSpec(
        command='/cleanup',
        description='Run the wiki cleanup/audit workflow and refresh the audit index.',
        prompt_file='cleanup.prompt.md',
        targets=(
            'Behavior-Log.md',
            'Skill-Usage-Log.md',
            'Project-Context-Log.md',
            'Runbook.md',
            'Home.md',
            'audits/orchestrator-wiki-audit-<YYYY-MM-DD>.md',
        ),
        supports_log_append=False,
        category='workflow',
        notes='Prompt-backed maintenance workflow; not handled by the append-only log writer.',
    ),
    '/refresh-model-catalog': PromptCommandSpec(
        command='/refresh-model-catalog',
        description='Regenerate the model catalog cache on demand.',
        prompt_file='refresh-model-catalog.prompt.md',
        targets=(
            'skills/model_catalog.json',
            '.github/agents/Orchestrator/skills/model_catalog.json',
        ),
        supports_log_append=False,
        category='workflow',
        notes='Prompt-backed cache refresh workflow; not handled by the append-only log writer.',
    ),
    '/refresh-model': PromptCommandSpec(
        command='/refresh-model',
        description='Shorter alias for `/refresh-model-catalog` — regenerate the model catalog cache on demand.',
        prompt_file='refresh-model.prompt.md',
        targets=(
            'skills/model_catalog.json',
            '.github/agents/Orchestrator/skills/model_catalog.json',
        ),
        supports_log_append=False,
        category='workflow',
        alias_for='/refresh-model-catalog',
        notes='Prompt-backed shorthand kept for slash-command ergonomics.',
    ),
    '/all-log': PromptCommandSpec(
        command='/all-log',
        description='Internal alias for `/full-log` used by runtime helpers.',
        prompt_file=None,
        targets=PROMPT_COMMANDS['/full-log'].targets if False else (
            'Behavior-Log.md',
            'Behavior-Patterns.md',
            'Learning-Backlog.md',
            'Project-Context-Log.md',
            'Runbook.md',
            'Skill-Usage-Log.md',
        ),
        supports_log_append=True,
        category='alias',
        alias_for='/full-log',
        notes='Intentionally internal-only; there is no dedicated `.github/prompts/all-log.prompt.md`.',
    ),
    '/critical': PromptCommandSpec(
        command='/critical',
        description='Internal critical-path checkpoint across behavior, context, and runbook.',
        prompt_file=None,
        targets=('Behavior-Log.md', 'Project-Context-Log.md', 'Runbook.md'),
        supports_log_append=True,
        category='internal',
        notes='Retained for scripted flows; not exposed as a slash prompt template.',
    ),
    '/behavior-log': PromptCommandSpec(
        command='/behavior-log',
        description='Internal alias for `/behavior`.',
        prompt_file=None,
        targets=('Behavior-Log.md',),
        supports_log_append=True,
        category='alias',
        alias_for='/behavior',
    ),
    '/pattern': PromptCommandSpec(
        command='/pattern',
        description='Internal alias for `/patterns-log`.',
        prompt_file=None,
        targets=('Behavior-Patterns.md',),
        supports_log_append=True,
        category='alias',
        alias_for='/patterns-log',
    ),
}


def normalize_command(command: str) -> str:
    normalized = (command or '').strip().lower()
    if normalized and not normalized.startswith('/'):
        normalized = '/' + normalized
    return normalized


def get_command_spec(command: str) -> PromptCommandSpec | None:
    return PROMPT_COMMANDS.get(normalize_command(command))


def get_append_command_targets() -> dict[str, list[str]]:
    return {
        command: list(spec.targets)
        for command, spec in PROMPT_COMMANDS.items()
        if spec.supports_log_append
    }


def get_prompt_backed_commands() -> dict[str, PromptCommandSpec]:
    return {
        command: spec
        for command, spec in PROMPT_COMMANDS.items()
        if spec.prompt_file is not None
    }


def discover_prompt_files(repo_root: Path) -> list[str]:
    """Discover prompt template filenames.

    The repository layout sometimes places prompt templates under `.github/prompts`
    (when the Orchestrator is packaged as a subfolder) or under `prompts/` at the
    repository root. This helper checks both locations and returns the union.
    """
    # Search upwards from the provided repo_root to find the first directory that
    # contains prompt templates. This supports both repository layouts where the
    # Orchestrator is nested under `.github/agents/Orchestrator` and layouts where
    # the Orchestrator lives at the repository root.
    for candidate_root in (repo_root, *repo_root.parents):
        found = []
        for candidate_dir in (candidate_root / PROMPTS_DIR, candidate_root / Path('prompts')):
            if candidate_dir.exists():
                found.extend(path.name for path in candidate_dir.glob('*.prompt.md'))
        if found:
            return sorted(set(found))

    # As a last resort, look for an Orchestrator subfolder under the passed
    # repo_root and prefer its prompts directory if present. This avoids
    # picking up unrelated prompt templates from other projects on the disk.
    for orch in repo_root.glob('**/Orchestrator'):
        for candidate_dir in (orch / '.github' / 'prompts', orch / 'prompts'):
            if candidate_dir.exists():
                return sorted({p.name for p in candidate_dir.glob('*.prompt.md')})

    # If there's no Orchestrator folder, fall back to scanning for any prompts
    # directories but limit results to avoid harvesting unrelated workspaces.
    found = []
    for candidate_dir in repo_root.glob('**/.github/prompts'):
        found.extend(path.name for path in Path(candidate_dir).glob('*.prompt.md'))
    for candidate_dir in repo_root.glob('**/prompts'):
        if candidate_dir.name == 'prompts' and candidate_dir.parent.name == '.github':
            continue
        found.extend(path.name for path in Path(candidate_dir).glob('*.prompt.md'))
    return sorted(set(found))


def build_manifest(repo_root: Path) -> list[dict[str, Any]]:
    return [
        PROMPT_COMMANDS[command].to_manifest_record(repo_root)
        for command in sorted(PROMPT_COMMANDS)
    ]
