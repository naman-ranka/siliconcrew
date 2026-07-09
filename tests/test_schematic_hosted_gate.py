"""X2M-5: schematic_tool gives an honest answer on hosted (no raw docker error).

Yosys-schematic needs local Docker, absent on Cloud Run. On hosted the tool used
to leak "failed to connect to the docker API at unix:///var/run/docker.sock…" to
the external app. It now returns a clear "not available on hosted" message,
mirroring the run_python_analysis hosted gate. Self-host is unaffected.
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


def test_hosted_returns_honest_message_no_docker_leak(monkeypatch):
    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    reset_settings_cache()
    from src.tools.wrappers import schematic_tool

    out = schematic_tool.invoke({"verilog_file": "design.v", "top_module": "design"})
    assert "hosted" in out.lower()
    assert "schematic" in out.lower()
    # No raw stack trace / docker-socket error leaks to the external app.
    assert "docker.sock" not in out.lower()
    assert "traceback" not in out.lower()


def test_self_host_does_not_short_circuit(monkeypatch, tmp_path):
    """Self-host must NOT hit the hosted gate: a missing file reaches the normal
    'does not exist' path (proves the gate is hosted-only, without needing docker)."""
    monkeypatch.delenv("SILICONCREW_HOSTED", raising=False)
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path))
    reset_settings_cache()
    from src.tools.wrappers import schematic_tool

    out = schematic_tool.invoke({"verilog_file": "nope.v", "top_module": "x"})
    assert "hosted" not in out.lower()
    assert "does not exist" in out.lower()
