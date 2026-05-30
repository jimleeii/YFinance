#!/usr/bin/env python3
"""Refresh `skills/model_catalog.json` from on-demand model discovery."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for _ in range(20):
        if (current / "AGENTS.md").exists() or (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path(__file__).resolve().parents[1]


def main() -> int:
    workspace_root = find_repo_root(Path(__file__))
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))

    from src.model_discovery import discover_model_catalog_bundle, save_model_catalog

    bundle = discover_model_catalog_bundle(repo_root=workspace_root)

    root_catalog_path = save_model_catalog(bundle.catalog, workspace_root / "skills" / "model_catalog.json")
    print(f"Wrote model catalog to {root_catalog_path}")

    mirror_root = workspace_root / ".github" / "agents" / "Orchestrator"
    mirror_catalog_path = mirror_root / "skills" / "model_catalog.json"
    if mirror_catalog_path.parent.exists():
        save_model_catalog(bundle.catalog, mirror_catalog_path)
        print(f"Wrote model catalog to {mirror_catalog_path}")

    parsed = json.loads(root_catalog_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise SystemExit(f"Invalid model catalog JSON: {root_catalog_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
