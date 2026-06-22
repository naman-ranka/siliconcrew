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
import tarfile
import uuid
from typing import Callable, List, Optional, Protocol, Tuple


# ---------------------------------------------------------------------------
# Object store seam — a tiny tar-blob interface, not a filesystem.
# ---------------------------------------------------------------------------


class ObjectStore(Protocol):
    """Store/retrieve a directory tree as a single tar blob under a key."""

    def exists(self, key: str) -> bool: ...
    def put_tree(self, key: str, local_dir: str) -> None: ...
    def get_tree(self, key: str, local_dir: str, subdirs: Optional[List[str]] = None) -> None: ...


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

    def exists(self, key: str) -> bool:
        return key in self._blobs

    def put_tree(self, key: str, local_dir: str) -> None:
        self._blobs[key] = _tar_dir_to_bytes(local_dir)

    def get_tree(self, key: str, local_dir: str, subdirs: Optional[List[str]] = None) -> None:
        if key not in self._blobs:
            os.makedirs(local_dir, exist_ok=True)
            return
        _untar_bytes_to_dir(self._blobs[key], local_dir, subdirs)


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

    def exists(self, key: str) -> bool:
        return self._blob(key).exists()

    def put_tree(self, key: str, local_dir: str) -> None:
        self._blob(key).upload_from_string(
            _tar_dir_to_bytes(local_dir), content_type="application/gzip"
        )

    def get_tree(self, key: str, local_dir: str, subdirs: Optional[List[str]] = None) -> None:
        blob = self._blob(key)
        if not blob.exists():
            os.makedirs(local_dir, exist_ok=True)
            return
        _untar_bytes_to_dir(blob.download_as_bytes(), local_dir, subdirs)


# ---------------------------------------------------------------------------
# Cloud workspace provider — stage in / hand POSIX path / sync back.
# ---------------------------------------------------------------------------


class CloudWorkspaceProvider:
    """Materialize a session workspace from object storage onto local scratch.

    ``workspace_for`` downloads the session tarball (if any) into a per-session
    scratch directory and returns that POSIX path — exactly what the tools expect.
    ``sync`` persists local changes back. The request lifecycle calls
    ``workspace_for`` on entry and ``sync`` on exit (see ``api.py`` integration).
    """

    def __init__(self, store: ObjectStore, scratch_dir: str, prefix: str = "workspaces"):
        self._store = store
        self._scratch_dir = scratch_dir
        self._prefix = prefix

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}/{session_id}"

    def _scratch(self, session_id: str) -> str:
        return os.path.join(self._scratch_dir, session_id)

    def workspace_for(self, session_id: str) -> str:
        scratch = self._scratch(session_id)
        os.makedirs(scratch, exist_ok=True)
        key = self._key(session_id)
        if self._store.exists(key):
            self._store.get_tree(key, scratch)
        return scratch

    def sync(self, session_id: str) -> None:
        """Persist the local scratch workspace back to object storage."""
        self._store.put_tree(self._key(session_id), self._scratch(session_id))


# ---------------------------------------------------------------------------
# Run stager — used by CloudJobOrfsRunner to move a run dir to/from storage.
# ---------------------------------------------------------------------------


def build_run_stager(settings) -> Tuple[Callable[[str], str], Callable[[str, str], None]]:
    """Return ``(stage_in, stage_out)`` for the cloud ORFS runner.

    ``stage_in`` tars a self-contained run dir to a unique object key and returns
    it as the handle the Cloud Run Job pulls. ``stage_out`` fetches the result
    subdirs the Job uploaded back under the same key into the local run dir, so
    the unchanged downstream parsers see the normal on-disk layout.
    """
    store = GcsObjectStore(bucket=settings.workspace_bucket, prefix="orfs-runs")
    return make_run_stager(store)


def make_run_stager(
    store: ObjectStore,
) -> Tuple[Callable[[str], str], Callable[[str, str], None]]:
    """Stager bound to an arbitrary object store (injectable for tests)."""

    def stage_in(run_dir: str) -> str:
        handle = f"{os.path.basename(run_dir.rstrip('/'))}-{uuid.uuid4().hex[:10]}"
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
