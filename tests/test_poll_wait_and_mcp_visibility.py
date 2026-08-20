import asyncio
import os
import shutil
import tempfile

import pytest

from src.tools import wrappers


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))


def test_tool_registry_matches_run_id_contract():
    """Wave 9 tool surface, checked at the source registry (wrappers.mcp_tools
    is exactly what mcp_server advertises): get_synthesis_status replaces
    get_synthesis_job + get_stage_status; the start+wait combo is gone; the
    bounded wait stays."""
    mcp_names = {t.name for t in wrappers.mcp_tools}

    assert "get_synthesis_status" in mcp_names
    assert "wait_for_synthesis" in mcp_names
    assert "start_synthesis" in mcp_names
    assert "retry_pd" in mcp_names

    assert "get_synthesis_job" not in mcp_names
    assert "get_stage_status" not in mcp_names
    assert "run_synthesis_and_wait" not in mcp_names

    architect_names = {t.name for t in wrappers.architect_tools}
    # The two surfaces differ by exactly one thing, derived from policy: MCP
    # also carries the session tools (a foreign client has to bootstrap its own
    # session; the in-process architect is already in one).
    session_tools = {t.name for t in wrappers.mcp_tools
                     if not wrappers.tool_policy(t).requires_session}
    assert session_tools, "the MCP surface must carry the session bootstrap"
    assert architect_names == mcp_names - session_tools


def test_mcp_advertises_the_run_id_keyed_readers():
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
