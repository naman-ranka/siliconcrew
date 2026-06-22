"""Auth wiring: token → Identity → tenant scoping + capability gating (I2)."""
from dataclasses import dataclass

import pytest

from src.platform_engines import auth as A
from src.platform_engines.identity import Action, AuthError, Identity


@dataclass
class FakeSettings:
    hosted: bool = True
    google_oauth_client_id: str = "cid"


class FakeVerifier:
    def verify(self, token):
        if token == "good":
            return Identity(user_id="google_42", email="u@x.com", anonymous=False, provider="google")
        raise AuthError("invalid_token", "bad token")


def test_parse_bearer():
    assert A.parse_bearer("Bearer abc123") == "abc123"
    assert A.parse_bearer("bearer abc123") == "abc123"
    assert A.parse_bearer("Basic abc") is None
    assert A.parse_bearer(None) is None
    assert A.parse_bearer("Bearer ") is None


def test_self_host_is_local_full_access():
    s = FakeSettings(hosted=False)
    ident = A.authenticate(None, settings=s)
    assert ident is A.LOCAL_IDENTITY and not ident.anonymous
    # Self-host scopes to None (unscoped store = today's behavior).
    assert A.scoped_user_id(ident, settings=s) is None
    # Local user may do everything, including synth/save/MCP.
    for action in Action:
        A.require_action(ident, action)
    A.ensure_signed_in(ident)  # no raise


def test_hosted_valid_token():
    s = FakeSettings(hosted=True)
    ident = A.authenticate("good", settings=s, verifier=FakeVerifier())
    assert ident.user_id == "google_42" and not ident.anonymous
    assert A.scoped_user_id(ident, settings=s) == "google_42"


def test_hosted_invalid_token_raises():
    s = FakeSettings(hosted=True)
    with pytest.raises(AuthError):
        A.authenticate("bad", settings=s, verifier=FakeVerifier())


def test_hosted_no_token_is_anonymous_trial():
    s = FakeSettings(hosted=True)
    ident = A.authenticate(None, settings=s, verifier=FakeVerifier(), session_hint="sess1")
    assert ident.anonymous and ident.user_id.startswith("anon_")
    assert A.scoped_user_id(ident, settings=s) == ident.user_id
    # Anonymous may lint/sim...
    A.require_action(ident, Action.LINT)
    A.require_action(ident, Action.SIMULATE)
    # ...but not synth/save/MCP.
    for action in (Action.SYNTHESIZE, Action.SAVE, Action.MCP):
        with pytest.raises(AuthError) as ei:
            A.require_action(ident, action)
        assert ei.value.code == "signin_required"
    with pytest.raises(AuthError):
        A.ensure_signed_in(ident)


def test_hosted_unconfigured_oauth_rejects_token():
    s = FakeSettings(hosted=True, google_oauth_client_id="")
    with pytest.raises(AuthError) as ei:
        A.authenticate("sometoken", settings=s, verifier=None)
    assert ei.value.code == "auth_unconfigured"


def test_anonymous_tier_string():
    s = FakeSettings(hosted=True)
    anon = A.authenticate(None, settings=s)
    assert anon.tier == "anonymous"
    user = A.authenticate("good", settings=s, verifier=FakeVerifier())
    assert user.tier == "user"
