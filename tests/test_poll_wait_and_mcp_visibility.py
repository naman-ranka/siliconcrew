import pytest
import asyncio
import os
import shutil
import tempfile

from src.tools import wrappers


def test_sleep_tool_clamps_seconds(monkeypatch):
    called = {"seconds": None}

    def _fake_sleep(seconds):
        called["seconds"] = seconds

    monkeypatch.setattr(wrappers.time, "sleep", _fake_sleep)

    msg = wrappers.sleep_tool.invoke({"seconds": 0})
    assert called["seconds"] == 1
    assert "1 second" in msg

    msg = wrappers.sleep_tool.invoke({"seconds": 99})
    assert called["seconds"] == 30
    assert "30 second" in msg


def test_mcp_does_not_expose_sleep_tool():
    pytest.importorskip("langgraph")

    scratch_root = os.path.join(os.path.dirname(__file__), "_tmp")
    os.makedirs(scratch_root, exist_ok=True)
    fake_home = tempfile.mkdtemp(prefix="mcp_home_", dir=scratch_root)

    old_home = os.environ.get("HOME")
    old_userprofile = os.environ.get("USERPROFILE")
    os.environ["HOME"] = fake_home
    os.environ["USERPROFILE"] = fake_home
    try:
        from mcp_server import RTLDesignMCPServer

        server = RTLDesignMCPServer()
        tools = asyncio.run(server.list_tools())
        names = {t.name for t in tools}

        assert "sleep_tool" not in names
        assert "wait_for_synthesis" in names
        assert "read_stage_report" in names
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
        if old_userprofile is None:
            os.environ.pop("USERPROFILE", None)
        else:
            os.environ["USERPROFILE"] = old_userprofile
        shutil.rmtree(fake_home, ignore_errors=True)
