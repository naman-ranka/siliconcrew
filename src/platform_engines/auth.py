"""Authentication wiring — turn a request's token into an Identity.

This is the pure, framework-free core (so it unit-tests without FastAPI). The
api.py / mcp_server.py layers call ``authenticate()`` and then thread the result
through the tenancy seam:

  * **self-host (not hosted):** every request is the single trusted local user.
    ``authenticate`` returns :data:`LOCAL_IDENTITY` and ``scoped_user_id`` is
    ``None`` — so the metadata store stays unscoped and behavior is bit-for-bit
    today's. No tokens, no OAuth.
  * **hosted:** a Bearer Google OAuth token is verified into a real Identity; no
    token yields an anonymous trial identity (lint/sim only). ``scoped_user_id``
    returns the real ``user_id`` so every query is tenant-filtered.

Capability gating (``authorize``) lives in :mod:`identity`; synth/save/MCP
require a signed-in identity, lint/sim allow the anonymous trial.
"""
from __future__ import annotations

import hmac
import logging
from typing import Optional

from src.platform_engines.identity import (
    Action,
    AuthError,
    GoogleOAuthVerifier,
    Identity,
    IdentityVerifier,
    authorize,
    new_anonymous,
)

logger = logging.getLogger(__name__)

# The trusted single user for self-host. Non-anonymous → full capabilities.
LOCAL_IDENTITY = Identity(user_id="local", email=None, anonymous=False, provider="local")

# Fixed identity used ONLY when the dev insecure-auth escape hatch is on.
DEV_IDENTITY = Identity(user_id="dev", email=None, anonymous=False, provider="dev")

# Fixed identity returned for the static service/test bearer token (staging only).
# Its own tenant ("test-bot") so automated-agent data never mingles with real
# users'. Non-anonymous → full capabilities (synth/save), via the real Bearer path.
TEST_IDENTITY = Identity(
    user_id="test-bot", email="test-bot@siliconcrew.local", anonymous=False, provider="test"
)

_warned_insecure_auth = False
_warned_test_bearer = False


def _warn_insecure_auth_once() -> None:
    """Loudly warn (once) that the insecure dev-auth escape hatch is active."""
    global _warned_insecure_auth
    if not _warned_insecure_auth:
        logger.warning(
            "SILICONCREW_DEV_INSECURE_AUTH is ON: every unauthenticated request "
            "is granted the fixed 'dev' identity with full capabilities. "
            "NEVER enable this in a multi-tenant or production deployment."
        )
        _warned_insecure_auth = True


def _warn_test_bearer_once() -> None:
    """Loudly warn (once) that the static test-bearer token is accepted."""
    global _warned_test_bearer
    if not _warned_test_bearer:
        logger.warning(
            "SILICONCREW_TEST_BEARER_TOKEN is set: requests bearing that secret "
            "authenticate as the fixed 'test-bot' identity with full capabilities. "
            "Staging only — NEVER set this in production."
        )
        _warned_test_bearer = True


def parse_bearer(authorization: Optional[str]) -> Optional[str]:
    """Extract the token from an ``Authorization: Bearer <token>`` header."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def build_verifier(settings=None) -> Optional[IdentityVerifier]:
    """Construct the token verifier from settings, or None if unconfigured.

    Prefers **WorkOS** when configured (Slice 3 identity unification): the
    deployed web sign-in then validates the same WorkOS token the MCP path does,
    so web and MCP resolve to one ``workos_<sub>`` user_id and a user's sessions
    show up in both places. Falls back to Google OAuth (today's direct sign-in)
    when WorkOS is not configured — so nothing changes until WORKOS_* is set.
    """
    if settings is None:
        from src.platform_engines.settings import get_settings

        settings = get_settings()
    if getattr(settings, "workos_configured", False):
        from src.platform_engines.identity import WorkOSVerifier

        return WorkOSVerifier(
            issuer=settings.workos_issuer,
            audience=settings.workos_audience,
            jwks_url=settings.workos_jwks_url,
        )
    if settings.google_oauth_client_id:
        return GoogleOAuthVerifier(settings.google_oauth_client_id)
    return None


def authenticate(
    token: Optional[str],
    *,
    settings=None,
    verifier: Optional[IdentityVerifier] = None,
    session_hint: Optional[str] = None,
) -> Identity:
    """Resolve the caller's :class:`Identity` from a bearer token.

    Raises :class:`AuthError` only when a token is supplied but invalid (or OAuth
    is unconfigured in hosted mode). A *missing* token in hosted mode is an
    anonymous trial, not an error.
    """
    if settings is None:
        from src.platform_engines.settings import get_settings

        settings = get_settings()

    if not settings.hosted:
        return LOCAL_IDENTITY

    if verifier is None:
        verifier = build_verifier(settings)

    if token:
        # Static service/test bearer (staging only): a constant-time match against
        # the configured secret authenticates as the fixed 'test-bot' identity.
        # The secret being set is the on-switch; empty (default) disables it.
        test_secret = getattr(settings, "test_bearer_token", "") or ""
        if test_secret and hmac.compare_digest(token, test_secret):
            _warn_test_bearer_once()
            return TEST_IDENTITY
        if verifier is None:
            raise AuthError("auth_unconfigured", "OAuth is not configured on this server.")
        return verifier.verify(token)

    # No token. The ONLY way to get a non-anonymous identity without a token is
    # the explicit, opt-in dev escape hatch — never granted by mere
    # misconfiguration. This keeps auth fail-closed: an unconfigured OAuth setup
    # yields an anonymous trial (lint/sim only), not silent full access.
    if getattr(settings, "dev_insecure_auth", False):
        _warn_insecure_auth_once()
        return DEV_IDENTITY

    return new_anonymous(session_hint)


def scoped_user_id(identity: Identity, settings=None) -> Optional[str]:
    """The user_id to filter metadata queries by — ``None`` in self-host.

    Returning ``None`` for self-host keeps the metadata store unscoped (today's
    single-tenant behavior); hosted returns the real tenant id.
    """
    if settings is None:
        from src.platform_engines.settings import get_settings

        settings = get_settings()
    if not settings.hosted:
        return None
    return identity.user_id


def require_action(identity: Identity, action: Action) -> None:
    """Raise :class:`AuthError` if ``identity`` may not perform ``action``."""
    authorize(identity, action)


def ensure_signed_in(identity: Identity) -> None:
    """Raise :class:`AuthError` if the identity is an anonymous trial."""
    if identity.anonymous:
        raise AuthError(
            "signin_required",
            "This action requires Google sign-in (anonymous trial covers lint/sim only).",
        )
