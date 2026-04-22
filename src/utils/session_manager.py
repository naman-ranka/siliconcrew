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
        """Creates tables if they don't exist and migrates missing columns."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Projects table (first-class entity)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Sessions table
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

            # Migrate: add missing columns
            existing = {row[1] for row in cursor.execute("PRAGMA table_info(session_metadata)")}
            if "session_name" not in existing:
                cursor.execute("ALTER TABLE session_metadata ADD COLUMN session_name TEXT")
            if "updated_at" not in existing:
                cursor.execute("ALTER TABLE session_metadata ADD COLUMN updated_at TIMESTAMP")
            if "project_id" not in existing:
                cursor.execute("ALTER TABLE session_metadata ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL")
                # Auto-migrate existing grouped sessions: "project/session" → project_id = "project"
                self._migrate_existing_groups(cursor)

            conn.commit()

    def _migrate_existing_groups(self, cursor):
        """Promote existing project/session naming convention to project_id FK."""
        rows = cursor.execute("SELECT session_id FROM session_metadata").fetchall()
        for (session_id,) in rows:
            if "/" in session_id:
                project_slug = session_id.split("/")[0]
                # Ensure project row exists
                cursor.execute(
                    "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
                    (project_slug, project_slug),
                )
                cursor.execute(
                    "UPDATE session_metadata SET project_id = ? WHERE session_id = ?",
                    (project_slug, session_id),
                )

    # -------------------------------------------------------------------------
    # Project methods
    # -------------------------------------------------------------------------

    def create_project(self, name: str) -> dict:
        """Create a new project. Returns the project dict."""
        slug = self._slugify(name)
        now = datetime.datetime.now()
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                    (slug, name, now),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Project '{slug}' already exists.")
        return {"id": slug, "name": name, "created_at": str(now)}

    def get_all_projects(self) -> list[dict]:
        """Return all projects ordered by name."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM projects ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def delete_project(self, project_id: str):
        """Delete a project and unassign its sessions (sessions are NOT deleted)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE session_metadata SET project_id = NULL WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()

    # -------------------------------------------------------------------------
    # Session methods
    # -------------------------------------------------------------------------

    def _slugify(self, name: str) -> str:
        safe = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
        return safe.strip("-_") or "project"

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

    def _upsert_session_metadata(self, session_id, session_name, model_name, project_id=None):
        now = datetime.datetime.now()
        with sqlite3.connect(self.db_path) as conn:
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

    def get_all_sessions(self):
        """Returns session IDs sorted by updated_at/created_at (newest first)."""
        if not os.path.exists(self.base_dir):
            return []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM session_metadata").fetchall()
        result = [dict(r) for r in rows if os.path.isdir(os.path.join(self.base_dir, r["session_id"]))]
        result.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
        return [r["session_id"] for r in result]

    def create_session(self, tag, model_name="gemini-3-flash-preview", project_id=None):
        """Creates a new session directory.
        If project_id given, the filesystem path is project_id/tag (maintains
        backward-compat with the slash-convention). project_id is also stored
        as metadata so the project is first-class.
        """
        if project_id:
            # Ensure the project exists in DB
            if not self.get_project(project_id):
                raise ValueError(f"Project '{project_id}' not found.")
            session_id = self._normalize_tag(f"{project_id}/{tag}")
        else:
            session_id = self._normalize_tag(tag)

        path = self._session_path(session_id)

        if os.path.exists(path):
            raise FileExistsError(f"Session '{session_id}' already exists.")

        os.makedirs(path)
        self._upsert_session_metadata(session_id, tag, model_name, project_id)
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

    def move_session_to_project(self, session_id: str, project_id: str | None):
        """Reassign a session to a different project (or no project).
        This is a metadata-only operation — the workspace directory is NOT moved.
        """
        if project_id is not None and not self.get_project(project_id):
            raise ValueError(f"Project '{project_id}' not found.")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE session_metadata SET project_id = ? WHERE session_id = ?",
                (project_id, session_id),
            )
            conn.commit()

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
