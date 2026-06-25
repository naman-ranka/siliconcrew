"""Remote-MCP auth core + transport middleware (Phase 2 — WorkOS).

Framework-light: exercises ``src.platform_engines.mcp_auth`` and the hosted-only
Starlette middleware directly (no LangChain / no mcp_server import), so it runs in
every CI lane. The mcp_server-level wiring (local stays authless, per-request
identity reaches ``call_tool``, two-user isolation) lives in
``test_mcp_remote_auth.py`` behind a langgraph import-skip.

Everything here mirrors the deployed wiring: CORS outermost, the WorkOS bearer
middleware inside it, the RFC 9728 metadata route public. The static staging test
bearer is used as the signed-in seam — no live WorkOS needed.
"""
from dataclasses import dataclass, field

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.platform_engines import mcp_auth as M
from src.platform_engines.identity import AuthError, Identity, WorkOSVerifier


# --- fakes ------------------------------------------------------------------


@dataclass
class FakeSettings:
    hosted: bool = True
    test_bearer_token: str = ""
    workos_issuer: str = "https://api.workos.com/sso/issuer/client_x"
    workos_jwks_url: str = "https://api.workos.com/sso/jwks/client_x"
    workos_audience: str = "https://mcp.siliconcrew.app/mcp"
    workos_client_id: str = "client_x"
    mcp_resource_url: str = "https://mcp.siliconcrew.app/mcp"

    @property
    def workos_configured(self) -> bool:
        return bool(self.workos_issuer and self.workos_jwks_url and self.workos_audience)


def _claims_for(token: str) -> dict:
    """Stand-in for WorkOS JWKS verification: token == sub (e.g. 'alice')."""
    if not token or token == "invalid":
        raise AuthError("invalid_token", "bad token")
    return {"sub": token, "email": f"{token}@example.com"}


def _verifier() -> WorkOSVerifier:
    return WorkOSVerifier(
        issuer="iss", audience="aud", jwks_url="jwks", _verify_fn=_claims_for
    )


# --- WorkOSVerifier: claims -> Identity -------------------------------------


def test_workos_verifier_maps_subject_to_workos_user_id():
    ident = _verifier().verify("alice")
    assert ident.user_id == "workos_alice"
    assert ident.email == "alice@example.com"
    assert ident.provider == "workos" and not ident.anonymous


def test_workos_verifier_rejects_missing_subject():
    v = WorkOSVerifier("i", "a", "j", _verify_fn=lambda t: {"email": "x@y.z"})
    with pytest.raises(AuthError) as ei:
        v.verify("tok")
    assert ei.value.code == "invalid_token"


# --- resolve_bearer_identity: strict, no anonymous-degrade ------------------


def test_resolve_valid_workos_token():
    ident = M.resolve_bearer_identity("bob", settings=FakeSettings(), verifier=_verifier())
    assert ident.user_id == "workos_bob"


def test_resolve_static_test_bearer_is_test_identity():
    s = FakeSettings(test_bearer_token="s3cret")
    ident = M.resolve_bearer_identity("s3cret", settings=s, verifier=_verifier())
    assert ident.user_id == "test-bot" and not ident.anonymous


def test_resolve_missing_token_raises_no_anonymous():
    with pytest.raises(AuthError) as ei:
        M.resolve_bearer_identity(None, settings=FakeSettings(), verifier=_verifier())
    assert ei.value.code == "missing_token"


def test_resolve_invalid_token_raises():
    with pytest.raises(AuthError):
        M.resolve_bearer_identity("invalid", settings=FakeSettings(), verifier=_verifier())


def test_resolve_unconfigured_server_raises():
    # No verifier and no test bearer: fail closed, never anonymous.
    s = FakeSettings(workos_issuer="", workos_jwks_url="", workos_audience="")
    with pytest.raises(AuthError) as ei:
        M.resolve_bearer_identity("tok", settings=s, verifier=None)
    assert ei.value.code == "auth_unconfigured"


# --- RFC 9728 metadata ------------------------------------------------------


def test_protected_resource_metadata_names_workos_issuer():
    doc = M.protected_resource_metadata(settings=FakeSettings())
    assert doc["authorization_servers"] == ["https://api.workos.com/sso/issuer/client_x"]
    assert doc["resource"] == "https://mcp.siliconcrew.app/mcp"
    assert doc["resource_name"] == "SiliconCrew"
    assert "mcp" in doc["scopes_supported"]


# --- middleware integration (mirrors deployed transport wiring) -------------


def _app(settings: FakeSettings):
    """Starlette app shaped like the hosted MCP transport: CORS → auth → routes.

    The ``/echo`` route stands in for the MCP handler, reading the per-request
    identity off ``request.state`` exactly as ``call_tool`` does via
    ``request_context.request.state``.
    """

    async def echo(request):
        ident = getattr(request.state, M.MCP_IDENTITY_STATE_KEY, None)
        return PlainTextResponse(ident.user_id if ident else "NONE")

    async def metadata(request):
        return JSONResponse(M.protected_resource_metadata(settings=settings))

    return Starlette(
        routes=[
            Route("/echo", echo),
            Route(M.PROTECTED_RESOURCE_PATH, metadata),
        ],
        middleware=[
            Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
            Middleware(M.HostedMCPAuthMiddleware, settings=settings, verifier=_verifier()),
        ],
    )


def test_valid_token_passes_and_stashes_identity():
    client = TestClient(_app(FakeSettings()))
    r = client.get("/echo", headers={"Authorization": "Bearer alice"})
    assert r.status_code == 200 and r.text == "workos_alice"


def test_two_users_resolve_to_distinct_identities():
    client = TestClient(_app(FakeSettings()))
    a = client.get("/echo", headers={"Authorization": "Bearer alice"})
    b = client.get("/echo", headers={"Authorization": "Bearer bob"})
    assert a.text == "workos_alice" and b.text == "workos_bob"
    assert a.text != b.text  # strict per-request isolation


def test_missing_token_is_401_with_www_authenticate_pointer():
    client = TestClient(_app(FakeSettings()))
    r = client.get("/echo")
    assert r.status_code == 401
    www = r.headers["www-authenticate"]
    assert www.startswith("Bearer")
    assert "resource_metadata=" in www
    assert M.PROTECTED_RESOURCE_PATH in www


def test_invalid_token_is_401():
    client = TestClient(_app(FakeSettings()))
    r = client.get("/echo", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401


def test_metadata_route_is_public_and_names_issuer():
    client = TestClient(_app(FakeSettings()))
    r = client.get(M.PROTECTED_RESOURCE_PATH)  # no auth header
    assert r.status_code == 200
    assert r.json()["authorization_servers"] == ["https://api.workos.com/sso/issuer/client_x"]


def test_options_preflight_not_challenged():
    client = TestClient(_app(FakeSettings()))
    r = client.options(
        "/echo",
        headers={
            "Origin": "https://claude.ai",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code < 400  # CORS preflight answered, not 401


def test_static_test_bearer_authenticates_over_transport():
    s = FakeSettings(test_bearer_token="staging-secret")
    client = TestClient(_app(s))
    r = client.get("/echo", headers={"Authorization": "Bearer staging-secret"})
    assert r.status_code == 200 and r.text == "test-bot"


# --- the load-bearing invariant: middleware -> transport handoff ------------


def test_scope_state_is_shared_between_request_objects():
    """The middleware stashes identity on ``scope['state']``; the MCP transport
    builds a *fresh* ``Request`` from the same scope. This asserts both Request
    objects see the same state — the exact mechanism that carries per-request
    identity into ``call_tool`` (request_context.request.state)."""
    from starlette.requests import Request

    scope = {"type": "http", "headers": [], "method": "GET", "path": "/mcp"}

    async def _noop():
        return {"type": "http.request"}

    middleware_request = Request(scope, _noop)
    ident = Identity(user_id="workos_zoe", provider="workos")
    setattr(middleware_request.state, M.MCP_IDENTITY_STATE_KEY, ident)

    # Transport reconstructs its own Request from the same scope.
    transport_request = Request(scope, _noop)
    seen = getattr(transport_request.state, M.MCP_IDENTITY_STATE_KEY, None)
    assert seen is ident and seen.user_id == "workos_zoe"
