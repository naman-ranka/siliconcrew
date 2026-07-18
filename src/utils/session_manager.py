import datetime
import os
import shutil

from src.agents import runtime_registry
from src.platform_engines.metadata_store import (
    DuplicateProject,
    DuplicateSession,
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
        # 4C (hosted-latency plan): a Codex-bound MCP subprocess spawn must not
        # re-run the schema DDL on a fresh Cloud SQL connection every turn —
        # the parent app provisioned the schema at boot and marks the
        # subprocess env accordingly (codex_engine._config_overrides). Everyone
        # else (self-host, standalone MCP, the app itself) provisions as before.
        if os.environ.get("SILICONCREW_SCHEMA_READY", "").strip().lower() not in ("1", "true", "yes"):
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

    def rename_project(self, project_id: str, name: str, user_id: str | None = None):
        """Rename a project's display name. The id/slug is immutable — sessions
        keep their ``project_id`` (and any ``<slug>/…`` paths) unchanged.
        Tenant-scoped: a non-owner's rename is a no-op."""
        self._store.rename_project(project_id, name, user_id=user_id)

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
        rows = self._store.get_all_session_rows(user_id=user_id)
        if self._uses_ephemeral_workspace_listing():
            result = rows
        else:
            if not os.path.exists(self.base_dir):
                return []
            result = [r for r in rows if os.path.isdir(os.path.join(self.base_dir, r["session_id"]))]
        result.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
        return [r["session_id"] for r in result]

    def _uses_ephemeral_workspace_listing(self) -> bool:
        """True when metadata, not local workspace dirs, is the durable list.

        Hosted Cloud Run uses Postgres plus object-storage-backed scratch paths.
        Local directories are per-instance and may disappear on cold starts, so
        filtering metadata rows through ``os.path.isdir`` makes valid hosted
        sessions vanish from the sidebar after refresh.
        """
        try:
            from src.platform_engines.settings import get_settings

            settings = get_settings()
            return (
                settings.hosted
                or settings.persistence_engine == "postgres"
                or settings.workspace_engine == "cloud"
            )
        except Exception:
            return not isinstance(self._store, SqliteMetadataStore)

    def create_session(self, tag, model_name=None, project_id=None, user_id=None):
        """Creates a new session directory owned by ``user_id`` (the tenant).
        If project_id given, the filesystem path is project_id/tag (maintains
        backward-compat with the slash-convention). project_id is also stored
        as metadata so the project is first-class.

        model_name=None -> the catalog default. Callers that omit the model
        (template forks, MCP create) must track the CURRENT default — a stale
        literal here shipped forks pinned to a deprecated needs-key model
        (live blind-test finding S1).
        """
        if model_name is None:
            from src.model_catalog import DEFAULT_MODEL

            model_name = DEFAULT_MODEL
        if project_id:
            # Ensure the project exists in DB (within the tenant's scope).
            if not self.get_project(project_id, user_id=user_id):
                raise ValueError(f"Project '{project_id}' not found.")
            session_id = self._normalize_tag(f"{project_id}/{tag}")
        else:
            session_id = self._normalize_tag(tag)

        path = self._session_path(session_id)

        # Fast, friendly pre-check against BOTH the local dir AND the shared
        # metadata store. On hosted, instance disk is ephemeral and per-instance,
        # so os.path.exists alone misses an id already owned on another instance;
        # the metadata store (Cloud SQL) is the authoritative shared namespace.
        if os.path.exists(path) or self._store.get_session(session_id, user_id=None):
            raise FileExistsError(f"Session '{session_id}' already exists.")

        os.makedirs(path)
        # Atomic insert (NOT upsert): the DB primary key is the cross-instance
        # arbiter for a NEW session. The pre-check above is only a fast path — it
        # is not atomic, so two forks of the same template on different instances
        # can both pass it. Exactly one INSERT wins; the loser gets
        # DuplicateSession and retries a fresh id (via _allocate_fork_session),
        # never adopting the winner's row nor — critically — clobbering the
        # winner's object-storage workspace on a later delete_workspace/sync.
        now = datetime.datetime.now()
        try:
            self._store.insert_session(session_id, user_id, tag, model_name, project_id, now)
        except DuplicateSession:
            shutil.rmtree(path, ignore_errors=True)  # undo the dir we just made
            raise FileExistsError(f"Session '{session_id}' already exists.")
        # Seed the default chat at birth: listing threads is read-only (never
        # materializes), so every session must honestly own its "Chat 1" row
        # from creation.
        self.ensure_default_thread(session_id, user_id=user_id)
        return session_id

    def ensure_session(self, tag, model_name=None, user_id=None):
        """Ensure a session has both a workspace directory and metadata row."""
        if model_name is None:
            from src.model_catalog import DEFAULT_MODEL

            model_name = DEFAULT_MODEL
        session_id = self._normalize_tag(tag)
        path = self._session_path(session_id)
        os.makedirs(path, exist_ok=True)
        self._upsert_session_metadata(session_id, tag, model_name, user_id=user_id)
        # Same seeding as create_session — MCP-materialized sessions must not
        # look chat-less to a read-only thread list. Seed with the session's
        # TRUE owner, never the caller: the upsert keeps a pre-existing
        # session's owner (COALESCE), and the thread row's owner is immutable
        # (INSERT OR IGNORE) — a caller merely NAMING someone else's id must
        # not permanently claim their default chat.
        row = self._store.get_session(session_id)  # unscoped: read the real owner
        owner = row.get("user_id") if row else user_id
        self.ensure_default_thread(session_id, user_id=owner)
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

    def rename_session(self, session_id: str, name: str, user_id=None):
        """Rename a session's DISPLAY name only.

        The session id and the workspace directory it names never change —
        renaming never moves files and never re-keys checkpoints or threads
        (they are all keyed by session_id). Tenant-scoped like
        move_session_to_project: a non-owner's rename is a no-op.
        """
        self._store.rename_session(session_id, name, user_id=user_id)

    def set_source_template(self, session_id, value, user_id=None):
        """Persist a fork's provenance JSON ({id,name,forked_at}) on the session
        row (owner-scoped). Thin passthrough — the durable store copy of the
        workspace ``.source_template.json`` so the "forked from" chip survives on
        hosted, where list endpoints never hydrate a workspace to read the file.
        """
        self._store.set_source_template(session_id, value, user_id=user_id)

    def update_session_stats(self, session_id, input_t, output_t, cached_t, cost, user_id=None):
        """Updates token stats and bumps updated_at for a session."""
        self._store.update_stats(
            session_id, input_t, output_t, cached_t,
            input_t + output_t + cached_t, cost, datetime.datetime.now(), user_id=user_id,
        )

    def delete_session(self, session_id, user_id=None):
        """Deletes a session directory, its metadata, chats and checkpoints
        (tenant-scoped)."""
        # Guard the filesystem delete behind the ownership check so a tenant
        # cannot rmtree another tenant's workspace by guessing the id.
        if user_id is not None and not self.owns_session(session_id, user_id):
            raise PermissionError(f"Session '{session_id}' not found for this user.")
        session_path = os.path.join(self.base_dir, session_id)
        if os.path.exists(session_path):
            shutil.rmtree(session_path)
        # On cloud, the durable workspace lives in object storage, NOT the local
        # dir just removed. Purge it too so a deleted id leaves no adoptable
        # manifest for a later same-name fork to hydrate (the D7 GC gap made
        # concrete by name-derived fork ids). Lazy + best-effort + cloud-only:
        # self-host has no provider and skips this entirely.
        try:
            from src.platform_engines.settings import get_settings

            if get_settings().is_cloud_workspace:
                from src.platform_engines.workspace_provider import (
                    get_workspace_provider,
                )

                delete_ws = getattr(get_workspace_provider(), "delete_workspace", None)
                if callable(delete_ws):
                    delete_ws(session_id)
        except Exception:
            pass
        # The store returns the cascaded chat ids — conversation checkpoints
        # are keyed by thread_id, so the purge works from EXACTLY what was
        # deleted (no separate pre-read that could fail or go stale apart
        # from the delete itself).
        deleted_threads = self._store.delete_session(session_id, user_id=user_id) or []
        # Notify extension runtimes for every deleted thread (+ legacy default).
        for _tid in {session_id, *deleted_threads}:
            runtime_registry.notify_thread_deleted(_tid, user_id)
        # Purge the conversation checkpoints for the deleted threads (+ the
        # legacy session-id default thread). Wave 10: in Postgres mode
        # checkpoints live in the shared Cloud SQL DB, so the store purges them
        # there; the SQLite store already purges its own (same file) inside
        # delete_session. Best-effort — never blocks the delete.
        purge = getattr(self._store, "delete_thread_checkpoints", None)
        if callable(purge):
            try:
                purge({session_id, *deleted_threads})
            except Exception:
                pass
        elif not hasattr(self._store, "_CHECKPOINT_TABLES"):
            # Legacy fallback (metadata store with neither hook): local sqlite.
            self._purge_local_checkpoints({session_id, *deleted_threads})

    def _purge_local_checkpoints(self, thread_ids):
        """Best-effort delete of LangGraph checkpoint rows in the local state DB."""
        import sqlite3

        try:
            conn = sqlite3.connect(self.db_path)
        except Exception:
            return
        try:
            for table in ("checkpoints", "checkpoint_writes", "checkpoint_blobs"):
                try:
                    for tid in thread_ids:
                        conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))
                except sqlite3.OperationalError:
                    pass  # table appears only after LangGraph's first write
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

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

    # -------------------------------------------------------------------------
    # Chat thread methods (a chat = a LangGraph thread_id; many per workspace)
    #
    # THE ONE RULE: threads are conversation history only. They all share the
    # LIVE workspace bound from session_id; deleting a thread never touches
    # files/runs. Owner/tenant scoping mirrors the session methods.
    # -------------------------------------------------------------------------

    def _short_title(self, text: str, limit: int = 48) -> str:
        t = " ".join((text or "").split())
        return (t[: limit - 1] + "…") if len(t) > limit else t

    def ensure_default_thread(self, session_id, user_id=None) -> dict:
        """Back-compat: a session's first/default thread has id == session_id.

        Existing conversations were checkpointed under thread_id == session_id, so
        they map in unchanged as "Chat 1"; only new chats get fresh UUIDs.
        Idempotent — safe to call on every list/connect.
        """
        now = datetime.datetime.now()
        self._store.ensure_thread(session_id, session_id, user_id, "Chat 1", None, now)
        return self._store.get_thread(session_id, user_id=user_id)

    def resolve_ws_thread(self, thread_id, session_id, user_id=None) -> str | None:
        """Validate a client-supplied chat id for a WebSocket turn.

        The default id (== session_id) is always legal and lazily materialized
        ("Chat 1"; legacy sessions predate creation-time seeding). Any OTHER id
        must already exist AND belong to this session (owner-scoped) — the WS
        never materializes arbitrary client-supplied ids (a stale or crafted
        thread id must not create rows). Returns the id to chat under, or
        None when the id is unknown/foreign.
        """
        if not thread_id or thread_id == session_id:
            self.ensure_default_thread(session_id, user_id=user_id)
            return session_id
        row = self._store.get_thread(thread_id, user_id=user_id)
        if row and row.get("session_id") == session_id:
            return thread_id
        return None

    def _last_used_model(self, session_id, user_id=None) -> str | None:
        """The creator's last-used model: newest thread with a model, else the
        session's model. New chats inherit this."""
        for t in self._store.list_threads(session_id, user_id=user_id):  # newest first
            if t.get("model"):
                return t["model"]
        meta = self._store.get_session(session_id, user_id=user_id)
        return (meta or {}).get("model_name")

    def create_thread(self, session_id, user_id=None, title=None, model=None, runtime="langchain") -> dict:
        """Create a new chat thread (fresh UUID id) under a session.

        New threads inherit the creator's last-used model when one isn't given.
        ``runtime`` is the shell-level marker that selects the agent runtime
        (native 'langchain', or a registered extension like 'codex').
        """
        import uuid

        self.ensure_default_thread(session_id, user_id=user_id)  # so "Chat 1" exists
        if model is None:
            model = self._last_used_model(session_id, user_id=user_id)
        now = datetime.datetime.now()
        thread_id = uuid.uuid4().hex
        if not title:
            n = self._store.count_threads(session_id, user_id=user_id) + 1
            title = f"Chat {n}"
        self._store.create_thread(thread_id, session_id, user_id, title, model, now, runtime=runtime)
        return self._store.get_thread(thread_id, user_id=user_id)

    def list_threads(self, session_id, user_id=None) -> list[dict]:
        """READ-ONLY thread list — browsing (drawer, quick-switch, nav rail)
        must never mutate a session. The default "Chat 1" row is seeded at
        session creation; legacy sessions materialize theirs on the first WS
        message (resolve_ws_thread) or a deliberate default-thread PATCH."""
        return self._store.list_threads(session_id, user_id=user_id)

    def get_thread(self, thread_id, user_id=None) -> dict | None:
        return self._store.get_thread(thread_id, user_id=user_id)

    def count_threads(self, session_id, user_id=None) -> int:
        """Honest thread-row count for one session (no ensure, no hydration)."""
        return self._store.count_threads(session_id, user_id=user_id)

    def count_threads_by_session(self, user_id=None) -> dict[str, int]:
        """{session_id: thread-row count} in ONE grouped query, for session lists.

        Counts what's in the table honestly: sessions created after Wave 8 are
        seeded with "Chat 1" at birth (count 1); legacy sessions show 0 until
        their default thread materializes on first WS message. Never ensures
        threads and never touches/hydrates workspaces.
        """
        return self._store.count_threads_by_session(user_id=user_id)

    def rename_thread(self, thread_id, title, user_id=None):
        self._store.update_thread(thread_id, user_id=user_id, title=title)

    def set_thread_model(self, thread_id, model, user_id=None):
        self._store.update_thread(thread_id, user_id=user_id, model=model)

    def set_thread_runtime(self, thread_id, runtime, user_id=None):
        """Set the shell-level runtime marker that drives dispatch (which
        registered agent runtime owns this thread). See runtime_registry."""
        self._store.update_thread(thread_id, user_id=user_id, runtime=runtime)

    def touch_thread(self, thread_id, user_id=None, auto_title_from: str | None = None):
        """Bump last_active; auto-title an untitled/default thread on first message."""
        now = datetime.datetime.now()
        title = None
        if auto_title_from:
            existing = self._store.get_thread(thread_id, user_id=user_id)
            cur = (existing or {}).get("title") if existing else None
            if not cur or cur in ("Chat 1", "New chat"):
                title = self._short_title(auto_title_from)
        self._store.update_thread(thread_id, user_id=user_id, title=title, last_active=now)

    def delete_thread(self, thread_id, user_id=None):
        """Delete a conversation only — never the workspace files/runs."""
        self._store.delete_thread(thread_id, user_id=user_id)
        # Let extension runtimes (e.g. Codex) drop their own per-thread state.
        # No-op with zero extensions registered; the shell never names Codex.
        runtime_registry.notify_thread_deleted(thread_id, user_id)

    def thread_belongs_to_session(self, thread_id, session_id, user_id=None) -> bool:
        t = self._store.get_thread(thread_id, user_id=user_id)
        return bool(t and t.get("session_id") == session_id)
