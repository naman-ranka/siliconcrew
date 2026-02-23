import pytest
import asyncio

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

    from mcp_server import RTLDesignMCPServer

    server = RTLDesignMCPServer()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}

    assert "sleep_tool" not in names
