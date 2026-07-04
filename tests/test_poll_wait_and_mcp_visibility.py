import pytest
import asyncio
import os
import shutil
import tempfile

from src.tools import wrappers


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))


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


def test_tool_registry_matches_run_id_contract():
    """Wave 9 tool surface, checked at the source registry (wrappers.mcp_tools
    is exactly what mcp_server advertises): get_synthesis_status replaces
    get_synthesis_job + get_stage_status; the start+wait combo is gone; the
    bounded wait stays; sleep_tool is architect-only."""
    mcp_names = {t.name for t in wrappers.mcp_tools}

    assert "get_synthesis_status" in mcp_names
    assert "wait_for_synthesis" in mcp_names
    assert "start_synthesis" in mcp_names
    assert "retry_pd" in mcp_names

    assert "get_synthesis_job" not in mcp_names
    assert "get_stage_status" not in mcp_names
    assert "run_synthesis_and_wait" not in mcp_names
    assert "sleep_tool" not in mcp_names

    architect_names = {t.name for t in wrappers.architect_tools}
    assert architect_names == mcp_names | {"sleep_tool"}


def test_mcp_does_not_expose_sleep_tool():
    pytest.importorskip("langgraph")
    pytest.importorskip("mcp")  # the MCP SDK is optional in dev environments

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
        assert "get_route_drc_summary" in names
        assert "get_cts_summary" in names
        assert "get_congestion_summary" in names
        assert "compare_pd_runs" in names
        assert "retry_pd" in names
        # Wave 9: one status tool keyed by run_id.
        assert "get_synthesis_status" in names
        assert "get_stage_status" not in names
        assert "get_synthesis_job" not in names
        assert "run_synthesis_and_wait" not in names
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
