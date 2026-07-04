import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _clear_synthesis_memory_state():
    """Synthesis bookkeeping is keyed by run_id (Wave 9) and run ids repeat
    across the temp workspaces tests create (every workspace starts at
    synth_0001), so process-memory caches must not leak between tests."""
    try:
        from src.tools import synthesis_manager as _sm
    except Exception:
        yield
        return
    _sm._JOBS.clear()
    _sm._POLL_CACHE.clear()
    _sm._POLL_BACKOFF_STATE.clear()
    yield
