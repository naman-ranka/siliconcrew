"""Engine-selected LangGraph checkpointer.

The checkpointer holds the conversation content (every message) as LangGraph
graph state. Self-host runs one process on a real disk, so SQLite on the local
``state.db`` is correct and needs no external service. Hosted runs on ephemeral,
per-instance Cloud Run disk with up to N concurrent instances, so a local file
loses conversations on restart/redeploy/scale AND is not shared across
instances — the durable store must be the Cloud SQL Postgres already used for
session/thread metadata (this finishes the migration already done for metadata,
it is not a new one).

Design:
- SQLite (self-host): a fresh ``AsyncSqliteSaver`` per ``open_checkpointer``
  call (cheap on a local file). No new runtime deps — psycopg / the postgres
  saver are imported ONLY in the postgres branch.
- Postgres (hosted): ONE app-scoped ``AsyncConnectionPool`` + a single shared
  ``AsyncPostgresSaver`` built once at startup (``.setup()`` runs the idempotent
  migrations); ``open_checkpointer`` yields that shared saver — never a
  per-turn connect/setup. The pool owns connection lifecycle.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Optional

# Set once at startup by ``init_checkpointer`` in postgres mode; None means
# SQLite mode (self-host) — ``open_checkpointer`` opens a per-call connection.
_SHARED_SAVER: Any = None
_POOL: Any = None


def _pool_sizes() -> tuple[int, int]:
    """(min, max) pool size from env — scale-to-zero friendly defaults.

    min=0 holds no idle connections when an instance is idle, so the Cloud SQL
    connection budget is a peak-load ceiling, not an idle cost. max is
    deliberately small: budget = max × backend_max_instances must stay under
    Cloud SQL max_connections (see plans/hosted-chat-durability.md Item 4).
    """
    try:
        pmin = int(os.environ.get("CHECKPOINT_POOL_MIN", "0"))
    except ValueError:
        pmin = 0
    try:
        pmax = int(os.environ.get("CHECKPOINT_POOL_MAX", "3"))
    except ValueError:
        pmax = 3
    return max(0, pmin), max(1, pmax)


async def init_checkpointer(settings) -> None:
    """Build the shared Postgres checkpointer + pool (hosted only).

    Fail-fast: any error here aborts startup rather than silently leaving the
    app on ephemeral SQLite in production — that would re-introduce the exact
    data-loss bug this exists to fix. No-op (and leaves SQLite mode) when the
    engine is not postgres.
    """
    global _SHARED_SAVER, _POOL
    if getattr(settings, "persistence_engine", "sqlite") != "postgres" or not getattr(
        settings, "database_url", ""
    ):
        return

    # Imported lazily so self-host never needs these packages installed.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pmin, pmax = _pool_sizes()
    # AsyncPostgresSaver requires autocommit connections (it manages its own
    # transactions) and dict rows.
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=pmin,
        max_size=pmax,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    # Idempotent: creates checkpoints / checkpoint_blobs / checkpoint_writes /
    # checkpoint_migrations and runs pending migrations.
    await saver.setup()
    _POOL = pool
    _SHARED_SAVER = saver
    print(f"[API] Checkpointer: Postgres (pool {pmin}-{pmax})")


async def close_checkpointer() -> None:
    """Close the shared pool on shutdown (no-op in SQLite mode)."""
    global _SHARED_SAVER, _POOL
    pool = _POOL
    _SHARED_SAVER = None
    _POOL = None
    if pool is not None:
        await pool.close()


def shared_saver() -> Any:
    """The shared Postgres saver, or None in SQLite mode. For open_checkpointer."""
    return _SHARED_SAVER


# Test seam: force the shared saver (and skip real pooling) in unit tests.
def _set_shared_saver_for_test(saver: Any) -> None:
    global _SHARED_SAVER
    _SHARED_SAVER = saver


@asynccontextmanager
async def open_sqlite_checkpointer(db_path: str):
    """A fresh AsyncSqliteSaver on ``db_path`` (self-host / local path).

    Compat shim for aiosqlite variants without ``Connection.is_alive`` that the
    langgraph sqlite saver expects.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    conn = await aiosqlite.connect(db_path)
    if not hasattr(conn, "is_alive"):
        def _is_alive() -> bool:
            return bool(getattr(conn, "_running", False))

        setattr(conn, "is_alive", _is_alive)
    try:
        yield AsyncSqliteSaver(conn)
    finally:
        await conn.close()


@asynccontextmanager
async def open_checkpointer(db_path: str):
    """Yield a checkpointer — the shared pooled Postgres saver (hosted) or a
    fresh per-call SQLite saver (self-host). Same interface either way, so all
    callers (``create_architect_agent(checkpointer=…)``, thread-history reads)
    are engine-agnostic."""
    saver = _SHARED_SAVER
    if saver is not None:
        # Postgres: the pool owns lifecycle — no per-call connect/close.
        yield saver
        return
    async with open_sqlite_checkpointer(db_path) as memory:
        yield memory
