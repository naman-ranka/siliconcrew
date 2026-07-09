"""F10: capability-gating of mutating MCP tools (drift guard).

`update_manifest` mutates the manifest — the single source of truth for design
files/roles/tops (CLAUDE.md invariant 1). Over MCP, mutating/persisting tools
must require a signed-in identity, so a hosted ANONYMOUS trial identity cannot
persist changes (the anonymous trial covers lint/sim only —
``identity.ANONYMOUS_ALLOWED``). The MCP server enforces this at
``call_tool`` via ``authorize(..., Action.SAVE)`` for any tool in
``RTLDesignMCPServer._PROTECTED_TOOLS`` (which aliases the shared
``src/api/tool_catalog.PROTECTED_TOOLS``).

``update_manifest`` has been in that shared set since the schema-driven-platform
unification (c072d5c), so the F10 exposure is already closed. These tests LOCK
it so a future refactor can't silently reopen it, and encode the broader
invariant (F2-style) so any newly added mutating MCP tool must consciously be
either PROTECTED or explicitly listed as intentionally open.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pytest.importorskip("langgraph")
pytest.importorskip("mcp")

# Mutating MCP tools that are INTENTIONALLY NOT sign-in-gated. The anonymous
# trial explicitly covers lint/sim (identity.ANONYMOUS_ALLOWED = {LINT,
# SIMULATE}), so simulation writes its results without a login. Anything else
# that mutates persistent design state MUST be PROTECTED. Adding to this set is
# a deliberate, reviewed decision — not a default.
_INTENTIONALLY_UNPROTECTED_MUTATORS = {"simulation_tool", "run_isolated_simulation"}


def test_update_manifest_is_capability_gated():
    """F10 regression: update_manifest must be in the MCP protection set so an
    anonymous identity is refused (authorize Action.SAVE) before it can mutate
    the manifest."""
    import mcp_server

    gate = mcp_server.RTLDesignMCPServer._PROTECTED_TOOLS
    assert "update_manifest" in gate, (
        "update_manifest mutates the manifest (single source of truth) and must "
        "require sign-in over MCP; without it a hosted anonymous identity could "
        "persist manifest changes"
    )


def test_mutating_mcp_tools_are_protected_or_explicitly_open():
    """Every mutating tool exposed over MCP must be either PROTECTED (sign-in
    required) or in the explicit intentionally-open allowlist. A new mutating
    tool added without a protection decision trips this test — the F2 pattern
    applied to capability gating, so update_manifest can't regress in isolation."""
    import mcp_server
    from src.tools.wrappers import mcp_tools
    from src.api.tool_catalog import MUTATING_TOOLS

    gate = mcp_server.RTLDesignMCPServer._PROTECTED_TOOLS
    advertised = {t.name for t in mcp_tools}
    exposed_mutators = MUTATING_TOOLS & advertised

    ungated = exposed_mutators - set(gate) - _INTENTIONALLY_UNPROTECTED_MUTATORS
    assert not ungated, (
        "mutating MCP tools that are neither PROTECTED nor explicitly listed as "
        f"intentionally open (an anonymous identity could persist state): {sorted(ungated)}"
    )
