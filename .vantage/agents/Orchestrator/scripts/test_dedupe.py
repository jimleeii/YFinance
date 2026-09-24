import sys
from pathlib import Path
try:
    # Add the orchestrator dir to sys.path so we can import hooks.log_hooks
    orchestrator_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(orchestrator_dir))
    from hooks import log_hooks

    # create a string containing a lone low surrogate U+DC8F
    surrogate_str = 'test ' + chr(0xDC8F)
    metadata = {'session_id': 's1'}
    print('calling _build_curated_dedupe_key with surrogate in summary...')
    key = log_hooks._build_curated_dedupe_key(metadata, summary=surrogate_str)
    print('OK:', key)
except Exception as e:
    print('ERROR:', type(e), e)
    raise
