"""WorkspaceProvider cloud impl — object storage staged to local scratch.

The EDA flow expects a POSIX filesystem (ORFS, iverilog, yosys all assume real
files). So we do **not** pretend object storage is a filesystem to the tools.
Instead the cloud provider *stages*: on acquire it materializes the session's
stored workspace into a local scratch directory and hands the tools a real
POSIX path; on sync it persists local changes back. The Phase 0
``WorkspaceProvider`` interface (``workspace_for``) is unchanged, so the tool
layer never knows which backend is active.

Persistence format (4A, hosted-latency plan): a workspace is stored as
content-addressed per-file blobs plus one small manifest object written LAST —
the atomic commit point. A sync therefore costs time proportional to *what
changed* (a one-file save uploads one blob + the manifest), not to the total
workspace size; deletes/renames propagate because a cold reader reconstructs
exactly the manifest's tree. The previous single-``.tar.gz``-per-session format
remains a read fallback: the first incremental sync converts a legacy
workspace and cleans the tar up. Blob GC for superseded content is deferred
with run retention/GC (orphaned blobs are unreferenced garbage, never
incorrect state).

``LocalWorkspaceProvider`` (Phase 0) stays the default for self-host.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat as stat_module
import tarfile
import threading
import time
import uuid
from contextlib import suppress
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
    Item-4 durable run_meta push path. ``get_file`` is its read-back (same raw
    key scheme, no ``.tar.gz`` spelling): False when the object is absent, so
    a reader can distinguish "no durable meta yet" from an empty pull.
    """

    def exists(self, key: str) -> bool: ...
    def put_tree(self, key: str, local_dir: str) -> None: ...
    def put_file(self, key: str, local_path: str) -> None: ...
    def get_file(self, key: str, local_path: str) -> bool: ...
    def get_tree(self, key: str, local_dir: str, subdirs: Optional[List[str]] = None) -> None: ...
    # A version token for the stored object (GCS generation), or None if absent.
    # Used by the workspace provider to skip re-downloading an unchanged object
    # (F3). Optional — a store that doesn't implement it disables the cache.
    def generation(self, key: str) -> Optional[str]: ...
    # Delete the tar blob at ``key`` (may raise if absent). Optional — used only
    # for the one-time legacy-tar cleanup after a workspace converts to the
    # incremental per-file format; the provider guards with getattr + suppress.
    def delete_tree(self, key: str) -> None: ...
    # Delete the raw object at ``key`` (put_file scheme, no ``.tar.gz`` — the
    # manifest / durable-meta namespace; may raise if absent). Optional — used
    # by fork rollback to drop a partially-committed workspace manifest; callers
    # guard with getattr + suppress.
    def delete_file(self, key: str) -> None: ...


def _store_generation(store, key: str) -> Optional[str]:
    """The object's version token, or None (absent, or the store lacks support)."""
    fn = getattr(store, "generation", None)
    if fn is None:
        return None
    try:
        return fn(key)
    except Exception:
        return None


def _sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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

    def get_file(self, key: str, local_path: str) -> bool:
        # Mirrors put_file's key scheme exactly (raw objects live in _files,
        # never in the tar-blob namespace).
        if key not in self._files:
            return False
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(self._files[key])
        return True

    def get_tree(self, key: str, local_dir: str, subdirs: Optional[List[str]] = None) -> None:
        if key not in self._blobs:
            os.makedirs(local_dir, exist_ok=True)
            return
        _untar_bytes_to_dir(self._blobs[key], local_dir, subdirs)

    def generation(self, key: str) -> Optional[str]:
        g = self._gen.get(key)
        return str(g) if g is not None else None

    def delete_tree(self, key: str) -> None:
        self._blobs.pop(key, None)
        self._gen.pop(key, None)

    def delete_file(self, key: str) -> None:
        self._files.pop(key, None)


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

    def get_file(self, key: str, local_path: str) -> bool:
        # Mirrors put_file's key scheme exactly: raw blob at the key itself
        # (no ``.tar.gz`` suffix).
        blob = self._raw_blob(key)
        if not blob.exists():
            return False
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        blob.download_to_filename(local_path)
        return True

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

    def delete_tree(self, key: str) -> None:
        # Raises NotFound when absent — callers doing best-effort cleanup suppress.
        self._blob(key).delete()

    def delete_file(self, key: str) -> None:
        # Raw object at the key itself (no ``.tar.gz``) — put_file namespace.
        # Raises NotFound when absent; best-effort callers suppress.
        self._raw_blob(key).delete()


# ---------------------------------------------------------------------------
# Cloud workspace provider — stage in / hand POSIX path / sync back.
# ---------------------------------------------------------------------------


class CloudWorkspaceProvider:
    """Materialize a session workspace from object storage onto local scratch.

    ``workspace_for`` materializes the session's stored workspace (manifest +
    per-file blobs; legacy single tarball as read fallback) into a per-session
    scratch directory and returns that POSIX path — exactly what the tools
    expect. ``sync`` persists local changes back **incrementally** (4A): only
    content not already in storage is uploaded, then one small manifest object
    is written LAST as the atomic commit point. The request lifecycle calls
    ``workspace_for`` on entry and ``sync`` on exit (see ``api.py`` integration).

    Consistency story (replaces the old blob's atomic-by-accident put):

      * Blobs are content-addressed (sha256) and therefore immutable — the file
        set named by any manifest is internally consistent forever.
      * The manifest is written last; a reader (any instance, any time) sees
        either the previous manifest or the new one, never a mix. A crash
        mid-sync leaves orphan blobs (garbage, GC deferred) but a fully
        consistent readable state.
      * Deletes/renames propagate because hydration reconstructs exactly the
        manifest's tree — nothing else.
      * The manifest records mode + mtime_ns (+ symlinks + empty dirs) so a
        cold hydrate is tree-faithful — tar preserved mtimes, and downstream
        "did THIS run produce it" logic depends on them (see CLAUDE.md).

    A store without the raw-object surface (``put_file``/``get_file`` — e.g.
    minimal test fakes) keeps the previous whole-tar behavior end to end.

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

    # -- incremental format plumbing (4A) ------------------------------------

    _BLOB_WORKERS = 8  # bounded parallelism for per-file GCS transfers

    def _manifest_key(self, session_id: str) -> str:
        # ``.`` never survives session-id normalization, so the ``.sc_*`` names
        # can never collide with a real session path.
        return f"{self._key(session_id)}/.sc_manifest.json"

    def _blob_key(self, session_id: str, content_hash: str) -> str:
        return f"{self._key(session_id)}/.sc_blobs/{content_hash}"

    def _index_path(self, session_id: str) -> str:
        # Sibling of the scratch dir, like the generation marker: never synced,
        # never listed. A pure cache — losing it only costs a re-hash/re-check.
        return self._scratch(session_id) + ".sc_index.json"

    def _store_supports_files(self) -> bool:
        return callable(getattr(self._store, "put_file", None)) and callable(
            getattr(self._store, "get_file", None)
        )

    def _read_index(self, session_id: str) -> Optional[dict]:
        try:
            with open(self._index_path(session_id), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _write_index(self, session_id: str, index: dict) -> None:
        path = self._index_path(session_id)
        try:
            tmp = f"{path}.tmp.{uuid.uuid4().hex}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(index, f)
            os.replace(tmp, path)
        except OSError:
            pass  # cache only; a miss costs a re-hash, never correctness

    def _fetch_manifest(self, session_id: str) -> Optional[Tuple[str, dict]]:
        """(manifest_content_hash, manifest_dict) from storage, or None.

        The content hash doubles as the cache token (marker ``m:<hash>``), so
        no separate generation/metadata API is needed for the new format.
        """
        if not self._store_supports_files():
            return None
        tmp = self._scratch(session_id) + f".manifest.{uuid.uuid4().hex}"
        try:
            if not self._store.get_file(self._manifest_key(session_id), tmp):
                return None
            with open(tmp, "rb") as f:
                raw = f.read()
            return hashlib.sha256(raw).hexdigest(), json.loads(raw.decode("utf-8"))
        finally:
            with suppress(OSError):
                os.remove(tmp)

    @staticmethod
    def _guard_member(dest: str, rel: str) -> str:
        """Reject manifest entries that would escape ``dest`` (parity with the
        tar path's ``_safe_extract`` traversal guard)."""
        target = os.path.realpath(os.path.join(dest, rel))
        dest_real = os.path.realpath(dest)
        if not (target == dest_real or target.startswith(dest_real + os.sep)):
            raise ValueError(f"Refusing path-traversal manifest entry: {rel}")
        return os.path.join(dest, rel)

    def _materialize_manifest(self, session_id: str, manifest: dict, dest: str) -> None:
        """Reconstruct the manifest's exact tree under ``dest`` (a private temp
        dir — the caller swaps it in atomically)."""
        os.makedirs(dest, exist_ok=True)
        for rel in manifest.get("dirs", []):
            os.makedirs(self._guard_member(dest, rel), exist_ok=True)

        files: dict = manifest.get("files", {})
        by_hash: dict[str, list[str]] = {}
        for rel, ent in files.items():
            self._guard_member(dest, rel)
            by_hash.setdefault(ent["h"], []).append(rel)

        def fetch(content_hash: str, rels: List[str]) -> None:
            first = os.path.join(dest, rels[0])
            os.makedirs(os.path.dirname(first), exist_ok=True)
            if not self._store.get_file(self._blob_key(session_id, content_hash), first):
                raise RuntimeError(
                    f"workspace blob missing for '{session_id}': {content_hash} ({rels[0]})"
                )
            for rel in rels[1:]:  # duplicate content: one download, N placements
                target = os.path.join(dest, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(first, target)

        items = list(by_hash.items())
        if len(items) > 1:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=self._BLOB_WORKERS) as pool:
                list(pool.map(lambda kv: fetch(*kv), items))  # list() re-raises
        elif items:
            fetch(*items[0])

        for rel, ent in files.items():
            full = os.path.join(dest, rel)
            mode = ent.get("mode")
            if mode is not None:
                with suppress(OSError):
                    os.chmod(full, mode & 0o7777)
            mtime_ns = ent.get("mtime_ns")
            if mtime_ns is not None:
                with suppress(OSError):
                    os.utime(full, ns=(mtime_ns, mtime_ns))

        # Symlinks last, so no file/dir placement above ever routes through one.
        for rel, link_target in manifest.get("symlinks", {}).items():
            full = self._guard_member(dest, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with suppress(OSError):
                os.symlink(link_target, full)

    @staticmethod
    def _index_after_hydration(manifest: dict) -> dict:
        """Stat-cache entries matching the tree just materialized (sizes and
        mtimes were restored from the manifest), so the next sync re-hashes
        nothing that didn't change."""
        entries = {
            rel: {"size": ent.get("size"), "mtime_ns": ent.get("mtime_ns"), "h": ent["h"]}
            for rel, ent in manifest.get("files", {}).items()
        }
        remote = sorted({ent["h"] for ent in manifest.get("files", {}).values()})
        return {"scan_ns": time.time_ns(), "entries": entries, "remote_hashes": remote}

    def _scan_tree(self, scratch: str, prev_entries: dict, prev_scan_ns: Optional[int]):
        """Walk the scratch tree into (manifest, index_entries, scan_ns).

        Hash reuse mirrors git's index rules: a file whose (size, mtime_ns)
        match the previous scan AND whose mtime predates that scan keeps its
        recorded hash; anything else is re-hashed (the racy-timestamp guard).
        """
        scan_ns = time.time_ns()
        files: dict = {}
        symlinks: dict = {}
        dirs: list[str] = []
        entries: dict = {}
        for root, dirnames, filenames in os.walk(scratch, followlinks=False):
            rel_root = os.path.relpath(root, scratch)
            rel_root = "" if rel_root == "." else rel_root.replace(os.sep, "/")
            kept_dirs = []
            for name in dirnames:
                rel = f"{rel_root}/{name}" if rel_root else name
                full = os.path.join(root, name)
                if os.path.islink(full):  # walk won't descend; record the link
                    symlinks[rel] = os.readlink(full)
                else:
                    dirs.append(rel)
                    kept_dirs.append(name)
            dirnames[:] = kept_dirs
            for name in filenames:
                rel = f"{rel_root}/{name}" if rel_root else name
                full = os.path.join(root, name)
                st = os.lstat(full)
                if stat_module.S_ISLNK(st.st_mode):
                    symlinks[rel] = os.readlink(full)
                    continue
                if not stat_module.S_ISREG(st.st_mode):
                    continue  # fifos/sockets: never legitimately in a workspace
                size, mtime_ns = st.st_size, st.st_mtime_ns
                prev = prev_entries.get(rel)
                if (
                    prev
                    and prev.get("size") == size
                    and prev.get("mtime_ns") == mtime_ns
                    and prev_scan_ns is not None
                    and mtime_ns < prev_scan_ns
                ):
                    content_hash = prev["h"]
                else:
                    content_hash = _sha256_file(full)
                files[rel] = {
                    "h": content_hash,
                    "size": size,
                    "mode": st.st_mode & 0o7777,
                    "mtime_ns": mtime_ns,
                }
                entries[rel] = {"size": size, "mtime_ns": mtime_ns, "h": content_hash}
        manifest = {
            "format": 1,
            "files": files,
            "symlinks": symlinks,
            "dirs": sorted(dirs),
        }
        return manifest, entries, scan_ns

    # -- the WorkspaceProvider surface ----------------------------------------

    def workspace_for(self, session_id: str) -> str:
        scratch = self._scratch(session_id)
        key = self._key(session_id)
        with self._lock_for(session_id):
            # Incremental format first: when a manifest exists it IS the truth
            # (a leftover legacy tar is stale after conversion).
            fetched = self._fetch_manifest(session_id)
            if fetched is not None:
                manifest_hash, manifest = fetched
                if os.path.isdir(scratch) and self._read_marker(session_id) == f"m:{manifest_hash}":
                    return scratch  # F3 cache hit: one small GET, no downloads
                tmp = f"{scratch}.tmp.{uuid.uuid4().hex}"
                try:
                    self._materialize_manifest(session_id, manifest, tmp)
                    self._atomic_swap(tmp, scratch)
                    self._write_marker(session_id, f"m:{manifest_hash}")
                    self._write_index(session_id, self._index_after_hydration(manifest))
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
                return scratch

            # Legacy single-tar fallback (pre-4A sessions, minimal stores).
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

        4A: incremental — upload only content not already stored, then commit
        by writing the manifest last. Cost is proportional to what changed
        (a one-file save = one blob + one small manifest), not to workspace
        size. Under the per-session lock so an upload never races a hydration
        swap; the marker is refreshed to the just-written manifest so a
        subsequent read on this instance doesn't re-download its own write (F3).
        """
        key = self._key(session_id)
        scratch = self._scratch(session_id)
        with self._lock_for(session_id):
            # A missing scratch dir means the session was deleted (or never
            # materialized on this instance) — NOT an empty workspace. Syncing
            # it would commit an empty-but-adoptable manifest, resurrecting a
            # session whose delete/fork-rollback just purged the durable
            # manifest on purpose (the D7 guarantee). A background flush racing
            # a delete lands here. An empty-but-EXISTING scratch still syncs.
            if not os.path.isdir(scratch):
                return
            if not self._store_supports_files():
                # Minimal store surface (tar-only fakes): previous behavior.
                self._store.put_tree(key, scratch)
                new_gen = _store_generation(self._store, key)
                if new_gen is not None and os.path.isdir(scratch):
                    self._write_marker(session_id, new_gen)
                return
            self._sync_incremental(session_id, key, scratch)

    def _sync_incremental(self, session_id: str, key: str, scratch: str) -> None:
        prior_marker = self._read_marker(session_id)
        index = self._read_index(session_id)
        if index is not None:
            known_hashes = set(index.get("remote_hashes", []))
            prev_entries = index.get("entries", {})
            prev_scan_ns = index.get("scan_ns")
        else:
            # Cold instance / lost cache: learn what storage already holds from
            # the remote manifest (one small GET) instead of re-uploading all.
            fetched = self._fetch_manifest(session_id)
            known_hashes = (
                {ent["h"] for ent in fetched[1].get("files", {}).values()} if fetched else set()
            )
            prev_entries = {}
            prev_scan_ns = None  # unknown history → hash everything once

        manifest, entries, scan_ns = self._scan_tree(scratch, prev_entries, prev_scan_ns)

        # Content not yet in storage uploads from a private SNAPSHOT whose hash
        # is computed from the snapshot itself — so a tool writing the file
        # concurrently with this sync can never get bytes stored under a hash
        # they don't match (the content-addressing invariant). On a detected
        # race the manifest entry is patched to the snapshot's actual hash; the
        # stat cache's racy-timestamp guard re-hashes that file next sync.
        pending = [rel for rel, ent in manifest["files"].items() if ent["h"] not in known_hashes]
        snap_dir = scratch + f".snap.{uuid.uuid4().hex}"
        upload_map: dict[str, str] = {}  # actual content hash -> snapshot path
        try:
            if pending:
                os.makedirs(snap_dir, exist_ok=True)
            for i, rel in enumerate(pending):
                snap = os.path.join(snap_dir, str(i))
                shutil.copyfile(os.path.join(scratch, rel), snap)
                content_hash = _sha256_file(snap)
                ent = manifest["files"][rel]
                if content_hash != ent["h"]:
                    ent["h"] = content_hash
                    ent["size"] = os.path.getsize(snap)
                    if rel in entries:
                        entries[rel]["h"] = content_hash
                if content_hash not in known_hashes:
                    upload_map.setdefault(content_hash, snap)

            raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            manifest_hash = hashlib.sha256(raw).hexdigest()

            if not upload_map and prior_marker == f"m:{manifest_hash}":
                # Nothing changed since the commit this instance last made/saw —
                # a no-change sync costs ZERO writes (the common case now that
                # Codex syncs once per turn, including turns that only read).
                self._write_index(session_id, {
                    "scan_ns": scan_ns,
                    "entries": entries,
                    "remote_hashes": sorted(known_hashes),
                })
                return

            def push(content_hash: str, snap: str) -> None:
                self._store.put_file(self._blob_key(session_id, content_hash), snap)

            items = list(upload_map.items())
            if len(items) > 1:
                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=self._BLOB_WORKERS) as pool:
                    list(pool.map(lambda kv: push(*kv), items))  # list() re-raises
            elif items:
                push(*items[0])

            # The commit point: blobs are all in place, now flip the manifest.
            tmp = scratch + f".manifest-out.{uuid.uuid4().hex}"
            try:
                with open(tmp, "wb") as f:
                    f.write(raw)
                self._store.put_file(self._manifest_key(session_id), tmp)
            finally:
                with suppress(OSError):
                    os.remove(tmp)
        finally:
            shutil.rmtree(snap_dir, ignore_errors=True)
        self._write_marker(session_id, f"m:{manifest_hash}")
        self._write_index(session_id, {
            "scan_ns": scan_ns,
            "entries": entries,
            "remote_hashes": sorted({ent["h"] for ent in manifest["files"].values()}),
        })

        # One-time conversion cleanup: this workspace was last hydrated from the
        # legacy tar (marker without the manifest prefix) — the tar is now stale
        # and must not shadow the manifest for any reader. Best-effort.
        if prior_marker is not None and not prior_marker.startswith("m:"):
            delete = getattr(self._store, "delete_tree", None)
            if callable(delete):
                with suppress(Exception):
                    delete(key)

    def delete_workspace(self, session_id: str) -> None:
        """Best-effort teardown of a session's staged workspace (fork rollback).

        Drops the local scratch tree + its sibling caches AND the committed
        manifest object, so a failed hosted fork leaves no adoptable workspace
        (D7): only the manifest makes a workspace adoptable, so deleting it
        suffices — the content-addressed blobs it referenced become unreferenced
        orphans (harmless, GC deferred). Never raises; the caller is unwinding an
        error and must not have it masked.
        """
        with self._lock_for(session_id):
            shutil.rmtree(self._scratch(session_id), ignore_errors=True)
            for sibling in (
                self._marker_path(session_id),
                self._index_path(session_id),
            ):
                with suppress(OSError):
                    os.remove(sibling)
            delete_file = getattr(self._store, "delete_file", None)
            if callable(delete_file):
                with suppress(Exception):
                    delete_file(self._manifest_key(session_id))


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
