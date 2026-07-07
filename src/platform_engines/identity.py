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
    # Local-only Python analysis. Deliberately NOT in ANONYMOUS_ALLOWED, but the
    # load-bearing "hosted OFF" switch is get_settings().hosted checked INSIDE the
    # tool (authorize() only distinguishes anonymous — a signed-in hosted user
    # would pass any Action). See run_python_analysis wrapper.
    PYTHON = "python"


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


# --- JWKS file cache (4C, hosted-latency plan) ------------------------------
#
# Every Codex turn spawns a fresh MCP subprocess whose first act is verifying
# the caller's bearer token; with PyJWKClient's in-memory cache that meant a
# cold HTTPS fetch of the WorkOS JWKS per spawn. Public signing keys are not
# secrets and rotate rarely, so a short-TTL file cache on instance-local disk
# (shared by every process on the instance) is the standard fix. A kid miss
# forces one refresh, so rotation still works within a single request. Purely
# a cache — never durable state (twelve-factor safe).

_JWKS_CACHE_TTL_SEC = 600


def _jwks_cache_path(jwks_url: str) -> str:
    import hashlib
    import os
    import tempfile

    digest = hashlib.sha256(jwks_url.encode("utf-8")).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"siliconcrew-jwks-{digest}.json")


def _fetch_jwks(jwks_url: str) -> dict:
    import json
    from urllib.request import urlopen

    with urlopen(jwks_url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_jwks_cached(jwks_url: str, force_refresh: bool = False) -> dict:
    """The JWKS dict for ``jwks_url`` — from the file cache when fresh."""
    import json
    import os
    import time

    path = _jwks_cache_path(jwks_url)
    if not force_refresh:
        try:
            if time.time() - os.stat(path).st_mtime < _JWKS_CACHE_TTL_SEC:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, ValueError):
            pass  # absent/stale/corrupt cache → fetch
    data = _fetch_jwks(jwks_url)
    try:
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)  # atomic vs concurrent spawns
    except OSError:
        pass  # cache write is best-effort; a miss only costs a re-fetch
    return data


class WorkOSVerifier:
    """Verify a WorkOS-issued access token (hosted remote-MCP + web auth).

    WorkOS runs the login/consent screens and issues the token; we are only the
    token-checker. This validates the RS256 signature against WorkOS's published
    JWKS, checks issuer/expiry, and (when configured) audience — standard
    ``PyJWT``, no hand-rolled crypto. The verified subject becomes
    ``workos_<sub>`` — the same scheme web and MCP share so one user_id spans both.

    Audience is OPTIONAL by design, because the two token profiles differ:

      * **MCP** (resource server): WorkOS issues an audience-bound token whose
        ``aud`` is our registered resource indicator (the ``/mcp`` URL). Set
        ``audience`` so we require + match it (the resource-binding the MCP spec
        wants; an unbound token is rejected).
      * **Web** (AuthKit SPA): the access token carries *no* ``aud`` claim. Leave
        ``audience`` empty so we validate issuer + signature + expiry only.
    """

    def __init__(self, issuer: str, audience: str, jwks_url: str, _verify_fn=None):
        self._issuer = issuer or None
        self._audience = audience or None
        self._jwks_url = jwks_url
        self._verify_fn = _verify_fn  # injectable for tests (no network / JWKS)

    def verify(self, token: str) -> Identity:
        claims = self._verify_token(token)
        sub = claims.get("sub")
        if not sub:
            raise AuthError("invalid_token", "Token missing subject claim.")
        return Identity(
            user_id=f"workos_{sub}",
            email=claims.get("email"),
            anonymous=False,
            provider="workos",
        )

    def _signing_key_for(self, token: str):
        """Resolve the token's RS256 signing key via the file-cached JWKS.

        Verification itself is unchanged (real signature check, fail-closed);
        only the key *transport* is cached. A kid absent from the cached set
        forces exactly one refresh so key rotation is honored immediately.
        """
        import jwt
        from jwt import PyJWKSet
        from jwt.exceptions import PyJWKClientError

        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise PyJWKClientError(f"Unable to read token header: {exc}") from exc
        for force in (False, True):
            try:
                key_set = PyJWKSet.from_dict(_load_jwks_cached(self._jwks_url, force_refresh=force))
            except Exception as exc:  # network failure or malformed/stale JWKS
                if not force:
                    continue  # one forced refresh before giving up
                if isinstance(exc, jwt.PyJWTError):
                    raise
                raise PyJWKClientError(f"JWKS fetch failed: {exc}") from exc
            signing_keys = [k for k in key_set.keys if k.public_key_use in ("sig", None) and k.key_id]
            if kid is None and len(signing_keys) == 1:
                return signing_keys[0]
            for k in signing_keys:
                if k.key_id == kid:
                    return k
        raise PyJWKClientError(f'Unable to find a signing key that matches: "{kid}"')

    def _verify_token(self, token: str) -> dict:
        if self._verify_fn is not None:
            return self._verify_fn(token)
        import jwt  # lazy (PyJWT) — only imported in hosted mode

        try:
            signing_key = self._signing_key_for(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "verify_iss": self._issuer is not None,
                    # AuthKit web tokens carry no `aud`; only enforce it when an
                    # audience (the MCP resource indicator) is configured.
                    "verify_aud": self._audience is not None,
                },
            )
        except jwt.PyJWTError as exc:  # signature/issuer/audience/expiry failures
            print(f"[JWT ERROR] Token validation failed: {exc}")
            raise AuthError("invalid_token", f"Token validation failed: {exc}") from exc
