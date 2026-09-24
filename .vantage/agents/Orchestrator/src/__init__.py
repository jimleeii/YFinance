"""Top-level package for the Orchestrator agent's Python modules.

This package exposes a lightweight version identifier and helps make the
``src`` modules importable as a package (they use "from src.x import y" in the
repository). Adding this file keeps that import style working when installed.
"""
__all__ = [
    "orchestrator_runtime",
    "skill_loader",
    "model_resolver",
    "policy_reloader",
    "workflow_state_machine",
]

__version__ = "0.1.0"
