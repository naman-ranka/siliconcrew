"""Remote-MCP authentication for the deployed app (WorkOS) — hosted only.

This is the framework-light core that turns an inbound ``Authorization: Bearer``
header on each MCP request into a SiliconCrew :class:`Identity`, plus the tiny
RFC 9728 "where to sign in" document and the Starlette middleware that enforces
auth in front of the ``/mcp`` and ``/sse`` transports.

The hard rule (see ``plans/phase2/MCP_REMOTE_AUTH_BRIEF.md``): **every line here
runs only when ``settings.hosted``**. Local / self-host never imports a verifier,
never reads WorkOS config, and never mounts the middleware — stdio MCP stays the
trusted ``LOCAL_IDENTITY`` with no auth, byte-for-byte as before.

Design note — why a custom ASGI middleware instead of the SDK auth backend:
the streamable-HTTP transport runs a *single* long-lived ``server.run()`` task,
so a contextvar set in the request's ASGI task would not propagate to the handler
task. Instead the middleware stashes the resolved identity on the request
**scope** (``scope["state"]``); the transport rebuilds its ``Request`` from that
same scope, so ``server.request_context.request.state`` carries the identity into
``call_tool`` reliably. Token *crypto* still uses a standard library (PyJWT via
:class:`~src.platform_engines.identity.WorkOSVerifier`) — nothing hand-rolled.
"""
from __future__ import annotations

import hmac
import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from src.platform_engines.auth import TEST_IDENTITY, _warn_test_bearer_once, parse_bearer
from src.platform_engines.identity import AuthError, Identity, WorkOSVerifier

logger = logging.getLogger(__name__)

# Key under which the verified per-request identity is stashed on the ASGI
# request scope (``scope["state"]``). Read back via the request in call_tool.
MCP_IDENTITY_STATE_KEY = "sc_mcp_identity"

# Standard location of the protected-resource metadata document (RFC 9728).
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"

# Default capabilities advertised in the metadata document when settings do not
# provide an MCP-specific scope list.
MCP_SCOPES_SUPPORTED = ["mcp"]


def build_workos_verifier(settings=None) -> Optional[WorkOSVerifier]:
    """Construct the WorkOS token verifier from settings, or ``None``.

    Returns ``None`` when WorkOS is not configured (so the caller can surface a
    clear "auth unconfigured" 401 rather than silently allowing anonymous use).
    """
    if settings is None:
        from src.platform_engines.settings import get_settings

        settings = get_settings()
    if not getattr(settings, "mcp_auth_configured", settings.workos_configured):
        return None
    return WorkOSVerifier(
        issuer=getattr(settings, "mcp_issuer", "") or settings.workos_issuer,
        audience=settings.workos_audience,
        jwks_url=getattr(settings, "mcp_jwks_url", "") or settings.workos_jwks_url,
    )


def resolve_bearer_identity(
    token: Optional[str],
    *,
    settings=None,
    verifier: Optional[WorkOSVerifier] = None,
) -> Identity:
    """Resolve a verified :class:`Identity` from a bearer token, or raise.

    Strict by design (the brief forbids anonymous-degrade on the hosted MCP
    path): a missing token, an unconfigured server, or an invalid token all
    raise :class:`AuthError`. There is no anonymous fallback here.

    The static staging test bearer (``SILICONCREW_TEST_BEARER_TOKEN``) is honored
    first via a constant-time compare so CI/agents can drive signed-in flows
    without a live WorkOS login — exactly as the web/API path does.
    """
    if settings is None:
        from src.platform_engines.settings import get_settings

        settings = get_settings()

    if not token:
        raise AuthError("missing_token", "Authentication required: no bearer token.")

    test_secret = getattr(settings, "test_bearer_token", "") or ""
    if test_secret and hmac.compare_digest(token, test_secret):
        _warn_test_bearer_once()
        return TEST_IDENTITY

    if verifier is None:
        verifier = build_workos_verifier(settings)
    if verifier is None:
        raise AuthError("auth_unconfigured", "WorkOS auth is not configured on this server.")

    return verifier.verify(token)


def protected_resource_metadata(settings=None, *, resource_url: Optional[str] = None) -> dict:
    """Build the RFC 9728 protected-resource metadata document (a plain dict).

    Names WorkOS (the issuer) as the authorization server the AI client should
    send the user to for a token. ``resource_url`` overrides the configured
    resource identifier (handy when deriving it from the inbound request).
    """
    if settings is None:
        from src.platform_engines.settings import get_settings

        settings = get_settings()
    resource = resource_url or settings.mcp_resource_url or settings.workos_audience
    auth_server = getattr(settings, "mcp_authorization_server", "") or settings.workos_issuer
    scopes = list(getattr(settings, "mcp_scopes_supported", ()) or MCP_SCOPES_SUPPORTED)
    doc = {
        "resource": resource,
        "authorization_servers": [auth_server] if auth_server else [],
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
        "resource_name": "SiliconCrew",
        "resource_documentation": "https://github.com/naman-ranka/siliconcrew",
    }
    jwks_uri = getattr(settings, "mcp_jwks_url", "") or ""
    if jwks_uri:
        doc["jwks_uri"] = jwks_uri
    return doc


async def complete_workos_standalone_connect(
    external_auth_id: str,
    identity: Identity,
    *,
    settings=None,
    http_post_json=None,
) -> dict:
    """Complete a WorkOS Standalone Connect MCP login.

    WorkOS remains the OAuth authorization server and token issuer. SiliconCrew
    only completes the user-authentication step after the frontend proves the
    user is signed in with the existing web bearer token. The returned
    ``redirect_uri`` sends the browser back to WorkOS; WorkOS then handles
    consent/token issuance and redirects to the AI client's callback.
    """
    if settings is None:
        from src.platform_engines.settings import get_settings

        settings = get_settings()

    external_auth_id = (external_auth_id or "").strip()
    if not external_auth_id:
        raise AuthError("invalid_request", "Missing external_auth_id.")
    if not identity or identity.anonymous:
        raise AuthError("signin_required", "A signed-in SiliconCrew user is required.")
    if not identity.email:
        raise AuthError("invalid_user", "Signed-in user is missing an email address.")

    api_key = getattr(settings, "workos_api_key", "") or ""
    if not api_key:
        raise AuthError("auth_unconfigured", "WORKOS_API_KEY is required for MCP Connect completion.")

    url = getattr(settings, "workos_connect_complete_url", "") or "https://api.workos.com/authkit/oauth2/complete"
    payload = {
        "external_auth_id": external_auth_id,
        "user": {
            "id": identity.user_id,
            "email": identity.email,
            "metadata": {
                "provider": identity.provider,
            },
        },
    }
    post_json = http_post_json or _post_json
    data = await post_json(url, payload, api_key)
    redirect_uri = data.get("redirect_uri") if isinstance(data, dict) else None
    if not redirect_uri:
        raise AuthError("workos_complete_failed", "WorkOS completion response did not include redirect_uri.")
    return {"redirect_uri": redirect_uri}


async def _post_json(url: str, payload: dict, bearer_token: str) -> dict:
    import asyncio

    def _send() -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise AuthError(
                "workos_complete_failed",
                f"WorkOS completion failed with HTTP {exc.code}: {raw[:500]}",
            ) from exc
        except urllib.error.URLError as exc:
            raise AuthError("workos_complete_failed", f"WorkOS completion request failed: {exc.reason}") from exc
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise AuthError("workos_complete_failed", "WorkOS completion returned invalid JSON.") from exc

    return await asyncio.to_thread(_send)


def _www_authenticate(resource_metadata_url: str, error: Optional[str] = None) -> str:
    """Build the ``WWW-Authenticate`` header value pointing at the metadata doc."""
    parts = ["Bearer"]
    if error:
        parts.append(f'error="{error}"')
    parts.append(f'resource_metadata="{resource_metadata_url}"')
    # First token is the scheme; remaining are comma-separated auth params.
    return parts[0] + " " + ", ".join(parts[1:]) if len(parts) > 1 else parts[0]


class HostedMCPAuthMiddleware:
    """ASGI middleware that enforces WorkOS bearer auth on hosted MCP requests.

    Mounted **only when ``settings.hosted``** in front of the ``/mcp`` and
    ``/sse`` transports. On a valid token it stashes the resolved identity on the
    request scope and forwards; otherwise it returns ``401`` with a
    ``WWW-Authenticate`` header pointing at the Slice-2 metadata document. The
    metadata route itself and CORS preflight (``OPTIONS``) are never challenged.
    """

    def __init__(self, app, *, settings=None, verifier: Optional[WorkOSVerifier] = None):
        self.app = app
        if settings is None:
            from src.platform_engines.settings import get_settings

            settings = get_settings()
        self._settings = settings
        # Resolve the verifier once; ``None`` means "configured-off" → every
        # request 401s with auth_unconfigured (fail-closed, never anonymous).
        self._verifier = verifier if verifier is not None else build_workos_verifier(settings)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")
        # Never challenge the public metadata doc or CORS preflight.
        if method == "OPTIONS" or path.startswith("/.well-known/"):
            await self.app(scope, receive, send)
            return

        token = parse_bearer(_header(scope, b"authorization"))
        try:
            identity = resolve_bearer_identity(
                token, settings=self._settings, verifier=self._verifier
            )
        except AuthError as exc:
            await self._unauthorized(scope, send, exc)
            return

        scope.setdefault("state", {})[MCP_IDENTITY_STATE_KEY] = identity
        await self.app(scope, receive, send)

    async def _unauthorized(self, scope, send, exc: AuthError) -> None:
        meta_url = _resource_metadata_url(scope, self._settings)
        body = json.dumps(
            {"error": exc.code, "error_description": exc.message}
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"www-authenticate", _www_authenticate(meta_url, exc.code).encode("latin-1")),
        ]
        await send({"type": "http.response.start", "status": 401, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def _header(scope, name: bytes) -> Optional[str]:
    for k, v in scope.get("headers", []):
        if k.lower() == name:
            return v.decode("latin-1")
    return None


def _resource_metadata_url(scope, settings) -> str:
    """Absolute URL of the metadata doc, derived from the request when possible."""
    host = _header(scope, b"host")
    if host:
        scheme = scope.get("scheme", "https")
        # Cloud Run terminates TLS upstream; honor the forwarded scheme.
        fwd = _header(scope, b"x-forwarded-proto")
        if fwd:
            scheme = fwd.split(",")[0].strip()
        return f"{scheme}://{host}{PROTECTED_RESOURCE_PATH}"
    base = (settings.mcp_resource_url or "").rstrip("/")
    return f"{base}{PROTECTED_RESOURCE_PATH}" if base else PROTECTED_RESOURCE_PATH
