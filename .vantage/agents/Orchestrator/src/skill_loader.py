"""Skill discovery utilities for the Orchestrator.

Provides a small, dependency-free loader that indexes `skills/*/SKILL.md` files
and produces a JSON manifest that the Orchestrator can consume.

This is intentionally simple: it parses a minimal YAML-like front matter
and extracts the first markdown heading and the first paragraph as a
human-friendly title/description.
"""
from __future__ import annotations

import os
import json
import re
from typing import Dict, Any, Optional, Tuple


def _parse_front_matter(content: str) -> Dict[str, Any]:
    """Naive front-matter parser: extracts simple `key: value` pairs.

    Only supports a tiny subset of YAML used in these SKILL.md files (strings
    and simple bracket lists). This avoids adding an external dependency.
    """
    fm: Dict[str, Any] = {}
    s = content.lstrip()
    if not s.startswith("---"):
        return fm
    parts = s.split("---", 2)
    if len(parts) < 3:
        return fm
    fm_text = parts[1]
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        # strip optional quotes
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        # list form: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            items = [i.strip().strip('"').strip("'") for i in val[1:-1].split(",") if i.strip()]
            fm[key] = items
        else:
            fm[key] = val
    return fm


def _parse_title_and_description(content: str) -> Tuple[Optional[str], str]:
    """Extract first markdown heading and the following paragraph as description.

    Falls back to using the first non-empty paragraph if no heading is present.
    """
    # Find first markdown header
    m = re.search(r"^\s*#{1,6}\s*(.+)$", content, re.MULTILINE)
    if m:
        title = m.group(1).strip()
        rest = content[m.end():].strip()
        paragraphs = re.split(r"\n\s*\n", rest)
        for p in paragraphs:
            if not p.strip():
                continue
            if re.match(r"^\s*#{1,6}\s*", p):
                continue
            # first non-header paragraph
            desc = "\n".join(p.strip().splitlines()[:5]).strip()
            return title, desc
        return title, ""

    # Fallback: first paragraph
    paragraphs = re.split(r"\n\s*\n", content.strip())
    for p in paragraphs:
        s = p.strip()
        if not s:
            continue
        lines = s.splitlines()
        first_line = lines[0].strip()
        desc = "\n".join(lines[1:6]).strip()
        return first_line, desc

    return None, ""


def discover_skills(skills_dir: str = "skills") -> Dict[str, Dict[str, Any]]:
    """Scan `skills_dir` for subfolders containing `SKILL.md` and return a manifest.

    Manifest shape:
      { skill_dir_name: { path, title, description, front_matter, raw } }
    """
    manifest: Dict[str, Dict[str, Any]] = {}
    if not os.path.isdir(skills_dir):
        return manifest

    for entry in sorted(os.listdir(skills_dir)):
        entry_path = os.path.join(skills_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        skill_md = os.path.join(entry_path, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        try:
            with open(skill_md, "r", encoding="utf8") as fh:
                content = fh.read()
        except Exception:
            # skip unreadable files
            continue

        fm = _parse_front_matter(content)
        title, description = _parse_title_and_description(content)
        manifest[entry] = {
            "path": os.path.relpath(skill_md).replace("\\", "/"),
            "title": title or fm.get("name") or entry,
            "description": description or fm.get("description", ""),
            "front_matter": fm,
            "raw": content,
        }

    return manifest


def save_manifest(manifest: Dict[str, Any], manifest_path: str = "skills/skills_manifest.json") -> None:
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    # Write to a temporary file first and atomically replace to avoid
    # truncating the manifest on partial failures or concurrent access.
    tmp_path = manifest_path + ".tmp"
    with open(tmp_path, "w", encoding="utf8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    try:
        os.replace(tmp_path, manifest_path)
    except Exception:
        # Fallback: attempt a direct write if atomic replace isn't supported.
        with open(manifest_path, "w", encoding="utf8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def load_manifest(manifest_path: str = "skills/skills_manifest.json") -> Dict[str, Any]:
    if not os.path.exists(manifest_path):
        return {}
    with open(manifest_path, "r", encoding="utf8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    m = discover_skills()
    save_manifest(m)
    print(f"Wrote manifest with {len(m)} skills to skills/skills_manifest.json")
