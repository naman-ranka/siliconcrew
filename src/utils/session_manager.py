import datetime
import os
import shutil
import sqlite3


class SessionManager:
    def __init__(self, base_dir="workspace", db_path="state.db"):
        self.base_dir = os.path.abspath(base_dir)
        self.db_path = os.path.abspath(db_path)

        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)

        self._init_metadata_db()

    def _init_metadata_db(self):
        """Creates the metadata table if it doesn't exist, and migrates missing columns."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
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
            existing = {row[1] for row in cursor.execute("PRAGMA table_info(session_metadata)")}
            if "session_name" not in existing:
                cursor.execute("ALTER TABLE session_metadata ADD COLUMN session_name TEXT")
            if "updated_at" not in existing:
                cursor.execute("ALTER TABLE session_metadata ADD COLUMN updated_at TIMESTAMP")
            conn.commit()

    def _normalize_tag(self, tag):
        if not tag:
            raise ValueError("Tag is required.")

        safe_tag = "".join(c for c in tag if c.isalnum() or c in ("-", "_", "/"))
        while "//" in safe_tag:
            safe_tag = safe_tag.replace("//", "/")
        safe_tag = safe_tag.strip("/")
        if not safe_tag or ".." in safe_tag:
            raise ValueError("Invalid tag format.")
        return safe_tag

    def _session_path(self, session_id):
        path = os.path.join(self.base_dir, session_id)
        if not os.path.realpath(path).startswith(os.path.realpath(self.base_dir)):
            raise ValueError("Invalid tag format.")
        return path

    def _upsert_session_metadata(self, session_id, session_name, model_name):
        now = datetime.datetime.now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO session_metadata (session_id, session_name, model_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    session_name = COALESCE(session_metadata.session_name, excluded.session_name),
                    model_name = COALESCE(session_metadata.model_name, excluded.model_name),
                    updated_at = excluded.updated_at
                """,
                (session_id, session_name, model_name, now, now),
            )
            conn.commit()

    def get_all_sessions(self):
        """Returns session IDs sorted by updated_at/created_at (newest first).
        Supports both flat (my_counter) and nested (exp1/counter_4bit) sessions."""
        if not os.path.exists(self.base_dir):
            return []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM session_metadata").fetchall()
        result = [dict(r) for r in rows if os.path.isdir(os.path.join(self.base_dir, r["session_id"]))]
        result.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
        return [r["session_id"] for r in result]

    def create_session(self, tag, model_name="gemini-3-flash-preview"):
        """Creates a new session directory using the tag.
        Supports nested tags like 'exp1/counter_4bit'.
        Raises FileExistsError if it exists."""
        session_id = self._normalize_tag(tag)
        path = self._session_path(session_id)

        if os.path.exists(path):
            raise FileExistsError(f"Session '{session_id}' already exists.")

        os.makedirs(path)
        self._upsert_session_metadata(session_id, tag, model_name)
        return session_id

    def ensure_session(self, tag, model_name="gemini-3-flash-preview"):
        """Ensure a session has both a workspace directory and metadata row."""
        session_id = self._normalize_tag(tag)
        path = self._session_path(session_id)
        os.makedirs(path, exist_ok=True)
        self._upsert_session_metadata(session_id, tag, model_name)
        return session_id

    def get_session_metadata(self, session_id):
        """Retrieves metadata for a session. Returns dict or None."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM session_metadata WHERE session_id = ?", (session_id,)).fetchone()
        if row:
            return dict(row)
        return None

    def update_session_stats(self, session_id, input_t, output_t, cached_t, cost):
        """Updates token stats and bumps updated_at for a session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE session_metadata
                SET input_tokens = ?, output_tokens = ?, cached_tokens = ?,
                    total_tokens = ?, total_cost = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (input_t, output_t, cached_t, input_t + output_t + cached_t, cost, datetime.datetime.now(), session_id),
            )
            conn.commit()

    def delete_session(self, session_id):
        """Deletes a session directory and its metadata."""
        session_path = os.path.join(self.base_dir, session_id)
        if os.path.exists(session_path):
            shutil.rmtree(session_path)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM session_metadata WHERE session_id = ?", (session_id,))
            for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (session_id,))
                except sqlite3.OperationalError:
                    pass
            conn.commit()

    def clear_all_sessions(self):
        """Deletes all workspace folders and the database."""
        if os.path.exists(self.base_dir):
            for item in os.listdir(self.base_dir):
                item_path = os.path.join(self.base_dir, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)

        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                print("Could not delete database file. It might be in use.")

    def get_workspace_path(self, session_id):
        return os.path.join(self.base_dir, session_id)
