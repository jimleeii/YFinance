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

# Ensure repository root is on sys.path so `src` package is importable when run from scripts/
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Handle an orchestrator request: persist artifacts and optionally run skill scripts")
    parser.add_argument("--prompt", "-p", default="", help="Request prompt to persist")
    parser.add_argument("--user", "-u", default="runtime-user", help="User name")
    parser.add_argument(
        "--dispatch", "-d", default="single-agent",
        choices=["direct", "single-agent", "multi-agent", "concurrent"],
        help="Dispatch path. Use 'concurrent' for independent parallel tracks.",
    )
    parser.add_argument("--event-flags", help="Structured JSON event flags to influence logging decisions")
    parser.add_argument("--metadata", help="Structured JSON metadata to carry into wiki log entries")
    parser.add_argument("--run-skill", help="Skill name to run a script from")
    parser.add_argument("--skill-script", help="Specific script filename inside the skill folder to run")
    parser.add_argument("--run-script", help="Arbitrary repo script path to run (python/ps1/sh)")
    parser.add_argument("--response-text", help="Subagent response text to score via score.py")
    parser.add_argument("--response-role", choices=["architect", "developer", "reviewer"],
                        help="Role hint for scoring (auto-detected when omitted)")
    parser.add_argument("--score-threshold", type=int, default=70,
                        help="Minimum passing contract score (default 70)")
    parser.add_argument("--cycle-id", help="Explicit cycle ID; auto-generated when omitted")
    args = parser.parse_args(argv)

    event_flags = {}
    if args.event_flags:
        try:
            event_flags = json.loads(args.event_flags)
            if not isinstance(event_flags, dict):
                raise ValueError("event flags must be a JSON object")
        except Exception as exc:
            parser.error(f"--event-flags must be a JSON object: {exc}")

    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except Exception as exc:
            parser.error(f"--metadata must be a JSON object: {exc}")

    # Import here after ensuring repo root is on sys.path to satisfy linter
    from src.orchestrator_runtime import handle_request

    # Inject explicit cycle_id into metadata when supplied
    if args.cycle_id:
        metadata.setdefault("cycle_id", args.cycle_id)

    result = handle_request(
        prompt=args.prompt,
        user=args.user,
        dispatch=args.dispatch,
        run_skill=args.run_skill,
        skill_script_name=args.skill_script,
        run_script_path=args.run_script,
        event_flags=event_flags,
        metadata=metadata,
        response_text=args.response_text,
        response_role=args.response_role,
        score_threshold=args.score_threshold,
    )

    # Print JSON to stdout so callers can parse it if desired.
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
