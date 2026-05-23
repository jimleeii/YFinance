#!/usr/bin/env python3
"""CLI wrapper to call `handle_request` in the orchestrator runtime.

This script is intended to be invoked by the Orchestrator agent (via
`execute/runInTerminal` or equivalent) at request intake to persist logs
and optionally execute a skill script.
"""
from __future__ import annotations

import argparse
import json
import sys

import os
import sys

# Ensure repository root is on sys.path so `src` package is importable when run from scripts/
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.orchestrator_runtime import handle_request


def main(argv=None):
    parser = argparse.ArgumentParser(description="Handle an orchestrator request: persist artifacts and optionally run skill scripts")
    parser.add_argument("--prompt", "-p", default="", help="Request prompt to persist")
    parser.add_argument("--user", "-u", default="runtime-user", help="User name")
    parser.add_argument("--dispatch", "-d", default="single-agent", help="Dispatch path")
    parser.add_argument("--run-skill", help="Skill name to run a script from")
    parser.add_argument("--skill-script", help="Specific script filename inside the skill folder to run")
    parser.add_argument("--run-script", help="Arbitrary repo script path to run (python/ps1/sh)")
    args = parser.parse_args(argv)

    result = handle_request(
        prompt=args.prompt,
        user=args.user,
        dispatch=args.dispatch,
        run_skill=args.run_skill,
        skill_script_name=args.skill_script,
        run_script_path=args.run_script,
    )

    # Print JSON to stdout so callers can parse it if desired.
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
