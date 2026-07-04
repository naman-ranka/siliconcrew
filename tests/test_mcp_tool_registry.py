"""Regression guard: every advertised MCP tool must be dispatchable.

`list_tools()` advertises tools from ``mcp_tools`` while ``call_tool()`` used to
dispatch through a hand-maintained map. The two drifted — run_isolated_simulation,
get_manifest and update_manifest were listed but raised "Unknown tool" when
called. Dispatch is now derived from ``mcp_tools`` (single source of truth); this
test fails loudly if that invariant is ever broken again.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pytest.importorskip("langgraph")
pytest.importorskip("mcp")


def test_every_advertised_tool_is_dispatchable():
    import mcp_server
    from src.tools.wrappers import mcp_tools

    advertised = {t.name for t in mcp_tools}
    dispatchable = set(mcp_server.TOOL_REGISTRY)

    missing = advertised - dispatchable
    assert not missing, f"advertised but not dispatchable (would raise 'Unknown tool'): {sorted(missing)}"


def test_registry_has_no_phantom_entries():
    """Every dispatchable name maps to a real tool object that can be invoked."""
    import mcp_server

    for name, tool in mcp_server.TOOL_REGISTRY.items():
        assert hasattr(tool, "invoke"), f"{name} is not an invocable tool"
        assert tool.name == name, f"registry key {name!r} != tool.name {tool.name!r}"
