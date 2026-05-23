#!/usr/bin/env python3
"""Repair existing orchestrator wiki log files with placeholder anchors.

This script backfills `.wiki/orchestrator/*.md` so older entries stop keeping
template fragments such as `#pat-yyyymmdd-xxx` and so headings split cleanly
between appended entries.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ENTRY_FILE_LINKS: dict[str, dict[str, str]] = {
    'Behavior-Log.md': {
        'Behavior-Patterns.md': 'pat',
        'Learning-Backlog.md': 'lrn',
    },
    'Behavior-Patterns.md': {
        'Behavior-Log.md': 'obs',
    },
    'Learning-Backlog.md': {
        'Behavior-Patterns.md': 'pat',
    },
    'Project-Context-Log.md': {
        'Behavior-Log.md': 'obs',
        'Learning-Backlog.md': 'lrn',
        'Runbook.md': 'chg',
    },
    'Runbook.md': {
        'Behavior-Patterns.md': 'pat',
        'Learning-Backlog.md': 'lrn',
    },
}


HEADING_RE = re.compile(r'(?<!\n)(?P<heading>[ \t]*###\s+(?P<entry_id>[A-Z]+-\d{8}(?:-\d{3,6})?))')
LINK_RE = re.compile(
    r'\[(?P<label>[^\]]+)\]\((?P<file>Behavior-Log|Behavior-Patterns|Learning-Backlog|Project-Context-Log|Runbook|Skill-Usage-Log)\.md#(?P<fragment>[^)]+)\)'
)


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for _ in range(10):
        if (current / '.wiki' / 'orchestrator').exists() and (current / '.github').exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path(__file__).resolve().parents[5]


def normalize_text(text: str, current_file: str) -> str:
    text = HEADING_RE.sub(r'\n\n\g<heading>', text)

    file_links = ENTRY_FILE_LINKS.get(current_file, {})
    if not file_links:
        return text

    current_entry_id: str | None = None
    output_lines: list[str] = []

    for line in text.splitlines():
        heading_match = re.fullmatch(r'[ \t]*###\s+(?P<entry_id>[A-Z]+-\d{8}(?:-\d{3,6})?)', line)
        if heading_match:
            current_entry_id = heading_match.group('entry_id')
            output_lines.append(line)
            continue

        if current_entry_id:
            suffix = current_entry_id.split('-', 1)[1]

            def replace(match: re.Match[str]) -> str:
                target_file = f"{match.group('file')}.md"
                target_prefix = file_links.get(target_file)
                if not target_prefix:
                    return match.group(0)
                return f"[{match.group('label')}]({target_file}#{target_prefix}-{suffix.lower()})"

            line = LINK_RE.sub(replace, line)

        output_lines.append(line)

    return '\n'.join(output_lines) + ('\n' if text.endswith('\n') else '')


def normalize_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8')
    updated = normalize_text(original, path.name)
    if updated == original:
        return False
    path.write_text(updated, encoding='utf-8')
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description='Backfill placeholder anchors in orchestrator wiki log files.')
    parser.add_argument('--root', help='Repository root. Defaults to discovery from this script location.')
    parser.add_argument('--dry-run', action='store_true', help='Report files that would change without writing them.')
    args = parser.parse_args()

    repo_root = Path(args.root).resolve() if args.root else find_repo_root()
    wiki_root = repo_root / '.wiki' / 'orchestrator'
    if not wiki_root.exists():
        print(f'Wiki root not found: {wiki_root}')
        return 2

    changed: list[str] = []
    for file_name in ('Behavior-Log.md', 'Behavior-Patterns.md', 'Learning-Backlog.md', 'Project-Context-Log.md', 'Runbook.md'):
        path = wiki_root / file_name
        if not path.exists():
            continue
        if normalize_file(path):
            changed.append(file_name)

    if changed:
        action = 'Would update' if args.dry_run else 'Updated'
        print(f"{action} {len(changed)} file(s):")
        for file_name in changed:
            print(f' - {file_name}')
    else:
        print('No orchestrator wiki files needed changes.')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())