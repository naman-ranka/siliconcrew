"""WorkspaceProvider cloud impl — object storage staged to local scratch.

The EDA flow expects a POSIX filesystem (ORFS, iverilog, yosys all assume real
files). So we do **not** pretend object storage is a filesystem to the tools.
Instead the cloud provider *stages*: on acquire it downloads the session's
tarball from object storage into a local scratch directory and hands the tools a
real POSIX path; on sync it tars the scratch dir back up to object storage. The
Phase 0 ``WorkspaceProvider`` interface (``workspace_for``) is unchanged, so the
tool layer never knows which backend is active.

``LocalWorkspaceProvider`` (Phase 0) stays the default for self-host.
"""
from __future__ import annotations

import io
import os
import shutil
import tarfile
import threading
import uuid
from typing import Callable, List, Optional, Protocol, Tuple


# ---------------------------------------------------------------------------
# Object store seam — a tiny tar-blob interface, not a filesystem.
# ---------------------------------------------------------------------------


class ObjectStore(Protocol):
    """Store/retrieve a directory tree as a single tar blob under a key.

    ``exists`` is the EXPLICIT presence check (``get_tree`` deliberately keeps
    its "absent blob → empty dir" behavior, so callers that must distinguish
    absence — e.g. the reconciler adopting cloud outputs — use ``exists``).
    ``put_file`` stores one small raw object (no tarring) under a key — the
    Item-4 durable run_meta push path.
    """

    def exists(self, key: str) -> bool: ...
    def put_tree(self, key: str, local_dir: str) -> None: ...
    def put_file(self, key: str, local_path: str) -> None: ...
    def get_tree(self, key: str, local_dir: str, subdirs: Optional[List[str]] = None) -> None: ...
    # A version token for the stored object (GCS generation), or None if absent.
    # Used by the workspace provider to skip re-downloading an unchanged object
    # (F3). Optional — a store that doesn't implement it disables the cache.
    def generation(self, key: str) -> Optional[str]: ...


def _store_generation(store, key: str) -> Optional[str]:
    """The object's version token, or None (absent, or the store lacks support)."""
    fn = getattr(store, "generation", None)
    if fn is None:
        return None
    try:
        return fn(key)
    except Exception:
        return None


def _tar_dir_to_bytes(local_dir: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if os.path.isdir(local_dir):
            for name in sorted(os.listdir(local_dir)):
                tar.add(os.path.join(local_dir, name), arcname=name)
    return buf.getvalue()


def _untar_bytes_to_dir(data: bytes, local_dir: str, subdirs: Optional[List[str]]) -> None:
    os.makedirs(local_dir, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = tar.getmembers()
        if subdirs:
            wanted = tuple(s.rstrip("/") for s in subdirs)
            members = [
                m for m in members
                if any(m.name == w or m.name.startswith(w + "/") for w in wanted)
            ]
        _safe_extract(tar, local_dir, members)


def _safe_extract(tar: tarfile.TarFile, dest: str, members) -> None:
    """Extract guarding against path traversal (CVE-2007-4559 class)."""
    dest_real = os.path.realpath(dest)
    for m in members:
        target = os.path.realpath(os.path.join(dest, m.name))
        if not (target == dest_real or target.startswith(dest_real + os.sep)):
            raise ValueError(f"Refusing path-traversal tar member: {m.name}")
    tar.extractall(dest, members=members)


class InMemoryObjectStore:
    """In-process tar-blob store for tests and local parity checks."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}
        self._files: dict[str, bytes] = {}
        self._gen: dict[str, int] = {}

    def exists(self, key: str) -> bool:
        return key in self._blobs or key in self._files

    def put_tree(self, key: str, local_dir: str) -> None:
        self._blobs[key] = _tar_dir_to_bytes(local_dir)
        self._gen[key] = self._gen.get(key, 0) + 1  # bump the version on each write

    def put_file(self, key: str, local_path: str) -> None:
        with open(local_path, "rb") as f:
            self._files[key] = f.read()

    def get_tree(self, key: str, local_dir: str, subdirs: Optional[List[str]] = None) -> None:
        if key not in self._blobs:
            os.makedirs(local_dir, exist_ok=True)
            return
        _untar_bytes_to_dir(self._blobs[key], local_dir, subdirs)

    def generation(self, key: str) -> Optional[str]:
        g = self._gen.get(key)
        return str(g) if g is not None else None


class GcsObjectStore:
    """Google Cloud Storage tar-blob store (lazy SDK import).

    One ``.tar.gz`` object per key — the simplest correct staging unit. Production
    wires this to the session/run bucket created by Terraform.
    """

    def __init__(self, bucket: str, prefix: str = "", client=None):
        self._bucket_name = bucket
        self._prefix = prefix.strip("/")
        self._client = client

    def _bucket(self):
        if self._client is None:
            from google.cloud import storage  # lazy: only needed in cloud mode

            self._client = storage.Client()
        return self._client.bucket(self._bucket_name)

    def _blob(self, key: str):
        path = f"{self._prefix}/{key}.tar.gz" if self._prefix else f"{key}.tar.gz"
        return self._bucket().blob(path)

    def _raw_blob(self, key: str):
        """Blob at the key itself (no ``.tar.gz`` suffix) — put_file objects."""
        path = f"{self._prefix}/{key}" if self._prefix else key
        return self._bucket().blob(path)

    def exists(self, key: str) -> bool:
        # A key can name a tar blob (put_tree) or a raw object (put_file);
        # check the tar spelling first (the common stage-in/out case).
        return self._blob(key).exists() or self._raw_blob(key).exists()

    def put_tree(self, key: str, local_dir: str) -> None:
        self._blob(key).upload_from_string(
            _tar_dir_to_bytes(local_dir), content_type="application/gzip"
        )

    def put_file(self, key: str, local_path: str) -> None:
        self._raw_blob(key).upload_from_filename(local_path)

    def get_tree(self, key: str, local_dir: str, subdirs: Optional[List[str]] = None) -> None:
        blob = self._blob(key)
        if not blob.exists():
            os.makedirs(local_dir, exist_ok=True)
            return
        _untar_bytes_to_dir(blob.download_as_bytes(), local_dir, subdirs)

    def generation(self, key: str) -> Optional[str]:
        path = f"{self._prefix}/{key}.tar.gz" if self._prefix else f"{key}.tar.gz"
        # get_blob does a metadata GET (cheap) and returns None if the object is
        # absent; .generation is the monotonic version token GCS assigns per write.
        blob = self._bucket().get_blob(path)
        return str(blob.generation) if blob is not None else None


# ---------------------------------------------------------------------------
# Cloud workspace provider — stage in / hand POSIX path / sync back.
# ---------------------------------------------------------------------------


class CloudWorkspaceProvider:
    """Materialize a session workspace from object storage onto local scratch.

    ``workspace_for`` downloads the session tarball (if any) into a per-session
    scratch directory and returns that POSIX path — exactly what the tools expect.
    ``sync`` persists local changes back. The request lifecycle calls
    ``workspace_for`` on entry and ``sync`` on exit (see ``api.py`` integration).

    Concurrency (F2 + F3) — mandatory once hydration runs off the event loop
    (F6), because every session open now hydrates the SAME session twice **in
    parallel**: the WS-connect (agent) path and the F4 snapshot read. Without
    care both would ``tar.extractall()`` into the live scratch dir at once → torn
    files / half-extracted trees / intermittent "not found" right after opening.

      * **Per-session lock** serializes ``workspace_for``/``sync`` for a session
        (different sessions never block each other).
      * **Temp-dir + atomic swap**: a hydration untars into a private temp dir and
        is swapped into place only when complete — an in-progress extract is
        never visible to a reader.
      * **Generation-skip (F3)**: if the materialized scratch already reflects the
        object's current generation, skip the download+untar entirely. So the
        second of the two open-time hydrations is a cache hit (no second untar),
        the F7 prewarm's scratch is actually reused, and the swap window never
        even opens on the common unchanged-generation open.
    """

    def __init__(self, store: ObjectStore, scratch_dir: str, prefix: str = "workspaces"):
        self._store = store
        self._scratch_dir = scratch_dir
        self._prefix = prefix
        self._locks: dict[str, "threading.Lock"] = {}
        self._locks_guard = threading.Lock()

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}/{session_id}"

    def _scratch(self, session_id: str) -> str:
        return os.path.join(self._scratch_dir, session_id)

    def _lock_for(self, session_id: str) -> "threading.Lock":
        with self._locks_guard:
            lk = self._locks.get(session_id)
            if lk is None:
                lk = threading.Lock()
                self._locks[session_id] = lk
            return lk

    def _marker_path(self, session_id: str) -> str:
        # A SIBLING of the scratch dir, never inside it — so it is neither tarred
        # into the upload (sync) nor shown in the workspace file listing.
        return self._scratch(session_id) + ".sc_generation"

    def _read_marker(self, session_id: str) -> Optional[str]:
        try:
            with open(self._marker_path(session_id), "r", encoding="utf-8") as f:
                return f.read().strip() or None
        except OSError:
            return None

    def _write_marker(self, session_id: str, generation: str) -> None:
        try:
            with open(self._marker_path(session_id), "w", encoding="utf-8") as f:
                f.write(generation)
        except OSError:
            pass  # marker is a best-effort cache; a miss only costs a re-download

    def workspace_for(self, session_id: str) -> str:
        scratch = self._scratch(session_id)
        key = self._key(session_id)
        with self._lock_for(session_id):
            generation = _store_generation(self._store, key)

            if generation is None:
                # No stored object yet (new session) — just ensure the dir exists.
                os.makedirs(scratch, exist_ok=True)
                return scratch

            # F3: the scratch already reflects the current object → reuse it.
            if os.path.isdir(scratch) and self._read_marker(session_id) == generation:
                return scratch

            # F2: hydrate into a private temp dir, then swap it in atomically so a
            # concurrent reader never sees a half-extracted tree. The marker is
            # written only after a successful swap (a crash mid-hydrate leaves a
            # stale marker → a safe re-download, never a torn tree).
            tmp = f"{scratch}.tmp.{uuid.uuid4().hex}"
            try:
                self._store.get_tree(key, tmp)
                self._atomic_swap(tmp, scratch)
                self._write_marker(session_id, generation)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            return scratch

    def _atomic_swap(self, tmp: str, scratch: str) -> None:
        """Replace ``scratch`` with the freshly-hydrated ``tmp`` tree.

        Directory ``os.replace`` can't overwrite a non-empty dir, so move the old
        tree aside first. The gap between the two renames is two syscalls (vs the
        multi-second extract, which happened entirely in ``tmp``), and with F3 the
        common unchanged-generation open takes the cache-hit path above and never
        reaches this swap at all.
        """
        os.makedirs(os.path.dirname(scratch), exist_ok=True)
        old = f"{scratch}.old.{uuid.uuid4().hex}"
        moved_old = False
        if os.path.exists(scratch):
            os.replace(scratch, old)
            moved_old = True
        try:
            os.replace(tmp, scratch)
        except OSError:
            if moved_old and not os.path.exists(scratch):
                os.replace(old, scratch)  # restore on failure
            raise
        finally:
            if moved_old:
                shutil.rmtree(old, ignore_errors=True)

    def sync(self, session_id: str) -> None:
        """Persist the local scratch workspace back to object storage.

        Under the per-session lock so an upload never races a hydration swap, and
        the generation marker is refreshed to the just-written object so a
        subsequent read on this instance doesn't re-download our own write (F3).
        """
        key = self._key(session_id)
        scratch = self._scratch(session_id)
        with self._lock_for(session_id):
            self._store.put_tree(key, scratch)
            new_gen = _store_generation(self._store, key)
            if new_gen is not None and os.path.isdir(scratch):
                self._write_marker(session_id, new_gen)


# ---------------------------------------------------------------------------
# Run stager — used by CloudJobOrfsRunner to move a run dir to/from storage.
# ---------------------------------------------------------------------------


def build_run_store(settings) -> "GcsObjectStore":
    """The object store holding staged ORFS runs (``orfs-runs/…`` in the bucket).

    Shared by the cloud run stager AND the synthesis manager's durable
    run_meta push / adoption path, so both address the same key space: a run
    handle ``<session_id>/<run_id>`` lands at
    ``orfs-runs/<session_id>/<run_id>`` in the workspace bucket.
    """
    return GcsObjectStore(bucket=settings.workspace_bucket, prefix="orfs-runs")


def build_run_stager(settings) -> Tuple[Callable[[str, str], str], Callable[[str, str], None]]:
    """Return ``(stage_in, stage_out)`` for the cloud ORFS runner.

    ``stage_in`` tars a self-contained run dir to an object key and returns
    it as the handle the Cloud Run Job pulls. ``stage_out`` fetches the result
    subdirs the Job uploaded back under the same key into the local run dir, so
    the unchanged downstream parsers see the normal on-disk layout.
    """
    return make_run_stager(build_run_store(settings))


def make_run_stager(
    store: ObjectStore,
) -> Tuple[Callable[[str, str], str], Callable[[str, str], None]]:
    """Stager bound to an arbitrary object store (injectable for tests)."""

    def stage_in(run_dir: str, handle: str = "") -> str:
        # Wave 9 (Item 4): the caller supplies the deterministic handle
        # (<session_id>/<run_id>, computed by the synthesis manager) so any
        # instance can reconstruct the prefix from the run alone. An empty
        # handle keeps the legacy unique-key mint as a fallback.
        handle = handle or f"{os.path.basename(run_dir.rstrip('/'))}-{uuid.uuid4().hex[:10]}"
        store.put_tree(handle, run_dir)
        return handle

    def stage_out(run_dir: str, handle: str) -> None:
        # The Job uploads its produced artifacts back under "<handle>/out"; pull
        # them into the local run dir. (The Job entrypoint lives in deploy/.)
        store.get_tree(f"{handle}/out", run_dir)

    return stage_in, stage_out


# ---------------------------------------------------------------------------
# Factory — chosen once by settings.
# ---------------------------------------------------------------------------

_PROVIDER = None


def get_workspace_provider():
    """Return the process-wide workspace provider selected by platform settings."""
    global _PROVIDER
    if _PROVIDER is not None:
        return _PROVIDER

    from src.platform_engines.settings import get_settings
    from src.utils.session_context import LocalWorkspaceProvider

    settings = get_settings()
    if settings.is_cloud_workspace:
        store = GcsObjectStore(bucket=settings.workspace_bucket, prefix="workspaces")
        _PROVIDER = CloudWorkspaceProvider(store, settings.workspace_scratch_dir)
    else:
        base = os.environ.get("RTL_WORKSPACE") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workspace"
        )
        _PROVIDER = LocalWorkspaceProvider(base)
    return _PROVIDER


def set_workspace_provider(provider) -> None:
    """Override the process-wide workspace provider (tests / explicit wiring)."""
    global _PROVIDER
    _PROVIDER = provider
