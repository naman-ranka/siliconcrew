"""The run_python_analysis capability gate (Item 2 / PA3 / PA4).

The load-bearing "hosted OFF" switch is get_settings().hosted checked INSIDE the
wrapper — so every path (agent / MCP / REST) is covered by construction, since
authorize() alone only distinguishes anonymous. Self-host (hosted off) is
allowed. These drive the actual LangChain tool wrapper.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pytest.importorskip("langchain_core")

from src.platform_engines.settings import reset_settings_cache


@pytest.fixture(autouse=True)
def _clean_settings():
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_hosted_reports_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    reset_settings_cache()
    from src.tools.wrappers import run_python_analysis

    out = run_python_analysis.invoke({"script_file": "gen.py", "args": []})
    assert "hosted" in out.lower()
    assert "not available" in out.lower() or "isn't available" in out.lower()


def test_self_host_runs_the_script(monkeypatch, tmp_path):
    monkeypatch.delenv("SILICONCREW_HOSTED", raising=False)
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("PYTHON_ENGINE", "native")  # deterministic, no docker dependency
    reset_settings_cache()
    (tmp_path / "gen.py").write_text("print('hello from self-host')\n")

    from src.tools.wrappers import run_python_analysis

    out = run_python_analysis.invoke({"script_file": "gen.py", "args": []})
    assert "hello from self-host" in out
    assert '"ok": true' in out.lower()


def test_action_python_not_anonymous_allowed():
    """Defense in depth: PYTHON is a capability an anonymous trial never has."""
    from src.platform_engines.identity import Action, ANONYMOUS_ALLOWED

    assert Action.PYTHON not in ANONYMOUS_ALLOWED
