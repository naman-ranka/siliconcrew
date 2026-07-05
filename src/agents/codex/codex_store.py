"""Codex-owned transcript + thread-map persistence.

Codex runs its own agent process and has NO LangGraph checkpointer, so its
conversation history must be stored explicitly (unlike the native runtime, whose
history lives in the checkpointer). These tables are codex-owned and live in the
same database as the shared metadata store, but nothing in the shared/LangChain
path references them — dropping this module + these two tables removes Codex
cleanly.

Tables
------
- ``codex_threads(thread_id PK, external_thread_id, updated_at)`` — maps our
  thread id to Codex's server-side thread id, so a follow-up turn can
  ``thread_resume`` instead of starting fresh.
- ``codex_messages(id PK, thread_id, role, content, message_type, event_type,
  tool_metadata, created_at)`` — the transcript (the checkpointer substitute),
  ordered by ``(created_at, id)``.

Ownership
---------
Rows are keyed by ``thread_id`` only. Tenant ownership is enforced UPSTREAM: the
api layer resolves the owner-scoped ``chat_threads`` row before touching this
store, so a caller never reaches here for a thread it does not own. Keeping the
codex store thread-id-keyed avoids duplicating the shared tenant logic here.

FK / cleanup
------------
``codex_messages.thread_id`` references ``chat_threads(id)``, but the shared
SQLite store runs with ``foreign_keys`` OFF, so ``ON DELETE CASCADE`` will not
fire on a thread/session delete. Cleanup is wired via a registry
``notify_thread_deleted`` hook (Phase 2b) that calls :meth:`delete_for_thread` —
NOT via codex-specific DELETEs inside the shared delete path (that would violate
the one-way dependency rule).

Engine
------
:func:`build_codex_store` mirrors ``build_metadata_store``'s engine selection.
SQLite (self-host) is implemented here. Postgres parity (hosted durability, so
Codex history survives redeploy/scale exactly like the native checkpointer now
does) is REQUIRED before hosted Codex launch and tracked as such.
"""
from __future__ import annotations

import datetime
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional


def _encode_tool_metadata(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value)


def _decode_tool_metadata(blob: Optional[str]) -> Optional[Dict[str, Any]]:
    if not blob:
        return None
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return None


def _decode_message(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["tool_metadata"] = _decode_tool_metadata(out.get("tool_metadata"))
    return out


class SqliteCodexStore:
    """Codex transcript + thread-map over the same SQLite ``state.db``."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS codex_threads (
                    thread_id TEXT PRIMARY KEY
                        REFERENCES chat_threads(id) ON DELETE CASCADE,
                    external_thread_id TEXT,
                    updated_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS codex_messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL
                        REFERENCES chat_threads(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    message_type TEXT,
                    event_type TEXT,
                    tool_metadata TEXT,
                    created_at TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_codex_messages_thread_created "
                "ON codex_messages(thread_id, created_at)"
            )
            conn.commit()

    # -- thread <-> external id map --
    def set_external_thread_id(self, thread_id: str, external_thread_id: str,
                               now: Optional[datetime.datetime] = None) -> None:
        now = now or datetime.datetime.now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO codex_threads (thread_id, external_thread_id, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(thread_id) DO UPDATE SET "
                "external_thread_id = excluded.external_thread_id, "
                "updated_at = excluded.updated_at",
                (thread_id, external_thread_id, now),
            )
            conn.commit()

    def get_external_thread_id(self, thread_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT external_thread_id FROM codex_threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return row[0] if row else None

    # -- transcript --
    def append_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        message_type: Optional[str] = None,
        event_type: Optional[str] = None,
        tool_metadata: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
        created_at: Optional[datetime.datetime] = None,
    ) -> Dict[str, Any]:
        message_id = message_id or uuid.uuid4().hex
        created_at = created_at or datetime.datetime.now()
        blob = _encode_tool_metadata(tool_metadata)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO codex_messages "
                "(id, thread_id, role, content, message_type, event_type, tool_metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (message_id, thread_id, role, content, message_type, event_type, blob, created_at),
            )
            conn.commit()
        return _decode_message({
            "id": message_id, "thread_id": thread_id, "role": role, "content": content,
            "message_type": message_type, "event_type": event_type,
            "tool_metadata": blob, "created_at": created_at,
        })

    def list_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM codex_messages WHERE thread_id = ? "
                "ORDER BY created_at ASC, id ASC",
                (thread_id,),
            ).fetchall()
        return [_decode_message(dict(r)) for r in rows]

    def delete_for_thread(self, thread_id: str) -> None:
        """Remove a thread's transcript + external-id map (the cleanup hook)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM codex_messages WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM codex_threads WHERE thread_id = ?", (thread_id,))
            conn.commit()


def build_codex_store(db_path: str):
    """Engine-selected Codex store (mirrors build_metadata_store).

    SQLite for self-host. Postgres parity is required before hosted Codex launch
    (so Codex history is durable across redeploy/scale, like the native
    checkpointer now is) — until then, enabling Codex under a Postgres engine
    fails loudly rather than silently losing history on a local disk.
    """
    from src.platform_engines.settings import get_settings

    settings = get_settings()
    if getattr(settings, "persistence_engine", "sqlite") == "postgres" and getattr(settings, "database_url", ""):
        raise NotImplementedError(
            "Postgres Codex transcript store is not implemented yet — required "
            "before hosted Codex launch (see plans/codex-engine-reference.md §7). "
            "Refusing to run Codex on ephemeral SQLite in a Postgres deployment."
        )
    return SqliteCodexStore(db_path)
