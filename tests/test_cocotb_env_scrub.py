"""Item 3: the native cocotb subprocess gets a SCRUBBED env (no backend secrets).

cocotb runs the agent's Python; the native ToolEngine used to merge the full
backend ``os.environ`` (API keys, DB URLs) into the child. run_cocotb now passes
a scrubbed ``base_env``; the engine uses it as the base instead of os.environ.
The docker path already isolates (clean image env + only explicit -e vars).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class _FakePopen:
    """Records the env handed to the child without actually spawning one."""

    last_env = None

    def __init__(self, argv, **kw):
        type(self).last_env = kw.get("env")
        self.returncode = 0

    def communicate(self, timeout=None):
        return ("", "")

    def poll(self):
        return 0

    def kill(self):
        pass


def test_native_engine_uses_base_env_not_os_environ(monkeypatch, tmp_path):
    import src.platform_engines.tool_engine as te

    monkeypatch.setattr(te.subprocess, "Popen", _FakePopen)
    monkeypatch.setenv("SC_LEAK_SECRET", "leaked-value")

    te.NativeToolEngine().run(
        image="x", command="true", cwd=str(tmp_path),
        env={"SC_SOURCES": "[]"}, timeout=5,
        base_env={"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)},
    )
    env = _FakePopen.last_env
    assert "SC_LEAK_SECRET" not in env       # host secret scrubbed
    assert env.get("SC_SOURCES") == "[]"     # engine env layered on top of base
    assert "PATH" in env


def test_native_engine_default_still_inherits_os_environ(monkeypatch, tmp_path):
    """Default (no base_env) is unchanged for xls/sby — they run tool binaries,
    not user scripts, and rely on the inherited environment."""
    import src.platform_engines.tool_engine as te

    monkeypatch.setattr(te.subprocess, "Popen", _FakePopen)
    monkeypatch.setenv("SC_INHERIT_ME", "yes")

    te.NativeToolEngine().run(image="x", command="true", cwd=str(tmp_path), timeout=5)
    assert _FakePopen.last_env.get("SC_INHERIT_ME") == "yes"


def test_run_cocotb_passes_scrubbed_base_env(monkeypatch, tmp_path):
    import src.tools.run_cocotb as rc

    captured = {}

    class _RecordingEngine:
        mode = "native"

        def run(self, **kw):
            captured.update(kw)
            return {
                "success": True,
                "stdout": "SC_COCOTB_RESULT pass=1 fail=0 xml=yes",
                "stderr": "",
                "timed_out": False,
                "command": "x",
            }

    monkeypatch.setattr(rc, "get_tool_engine", lambda: _RecordingEngine())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    (tmp_path / "dut.v").write_text("module dut; endmodule")

    rc.run_cocotb(["dut.v"], "dut", "test_dut", cwd=str(tmp_path))

    base_env = captured.get("base_env")
    assert base_env is not None, "run_cocotb must pass base_env to scrub the native child"
    assert "ANTHROPIC_API_KEY" not in base_env
    assert "PATH" in base_env
