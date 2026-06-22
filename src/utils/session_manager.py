import datetime
import os
import shutil

from src.platform_engines.metadata_store import (
    DuplicateProject,
    SqliteMetadataStore,
    build_metadata_store,
)


class SessionManager:
    """Owns the session/project *filesystem* layout; delegates all relational
    metadata to a swappable :class:`MetadataStore` (SQLite for self-host, Cloud
    SQL/Postgres for horizontal scale). The public interface is unchanged.
    """

    def __init__(self, base_dir="workspace", db_path="state.db", metadata_store=None):
        self.base_dir = os.path.abspath(base_dir)
        self.db_path = os.path.abspath(db_path)

        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)

        # Default to the config-selected store (SQLite unless hosted+Postgres),
        # but allow explicit injection for tests / embedding.
        self._store = metadata_store or build_metadata_store(self.db_path)
        self._store.init_schema()

    # -------------------------------------------------------------------------
    # Project methods
    # -------------------------------------------------------------------------

    def create_project(self, name: str, user_id: str | None = None) -> dict:
        """Create a new project. Returns the project dict."""
        slug = self._slugify(name)
        now = datetime.datetime.now()
        try:
            self._store.create_project(slug, name, now, user_id=user_id)
        except DuplicateProject:
            raise ValueError(f"Project '{slug}' already exists.")
        return {"id": slug, "name": name, "created_at": str(now)}

    def get_all_projects(self, user_id: str | None = None) -> list[dict]:
        """Return all projects ordered by name (tenant-scoped when user_id given)."""
        return self._store.get_all_projects(user_id=user_id)

    def get_project(self, project_id: str, user_id: str | None = None) -> dict | None:
        return self._store.get_project(project_id, user_id=user_id)

    def delete_project(self, project_id: str, user_id: str | None = None):
        """Delete a project and unassign its sessions (sessions are NOT deleted)."""
        self._store.delete_project(project_id, user_id=user_id)

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

    def _upsert_session_metadata(self, session_id, session_name, model_name, project_id=None, user_id=None):
        now = datetime.datetime.now()
        self._store.upsert_session(session_id, user_id, session_name, model_name, project_id, now)

    def get_all_sessions(self, user_id: str | None = None):
        """Returns session IDs sorted by updated_at/created_at (newest first).

        When ``user_id`` is given, only that tenant's sessions are returned.
        """
        if not os.path.exists(self.base_dir):
            return []
        rows = self._store.get_all_session_rows(user_id=user_id)
        result = [r for r in rows if os.path.isdir(os.path.join(self.base_dir, r["session_id"]))]
        result.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
        return [r["session_id"] for r in result]

    def create_session(self, tag, model_name="gemini-3-flash-preview", project_id=None, user_id=None):
        """Creates a new session directory owned by ``user_id`` (the tenant).
        If project_id given, the filesystem path is project_id/tag (maintains
        backward-compat with the slash-convention). project_id is also stored
        as metadata so the project is first-class.
        """
        if project_id:
            # Ensure the project exists in DB (within the tenant's scope).
            if not self.get_project(project_id, user_id=user_id):
                raise ValueError(f"Project '{project_id}' not found.")
            session_id = self._normalize_tag(f"{project_id}/{tag}")
        else:
            session_id = self._normalize_tag(tag)

        path = self._session_path(session_id)

        if os.path.exists(path):
            raise FileExistsError(f"Session '{session_id}' already exists.")

        os.makedirs(path)
        self._upsert_session_metadata(session_id, tag, model_name, project_id, user_id=user_id)
        return session_id

    def ensure_session(self, tag, model_name="gemini-3-flash-preview", user_id=None):
        """Ensure a session has both a workspace directory and metadata row."""
        session_id = self._normalize_tag(tag)
        path = self._session_path(session_id)
        os.makedirs(path, exist_ok=True)
        self._upsert_session_metadata(session_id, tag, model_name, user_id=user_id)
        return session_id

    def get_session_metadata(self, session_id, user_id=None):
        """Retrieves metadata for a session (tenant-scoped when user_id given).

        Returns None if the session does not exist OR is not owned by user_id —
        the load-bearing check for cross-tenant isolation.
        """
        return self._store.get_session(session_id, user_id=user_id)

    def owns_session(self, session_id, user_id) -> bool:
        """True iff ``session_id`` exists and is owned by ``user_id``.

        With ``user_id=None`` (self-host) this is true for any existing session.
        """
        return self._store.get_session(session_id, user_id=user_id) is not None

    def move_session_to_project(self, session_id: str, project_id: str | None, user_id=None):
        """Reassign a session to a different project (or no project).
        This is a metadata-only operation — the workspace directory is NOT moved.
        """
        if project_id is not None and not self.get_project(project_id, user_id=user_id):
            raise ValueError(f"Project '{project_id}' not found.")
        self._store.move_session(session_id, project_id, user_id=user_id)

    def update_session_stats(self, session_id, input_t, output_t, cached_t, cost, user_id=None):
        """Updates token stats and bumps updated_at for a session."""
        self._store.update_stats(
            session_id, input_t, output_t, cached_t,
            input_t + output_t + cached_t, cost, datetime.datetime.now(), user_id=user_id,
        )

    def delete_session(self, session_id, user_id=None):
        """Deletes a session directory and its metadata (tenant-scoped)."""
        # Guard the filesystem delete behind the ownership check so a tenant
        # cannot rmtree another tenant's workspace by guessing the id.
        if user_id is not None and not self.owns_session(session_id, user_id):
            raise PermissionError(f"Session '{session_id}' not found for this user.")
        session_path = os.path.join(self.base_dir, session_id)
        if os.path.exists(session_path):
            shutil.rmtree(session_path)
        self._store.delete_session(session_id, user_id=user_id)

    def clear_all_sessions(self):
        """Deletes all workspace folders and the database."""
        if os.path.exists(self.base_dir):
            for item in os.listdir(self.base_dir):
                item_path = os.path.join(self.base_dir, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)

        drop = getattr(self._store, "drop_all", None)
        if callable(drop):
            drop()

    def get_workspace_path(self, session_id):
        return os.path.join(self.base_dir, session_id)
