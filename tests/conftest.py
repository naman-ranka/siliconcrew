import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _clear_synthesis_memory_state():
    """Synthesis bookkeeping is keyed by workspace::run_id and the temp
    workspaces tests create repeat both parts across tests (tmp_path reuse,
    every workspace starts at synth_0001), so process-memory caches must not
    leak between tests."""
    try:
        from src.tools import synthesis_manager as _sm
    except Exception:
        yield
        return
    _sm._JOBS.clear()
    _sm._POLL_CACHE.clear()
    _sm._POLL_BACKOFF_STATE.clear()
    yield
