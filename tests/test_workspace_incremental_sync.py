"""4A (hosted-latency plan): incremental per-file workspace sync.

The hosted workspace used to be persisted as ONE gzipped tar per session, so a
one-line save after synthesis re-uploaded hundreds of MB (~15s observed). Now a
sync uploads only content not already in storage (content-addressed blobs) and
commits by writing one small manifest LAST. These tests pin the plan's §5 hard
constraints: cost ∝ change, cross-instance reconstruction (twelve-factor),
atomic commit ordering, delete/rename propagation, legacy-tar conversion, and
the traversal guard the tar path already had.
"""
import json
import os
import time

import pytest

from src.platform_engines.workspace_provider import (
    CloudWorkspaceProvider,
    InMemoryObjectStore,
)


class RecordingStore(InMemoryObjectStore):
    """InMemory store that records every raw-object write/read in order."""

    def __init__(self):
        super().__init__()
        self.put_file_keys = []
        self.get_file_keys = []
        self.deleted_trees = []

    def put_file(self, key, local_path):
        self.put_file_keys.append(key)
        return super().put_file(key, local_path)

    def get_file(self, key, local_path):
        self.get_file_keys.append(key)
        return super().get_file(key, local_path)

    def delete_tree(self, key):
        self.deleted_trees.append(key)
        return super().delete_tree(key)


def _write(ws, rel, content):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path) or ws, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _blob_puts(store):
    return [k for k in store.put_file_keys if "/.sc_blobs/" in k]


def _manifest_puts(store):
    return [k for k in store.put_file_keys if k.endswith("/.sc_manifest.json")]


# --- cost ∝ change (§6A) -----------------------------------------------------


def test_single_file_edit_uploads_only_that_file(tmp_path):
    """The headline regression test: after a heavy workspace is synced once,
    editing ONE file uploads exactly one blob + the manifest — never the tree."""
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    for i in range(20):  # a 'heavy' workspace stand-in
        _write(ws, f"runs/r{i}/artifact.bin", f"artifact {i}" * 100)
    _write(ws, "top.v", "module top; endmodule\n")
    p.sync("s")
    baseline_blobs = len(_blob_puts(store))
    assert baseline_blobs == 21  # everything uploads exactly once initially

    _write(ws, "top.v", "module top; /* edited */ endmodule\n")
    p.sync("s")

    assert len(_blob_puts(store)) == baseline_blobs + 1, (
        "a one-file edit must upload exactly one new blob, not the tree"
    )
    assert len(_manifest_puts(store)) == 2


def test_no_change_sync_writes_nothing(tmp_path):
    """A turn that only read (Codex now syncs once per turn regardless) must
    cost zero PUTs."""
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "a.v", "// a\n")
    p.sync("s")
    puts_after_first = len(store.put_file_keys)

    p.sync("s")  # nothing changed
    assert len(store.put_file_keys) == puts_after_first


def test_duplicate_content_uploads_once(tmp_path):
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "a.v", "same content\n")
    _write(ws, "b.v", "same content\n")
    p.sync("s")
    assert len(_blob_puts(store)) == 1  # content-addressed: one blob, two paths

    # ...and a cold instance still gets both files.
    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    ws2 = p2.workspace_for("s")
    for name in ("a.v", "b.v"):
        with open(os.path.join(ws2, name), encoding="utf-8") as f:
            assert f.read() == "same content\n"


def test_rename_uploads_no_new_content(tmp_path):
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "old_name.v", "module m; endmodule\n")
    p.sync("s")
    blobs_before = len(_blob_puts(store))

    os.rename(os.path.join(ws, "old_name.v"), os.path.join(ws, "new_name.v"))
    p.sync("s")
    assert len(_blob_puts(store)) == blobs_before  # same content → no new blob

    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    ws2 = p2.workspace_for("s")
    assert os.path.isfile(os.path.join(ws2, "new_name.v"))
    assert not os.path.exists(os.path.join(ws2, "old_name.v"))  # rename propagated


# --- deletes propagate (§5.3) -------------------------------------------------


def test_delete_propagates_to_cold_instance(tmp_path):
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "keep.v", "// keep\n")
    _write(ws, "gone.v", "// gone\n")
    p.sync("s")

    os.remove(os.path.join(ws, "gone.v"))
    p.sync("s")

    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    ws2 = p2.workspace_for("s")
    assert os.path.isfile(os.path.join(ws2, "keep.v"))
    assert not os.path.exists(os.path.join(ws2, "gone.v")), (
        "a deleted file must not linger in storage/hydration"
    )


# --- cross-instance fidelity (§5.1) --------------------------------------------


def test_cold_instance_reconstructs_exact_tree(tmp_path):
    """Twelve-factor: a DIFFERENT, cold instance must reconstruct the exact
    workspace — nested dirs, empty dirs, exec bits, mtimes, symlinks."""
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")

    _write(ws, "src/rtl/top.v", "module top; endmodule\n")
    _write(ws, "runs/synth_0001/run_meta.json", "{}")
    os.makedirs(os.path.join(ws, "empty_dir"))
    script = os.path.join(ws, "run.sh")
    _write(ws, "run.sh", "#!/bin/sh\n")
    os.chmod(script, 0o755)
    old_mtime_ns = 1_600_000_000_123_456_789  # tar preserved mtimes; so must we
    os.utime(os.path.join(ws, "src/rtl/top.v"), ns=(old_mtime_ns, old_mtime_ns))
    os.symlink("src/rtl/top.v", os.path.join(ws, "top_link.v"))
    p.sync("s")

    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    ws2 = p2.workspace_for("s")

    with open(os.path.join(ws2, "src/rtl/top.v"), encoding="utf-8") as f:
        assert f.read() == "module top; endmodule\n"
    assert os.path.isfile(os.path.join(ws2, "runs/synth_0001/run_meta.json"))
    assert os.path.isdir(os.path.join(ws2, "empty_dir"))
    assert os.stat(os.path.join(ws2, "run.sh")).st_mode & 0o777 == 0o755
    assert os.lstat(os.path.join(ws2, "src/rtl/top.v")).st_mtime_ns == old_mtime_ns
    assert os.readlink(os.path.join(ws2, "top_link.v")) == "src/rtl/top.v"


def test_own_write_not_redownloaded_and_cache_hit_open_is_cheap(tmp_path):
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "a.v", "// a\n")
    p.sync("s")

    store.get_file_keys.clear()
    ws_again = p.workspace_for("s")
    assert ws_again == ws
    blob_gets = [k for k in store.get_file_keys if "/.sc_blobs/" in k]
    assert blob_gets == [], "unchanged open must not re-download any blob"


# --- atomicity (§5.2) -----------------------------------------------------------


def test_manifest_is_written_after_all_blobs(tmp_path):
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    for i in range(5):
        _write(ws, f"f{i}.v", f"// {i}\n")
    p.sync("s")

    manifest_pos = store.put_file_keys.index(_manifest_puts(store)[0])
    blob_positions = [store.put_file_keys.index(k) for k in _blob_puts(store)]
    assert all(pos < manifest_pos for pos in blob_positions), (
        "the manifest is the commit point — it must be written last"
    )


def test_crash_before_manifest_leaves_old_state_readable(tmp_path):
    """Blobs uploaded but the manifest put crashes → storage still serves the
    previous, fully consistent workspace to a cold reader."""

    class CrashingStore(RecordingStore):
        def __init__(self):
            super().__init__()
            self.crash_on_manifest = False

        def put_file(self, key, local_path):
            if self.crash_on_manifest and key.endswith("/.sc_manifest.json"):
                raise RuntimeError("simulated instance death mid-sync")
            return super().put_file(key, local_path)

    store = CrashingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "a.v", "// v1\n")
    p.sync("s")

    _write(ws, "a.v", "// v2\n")
    _write(ws, "b.v", "// new\n")
    store.crash_on_manifest = True
    with pytest.raises(RuntimeError):
        p.sync("s")

    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    ws2 = p2.workspace_for("s")
    with open(os.path.join(ws2, "a.v"), encoding="utf-8") as f:
        assert f.read() == "// v1\n"  # previous commit, complete
    assert not os.path.exists(os.path.join(ws2, "b.v"))  # never half-visible


# --- legacy tar migration -------------------------------------------------------


def test_legacy_tar_workspace_converts_on_first_sync(tmp_path):
    store = RecordingStore()
    seed = tmp_path / "seed"
    (seed / "runs").mkdir(parents=True)
    (seed / "top.v").write_text("module top; endmodule\n")
    (seed / "runs" / "meta.json").write_text("{}")
    store.put_tree("workspaces/s", str(seed))  # a pre-4A stored workspace

    # Hydrates from the tar (read fallback), then converts on the first sync.
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    assert os.path.isfile(os.path.join(ws, "top.v"))
    _write(ws, "new.v", "// added post-migration\n")
    p.sync("s")

    assert _manifest_puts(store), "first sync must write the manifest format"
    assert store.deleted_trees == ["workspaces/s"], (
        "the stale legacy tar must be cleaned up after conversion"
    )

    # A cold instance reconstructs everything from the new format alone.
    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    ws2 = p2.workspace_for("s")
    assert os.path.isfile(os.path.join(ws2, "top.v"))
    assert os.path.isfile(os.path.join(ws2, "runs", "meta.json"))
    assert os.path.isfile(os.path.join(ws2, "new.v"))


# --- defense in depth ------------------------------------------------------------


def test_path_traversal_manifest_rejected(tmp_path):
    """Parity with the tar path's _safe_extract guard: a crafted manifest must
    not write outside the scratch dir."""
    store = RecordingStore()
    evil = {
        "format": 1,
        "files": {"../escape.v": {"h": "0" * 64, "size": 1, "mode": 0o644, "mtime_ns": 0}},
        "symlinks": {},
        "dirs": [],
    }
    blob = tmp_path / "m.json"
    blob.write_text(json.dumps(evil))
    store.put_file("workspaces/s/.sc_manifest.json", str(blob))

    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    with pytest.raises(ValueError, match="path-traversal"):
        p.workspace_for("s")


def test_missing_blob_fails_loudly_never_torn(tmp_path):
    """A manifest referencing an absent blob (corruption) must raise — never
    swap in a partial tree or silently serve an empty workspace."""
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "a.v", "// a\n")
    p.sync("s")
    # Corrupt storage: drop the blob behind the manifest's back.
    blob_key = _blob_puts(store)[0]
    store._files.pop(blob_key)

    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    with pytest.raises(RuntimeError, match="blob missing"):
        p2.workspace_for("s")
    assert not os.path.isdir(os.path.join(str(tmp_path / "scratch2"), "s"))


def test_concurrent_write_between_scan_and_upload_stays_consistent(tmp_path, monkeypatch):
    """A tool writing a file WHILE sync runs must never get bytes stored under
    a hash they don't match (content-addressing invariant): uploads are
    snapshotted and hashed from the snapshot, and the manifest is patched to
    the snapshot's actual hash — git's rule. Pre-fix, the live file was
    uploaded under the stale scan-time hash."""
    import hashlib

    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "a.v", "// v1\n")

    real_scan = p._scan_tree

    def racing_scan(scratch, prev_entries, prev_scan_ns):
        out = real_scan(scratch, prev_entries, prev_scan_ns)
        _write(ws, "a.v", "// v2 (raced)\n")  # lands after the scan hashed v1
        return out

    monkeypatch.setattr(p, "_scan_tree", racing_scan)
    p.sync("s")

    v2_hash = hashlib.sha256(b"// v2 (raced)\n").hexdigest()
    assert f"workspaces/s/.sc_blobs/{v2_hash}" in store.put_file_keys, (
        "the uploaded blob must be keyed by the hash of the bytes actually uploaded"
    )
    p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
    ws2 = p2.workspace_for("s")
    with open(os.path.join(ws2, "a.v"), encoding="utf-8") as f:
        assert f.read() == "// v2 (raced)\n"


# --- stat-cache honesty -----------------------------------------------------------


def test_touched_but_identical_file_is_not_reuploaded(tmp_path):
    """mtime changed, content identical: the file is re-hashed (stat cache
    miss) but the content hash matches storage → still no blob upload."""
    store = RecordingStore()
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))
    ws = p.workspace_for("s")
    _write(ws, "a.v", "// a\n")
    p.sync("s")
    blobs = len(_blob_puts(store))

    time.sleep(0.01)
    os.utime(os.path.join(ws, "a.v"))  # touch: new mtime, same bytes
    p.sync("s")
    assert len(_blob_puts(store)) == blobs
