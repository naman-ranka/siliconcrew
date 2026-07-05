"""Wave 10 — hosted chat durability (Postgres checkpointer).

The checkpointer holds the conversation content. Self-host keeps a per-call
``AsyncSqliteSaver`` on the local ``state.db``; hosted builds ONE app-scoped
``AsyncConnectionPool`` + a shared ``AsyncPostgresSaver`` at startup.

Real Cloud SQL is not available in CI, so the Postgres branch is exercised with
recording fakes injected into ``sys.modules`` (the module imports
``AsyncPostgresSaver`` / ``AsyncConnectionPool`` / ``dict_row`` lazily, INSIDE
``init_checkpointer``, so setitem-injection controls them without touching the
product code).
"""
import asyncio
import sys

import pytest

from src.platform_engines import checkpointer as ckpt


# The module keeps process globals (the shared saver + pool). Reset them around
# every test so state never leaks between the sqlite/postgres cases.
@pytest.fixture(autouse=True)
def _reset_checkpointer_globals():
    ckpt._SHARED_SAVER = None
    ckpt._POOL = None
    yield
    ckpt._SHARED_SAVER = None
    ckpt._POOL = None


# --------------------------------------------------------------------------- #
# Fakes for the lazily-imported Postgres symbols.
# --------------------------------------------------------------------------- #


class FakeAsyncConnectionPool:
    """Records construction args + open/close awaits; never touches a network."""

    instances: list = []

    def __init__(self, conninfo=None, min_size=None, max_size=None, open=None, kwargs=None):
        self.conninfo = conninfo
        self.min_size = min_size
        self.max_size = max_size
        self.open_flag = open
        self.kwargs = kwargs or {}
        self.opened = False
        self.closed = False
        FakeAsyncConnectionPool.instances.append(self)

    async def open(self):
        self.opened = True

    async def close(self):
        self.closed = True


class FakeAsyncPostgresSaver:
    """Records the pool it wraps and whether setup() was awaited."""

    instances: list = []

    def __init__(self, pool):
        self.pool = pool
        self.setup_called = False
        FakeAsyncPostgresSaver.instances.append(self)

    async def setup(self):
        self.setup_called = True


def _install_pg_fakes(monkeypatch, *, saver_cls=FakeAsyncPostgresSaver,
                      pool_cls=FakeAsyncConnectionPool):
    """Inject fake modules for the three symbols init_checkpointer imports.

    The module does ``from langgraph.checkpoint.postgres.aio import
    AsyncPostgresSaver``, ``from psycopg.rows import dict_row`` and ``from
    psycopg_pool import AsyncConnectionPool`` INSIDE the function; injecting the
    leaf modules into sys.modules is enough (the import machinery returns a
    sys.modules hit without importing parents), and none of these packages are
    installed in CI.
    """
    import types

    saver_cls.instances = []
    pool_cls.instances = []

    aio_mod = types.ModuleType("langgraph.checkpoint.postgres.aio")
    aio_mod.AsyncPostgresSaver = saver_cls
    rows_mod = types.ModuleType("psycopg.rows")
    rows_mod.dict_row = object()
    pool_mod = types.ModuleType("psycopg_pool")
    pool_mod.AsyncConnectionPool = pool_cls

    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres.aio", aio_mod)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows_mod)
    monkeypatch.setitem(sys.modules, "psycopg_pool", pool_mod)
    return rows_mod.dict_row


class FakeSettings:
    def __init__(self, persistence_engine="sqlite", database_url=""):
        self.persistence_engine = persistence_engine
        self.database_url = database_url


# --------------------------------------------------------------------------- #
# 1. open_checkpointer — sqlite path (no shared saver).
# --------------------------------------------------------------------------- #


def test_open_checkpointer_sqlite_yields_fresh_saver_and_closes(tmp_path):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db = str(tmp_path / "state.db")

    async def _one_call():
        async with ckpt.open_checkpointer(db) as saver:
            assert isinstance(saver, AsyncSqliteSaver)
            conn = saver.conn
            assert conn.is_alive()
            return saver, conn

    saver1, conn1 = asyncio.run(_one_call())
    # The per-call connection is closed after the context exits.
    assert conn1.is_alive() is False

    saver2, conn2 = asyncio.run(_one_call())
    # A second call opens a DISTINCT saver/connection (fresh per call).
    assert saver2 is not saver1
    assert conn2 is not conn1


# --------------------------------------------------------------------------- #
# 2. init_checkpointer — no-op unless (postgres AND database_url).
# --------------------------------------------------------------------------- #


def test_init_checkpointer_noop_in_sqlite_mode():
    asyncio.run(ckpt.init_checkpointer(FakeSettings("sqlite", "")))
    assert ckpt.shared_saver() is None


def test_init_checkpointer_fail_fast_postgres_without_database_url():
    # Postgres engine but empty DSN → REFUSE to boot (adversarial review F2):
    # a silent no-op would leave the app on ephemeral SQLite and lose
    # conversations + session rows on restart/scale, invisibly.
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        asyncio.run(ckpt.init_checkpointer(FakeSettings("postgres", "")))
    assert ckpt.shared_saver() is None


# --------------------------------------------------------------------------- #
# 3. init_checkpointer — Postgres branch (fake pool + saver).
# --------------------------------------------------------------------------- #


def test_init_checkpointer_postgres_builds_pool_saver_and_open_checkpointer_yields_it(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_POOL_MAX", "5")
    monkeypatch.delenv("CHECKPOINT_POOL_MIN", raising=False)
    dict_row_sentinel = _install_pg_fakes(monkeypatch)

    asyncio.run(ckpt.init_checkpointer(FakeSettings("postgres", "postgresql://db/x")))

    # One pool, constructed with the env-derived sizes + required kwargs.
    assert len(FakeAsyncConnectionPool.instances) == 1
    pool = FakeAsyncConnectionPool.instances[0]
    assert pool.conninfo == "postgresql://db/x"
    assert pool.min_size == 0        # default
    assert pool.max_size == 5        # CHECKPOINT_POOL_MAX
    assert pool.open_flag is False   # built closed, opened explicitly
    assert pool.kwargs == {"autocommit": True, "row_factory": dict_row_sentinel}
    assert pool.opened is True       # await pool.open()

    # One saver, wrapping that pool, with setup() awaited.
    assert len(FakeAsyncPostgresSaver.instances) == 1
    saver = FakeAsyncPostgresSaver.instances[0]
    assert saver.pool is pool
    assert saver.setup_called is True

    # The shared saver is that saver, and open_checkpointer yields it by
    # IDENTITY — no per-call sqlite connection is opened.
    assert ckpt.shared_saver() is saver

    async def _yields_shared():
        async with ckpt.open_checkpointer("/unused/path.db") as memory:
            return memory

    assert asyncio.run(_yields_shared()) is saver

    # Shutdown closes the pool and nulls the shared saver.
    asyncio.run(ckpt.close_checkpointer())
    assert pool.closed is True
    assert ckpt.shared_saver() is None
    assert ckpt._POOL is None


# --------------------------------------------------------------------------- #
# 4. Fail-fast — a setup() that raises aborts startup (and closes the pool).
# --------------------------------------------------------------------------- #


def test_init_checkpointer_fail_fast_propagates_and_closes_pool(monkeypatch):
    class ExplodingSaver(FakeAsyncPostgresSaver):
        async def setup(self):
            raise RuntimeError("setup boom")

    _install_pg_fakes(monkeypatch, saver_cls=ExplodingSaver)

    with pytest.raises(RuntimeError, match="setup boom"):
        asyncio.run(ckpt.init_checkpointer(FakeSettings("postgres", "postgresql://db/x")))

    # Fail-fast contract: no broken app is left behind.
    assert ckpt.shared_saver() is None
    assert ckpt._POOL is None
    # The pool it opened must not leak — it is closed before the re-raise.
    pool = FakeAsyncConnectionPool.instances[0]
    assert pool.opened is True
    assert pool.closed is True


# --------------------------------------------------------------------------- #
# 5. _pool_sizes — env parsing / defaults / clamping.
# --------------------------------------------------------------------------- #


def test_pool_sizes_defaults(monkeypatch):
    monkeypatch.delenv("CHECKPOINT_POOL_MIN", raising=False)
    monkeypatch.delenv("CHECKPOINT_POOL_MAX", raising=False)
    # max default 10 (review F1: per-instance headroom under Cloud Run
    # concurrency; the custom tier's max_connections covers 10 x 10).
    assert ckpt._pool_sizes() == (0, 10)


def test_pool_sizes_from_env(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_POOL_MIN", "2")
    monkeypatch.setenv("CHECKPOINT_POOL_MAX", "8")
    assert ckpt._pool_sizes() == (2, 8)


def test_pool_sizes_garbage_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_POOL_MIN", "abc")
    monkeypatch.setenv("CHECKPOINT_POOL_MAX", "not-a-number")
    assert ckpt._pool_sizes() == (0, 10)


def test_pool_sizes_max_floored_to_at_least_one(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_POOL_MIN", "0")
    monkeypatch.setenv("CHECKPOINT_POOL_MAX", "0")
    pmin, pmax = ckpt._pool_sizes()
    assert pmin == 0
    assert pmax == 1   # a pool needs at least one connection


def test_pool_sizes_min_floored_to_at_least_zero(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_POOL_MIN", "-5")
    monkeypatch.setenv("CHECKPOINT_POOL_MAX", "3")
    assert ckpt._pool_sizes() == (0, 3)
