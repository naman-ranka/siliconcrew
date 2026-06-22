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

# The trusted single user for self-host. Non-anonymous → full capabilities.
LOCAL_IDENTITY = Identity(user_id="local", email=None, anonymous=False, provider="local")


def parse_bearer(authorization: Optional[str]) -> Optional[str]:
    """Extract the token from an ``Authorization: Bearer <token>`` header."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def build_verifier(settings=None) -> Optional[IdentityVerifier]:
    """Construct the OAuth verifier from settings, or None if unconfigured."""
    if settings is None:
        from src.platform_engines.settings import get_settings

        settings = get_settings()
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
        if verifier is None:
            raise AuthError("auth_unconfigured", "OAuth is not configured on this server.")
        return verifier.verify(token)

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
