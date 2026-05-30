from pathlib import Path
import sys

# Ensure the Orchestrator hooks package is importable
orchestrator_root = Path('.github/agents/Orchestrator').resolve()
if str(orchestrator_root) not in sys.path:
    sys.path.insert(0, str(orchestrator_root))

from hooks.log_hooks import log_cycle

res = log_cycle(
    dispatch_path='single-agent',
    event_flags={},
    summary='Test preview for model label mapping',
    skills=None,
    metadata={'selected_model': 'gpt-5.4-mini'},
    transcript=None,
    force_persist_all=False,
    author='test',
    root=orchestrator_root,
    target_root=Path('.').resolve(),
    preview=True,
    prompt_command=None,
)
print(res)
