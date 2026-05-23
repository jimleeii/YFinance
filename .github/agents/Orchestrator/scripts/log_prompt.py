#!/usr/bin/env python3
"""CLI to append prompt-style log entries to repository template log files.

Usage examples:
  python scripts/log_prompt.py /full-log "Fixed agent routing bug"
  echo "Detailed multi-line message" | python scripts/log_prompt.py /info -a "Wei Li"

The script maps short prompt commands (e.g. `/full-log`, `/info`, `/error`) to
one or more markdown files under the `.wiki/orchestrator/` folder and appends a timestamped
entry.
"""
from __future__ import annotations

import argparse
import json
import getpass
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import textwrap
import re

TEMPLATES_DIR_NAME = ".wiki/orchestrator"

LOG_COMMANDS: Dict[str, List[str]] = {
    "/full-log": [
        "Behavior-Log.md",
        "Behavior-Patterns.md",
        "Learning-Backlog.md",
        "Project-Context-Log.md",
        "Runbook.md",
        "Skill-Usage-Log.md",
    ],
    "/all-log": [
        "Behavior-Log.md",
        "Behavior-Patterns.md",
        "Learning-Backlog.md",
        "Project-Context-Log.md",
        "Runbook.md",
        "Skill-Usage-Log.md",
    ],
    "/critical": ["Behavior-Log.md", "Project-Context-Log.md", "Runbook.md"],
    "/error": ["Behavior-Log.md", "Project-Context-Log.md"],
    "/warning": ["Behavior-Log.md", "Behavior-Patterns.md"],
    "/warn": ["Behavior-Log.md", "Behavior-Patterns.md"],
    "/info": ["Skill-Usage-Log.md", "Behavior-Log.md"],
    "/debug": ["Runbook.md", "Learning-Backlog.md"],
    "/trace": ["Learning-Backlog.md"],
    "/behavior-log": ["Behavior-Log.md"],
    "/behavior": ["Behavior-Log.md"],
    "/patterns-log": ["Behavior-Patterns.md"],
    "/pattern": ["Behavior-Patterns.md"],
    "/learning-backlog": ["Learning-Backlog.md"],
    "/project-context": ["Project-Context-Log.md"],
    "/runbook": ["Runbook.md"],
    "/skill-usage": ["Skill-Usage-Log.md"],
}


def find_repo_root(start: Path | None = None) -> Path:
    p = Path(start or __file__).resolve()
    cur = p if p.is_dir() else p.parent
    markers = (TEMPLATES_DIR_NAME, 'orchestrator.agent.md', '.git')
    
    # First pass: look for .git to find the true workspace root
    git_root = None
    for _ in range(20):
        if (cur / '.git').exists():
            git_root = cur
            break
        if cur.parent == cur:
            break
        cur = cur.parent
    
    if git_root:
        return git_root
    
    # Fallback: if no .git found, look for other markers
    cur = Path(start or __file__).resolve()
    cur = cur if cur.is_dir() else cur.parent
    for _ in range(20):
        for m in markers:
            if (cur / m).exists():
                return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(__file__).resolve().parents[1]


def get_author(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(["git", "config", "--get", "user.name"], cwd=str(repo_root), stderr=subprocess.DEVNULL)
        name = out.decode().strip()
        if name:
            return name
    except Exception:
        pass
    name = os.environ.get("GIT_AUTHOR_NAME") or os.environ.get("USER") or os.environ.get("USERNAME")
    if name:
        return name
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def format_entry(command: str, author: str, message: str, tags: str | None = None) -> str:
    now = datetime.now(timezone.utc).astimezone()
    timestamp = now.isoformat(timespec="seconds")
    header = f"### {timestamp} — {command} — {author}\n\n"
    if tags:
        header += f"Tags: {tags}\n\n"
    body = message.strip() + "\n\n"
    return header + body


def ensure_file(path: Path):
    if not path.exists():
        path.write_text(f"# {path.name}\n\n", encoding="utf-8")


def _normalize_label(label: str) -> str:
    cleaned = label.lower().replace("/", "_")
    cleaned = re.sub(r"[()]+", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    return re.sub(r"_+", "_", cleaned).strip("_")


def _context_key_aliases(label: str) -> list[str]:
    normalized = _normalize_label(label)
    aliases = [normalized]

    if normalized == "affected_subagent_s":
        aliases.append("affected_subagents")
    elif normalized == "subagent_s":
        aliases.append("subagents")

    return aliases


def _stringify_context_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_stringify_context_value(item) for item in value if _stringify_context_value(item))
    if isinstance(value, dict):
        return ", ".join(f"{key}={_stringify_context_value(item)}" for key, item in value.items())
    return str(value)


def _parse_context_payload(message: str) -> tuple[str, Dict[str, Any] | None]:
    stripped = message.strip()
    if not stripped.startswith("{"):
        return message, None
    try:
        payload = json.loads(stripped)
    except Exception:
        return message, None
    if not isinstance(payload, dict):
        return message, None
    return "", payload


def _context_for_target(context_payload: Dict[str, Any] | None, target_name: str) -> Dict[str, Any] | None:
    if not context_payload:
        return None
    if "defaults" in context_payload or "targets" in context_payload:
        merged: Dict[str, Any] = {}
        defaults = context_payload.get("defaults")
        if isinstance(defaults, dict):
            merged.update(defaults)
        targets = context_payload.get("targets")
        if isinstance(targets, dict):
            target_context = targets.get(target_name)
            if isinstance(target_context, dict):
                merged.update(target_context)
        return merged or None
    return context_payload


def _extract_entry_template(block_text: str) -> str | None:
    """Extract and dedent the contents of an `entry_template: |` block."""
    m = re.search(r'entry_template:\s*\|\s*\n', block_text)
    if not m:
        return None
    lines = block_text[m.end():].splitlines()
    collected = []
    for line in lines:
        if line.startswith(' ') or line.startswith('\t') or line.strip() == '':
            collected.append(line)
            continue
        break
    if not collected:
        return None
    tpl = '\n'.join(collected)
    return textwrap.dedent(tpl).rstrip('\n')


def _normalize_internal_log_links(text: str) -> str:
    """Normalize orchestrator wiki fragments so internal anchors stay consistent."""
    internal_log_files = (
        'Behavior-Log.md',
        'Behavior-Patterns.md',
        'Learning-Backlog.md',
        'Project-Context-Log.md',
        'Runbook.md',
        'Skill-Usage-Log.md',
    )

    pattern = re.compile(
        rf'(\[(?P<label>[^\]]+)\]\((?P<file>{"|".join(re.escape(name) for name in internal_log_files)})#)(?P<fragment>[^)]+)(\))'
    )

    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group('fragment').lower()}{match.group(5)}"

    return pattern.sub(replace, text)


def _find_prompt_templates(repo_root: Path, cmd_name: str) -> tuple[Dict[str, str], str | None]:
    """Find per-target prompt templates in .github/prompts/<cmd_name>.prompt.md.

    Returns a tuple of:
    - mapping of target file name -> template text
    - default template for prompt files that define a single template block
    """
    prompt_path = repo_root / '.github' / 'prompts' / f"{cmd_name}.prompt.md"
    if not prompt_path.exists():
        return {}, None
    text = prompt_path.read_text(encoding='utf-8')
    lines = text.splitlines()
    templates: Dict[str, str] = {}
    default_template: str | None = None
    current_target: str | None = None

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        heading_match = re.fullmatch(r'(?:#{1,6}\s+)?`?(?P<target>[A-Za-z0-9_.-]+\.md)`?', stripped)
        if heading_match:
            current_target = heading_match.group('target')
            i += 1
            continue

        if stripped.startswith('```'):
            fence_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                fence_lines.append(lines[i])
                i += 1

            tpl = _extract_entry_template('\n'.join(fence_lines))
            if tpl:
                if current_target:
                    templates[current_target] = tpl
                elif default_template is None:
                    default_template = tpl
                current_target = None

            if i < len(lines) and lines[i].strip().startswith('```'):
                i += 1
            continue

        i += 1

    return templates, default_template


def _render_template(
    template: str,
    message: str,
    author: str,
    tags: str | None = None,
    context: Dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc).astimezone()
    date = now.strftime('%Y%m%d')
    time = now.strftime('%H%M%S')
    iso = now.isoformat(timespec='seconds')
    utc = now.astimezone(timezone.utc).replace(microsecond=0).isoformat()

    context_values = {_normalize_label(str(key)): _stringify_context_value(value) for key, value in (context or {}).items()}

    tpl = template
    for token, value in (
        ('YYYYMMDDHHMMSS', date + time),
        ('yyyymmddhhmmss', date + time),
        ('YYYYMMDD', date),
        ('yyyymmdd', date),
        ('HHMMSS', time),
        ('hhmmss', time),
        ('XXX', time),
        ('xxx', time),
    ):
        tpl = tpl.replace(token, value)
    tpl = _normalize_internal_log_links(tpl)
    lines = tpl.splitlines()
    out_lines: list[str] = []
    inserted_change = False
    for line in lines:
        stripped = line.strip()
        low = stripped.lower()

        if low.startswith('###'):
            out_lines.append(line)
            continue

        field_match = re.match(r'^(?P<indent>\s*-\s*)(?P<label>[^:]+):(?P<rest>.*)$', line)
        if field_match:
            label = field_match.group('label').strip()
            aliases = _context_key_aliases(label)

            # Prefer structured context values when available.
            value = next((context_values.get(alias, '') for alias in aliases if context_values.get(alias, '')), '')

            if not value:
                norm_label = aliases[0]
                if norm_label == 'date':
                    value = context_values.get('date', iso)
                elif norm_label == 'timestamp_utc':
                    value = context_values.get('timestamp_utc', utc)
                elif norm_label == 'change_applied':
                    value = context_values.get('change_applied', message)
                    if value:
                        inserted_change = True
                elif norm_label == 'summary':
                    value = context_values.get('summary', '')

            if value:
                if '\n' in value:
                    out_lines.append(f"{field_match.group('indent')}{label}: |")
                    for value_line in value.splitlines():
                        out_lines.append(f"{field_match.group('indent').replace('- ', '  ')}{value_line}")
                else:
                    out_lines.append(f"{field_match.group('indent')}{label}: {value}")
                continue

            if norm_label == 'contract_score':
                continue

        if low.startswith('- date:'):
            out_lines.append(f"- Date: {context_values.get('date', iso)}")
            continue
        if low.startswith('- timestamp (utc):'):
            out_lines.append(f"- Timestamp (UTC): {context_values.get('timestamp_utc', utc)}")
            continue

        # Keep the template line unchanged if no structured value is provided.
        out_lines.append(line)

    if not context_values and not inserted_change:
        out_lines.append('')
        out_lines.extend(message.splitlines())

    # Optionally add tags/author if not present in template
    if tags:
        out_lines.append('')
        out_lines.append(f"Tags: {tags}")
    if author:
        out_lines.append('')
        out_lines.append(f"Author: {author}")

    return '\n'.join(out_lines) + '\n\n'


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a prompt-style log entry to repository template log files.")
    parser.add_argument("command", help="Prompt command name (e.g. /full-log, /info)")
    parser.add_argument("message", nargs="?", help="Message text to log. If omitted, read from stdin.")
    parser.add_argument("-a", "--author", help="Author name to include in the entry.")
    parser.add_argument("-t", "--tags", help="Comma-separated tags to add to the entry.")
    parser.add_argument("--preview", action="store_true", help="Print the generated entries but do not write files.")
    parser.add_argument("--root", help="Repository root (for testing). If omitted, discovered automatically.")
    args = parser.parse_args()

    repo_root = Path(args.root) if args.root else find_repo_root(Path(__file__))
    templates_dir = repo_root / TEMPLATES_DIR_NAME

    if not templates_dir.exists():
        print(f"Templates directory not found at {templates_dir}; creating it.")
        templates_dir.mkdir(parents=True, exist_ok=True)

    cmd = args.command.strip()
    if not cmd.startswith("/"):
        cmd = "/" + cmd
    cmd_low = cmd.lower()

    targets = LOG_COMMANDS.get(cmd_low)
    if targets is None:
        print("Unknown command:", cmd)
        print("Available commands:")
        for k in sorted(LOG_COMMANDS.keys()):
            print(" ", k)
        return 2

    msg = args.message
    if not msg:
        if not sys.stdin.isatty():
            msg = sys.stdin.read().strip()
        else:
            print("Enter message (end with Ctrl-D/Ctrl-Z):")
            try:
                msg = sys.stdin.read().strip()
            except KeyboardInterrupt:
                msg = ""
    if not msg:
        print("No message provided; aborting.")
        return 1

    message_body, context_payload = _parse_context_payload(msg)

    author = args.author or get_author(repo_root)

    entries: Dict[Path, str] = {}
    # Attempt to find prompt-based entry templates for this command in prompts/
    cmd_name = cmd_low.lstrip('/')
    prompt_templates, default_template = _find_prompt_templates(repo_root, cmd_name)
    for f in targets:
        path = templates_dir / f
        ensure_file(path)
        prompt_tpl = prompt_templates.get(f) or default_template
        if prompt_tpl:
            target_context = _context_for_target(context_payload, f)
            entry = _render_template(prompt_tpl, message_body, author, args.tags, context=target_context)
        else:
            entry = format_entry(cmd, author, msg, args.tags)
        entries[path] = entry

    if args.preview:
        print("--- Preview (no files written) ---")
        for path, entry in entries.items():
            print(f"\n--- {path} ---\n")
            print(entry)
        return 0

    for path, entry in entries.items():
        with path.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    print(f"Wrote entry for {len(entries)} file(s):")
    for p in entries.keys():
        try:
            print(" -", p.relative_to(repo_root))
        except Exception:
            print(" -", str(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
