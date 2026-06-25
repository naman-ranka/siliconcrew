"""Auth wiring: token → Identity → tenant scoping + capability gating (I2)."""
from dataclasses import dataclass

import pytest

from src.platform_engines import auth as A
from src.platform_engines.identity import Action, AuthError, Identity


@dataclass
class FakeSettings:
    hosted: bool = True
    google_oauth_client_id: str = "cid"
    dev_insecure_auth: bool = False
    test_bearer_token: str = ""


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


def test_hosted_no_oauth_no_token_is_anonymous_failclosed():
    # Unconfigured OAuth + no token must FAIL CLOSED: an anonymous trial
    # (lint/sim only), never silent non-anonymous full access. This is the
    # regression guard for the old fail-open "mock_" identity.
    s = FakeSettings(hosted=True, google_oauth_client_id="", dev_insecure_auth=False)
    ident = A.authenticate(None, settings=s, verifier=None, session_hint="sess1")
    assert ident.anonymous
    assert ident.user_id.startswith("anon_")
    with pytest.raises(AuthError):
        A.ensure_signed_in(ident)


def test_static_test_bearer_grants_fixed_test_identity():
    # The configured secret authenticates as the FIXED 'test-bot' tenant with
    # full capabilities (synth/save), via the real Bearer path — so automated
    # agents/CI can drive signed-in flows without a real Google login.
    s = FakeSettings(hosted=True, test_bearer_token="s3cret-staging-token")
    ident = A.authenticate("s3cret-staging-token", settings=s, verifier=FakeVerifier())
    assert ident is A.TEST_IDENTITY
    assert ident.user_id == "test-bot" and not ident.anonymous
    assert A.scoped_user_id(ident, settings=s) == "test-bot"
    A.ensure_signed_in(ident)  # no raise
    for action in Action:
        A.require_action(ident, action)


def test_static_test_bearer_requires_exact_match():
    # A non-matching token is NOT the test identity — it falls through to the real
    # verifier (so genuine Google tokens still work alongside the test bearer).
    s = FakeSettings(hosted=True, test_bearer_token="s3cret-staging-token")
    real = A.authenticate("good", settings=s, verifier=FakeVerifier())
    assert real.user_id == "google_42"
    with pytest.raises(AuthError):
        A.authenticate("wrong-secret", settings=s, verifier=FakeVerifier())


def test_static_test_bearer_off_by_default():
    # Empty secret (default) = feature disabled: the would-be secret is just an
    # ordinary (invalid) token handed to the verifier.
    s = FakeSettings(hosted=True, test_bearer_token="")
    with pytest.raises(AuthError):
        A.authenticate("any-token", settings=s, verifier=FakeVerifier())


def test_dev_insecure_auth_flag_grants_fixed_dev_identity():
    # The ONLY way to get a non-anonymous identity without a token: the explicit
    # opt-in escape hatch. The identity is a FIXED 'dev' user — not derived from
    # the attacker-controllable session_hint — so it cannot impersonate tenants.
    s = FakeSettings(hosted=True, google_oauth_client_id="", dev_insecure_auth=True)
    ident_a = A.authenticate(None, settings=s, verifier=None, session_hint="attacker")
    ident_b = A.authenticate(None, settings=s, verifier=None, session_hint="victim")
    assert ident_a.user_id == "dev" and not ident_a.anonymous
    assert ident_a.user_id == ident_b.user_id  # independent of session_hint
    A.ensure_signed_in(ident_a)  # no raise — full capabilities

