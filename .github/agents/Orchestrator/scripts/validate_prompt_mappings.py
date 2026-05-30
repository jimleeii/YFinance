#!/usr/bin/env python3
"""Validate that prompt templates and command mappings stay aligned.

The validator treats `prompt_registry.py` as the canonical registry and checks:
- every prompt-backed command has a real `.github/prompts/*.prompt.md` file
- every prompt file is referenced by exactly one registry entry
- every target declared by the registry is mentioned in the prompt content
- append-capable commands declare at least one target
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from prompt_registry import (  # noqa: E402
    PROMPT_COMMANDS,
    build_manifest,
    discover_prompt_files,
)


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


def _target_token(target: str) -> str:
    return target.replace('audits/', '').strip()


def validate_manifest(repo_root: Path) -> list[str]:
    # If the provided repo_root doesn't contain prompt templates, search up the
    # ancestor chain for a directory that does. Tests running in different
    # workspace layouts may pass an ancestor path; this makes validation robust.
    for candidate_root in (repo_root, *repo_root.parents):
        if (candidate_root / '.github' / 'prompts').exists() or (candidate_root / 'prompts').exists():
            repo_root = candidate_root
            break

    # Support both `.github/prompts` (packaged layout) and top-level `prompts/` (repo-local)
    prompt_dirs = [repo_root / '.github' / 'prompts', repo_root / 'prompts']

    # If the repo_root still doesn't contain a prompts directory, look for an
    # Orchestrator subfolder and prefer its prompts directory (handles the
    # case where the caller passed an ancestor directory).
    if not any(d.exists() for d in prompt_dirs):
        for orch in repo_root.glob('**/Orchestrator'):
            for candidate in (orch / '.github' / 'prompts', orch / 'prompts'):
                if candidate.exists():
                    prompt_dirs = [candidate]
                    break
            if any(d.exists() for d in prompt_dirs):
                break
    discovered = set(discover_prompt_files(repo_root))
    referenced: dict[str, str] = {}
    errors: list[str] = []

    for command, spec in sorted(PROMPT_COMMANDS.items()):
        if spec.supports_log_append and not spec.targets:
            errors.append(f'{command}: append-capable command must declare at least one target')

        if spec.prompt_file is None:
            continue

        # locate the prompt file in any known prompt directory
        prompt_path = None
        for pd in prompt_dirs:
            candidate = pd / spec.prompt_file
            if candidate.exists():
                prompt_path = candidate
                break

        if prompt_path is None:
            errors.append(f'{command}: prompt file missing: .github/prompts/{spec.prompt_file}')
            continue

        previous = referenced.get(spec.prompt_file)
        if previous and previous != command:
            errors.append(f'{command}: prompt file {spec.prompt_file} is already owned by {previous}')
        referenced[spec.prompt_file] = command

        prompt_text = prompt_path.read_text(encoding='utf-8')
        for target in spec.targets:
            token = _target_token(target)
            if token not in prompt_text:
                errors.append(f'{command}: target `{target}` not mentioned in {spec.prompt_file}')

    orphaned = sorted(discovered - set(referenced))
    for prompt_name in orphaned:
        errors.append(f'orphan prompt template: .github/prompts/{prompt_name}')

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate Orchestrator prompt-command mappings')
    parser.add_argument('--root', help='Repository root; auto-detected when omitted')
    parser.add_argument('--json', action='store_true', help='Emit JSON instead of plain text')
    parser.add_argument('--manifest', action='store_true', help='Print the resolved command manifest')
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve() if args.root else _find_repo_root()
    errors = validate_manifest(repo_root)

    if args.manifest:
        manifest = build_manifest(repo_root)
        if args.json:
            print(json.dumps({'manifest': manifest, 'errors': errors}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(manifest, indent=2, ensure_ascii=False))
            if errors:
                print('\nValidation errors:')
                for error in errors:
                    print(f' - {error}')
        return 1 if errors else 0

    if args.json:
        print(json.dumps({'errors': errors}, indent=2, ensure_ascii=False))
    elif errors:
        print('Prompt mapping validation failed:')
        for error in errors:
            print(f' - {error}')
    else:
        print('Prompt mapping validation passed.')

    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
