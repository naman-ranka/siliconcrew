"""The MCP server states its preconditions ONCE, at connect time.

A client that has never seen SiliconCrew (Claude Code, Codex, Cursor) gets a
tool list and nothing else: every tool but the session tools is refused until a
session is active, and no tool description says so. The draft fix was to add
that sentence to all 40 descriptions — one fact hand-copied 40 times, i.e. the
drift this platform's "one registry, zero drift" rule exists to prevent.

The protocol already has the right place for it: ``InitializeResult.instructions``,
delivered once per connection. ``Server(instructions=...)`` (mcp 1.29.0) is
carried into ``create_initialization_options()``, which every transport here
(stdio / SSE / streamable HTTP / the api.py mount) already passes to
``server.run`` — so one constant covers all of them.

These tests pin the stranger's bootstrap path end to end:

* the instructions really arrive in the ``initialize`` response (real handshake
  over the SDK's in-memory transport, not a field read);
* every tool the instructions name is really advertised — so the text cannot rot
  into pointing at a tool that no longer exists;
* the tool they tell a stranger to call FIRST actually produces a session, and a
  gated tool works afterwards; and
* the gate's refusal message names that same recovery tool.

**No tool name is written down here.** The bootstrap tool is DERIVED: of the
tools the instructions mention, it is the one that, called from a fresh
no-session server, leaves a session active. Rename ``create_session_tool``
tomorrow and these tests retarget themselves; leave a stale name in the prose
and they fail.
"""
from __future__ import annotations

import asyncio
import re

import pytest

pytest.importorskip("langgraph")

from mcp.shared.memory import create_connected_server_and_client_session

from mcp_server import SERVER_INSTRUCTIONS, RTLDesignMCPServer

# Tool-name shape, matching the drift guard's: lowercase snake with >= 1 "_".
_SNAKE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")


@pytest.fixture
def make_server(tmp_path, monkeypatch):
    """Build servers under tmp_path, so the bootstrap probe below may create a
    real session without touching the repo workspace or the developer's
    ~/.siliconcrew.

    Each server gets its OWN workspace + state db: the probe calls one candidate
    tool per server, and a session left behind by an earlier candidate would make
    a later one (``set_active_session`` on the id the first probe happened to
    create) look like a session creator too."""
    counter = {"n": 0}

    def _make():
        counter["n"] += 1
        world = tmp_path / f"world{counter['n']}"
        monkeypatch.setenv("RTL_WORKSPACE", str(world / "workspace"))
        monkeypatch.setenv("RTL_DATA_DIR", str(world / "data"))
        return RTLDesignMCPServer()

    return _make


def _advertised(server) -> dict:
    """name -> Tool, straight off the live tools/list response."""
    return {t.name: t for t in asyncio.run(server.list_tools())}


def _names_in(text: str, advertised: dict) -> set:
    """Tool names the prose mentions, resolved against what is advertised."""
    return {tok for tok in _SNAKE.findall(text) if tok in advertised}


def _probe_args(tool) -> dict:
    """Minimal arguments for a tool, built from its own input schema."""
    schema = tool.inputSchema or {}
    props = schema.get("properties") or {}
    args = {}
    for field in schema.get("required") or []:
        spec = props.get(field) or {}
        args[field] = 1 if spec.get("type") in ("integer", "number") else "instructions_probe"
    return args


def _bootstrap_tool(make_server) -> str:
    """The tool the instructions send a stranger to first, derived by BEHAVIOUR:
    call each mentioned tool on a fresh, session-less server and keep the one
    that leaves a session active. Never a literal name."""
    advertised = _advertised(make_server())
    winners = []
    for name in sorted(_names_in(SERVER_INSTRUCTIONS, advertised)):
        server = make_server()
        assert server.current_session is None
        asyncio.run(server.call_tool(name, _probe_args(advertised[name])))
        if server.current_session:
            winners.append(name)
    assert len(winners) == 1, f"expected exactly one session-creating tool, got {winners}"
    return winners[0]


def test_instructions_are_served_on_initialize(make_server):
    """A real client handshake carries the instructions — the connect-time
    delivery is the whole point, so assert the wire, not the attribute."""
    server = make_server()

    async def main():
        async with create_connected_server_and_client_session(server.server) as client:
            return await client.initialize()

    result = asyncio.run(main())
    assert result.instructions == SERVER_INSTRUCTIONS
    assert result.instructions.strip()


def test_instructions_only_name_live_tools(make_server):
    """Every backticked name in the prose is a tool that is actually advertised.
    A rename that misses this text is a stranger sent to a nonexistent tool."""
    advertised = _advertised(make_server())
    quoted = set(re.findall(r"`([a-z0-9_]+)`", SERVER_INSTRUCTIONS))
    tool_shaped = {tok for tok in quoted if _SNAKE.fullmatch(tok)}
    assert tool_shaped, "instructions name no tools at all"
    dead = tool_shaped - set(advertised)
    assert not dead, f"instructions reference tools that are not advertised: {sorted(dead)}"


def test_instructions_bootstrap_a_stranger(make_server):
    """Following the instructions from cold actually works: the tool they name
    first creates a session, and a previously-gated tool then runs."""
    bootstrap = _bootstrap_tool(make_server)
    advertised = _advertised(make_server())

    server = make_server()
    gated = sorted(set(advertised) - _names_in(SERVER_INSTRUCTIONS, advertised))[0]

    # Empty arguments on purpose: past the gate the call dies in schema
    # validation, so this exercises the GATE and never runs real design work.
    before = asyncio.run(server.call_tool(gated, {}))
    assert "No active session" in before[0].text  # gated while a stranger

    asyncio.run(server.call_tool(bootstrap, _probe_args(advertised[bootstrap])))
    assert server.current_session

    after = asyncio.run(server.call_tool(gated, {}))
    assert "No active session" not in after[0].text  # gate cleared by the documented step


def test_gate_error_points_at_the_recovery_tool(make_server):
    """The refusal must be recoverable from its own text: a stranger who never
    read the instructions still learns which tool to call."""
    bootstrap = _bootstrap_tool(make_server)
    server = make_server()
    advertised = _advertised(server)
    gated = sorted(set(advertised) - _names_in(SERVER_INSTRUCTIONS, advertised))[0]

    message = asyncio.run(server.call_tool(gated, {}))[0].text

    assert bootstrap in message, f"gate error does not name the recovery tool: {message!r}"
    dead = {tok for tok in _SNAKE.findall(message) if "_" in tok} - set(advertised) - {gated}
    assert not dead, f"gate error names tools that are not advertised: {sorted(dead)}"
