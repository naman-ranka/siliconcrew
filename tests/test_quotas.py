"""Per-user quota + identity gating tests (Phase 2, slice 4)."""
from types import SimpleNamespace

import pytest

from src.platform_engines.identity import (
    Action,
    AuthError,
    GoogleOAuthVerifier,
    authorize,
    new_anonymous,
)
from src.platform_engines.quotas import (
    DEFAULT_POLICIES,
    QuotaExceeded,
    QuotaManager,
    QuotaPolicy,
    build_quota_manager,
)


# ---- identity gating -------------------------------------------------------


def test_anonymous_can_lint_and_sim_but_not_synth():
    anon = new_anonymous("sess1")
    authorize(anon, Action.LINT)       # no raise
    authorize(anon, Action.SIMULATE)   # no raise
    for action in (Action.SYNTHESIZE, Action.SAVE, Action.MCP):
        with pytest.raises(AuthError) as ei:
            authorize(anon, action)
        assert ei.value.code == "signin_required"


def test_signed_in_user_can_do_everything():
    user = GoogleOAuthVerifier(
        client_id="cid", _verify_fn=lambda t: {"sub": "123", "aud": "cid", "email": "a@b.com"}
    ).verify("tok")
    assert not user.anonymous and user.user_id == "google_123"
    for action in Action:
        authorize(user, action)  # no raise


def test_oauth_rejects_wrong_audience():
    v = GoogleOAuthVerifier(client_id="cid", _verify_fn=lambda t: {"sub": "1", "aud": "other"})
    with pytest.raises(AuthError) as ei:
        v.verify("tok")
    assert ei.value.code == "invalid_audience"


# ---- quotas ----------------------------------------------------------------


def test_concurrency_cap_blocks_sixth_inflight_run():
    qm = QuotaManager()
    reservations = [qm.reserve_synth_run("u1", tier="user") for _ in range(5)]
    with pytest.raises(QuotaExceeded) as ei:
        qm.reserve_synth_run("u1", tier="user")
    assert ei.value.code == "concurrency_limit"
    # Releasing frees the slot.
    qm.release_synth_run(reservations[0], compute_minutes=1.0)
    qm.reserve_synth_run("u1", tier="user")  # no raise now


def test_different_users_do_not_share_concurrency():
    qm = QuotaManager()
    qm.reserve_synth_run("u1")
    qm.reserve_synth_run("u2")  # independent — no raise


def test_daily_run_limit():
    policy = {"user": QuotaPolicy(synth_runs_per_day=2, compute_minutes_per_month=1000, max_concurrent_synth=5)}
    qm = QuotaManager(policies=policy)
    for _ in range(2):
        r = qm.reserve_synth_run("u1")
        qm.release_synth_run(r, compute_minutes=0.1)
    with pytest.raises(QuotaExceeded) as ei:
        qm.reserve_synth_run("u1")
    assert ei.value.code == "daily_run_limit"


def test_monthly_compute_budget():
    policy = {"user": QuotaPolicy(synth_runs_per_day=100, compute_minutes_per_month=5, max_concurrent_synth=5)}
    qm = QuotaManager(policies=policy)
    r = qm.reserve_synth_run("u1")
    qm.release_synth_run(r, compute_minutes=5.0)  # exhaust the budget
    with pytest.raises(QuotaExceeded) as ei:
        qm.reserve_synth_run("u1")
    assert ei.value.code == "monthly_compute_limit"


def test_anonymous_tier_cannot_reserve_synth():
    qm = QuotaManager()
    with pytest.raises(QuotaExceeded) as ei:
        qm.reserve_synth_run("anon_x", tier="anonymous")
    assert ei.value.code == "synth_not_allowed"


def test_soft_cap_failure_does_not_leak_concurrency():
    policy = {"user": QuotaPolicy(synth_runs_per_day=0, compute_minutes_per_month=1000, max_concurrent_synth=1)}
    qm = QuotaManager(policies=policy)
    with pytest.raises(QuotaExceeded) as ei:
        qm.reserve_synth_run("u1")
    assert ei.value.code == "daily_run_limit"
    # Concurrency slot must have been released so the user isn't permanently stuck.
    assert qm.usage("u1")["concurrent_synth"] == 0


def test_quota_exceeded_envelope_shape():
    qm = QuotaManager()
    for _ in range(5):
        qm.reserve_synth_run("u1")
    try:
        qm.reserve_synth_run("u1")
    except QuotaExceeded as e:
        env = e.to_envelope()
        assert env["ok"] is False
        assert env["error"]["code"] == "concurrency_limit"
        assert "message" in env["error"]


def test_usage_reporting():
    qm = QuotaManager()
    r = qm.reserve_synth_run("u1")
    qm.release_synth_run(r, compute_minutes=3.5)
    u = qm.usage("u1")
    assert u["runs_today"] == 1
    assert u["compute_minutes_month"] == 3.5
    assert u["max_concurrent_synth"] == DEFAULT_POLICIES["user"].max_concurrent_synth


def test_build_quota_manager_uses_settings_policy():
    settings = SimpleNamespace(
        persistence_engine="sqlite",
        database_url="",
        synth_runs_per_day=20,
        synth_compute_minutes_per_month=600,
        synth_max_concurrent_per_user=3,
    )
    qm = build_quota_manager(settings)
    for _ in range(3):
        qm.reserve_synth_run("u1")
    with pytest.raises(QuotaExceeded) as ei:
        qm.reserve_synth_run("u1")
    assert ei.value.code == "concurrency_limit"
    assert qm.usage("u1")["max_concurrent_synth"] == 3
