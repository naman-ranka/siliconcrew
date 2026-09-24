import os
import sys
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# No test may touch the developer's real app state. api.py binds DB_PATH and the
# workspace dir at import time from these two variables, falling back to
# ~/.siliconcrew/state.db and <checkout>/workspace, so set them before any test
# module imports it. Unconditional: a developer's shell may point them at real data.
_TEST_STATE = tempfile.mkdtemp(prefix="siliconcrew-tests-")
os.environ["RTL_DATA_DIR"] = os.path.join(_TEST_STATE, "data")
os.environ["RTL_WORKSPACE"] = os.path.join(_TEST_STATE, "workspace")


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
    yield


@pytest.fixture(autouse=True)
def _isolate_user_skill_layer(tmp_path_factory):
    """No test may see the developer's own skills.

    The user layer is real local state (``~/.siliconcrew/skills`` by default),
    so without this a machine where someone wrote or disabled a skill would run
    a different suite than CI — and the failures would look like product bugs.
    Every test gets an empty layer; a test about the layer fills its own.
    """
    try:
        from src.platform_engines.user_skill_store import (
            LocalUserSkillStore,
            set_user_skill_store,
        )
    except Exception:
        yield
        return
    set_user_skill_store(LocalUserSkillStore(tmp_path_factory.mktemp("user-skills")))
    try:
        yield
    finally:
        set_user_skill_store(None)
