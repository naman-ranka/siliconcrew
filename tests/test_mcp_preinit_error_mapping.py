"""F9c: the "-32602 Invalid request parameters" lie after a backend restart.

Symptom: during a hosted deploy / Cloud Run revision swap, MCP clients received
JSON-RPC ``-32602 "Invalid request parameters"`` — which reads as a bad-argument
bug and sends external developers hunting a nonexistent one.

Root cause (all in the vendored ``mcp`` SDK, reproduced below):
  * The Streamable HTTP transport is created session-less (``mcp_session_id=None``)
    but the server was run with the DEFAULT ``stateless=False``. That leaves the
    single long-lived ``ServerSession`` in ``NotInitialized`` until an
    ``initialize`` handshake.
  * After a restart, the claude.ai connector reuses its old session and sends a
    ``tools/call`` WITHOUT re-handshaking. ``ServerSession._received_request``
    then raises ``RuntimeError("Received request before initialization was
    complete")`` (mcp/server/session.py).
  * The base receive loop (mcp/shared/session.py) catches that RuntimeError with
    the SAME ``except Exception`` block it uses for genuine request-schema
    failures and blanket-maps it to ``INVALID_PARAMS`` (-32602) — the lie.

The mis-map itself lives in third-party SDK code (not ours to patch). Our
server-side lever is to pair the session-less transport with a stateless session
(``stateless=True``), exactly as the SDK's own ``StreamableHTTPSessionManager``
does — then a post-restart request is treated as post-init and simply works
instead of erroring. mcp_server.run(transport="http") now does this; the hosted
mount in api.py needs the same one-liner (documented in the report — outside the
implementer's file fence).

These tests reproduce the mechanism and assert the fix direction. No live
probing; async driven with ``asyncio.run`` (no pytest-asyncio).
"""
import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pytest.importorskip("mcp")
anyio = pytest.importorskip("anyio")

from mcp.server import Server
from mcp.server.session import ServerSession
import mcp.types as types


def _make_session(stateless: bool) -> ServerSession:
    """A ServerSession over in-memory streams, mirroring how the server is run:
    a session-less transport paired with ``stateless``."""
    s2c_send, _s2c_recv = anyio.create_memory_object_stream(10)
    _c2s_send, c2s_recv = anyio.create_memory_object_stream(10)
    opts = Server("test").create_initialization_options()
    return ServerSession(c2s_recv, s2c_send, opts, stateless=stateless)


# A non-initialize request (as a post-restart reconnect would send before
# re-handshaking). ``_received_request`` only reads ``.request.root``.
_PREINIT_REQUEST = SimpleNamespace(
    request=SimpleNamespace(root=types.ListToolsRequest(method="tools/list"))
)


def test_default_session_raises_preinit_error_that_maps_to_invalid_params():
    """stateless=False (the buggy pairing): a request before the handshake raises
    the RuntimeError that the SDK receive loop blanket-maps to -32602 — the F9c
    lie. This is what a client saw after a backend restart with no re-handshake."""
    session = _make_session(stateless=False)

    with pytest.raises(RuntimeError, match="before initialization was complete"):
        asyncio.run(session._received_request(_PREINIT_REQUEST))


def test_stateless_session_tolerates_preinit_request():
    """stateless=True (the fix): the session is treated as initialized, so a
    post-restart request does NOT raise — no spurious -32602. This is the pairing
    mcp_server.run(transport='http') now uses (and that api.py should adopt)."""
    session = _make_session(stateless=True)

    # Must not raise the pre-init RuntimeError.
    result = asyncio.run(session._received_request(_PREINIT_REQUEST))
    assert result is None  # falls through without the init guard


def test_preinit_runtime_error_is_caught_as_generic_exception():
    """Pin WHY the message is a lie: the SDK receive loop's ``except Exception``
    (mcp/shared/session.py) that emits -32602 catches this RuntimeError just like
    a genuine schema-validation error — the two are indistinguishable to the
    client. Documents the mapping this fix routes around."""
    session = _make_session(stateless=False)
    try:
        asyncio.run(session._received_request(_PREINIT_REQUEST))
        raised = None
    except Exception as exc:  # noqa: BLE001 — mirrors the SDK's broad catch
        raised = exc

    assert isinstance(raised, Exception)
    assert not isinstance(raised, (ValueError, TypeError)), (
        "the pre-init failure is not an argument-validation error, yet the SDK "
        "reports it as -32602 'Invalid request parameters'"
    )
