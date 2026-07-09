"""Item 2 — publish_templates golden test (no live GCS, no google-cloud import).

Drives the pure ``publish`` core with an in-memory recording store over a tmp
fixture bundle: asserts the D4 index shape, that the source archive is the
workspace subtree only (no ``template.json`` inside), that the binaries archive
holds exactly the ``.sc_binaries.json``-listed paths, and that ``index.json`` is
written LAST (atomic publish).
"""
import json
import os

from scripts import publish_templates as PUB
from src.platform_engines.workspace_provider import InMemoryObjectStore


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content))


GDS_REL = "synth_runs/synth_0001/orfs_results/sky130hd/fifo/base/6_final.gds"


def _make_fixture(tmp_path):
    """A split source bundle + a separate checkout that still holds the binary."""
    examples = tmp_path / "examples"
    ws = examples / "demo" / "workspace"
    _write(str(examples / "demo" / "template.json"), {
        "id": "demo", "name": "Demo FIFO", "description": "d",
        "highlights": ["h"], "top_module": "fifo", "platform": "sky130hd",
        "source_note": "authored",
    })
    _write(str(ws / "fifo.v"), "module fifo(); endmodule\n")
    _write(str(ws / "manifest.json"), {"sessionId": "", "synthTop": "fifo"})
    _write(str(ws / "synth_runs" / "synth_0001" / "run_meta.json"),
           {"id": "synth_0001", "status": "completed"})
    _write(str(ws / ".sc_binaries.json"),
           {"version": 1, "files": [{"path": GDS_REL, "bytes": 9, "sha256": "deadbeef"}]})

    # The split-out binary lives only in the --binaries-from checkout. publish()
    # takes examples-level roots (main() appends "examples" to --binaries-from).
    binaries_examples = tmp_path / "presplit" / "examples"
    _write(str(binaries_examples / "demo" / "workspace" / GDS_REL.replace("/", os.sep)),
           "GDS-BYTES")
    return str(examples), str(binaries_examples)


class _RecordingStore(InMemoryObjectStore):
    def __init__(self):
        super().__init__()
        self.ops = []

    def put_tree(self, key, local_dir):
        self.ops.append(("put_tree", key))
        super().put_tree(key, local_dir)

    def put_file(self, key, local_path):
        self.ops.append(("put_file", key))
        super().put_file(key, local_path)


def _extract_rel_paths(store, key, tmp_dir):
    store.get_tree(key, tmp_dir)
    out = []
    for root, _dirs, files in os.walk(tmp_dir):
        for name in files:
            out.append(os.path.relpath(os.path.join(root, name), tmp_dir).replace(os.sep, "/"))
    return sorted(out)


def test_publish_golden(tmp_path):
    examples_root, binaries_root = _make_fixture(tmp_path)
    store = _RecordingStore()

    index = PUB.publish(store, examples_root, binaries_root, ["demo"], log=lambda *_: None)

    # --- index shape (D4) ---
    assert index["version"] == 1
    assert index["generated_at"].endswith("+00:00")
    assert len(index["templates"]) == 1
    e = index["templates"][0]
    for k in ("id", "name", "description", "highlights", "top_module", "platform",
              "source_note", "file_count", "run_count", "files", "conversations", "tier"):
        assert k in e, k
    assert e["tier"] == "official"
    assert e["run_count"] == 1
    for side in ("source", "binaries"):
        assert set(e[side]) == {"key", "bytes", "sha256"}
        assert e[side]["bytes"] > 0
    assert e["source"]["key"] == "bundles/demo/source"
    assert e["binaries"]["key"] == "bundles/demo/binaries"

    # Preview computed from the FULL bundle: the gds + source are listed, the
    # bookkeeping dotfile is hidden (A13).
    assert "fifo.v" in e["files"]
    assert GDS_REL in e["files"]
    assert ".sc_binaries.json" not in e["files"]

    # --- source archive = workspace subtree only (no template.json inside) ---
    src_paths = _extract_rel_paths(store, "bundles/demo/source", str(tmp_path / "x_src"))
    assert "fifo.v" in src_paths and "manifest.json" in src_paths
    assert ".sc_binaries.json" in src_paths  # forks need it (D9)
    assert "template.json" not in src_paths
    assert GDS_REL not in src_paths  # the binary is NOT in the source archive

    # --- binaries archive = exactly the listed paths ---
    bin_paths = _extract_rel_paths(store, "bundles/demo/binaries", str(tmp_path / "x_bin"))
    assert bin_paths == [GDS_REL]

    # --- index.json written LAST (atomic publish) ---
    assert store.ops[-1] == ("put_file", "index.json")
    put_file_idx = [i for i, (op, k) in enumerate(store.ops) if op == "put_file" and k == "index.json"][0]
    put_tree_idxs = [i for i, (op, _k) in enumerate(store.ops) if op == "put_tree"]
    assert all(i < put_file_idx for i in put_tree_idxs)


def test_publish_missing_binary_fails_loudly(tmp_path):
    examples_root, _ = _make_fixture(tmp_path)
    # Point binaries-from at an empty checkout: the listed gds is absent.
    empty = tmp_path / "empty" / "examples"
    empty.mkdir(parents=True)
    store = _RecordingStore()
    try:
        PUB.publish(store, examples_root, str(empty), ["demo"], log=lambda *_: None)
        assert False, "expected FileNotFoundError for the missing binary"
    except FileNotFoundError as exc:
        assert "demo" in str(exc)
    # Nothing was written (the failure happened before any upload for this bundle).
    assert store.ops == []


def test_dry_run_uploads_nothing(tmp_path):
    examples_root, binaries_root = _make_fixture(tmp_path)
    store = _RecordingStore()
    index = PUB.publish(store, examples_root, binaries_root, ["demo"], dry_run=True, log=lambda *_: None)
    assert len(index["templates"]) == 1
    assert store.ops == []  # dry-run: no uploads
