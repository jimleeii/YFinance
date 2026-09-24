#!/usr/bin/env python3
"""Backward-compatible CLI wrapper around ``src.model_discovery``."""
from __future__ import annotations

from src.model_discovery import main


if __name__ == "__main__":
    raise SystemExit(main())
