"""Identity + capability gating (Phase 2, slice 4).

Locked decision: Google OAuth, with an anonymous trial allowed for lint/sim and
sign-in required for synth + save + MCP. This module answers two questions:

  * *who is this request?* — ``IdentityVerifier.verify(token) -> Identity``
  * *may this identity do this action?* — ``authorize(identity, action)``

The verifier is an interface so the OAuth dependency is isolated and tests use a
fake. The anonymous trial is a first-class ``Identity`` (not "no identity"), so
quotas and isolation apply to it too.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class Action(str, Enum):
    LINT = "lint"
    SIMULATE = "simulate"
    SYNTHESIZE = "synthesize"
    SAVE = "save"
    MCP = "mcp"


# Anonymous trial is limited to the cheap, safe stages.
ANONYMOUS_ALLOWED = frozenset({Action.LINT, Action.SIMULATE})


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: Optional[str] = None
    anonymous: bool = False
    provider: str = "google"

    @property
    def tier(self) -> str:
        return "anonymous" if self.anonymous else "user"


def new_anonymous(session_hint: Optional[str] = None) -> Identity:
    """Mint a stable-per-trial anonymous identity (still tenant-isolated)."""
    uid = f"anon_{session_hint or uuid.uuid4().hex[:12]}"
    return Identity(user_id=uid, email=None, anonymous=True, provider="anonymous")


class AuthError(Exception):
    """Raised when an identity may not perform an action."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def authorize(identity: Identity, action: Action) -> None:
    """Raise :class:`AuthError` if ``identity`` may not perform ``action``.

    Defense-in-depth: this is checked on every action (not just at login), so an
    anonymous token can never reach synth/save/MCP even if a handler forgets.
    """
    if identity.anonymous and action not in ANONYMOUS_ALLOWED:
        raise AuthError(
            code="signin_required",
            message=f"Action '{action.value}' requires Google sign-in (anonymous trial covers lint/sim only).",
        )


class IdentityVerifier(Protocol):
    def verify(self, token: str) -> Identity: ...


class GoogleOAuthVerifier:
    """Verify a Google OAuth ID token (lazy google-auth import).

    Production passes the OAuth client id; this validates signature, audience,
    and issuer, then maps the verified claims to an :class:`Identity`.
    """

    def __init__(self, client_id: str, _verify_fn=None):
        self._client_id = client_id
        self._verify_fn = _verify_fn  # injectable for tests

    def verify(self, token: str) -> Identity:
        claims = self._verify_token(token)
        if not claims.get("sub"):
            raise AuthError("invalid_token", "Token missing subject claim.")
        if claims.get("aud") != self._client_id:
            raise AuthError("invalid_audience", "Token audience does not match this app.")
        return Identity(
            user_id=f"google_{claims['sub']}",
            email=claims.get("email"),
            anonymous=False,
            provider="google",
        )

    def _verify_token(self, token: str) -> dict:
        if self._verify_fn is not None:
            return self._verify_fn(token)
        from google.oauth2 import id_token  # lazy
        from google.auth.transport import requests as g_requests

        return id_token.verify_oauth2_token(token, g_requests.Request(), self._client_id)
