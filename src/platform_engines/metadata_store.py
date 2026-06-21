"""MetadataStore — session/project metadata behind a swappable backend.

Per-process SQLite (``state.db``) is correct for self-host but cannot be shared
across horizontally-scaled Cloud Run instances. This module isolates *all* of
the session-manager's relational operations behind one interface so the backend
swaps from SQLite to Cloud SQL / Postgres with no change to ``SessionManager``'s
public API (which still owns the filesystem/workspace side).

  * :class:`SqliteMetadataStore` — today's schema + queries, encapsulated.
  * :class:`PostgresMetadataStore` — the same operations over psycopg (Cloud SQL).

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
    def create_project(self, slug: str, name: str, created_at: Any) -> None: ...
    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]: ...
    def get_all_projects(self) -> List[Dict[str, Any]]: ...
    def delete_project(self, project_id: str) -> None: ...
    # sessions
    def upsert_session(self, session_id: str, session_name: str, model_name: str,
                       project_id: Optional[str], now: Any) -> None: ...
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    def get_all_session_rows(self) -> List[Dict[str, Any]]: ...
    def move_session(self, session_id: str, project_id: Optional[str]) -> None: ...
    def update_stats(self, session_id: str, input_t: int, output_t: int,
                     cached_t: int, total_t: int, cost: float, now: Any) -> None: ...
    def delete_session(self, session_id: str) -> None: ...


class DuplicateProject(Exception):
    pass


# ---------------------------------------------------------------------------
# SQLite — encapsulates exactly today's schema and queries.
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS session_metadata (
                    session_id TEXT PRIMARY KEY,
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
            conn.commit()

    def _migrate_existing_groups(self, cur) -> None:
        rows = cur.execute("SELECT session_id FROM session_metadata").fetchall()
        for (session_id,) in rows:
            if "/" in session_id:
                project_slug = session_id.split("/")[0]
                cur.execute("INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
                            (project_slug, project_slug))
                cur.execute("UPDATE session_metadata SET project_id = ? WHERE session_id = ?",
                            (project_slug, session_id))

    def create_project(self, slug, name, created_at):
        with self._connect() as conn:
            try:
                conn.execute("INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                             (slug, name, created_at))
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise DuplicateProject(slug) from exc

    def get_project(self, project_id):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def get_all_projects(self):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM projects ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]

    def delete_project(self, project_id):
        with self._connect() as conn:
            conn.execute("UPDATE session_metadata SET project_id = NULL WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()

    def upsert_session(self, session_id, session_name, model_name, project_id, now):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_metadata (session_id, session_name, model_name, project_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    session_name = COALESCE(session_metadata.session_name, excluded.session_name),
                    model_name = COALESCE(session_metadata.model_name, excluded.model_name),
                    project_id = COALESCE(excluded.project_id, session_metadata.project_id),
                    updated_at = excluded.updated_at
                """,
                (session_id, session_name, model_name, project_id, now, now),
            )
            conn.commit()

    def get_session(self, session_id):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM session_metadata WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_all_session_rows(self):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM session_metadata").fetchall()
        return [dict(r) for r in rows]

    def move_session(self, session_id, project_id):
        with self._connect() as conn:
            conn.execute("UPDATE session_metadata SET project_id = ? WHERE session_id = ?",
                         (project_id, session_id))
            conn.commit()

    def update_stats(self, session_id, input_t, output_t, cached_t, total_t, cost, now):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE session_metadata
                SET input_tokens = ?, output_tokens = ?, cached_tokens = ?,
                    total_tokens = ?, total_cost = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (input_t, output_t, cached_t, total_t, cost, now, session_id),
            )
            conn.commit()

    def delete_session(self, session_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM session_metadata WHERE session_id = ?", (session_id,))
            for table in self._CHECKPOINT_TABLES:
                try:
                    conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (session_id,))
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


# ---------------------------------------------------------------------------
# Postgres / Cloud SQL — same operations over psycopg (lazy import).
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
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS session_metadata (
                    session_id TEXT PRIMARY KEY,
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
            conn.commit()

    def create_project(self, slug, name, created_at):
        import psycopg.errors as pg_errors  # lazy

        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO projects (id, name, created_at) VALUES (%s, %s, %s)",
                            (slug, name, created_at))
                conn.commit()
        except pg_errors.UniqueViolation as exc:
            raise DuplicateProject(slug) from exc

    def get_project(self, project_id):
        return self._one("SELECT * FROM projects WHERE id = %s", (project_id,))

    def get_all_projects(self):
        return self._all("SELECT * FROM projects ORDER BY name ASC")

    def delete_project(self, project_id):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE session_metadata SET project_id = NULL WHERE project_id = %s", (project_id,))
            cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
            conn.commit()

    def upsert_session(self, session_id, session_name, model_name, project_id, now):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO session_metadata (session_id, session_name, model_name, project_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(session_id) DO UPDATE SET
                    session_name = COALESCE(session_metadata.session_name, excluded.session_name),
                    model_name = COALESCE(session_metadata.model_name, excluded.model_name),
                    project_id = COALESCE(excluded.project_id, session_metadata.project_id),
                    updated_at = excluded.updated_at
                """,
                (session_id, session_name, model_name, project_id, now, now),
            )
            conn.commit()

    def get_session(self, session_id):
        return self._one("SELECT * FROM session_metadata WHERE session_id = %s", (session_id,))

    def get_all_session_rows(self):
        return self._all("SELECT * FROM session_metadata")

    def move_session(self, session_id, project_id):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE session_metadata SET project_id = %s WHERE session_id = %s",
                        (project_id, session_id))
            conn.commit()

    def update_stats(self, session_id, input_t, output_t, cached_t, total_t, cost, now):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE session_metadata
                SET input_tokens = %s, output_tokens = %s, cached_tokens = %s,
                    total_tokens = %s, total_cost = %s, updated_at = %s
                WHERE session_id = %s
                """,
                (input_t, output_t, cached_t, total_t, cost, now, session_id),
            )
            conn.commit()

    def delete_session(self, session_id):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM session_metadata WHERE session_id = %s", (session_id,))
            conn.commit()

    # -- helpers --
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
