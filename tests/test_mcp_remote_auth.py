"""mcp_server-level remote-auth wiring (Phase 2 — WorkOS).

Behind ``importorskip('langgraph')`` because it imports the LangChain-heavy
``mcp_server``; the framework-light core is covered in ``test_mcp_auth.py``.

Proves the two contracts the brief is strict about:
  * **Local stays authless and unchanged** — ``hosted`` false → no middleware, no
    metadata route, ``LOCAL_IDENTITY``, unscoped store (the REQUIRED guard).
  * **Per-request identity** — in hosted mode ``_current_identity`` reflects the
    identity stashed on the in-flight request (the same mechanism the transport
    middleware uses), so two users are strictly isolated over MCP.
"""
from types import SimpleNamespace

import pytest

pytest.importorskip("langgraph")

from mcp.server.lowlevel.server import request_ctx  # noqa: E402

from mcp_server import RTLDesignMCPServer  # noqa: E402
from src.platform_engines.auth import LOCAL_IDENTITY  # noqa: E402
from src.platform_engines.identity import Identity  # noqa: E402
from src.platform_engines.mcp_auth import (  # noqa: E402
    MCP_IDENTITY_STATE_KEY,
    PROTECTED_RESOURCE_PATH,
)
from src.platform_engines.settings import reset_settings_cache  # noqa: E402


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A locally-constructed MCP server (no hosted wiring side effects)."""
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("SILICONCREW_HOSTED", raising=False)
    reset_settings_cache()
    try:
        yield RTLDesignMCPServer()
    finally:
        reset_settings_cache()


def _bind_request(identity):
    """Simulate an in-flight MCP request carrying ``identity`` on its scope state."""
    state = SimpleNamespace()
    if identity is not None:
        setattr(state, MCP_IDENTITY_STATE_KEY, identity)
    request = SimpleNamespace(state=state)
    return request_ctx.set(SimpleNamespace(request=request))


# --- local stays authless and unchanged (the hard rule) ---------------------


def test_local_mode_is_authless_and_unchanged(server):
    assert server._hosted is False
    # Trusted local user, unscoped store — byte-for-byte today's behavior.
    assert server._current_identity() is LOCAL_IDENTITY
    assert server._scoped_user_id() is None
    assert server._resolve_identity() is LOCAL_IDENTITY
    # No auth middleware, no metadata route mounted in local mode.
    assert server._hosted_auth_middleware() == []
    assert server._well_known_routes() == []
    assert "No authentication required" in server._auth_banner()


# --- hosted: per-request identity + isolation -------------------------------


def test_hosted_uses_per_request_identity(server):
    server._hosted = True
    alice = Identity(user_id="workos_alice", email="a@x.io", provider="workos")
    token = _bind_request(alice)
    try:
        assert server._current_identity().user_id == "workos_alice"
        assert server._scoped_user_id() == "workos_alice"
    finally:
        request_ctx.reset(token)


def test_hosted_two_users_are_isolated(server):
    server._hosted = True
    for uid in ("workos_alice", "workos_bob"):
        token = _bind_request(Identity(user_id=uid, provider="workos"))
        try:
            assert server._scoped_user_id() == uid
        finally:
            request_ctx.reset(token)


def test_hosted_without_request_falls_back_to_process_identity(server):
    server._hosted = True
    # No request context bound → fall back to the process identity (fail-safe;
    # real requests always carry one because the middleware enforces it).
    assert server._current_identity() is server.identity


def test_hosted_mounts_auth_middleware_and_metadata_route(server, monkeypatch):
    server._hosted = True
    mw = server._hosted_auth_middleware()
    assert len(mw) == 1
    routes = server._well_known_routes()
    assert len(routes) == 1 and routes[0].path == PROTECTED_RESOURCE_PATH
    assert "WorkOS" in server._auth_banner()
