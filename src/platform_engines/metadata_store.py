"""MetadataStore — session/project metadata behind a swappable backend.

Per-process SQLite (``state.db``) is correct for self-host but cannot be shared
across horizontally-scaled Cloud Run instances. This module isolates *all* of
the session-manager's relational operations behind one interface so the backend
swaps from SQLite to Cloud SQL / Postgres with no change to ``SessionManager``'s
public API (which still owns the filesystem/workspace side).

  * :class:`SqliteMetadataStore` — today's schema + queries, encapsulated.
  * :class:`PostgresMetadataStore` — the same operations over psycopg (Cloud SQL).

Multi-tenancy (the release gate)
--------------------------------
Every session/project row carries an owning ``user_id`` (tenant). Every read and
mutation is filtered by it, *tenant-scoped by construction*. The ``user_id``
argument is optional and defaults to ``None``:

  * ``None``  → self-host / single-tenant: no tenant filter (today's behavior,
    bit-for-bit). Legacy rows (NULL owner) remain visible here.
  * a value  → hosted multi-tenant: the query only ever touches that tenant's
    rows, so user A can never read/mutate user B's session or workspace.

Only relational metadata moves here. Workspace *files* are externalized
separately via :mod:`workspace_provider`; the two seams are independent.
"""
from __future__ import annotations

import datetime
import os
import sqlite3
from typing import Any, Dict, List, Optional, Protocol


class MetadataStore(Protocol):
    # schema
    def init_schema(self) -> None: ...
    # projects
    def create_project(self, slug: str, name: str, created_at: Any, user_id: Optional[str] = None) -> None: ...
    def get_project(self, project_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]: ...
    def get_all_projects(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]: ...
    def rename_project(self, project_id: str, name: str, user_id: Optional[str] = None) -> None: ...
    def delete_project(self, project_id: str, user_id: Optional[str] = None) -> None: ...
    # sessions
    def upsert_session(self, session_id: str, user_id: Optional[str], session_name: str,
                       model_name: str, project_id: Optional[str], now: Any) -> None: ...
    def get_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]: ...
    def get_all_session_rows(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]: ...
    def move_session(self, session_id: str, project_id: Optional[str], user_id: Optional[str] = None) -> None: ...
    # Display-only rename: session_id (the primary key = workspace dir) never changes.
    def rename_session(self, session_id: str, name: str, user_id: Optional[str] = None) -> None: ...
    def update_stats(self, session_id: str, input_t: int, output_t: int, cached_t: int,
                     total_t: int, cost: float, now: Any, user_id: Optional[str] = None) -> None: ...
    def delete_session(self, session_id: str, user_id: Optional[str] = None) -> None: ...
    # chat threads (a chat = a LangGraph thread_id; many per session/workspace)
    def create_thread(self, thread_id: str, session_id: str, user_id: Optional[str],
                      title: str, model: Optional[str], now: Any) -> None: ...
    def ensure_thread(self, thread_id: str, session_id: str, user_id: Optional[str],
                      title: str, model: Optional[str], now: Any) -> None: ...
    def get_thread(self, thread_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]: ...
    def list_threads(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]: ...
    def count_threads(self, session_id: str, user_id: Optional[str] = None) -> int: ...
    # One grouped COUNT for the whole session list ({session_id: rows}) — no N+1.
    def count_threads_by_session(self, user_id: Optional[str] = None) -> Dict[str, int]: ...
    def update_thread(self, thread_id: str, user_id: Optional[str] = None, *,
                      title: Optional[str] = None, model: Optional[str] = None,
                      last_active: Any = None) -> None: ...
    def delete_thread(self, thread_id: str, user_id: Optional[str] = None) -> None: ...
    # identity migration (operator tool, Slice 3): re-key every row owned by
    # old_user_id to new_user_id. Used to unify google_<sub> -> workos_<sub>
    # when the deployed web sign-in moves to WorkOS. Returns rows moved.
    def reassign_user(self, old_user_id: str, new_user_id: str) -> int: ...


class DuplicateProject(Exception):
    pass


# ---------------------------------------------------------------------------
# SQLite — encapsulates today's schema and queries, plus the tenant column.
# ---------------------------------------------------------------------------


class SqliteMetadataStore:
    _CHECKPOINT_TABLES = ("checkpoints", "checkpoint_writes", "checkpoint_blobs")

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def init_schema(self) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    user_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS session_metadata (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    session_name TEXT,
                    model_name TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cached_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    total_cost REAL DEFAULT 0.0
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    title TEXT,
                    model TEXT,
                    created_at TIMESTAMP,
                    last_active TIMESTAMP
                )
                """
            )
            self._migrate_columns(cur)
            # Tenant-scoped listing index (user_id, created_at).
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_user_created "
                "ON session_metadata(user_id, created_at)"
            )
            # Thread listing index (newest-active first within a session).
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_thread_session_active "
                "ON chat_threads(session_id, last_active)"
            )
            conn.commit()

    def _migrate_columns(self, cur) -> None:
        existing = {row[1] for row in cur.execute("PRAGMA table_info(session_metadata)")}
        if "session_name" not in existing:
            cur.execute("ALTER TABLE session_metadata ADD COLUMN session_name TEXT")
        if "updated_at" not in existing:
            cur.execute("ALTER TABLE session_metadata ADD COLUMN updated_at TIMESTAMP")
        if "project_id" not in existing:
            cur.execute(
                "ALTER TABLE session_metadata ADD COLUMN project_id TEXT "
                "REFERENCES projects(id) ON DELETE SET NULL"
            )
            self._migrate_existing_groups(cur)
        # Tenant column. Legacy rows keep user_id NULL ("unowned"): visible only
        # to unscoped (self-host) queries, never to a real tenant.
        if "user_id" not in existing:
            cur.execute("ALTER TABLE session_metadata ADD COLUMN user_id TEXT")
        proj_cols = {row[1] for row in cur.execute("PRAGMA table_info(projects)")}
        if "user_id" not in proj_cols:
            cur.execute("ALTER TABLE projects ADD COLUMN user_id TEXT")

    def _migrate_existing_groups(self, cur) -> None:
        rows = cur.execute("SELECT session_id FROM session_metadata").fetchall()
        for (session_id,) in rows:
            if "/" in session_id:
                project_slug = session_id.split("/")[0]
                cur.execute("INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
                            (project_slug, project_slug))
                cur.execute("UPDATE session_metadata SET project_id = ? WHERE session_id = ?",
                            (project_slug, session_id))

    # -- projects --

    def create_project(self, slug, name, created_at, user_id=None):
        with self._connect() as conn:
            try:
                conn.execute("INSERT INTO projects (id, name, user_id, created_at) VALUES (?, ?, ?, ?)",
                             (slug, name, user_id, created_at))
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise DuplicateProject(slug) from exc

    def get_project(self, project_id, user_id=None):
        sql = "SELECT * FROM projects WHERE id = ?"
        params: list = [project_id]
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_all_projects(self, user_id=None):
        sql = "SELECT * FROM projects"
        params: list = []
        if user_id is not None:
            sql += " WHERE user_id = ?"
            params.append(user_id)
        sql += " ORDER BY name ASC"
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def rename_project(self, project_id, name, user_id=None):
        """Rename a project's display name (the id/slug is immutable).

        Tenant-scoped like move_session: a non-owner's rename is a no-op.
        """
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE projects SET name = ? WHERE id = ?{owner}",
                (name, project_id, *oparams),
            )
            conn.commit()

    def delete_project(self, project_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE session_metadata SET project_id = NULL WHERE project_id = ?{owner}",
                (project_id, *oparams),
            )
            conn.execute(f"DELETE FROM projects WHERE id = ?{owner}", (project_id, *oparams))
            conn.commit()

    # -- sessions --

    def upsert_session(self, session_id, user_id, session_name, model_name, project_id, now):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_metadata (session_id, user_id, session_name, model_name, project_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    -- owner is immutable once set (first writer wins).
                    user_id = COALESCE(session_metadata.user_id, excluded.user_id),
                    session_name = COALESCE(session_metadata.session_name, excluded.session_name),
                    model_name = COALESCE(session_metadata.model_name, excluded.model_name),
                    project_id = COALESCE(excluded.project_id, session_metadata.project_id),
                    updated_at = excluded.updated_at
                """,
                (session_id, user_id, session_name, model_name, project_id, now, now),
            )
            conn.commit()

    def get_session(self, session_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM session_metadata WHERE session_id = ?{owner}",
                (session_id, *oparams),
            ).fetchone()
        return dict(row) if row else None

    def get_all_session_rows(self, user_id=None):
        sql = "SELECT * FROM session_metadata"
        params: list = []
        if user_id is not None:
            sql += " WHERE user_id = ?"
            params.append(user_id)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def move_session(self, session_id, project_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE session_metadata SET project_id = ? WHERE session_id = ?{owner}",
                (project_id, session_id, *oparams),
            )
            conn.commit()

    def rename_session(self, session_id, name, user_id=None):
        """DISPLAY-ONLY rename: updates ``session_name``. The session_id (primary
        key, and thus the workspace directory it names) never changes.
        Tenant-scoped like move_session: a non-owner's rename is a no-op.
        """
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE session_metadata SET session_name = ? WHERE session_id = ?{owner}",
                (name, session_id, *oparams),
            )
            conn.commit()

    def update_stats(self, session_id, input_t, output_t, cached_t, total_t, cost, now, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE session_metadata
                SET input_tokens = ?, output_tokens = ?, cached_tokens = ?,
                    total_tokens = ?, total_cost = ?, updated_at = ?
                WHERE session_id = ?{owner}
                """,
                (input_t, output_t, cached_t, total_t, cost, now, session_id, *oparams),
            )
            conn.commit()

    def delete_session(self, session_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            # Chat ids first — the cascade below needs them for the checkpoint
            # tables (keyed by thread_id, no FK anywhere: manual cascade).
            thread_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM chat_threads WHERE session_id = ?", (session_id,)
                )
            ]
            cur = conn.execute(
                f"DELETE FROM session_metadata WHERE session_id = ?{owner}",
                (session_id, *oparams),
            )
            # Cascade only when the owner-gated session delete matched (defense
            # in depth on top of SessionManager's PermissionError); self-host
            # (user_id=None) also sweeps orphans with no session row.
            if cur.rowcount or user_id is None:
                conn.execute(
                    "DELETE FROM chat_threads WHERE session_id = ?", (session_id,)
                )
                # Every chat's checkpoints + the legacy default (thread_id ==
                # session_id). The tables appear only after LangGraph's first
                # write, hence the per-table tolerance.
                for table in self._CHECKPOINT_TABLES:
                    try:
                        for tid in {session_id, *thread_ids}:
                            conn.execute(
                                f"DELETE FROM {table} WHERE thread_id = ?", (tid,)
                            )
                    except sqlite3.OperationalError:
                        pass
            conn.commit()

    # -- chat threads --

    def create_thread(self, thread_id, session_id, user_id, title, model, now):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_threads (id, session_id, user_id, title, model, created_at, last_active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (thread_id, session_id, user_id, title, model, now, now),
            )
            conn.commit()

    def ensure_thread(self, thread_id, session_id, user_id, title, model, now):
        """Insert the thread row only if absent (idempotent; never clobbers)."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_threads (id, session_id, user_id, title, model, created_at, last_active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (thread_id, session_id, user_id, title, model, now, now),
            )
            conn.commit()

    def get_thread(self, thread_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM chat_threads WHERE id = ?{owner}", (thread_id, *oparams)
            ).fetchone()
        return dict(row) if row else None

    def list_threads(self, session_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM chat_threads WHERE session_id = ?{owner} "
                "ORDER BY last_active DESC, created_at DESC",
                (session_id, *oparams),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_threads(self, session_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM chat_threads WHERE session_id = ?{owner}",
                (session_id, *oparams),
            ).fetchone()
        return int(row[0]) if row else 0

    def count_threads_by_session(self, user_id=None):
        """{session_id: thread-row count} in ONE grouped query (session-list use).

        Sessions with no thread rows simply aren't in the dict (callers default
        to 0) — a fresh session has no rows until its default thread is created.
        """
        sql = "SELECT session_id, COUNT(*) FROM chat_threads"
        params: list = []
        if user_id is not None:
            sql += " WHERE user_id = ?"
            params.append(user_id)
        sql += " GROUP BY session_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def update_thread(self, thread_id, user_id=None, *, title=None, model=None, last_active=None):
        sets, params = [], []
        if title is not None:
            sets.append("title = ?"); params.append(title)
        if model is not None:
            sets.append("model = ?"); params.append(model)
        if last_active is not None:
            sets.append("last_active = ?"); params.append(last_active)
        if not sets:
            return
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE chat_threads SET {', '.join(sets)} WHERE id = ?{owner}",
                (*params, thread_id, *oparams),
            )
            conn.commit()

    def delete_thread(self, thread_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn:
            cur = conn.execute(
                f"DELETE FROM chat_threads WHERE id = ?{owner}", (thread_id, *oparams)
            )
            deleted = cur.rowcount
            # Conversation-only: drop this thread's LangGraph checkpoints (same
            # state.db). Never touches workspace files/runs.
            if deleted:
                for table in self._CHECKPOINT_TABLES:
                    try:
                        conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
                    except sqlite3.OperationalError:
                        pass
            conn.commit()

    def drop_all(self) -> None:
        """Used by clear_all_sessions: remove the underlying db file."""
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                print("Could not delete database file. It might be in use.")

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        """Re-key every row owned by ``old_user_id`` to ``new_user_id`` (Slice 3).

        The identity-unification migration primitive: when the deployed web
        sign-in moves to WorkOS, a user's id changes from ``google_<sub>`` to
        ``workos_<sub>`` (linked by verified email). This moves their projects,
        sessions, and chat threads to the new id so their data keeps showing up.
        Operator-invoked and idempotent (re-running moves nothing). Returns the
        number of rows moved.
        """
        if not old_user_id or not new_user_id:
            raise ValueError("reassign_user requires both old and new user_id")
        if old_user_id == new_user_id:
            return 0
        with self._connect() as conn:
            total = 0
            for table in ("projects", "session_metadata", "chat_threads"):
                cur = conn.execute(
                    f"UPDATE {table} SET user_id = ? WHERE user_id = ?",
                    (new_user_id, old_user_id),
                )
                total += cur.rowcount
            conn.commit()
        return total

    @staticmethod
    def _owner_clause(user_id):
        return (" AND user_id = ?", (user_id,)) if user_id is not None else ("", ())


# ---------------------------------------------------------------------------
# Postgres / Cloud SQL — same operations + tenant column over psycopg.
# ---------------------------------------------------------------------------


class PostgresMetadataStore:
    """Cloud SQL (Postgres) backend. Identical semantics to the SQLite store.

    Connection is a DSN (``DATABASE_URL``); on Cloud Run this points at the Cloud
    SQL connector socket. psycopg is imported lazily so self-host never needs it.
    """

    def __init__(self, dsn: str, connect=None):
        self._dsn = dsn
        self._connect_fn = connect  # injectable for tests

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self._dsn)
        import psycopg  # lazy

        return psycopg.connect(self._dsn)

    def init_schema(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    user_id TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS session_metadata (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    session_name TEXT,
                    model_name TEXT,
                    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ,
                    input_tokens BIGINT DEFAULT 0,
                    output_tokens BIGINT DEFAULT 0,
                    cached_tokens BIGINT DEFAULT 0,
                    total_tokens BIGINT DEFAULT 0,
                    total_cost DOUBLE PRECISION DEFAULT 0.0
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    title TEXT,
                    model TEXT,
                    created_at TIMESTAMPTZ,
                    last_active TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_user_created "
                "ON session_metadata(user_id, created_at)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_thread_session_active "
                "ON chat_threads(session_id, last_active)"
            )
            conn.commit()

    def create_project(self, slug, name, created_at, user_id=None):
        import psycopg.errors as pg_errors  # lazy

        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO projects (id, name, user_id, created_at) VALUES (%s, %s, %s, %s)",
                            (slug, name, user_id, created_at))
                conn.commit()
        except pg_errors.UniqueViolation as exc:
            raise DuplicateProject(slug) from exc

    def get_project(self, project_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        return self._one(f"SELECT * FROM projects WHERE id = %s{owner}", (project_id, *oparams))

    def get_all_projects(self, user_id=None):
        if user_id is not None:
            return self._all("SELECT * FROM projects WHERE user_id = %s ORDER BY name ASC", (user_id,))
        return self._all("SELECT * FROM projects ORDER BY name ASC")

    def rename_project(self, project_id, name, user_id=None):
        """Postgres parity for :meth:`SqliteMetadataStore.rename_project`."""
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE projects SET name = %s WHERE id = %s{owner}",
                (name, project_id, *oparams),
            )
            conn.commit()

    def delete_project(self, project_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE session_metadata SET project_id = NULL WHERE project_id = %s{owner}",
                (project_id, *oparams),
            )
            cur.execute(f"DELETE FROM projects WHERE id = %s{owner}", (project_id, *oparams))
            conn.commit()

    def upsert_session(self, session_id, user_id, session_name, model_name, project_id, now):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO session_metadata (session_id, user_id, session_name, model_name, project_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id = COALESCE(session_metadata.user_id, excluded.user_id),
                    session_name = COALESCE(session_metadata.session_name, excluded.session_name),
                    model_name = COALESCE(session_metadata.model_name, excluded.model_name),
                    project_id = COALESCE(excluded.project_id, session_metadata.project_id),
                    updated_at = excluded.updated_at
                """,
                (session_id, user_id, session_name, model_name, project_id, now, now),
            )
            conn.commit()

    def get_session(self, session_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        return self._one(f"SELECT * FROM session_metadata WHERE session_id = %s{owner}", (session_id, *oparams))

    def get_all_session_rows(self, user_id=None):
        if user_id is not None:
            return self._all("SELECT * FROM session_metadata WHERE user_id = %s", (user_id,))
        return self._all("SELECT * FROM session_metadata")

    def move_session(self, session_id, project_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE session_metadata SET project_id = %s WHERE session_id = %s{owner}",
                (project_id, session_id, *oparams),
            )
            conn.commit()

    def rename_session(self, session_id, name, user_id=None):
        """Postgres parity for :meth:`SqliteMetadataStore.rename_session` —
        DISPLAY-ONLY: the session_id/workspace directory never changes."""
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE session_metadata SET session_name = %s WHERE session_id = %s{owner}",
                (name, session_id, *oparams),
            )
            conn.commit()

    def update_stats(self, session_id, input_t, output_t, cached_t, total_t, cost, now, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE session_metadata
                SET input_tokens = %s, output_tokens = %s, cached_tokens = %s,
                    total_tokens = %s, total_cost = %s, updated_at = %s
                WHERE session_id = %s{owner}
                """,
                (input_t, output_t, cached_t, total_t, cost, now, session_id, *oparams),
            )
            conn.commit()

    def delete_session(self, session_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM session_metadata WHERE session_id = %s{owner}", (session_id, *oparams))
            # Same manual cascade as SQLite (no FK). Checkpoints are NOT here:
            # they live in the local sqlite state DB even in Postgres mode —
            # SessionManager.delete_session does that best-effort cleanup.
            if cur.rowcount or user_id is None:
                cur.execute("DELETE FROM chat_threads WHERE session_id = %s", (session_id,))
            conn.commit()

    # -- chat threads --

    def create_thread(self, thread_id, session_id, user_id, title, model, now):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_threads (id, session_id, user_id, title, model, created_at, last_active) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (thread_id, session_id, user_id, title, model, now, now),
            )
            conn.commit()

    def ensure_thread(self, thread_id, session_id, user_id, title, model, now):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_threads (id, session_id, user_id, title, model, created_at, last_active) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (thread_id, session_id, user_id, title, model, now, now),
            )
            conn.commit()

    def get_thread(self, thread_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        return self._one(f"SELECT * FROM chat_threads WHERE id = %s{owner}", (thread_id, *oparams))

    def list_threads(self, session_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        return self._all(
            f"SELECT * FROM chat_threads WHERE session_id = %s{owner} "
            "ORDER BY last_active DESC, created_at DESC",
            (session_id, *oparams),
        )

    def count_threads(self, session_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM chat_threads WHERE session_id = %s{owner}", (session_id, *oparams))
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def count_threads_by_session(self, user_id=None):
        """Postgres parity for :meth:`SqliteMetadataStore.count_threads_by_session`."""
        sql = "SELECT session_id, COUNT(*) FROM chat_threads"
        params: tuple = ()
        if user_id is not None:
            sql += " WHERE user_id = %s"
            params = (user_id,)
        sql += " GROUP BY session_id"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def update_thread(self, thread_id, user_id=None, *, title=None, model=None, last_active=None):
        sets, params = [], []
        if title is not None:
            sets.append("title = %s"); params.append(title)
        if model is not None:
            sets.append("model = %s"); params.append(model)
        if last_active is not None:
            sets.append("last_active = %s"); params.append(last_active)
        if not sets:
            return
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE chat_threads SET {', '.join(sets)} WHERE id = %s{owner}",
                (*params, thread_id, *oparams),
            )
            conn.commit()

    def delete_thread(self, thread_id, user_id=None):
        owner, oparams = self._owner_clause(user_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM chat_threads WHERE id = %s{owner}", (thread_id, *oparams))
            conn.commit()
        # Checkpoints live in the LangGraph store (sqlite state.db in self-host);
        # Postgres deployments prune via the checkpointer's own retention.

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        """Postgres parity for the Slice-3 identity-unification re-key.

        See :meth:`SqliteMetadataStore.reassign_user`.
        """
        if not old_user_id or not new_user_id:
            raise ValueError("reassign_user requires both old and new user_id")
        if old_user_id == new_user_id:
            return 0
        total = 0
        with self._connect() as conn, conn.cursor() as cur:
            for table in ("projects", "session_metadata", "chat_threads"):
                cur.execute(
                    f"UPDATE {table} SET user_id = %s WHERE user_id = %s",
                    (new_user_id, old_user_id),
                )
                total += cur.rowcount
            conn.commit()
        return total

    # -- helpers --
    @staticmethod
    def _owner_clause(user_id):
        return (" AND user_id = %s", (user_id,)) if user_id is not None else ("", ())

    def _one(self, sql, params):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    def _all(self, sql, params=()):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]


def build_metadata_store(db_path: str) -> MetadataStore:
    """Pick the metadata backend from platform settings (sqlite default)."""
    from src.platform_engines.settings import get_settings

    settings = get_settings()
    if settings.persistence_engine == "postgres" and settings.database_url:
        return PostgresMetadataStore(settings.database_url)
    return SqliteMetadataStore(db_path)
