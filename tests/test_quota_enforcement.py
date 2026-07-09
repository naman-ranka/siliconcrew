"""Quota enforcement around synthesis + multi-instance semantics (Phase 2 I4)."""
from concurrent.futures import Future

import pytest

import src.tools.synthesis_manager as sm
from src.platform_engines.quotas import (
    InMemoryQuotaStore,
    PostgresQuotaStore,
    QuotaExceeded,
    QuotaManager,
    QuotaPolicy,
)
from src.utils.session_context import SessionContext, session_scope


# --------------------------------------------------------------------------
# Enforcement through start_synthesis_job (no real ORFS — worker is stubbed)
# --------------------------------------------------------------------------


class ManualExecutor:
    """Captures submitted runners without executing them (so a reservation stays
    held), then runs them on demand to exercise the release path."""

    def __init__(self):
        self.pending = []

    def submit(self, fn, *args):
        f: Future = Future()
        self.pending.append((f, fn, args))
        return f

    def run_all(self):
        for f, fn, args in self.pending:
            try:
                f.set_result(fn(*args))
            except Exception as exc:  # noqa: BLE001
                f.set_exception(exc)
        self.pending = []


@pytest.fixture
def governed(tmp_path, monkeypatch):
    """Install a manual executor + a quota manager, with the worker stubbed."""
    monkeypatch.setattr(sm, "_job_worker", lambda *a, **k: {"status": "completed"})
    monkeypatch.setattr(sm, "_retry_pd_worker", lambda *a, **k: {"status": "completed"})
    execu = ManualExecutor()
    sm.set_job_executor(execu)
    policy = {"user": QuotaPolicy(synth_runs_per_day=5, compute_minutes_per_month=1000, max_concurrent_synth=1),
              "anonymous": QuotaPolicy(0, 0, 0)}
    qm = QuotaManager(policies=policy)
    sm.set_quota_manager(qm)
    try:
        yield execu, qm, str(tmp_path)
    finally:
        sm.set_job_executor(None)
        sm.set_quota_manager(None)


def _start(workspace):
    return sm.start_synthesis_job(workspace=workspace, verilog_files=["a.v"], top_module="t")


def test_concurrency_cap_blocks_second_run_and_release_frees(governed):
    execu, qm, ws = governed
    with session_scope(SessionContext("s1", ws, user_id="alice", tier="user")):
        first = _start(ws)
        assert "job_id" in first and first.get("status") == "queued"
        # Second concurrent run for the same user is rejected (slot still held).
        second = _start(ws)
        assert second.get("status") == "rejected"
        assert second["error"]["code"] == "concurrency_limit"

        # Completing the first run releases the slot...
        execu.run_all()
        third = _start(ws)
        assert "job_id" in third and third.get("status") == "queued"


def test_completed_background_job_syncs_workspace_provider(governed):
    execu, _qm, ws = governed
    from src.platform_engines.workspace_provider import set_workspace_provider

    class SyncProvider:
        def __init__(self):
            self.synced = []

        def sync(self, session_id):
            self.synced.append(session_id)

    provider = SyncProvider()
    set_workspace_provider(provider)
    try:
        with session_scope(SessionContext("s1", ws, user_id="alice", tier="user")):
            first = _start(ws)
            assert "job_id" in first and first.get("status") == "queued"
            assert provider.synced == []

            execu.run_all()

            assert provider.synced == ["s1"]
    finally:
        set_workspace_provider(None)


def test_anonymous_tier_cannot_synth(governed):
    _execu, _qm, ws = governed
    with session_scope(SessionContext("s2", ws, user_id="anon_x", tier="anonymous")):
        result = _start(ws)
        assert result.get("status") == "rejected"
        assert result["error"]["code"] == "synth_not_allowed"


def test_different_users_not_blocked(governed):
    _execu, _qm, ws = governed
    with session_scope(SessionContext("sa", ws, user_id="alice", tier="user")):
        assert "job_id" in _start(ws)
    with session_scope(SessionContext("sb", ws, user_id="bob", tier="user")):
        assert "job_id" in _start(ws)  # independent tenant, own slot


def test_no_quota_manager_is_unchanged(tmp_path, monkeypatch):
    """Self-host (no quota manager) path: synthesis proceeds, no rejection."""
    monkeypatch.setattr(sm, "_job_worker", lambda *a, **k: {"status": "completed"})
    execu = ManualExecutor()
    sm.set_job_executor(execu)
    sm.set_quota_manager(None)
    try:
        with session_scope(SessionContext("s", str(tmp_path), user_id=None)):
            r1 = _start(str(tmp_path))
            r2 = _start(str(tmp_path))  # no cap → both accepted
            assert "job_id" in r1 and "job_id" in r2
    finally:
        sm.set_job_executor(None)


# --------------------------------------------------------------------------
# Multi-instance semantics (caps survive horizontal scaling)
# --------------------------------------------------------------------------


def test_shared_store_serializes_two_app_instances():
    """Two QuotaManagers (two replicas) over ONE shared store enforce the cap."""
    shared = InMemoryQuotaStore()
    policy = {"user": QuotaPolicy(synth_runs_per_day=5, compute_minutes_per_month=1000, max_concurrent_synth=1)}
    inst_a = QuotaManager(store=shared, policies=policy)
    inst_b = QuotaManager(store=shared, policies=policy)
    inst_a.reserve_synth_run("alice")  # replica A takes the only slot
    with pytest.raises(QuotaExceeded) as ei:
        inst_b.reserve_synth_run("alice")  # replica B is blocked by the shared store
    assert ei.value.code == "concurrency_limit"


class _FakePg:
    """Minimal shared-state Postgres double for the concurrency-acquire path."""

    def __init__(self):
        self.counts = {}
        self.updated_at = {}
        self.sql = []

    def connect(self, _dsn):
        return _FakePgConn(self)


class _FakePgConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return _FakePgCursor(self.db)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakePgCursor:
    def __init__(self, db):
        self.db = db
        self._last = None

    def execute(self, sql, params=()):
        self.db.sql.append(sql)
        c = self.db.counts
        if "INSERT INTO quota_concurrency" in sql:
            c.setdefault(params[0], 0)
            if len(params) > 1:
                self.db.updated_at.setdefault(params[0], params[1])
        elif "SELECT count" in sql and "FROM quota_concurrency" in sql:
            self._last = (c.get(params[0], 0), self.db.updated_at.get(params[0], 0))
        elif "count = count + 1" in sql:
            self.db.updated_at[params[1]] = params[0]
            c[params[1]] = c.get(params[1], 0) + 1
        elif "SET count = 0" in sql:
            self.db.updated_at[params[1]] = params[0]
            c[params[1]] = 0
        elif "GREATEST(count - 1" in sql:
            self.db.updated_at[params[1]] = params[0]
            c[params[1]] = max(0, c.get(params[1], 0) - 1)

    def fetchone(self):
        return self._last

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_postgres_store_atomic_acquire_uses_for_update():
    db = _FakePg()
    store = PostgresQuotaStore("dsn", connect=db.connect)
    assert store.try_acquire_concurrency("u", 1) is True
    assert store.try_acquire_concurrency("u", 1) is False   # cap reached
    store.release_concurrency("u")
    assert store.try_acquire_concurrency("u", 1) is True     # slot freed
    # The acquire must lock the row to be atomic across replicas.
    assert any("FOR UPDATE" in s for s in db.sql)


def test_postgres_store_reclaims_stale_concurrency_slot():
    db = _FakePg()
    now = {"t": 100.0}
    store = PostgresQuotaStore(
        "dsn",
        connect=db.connect,
        stale_concurrency_sec=30,
        clock=lambda: now["t"],
    )

    assert store.try_acquire_concurrency("u", 1) is True
    assert store.try_acquire_concurrency("u", 1) is False

    now["t"] = 131.0

    assert store.try_acquire_concurrency("u", 1) is True
    assert db.counts["u"] == 1
