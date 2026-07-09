"""Item 1 — the source/binary split tool (scripts/split_bundle_binaries.py).

Covers the classifier (only the heavy result TYPES move; markers/reports stay),
the ``.sc_binaries.json`` manifest shape, apply idempotence, and the A1 parity
guarantee: splitting a real bundle must not change ``get_synthesis_metrics`` or
the stage-completion set (those read the KEPT ``.rpt``/``.txt``/``.log``/marker
files, never the moved binaries). No pytest-asyncio: everything here is sync.
"""
import hashlib
import json
import os
import shutil

import pytest

from scripts import split_bundle_binaries as S


# ---------------------------------------------------------------------------
# Classifier (is_binary) — by directory membership + extension, never filename
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel,expected",
    [
        ("synth_runs/s1/orfs_results/sky130hd/top/base/6_final.gds", True),
        ("synth_runs/s1/orfs_results/sky130hd/top/base/6_final.def", True),
        ("synth_runs/s1/orfs_results/sky130hd/top/base/6_final.spef", True),
        ("synth_runs/s1/orfs_results/sky130hd/top/base/1_1_yosys.rtlil", True),
        ("synth_runs/s1/orfs_results/sky130hd/top/base/6_final.v", True),
        # Heavy unread blobs: mem.json (exact name) and any .guide under results.
        ("synth_runs/s1/orfs_results/sky130hd/top/base/mem.json", True),
        ("synth_runs/s1/orfs_results/sky130hd/top/base/route.guide", True),
        ("synth_runs/s1/orfs_reports/sky130hd/top/base/final_all.webp", True),
        # KEPT: markers/reports/config under the same trees.
        ("synth_runs/s1/orfs_results/sky130hd/top/base/5_route.sdc", False),
        # KEPT: a non-mem .json under results (only mem.json moves, not blanket).
        ("synth_runs/s1/orfs_results/sky130hd/top/base/1_synth.json", False),
        ("synth_runs/s1/orfs_results/sky130hd/top/base/clock_period.txt", False),
        ("synth_runs/s1/orfs_reports/sky130hd/top/base/6_finish.rpt", False),
        ("synth_runs/s1/orfs_reports/sky130hd/top/base/synth_stat.txt", False),
        # KEPT: same names/extensions OUTSIDE the result trees.
        ("synth_runs/s1/inputs/top.v", False),
        ("synth_runs/s1/mem.json", False),  # mem.json only counts under orfs_results
        ("top.v", False),
        ("manifest.json", False),
        ("preview.webp", False),  # a webp not under orfs_reports stays
    ],
)
def test_is_binary_classifies_by_tree_and_type(rel, expected):
    assert S.is_binary(rel) is expected


# ---------------------------------------------------------------------------
# A synthetic bundle with both moved + kept files
# ---------------------------------------------------------------------------


def _write(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(content, (bytes, bytearray)) else "w"
    with open(path, mode) as f:
        f.write(content)


def _make_bundle(root, template_id="demo"):
    ws = os.path.join(root, template_id, "workspace")
    base_res = os.path.join(ws, "synth_runs", "s1", "orfs_results", "sky130hd", "top", "base")
    base_rep = os.path.join(ws, "synth_runs", "s1", "orfs_reports", "sky130hd", "top", "base")
    # Moved (heavy result types):
    _write(os.path.join(base_res, "6_final.gds"), b"GDS" * 100)
    _write(os.path.join(base_res, "6_final.def"), b"DEF" * 100)
    _write(os.path.join(base_res, "6_final.spef"), b"SPEF" * 50)
    _write(os.path.join(base_res, "1_1_yosys.rtlil"), b"RTLIL" * 50)
    _write(os.path.join(base_res, "6_final.v"), b"module top(); endmodule\n")
    _write(os.path.join(base_res, "mem.json"), b'{"macros": []}' * 100)
    _write(os.path.join(base_res, "route.guide"), b"guide" * 100)
    _write(os.path.join(base_rep, "final_all.webp"), b"WEBP" * 20)
    # Kept (markers, reports, config, source):
    _write(os.path.join(base_res, "5_route.sdc"), "create_clock\n")
    _write(os.path.join(base_res, "1_synth.json"), "{}\n")  # non-mem json stays
    _write(os.path.join(base_rep, "6_finish.rpt"), "finished\n")
    _write(os.path.join(ws, "synth_runs", "s1", "inputs", "top.v"), "module top(); endmodule\n")
    _write(os.path.join(ws, "top.v"), "module top(); endmodule\n")
    return ws


def test_dry_run_lists_but_changes_nothing(tmp_path):
    ws = _make_bundle(str(tmp_path))
    bundle = os.path.dirname(ws)
    entries = S.split_bundle(bundle, apply=False)
    moved = {e["path"] for e in entries}
    assert moved == {
        "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.gds",
        "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.def",
        "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.spef",
        "synth_runs/s1/orfs_results/sky130hd/top/base/1_1_yosys.rtlil",
        "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.v",
        "synth_runs/s1/orfs_results/sky130hd/top/base/mem.json",
        "synth_runs/s1/orfs_results/sky130hd/top/base/route.guide",
        "synth_runs/s1/orfs_reports/sky130hd/top/base/final_all.webp",
    }
    # Nothing deleted, no manifest written.
    assert os.path.isfile(os.path.join(ws, "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.gds"))
    assert not os.path.exists(os.path.join(ws, S.SC_BINARIES_NAME))


def test_apply_writes_manifest_and_moves_only_binaries(tmp_path):
    ws = _make_bundle(str(tmp_path))
    bundle = os.path.dirname(ws)
    gds = os.path.join(ws, "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.gds")
    expected_sha = hashlib.sha256(open(gds, "rb").read()).hexdigest()

    S.split_bundle(bundle, apply=True)

    # Manifest shape.
    manifest = json.load(open(os.path.join(ws, S.SC_BINARIES_NAME), encoding="utf-8"))
    assert manifest["version"] == S.SC_BINARIES_VERSION
    paths = [f["path"] for f in manifest["files"]]
    assert paths == sorted(paths)  # deterministic ordering
    assert all(set(f) == {"path", "bytes", "sha256"} for f in manifest["files"])
    gds_entry = next(f for f in manifest["files"] if f["path"].endswith("6_final.gds"))
    assert gds_entry["sha256"] == expected_sha
    assert gds_entry["bytes"] == 300

    base = "synth_runs/s1/orfs_results/sky130hd/top/base"
    # Binaries gone — including mem.json (exact name) and route.guide.
    assert not os.path.exists(gds)
    assert not os.path.exists(os.path.join(ws, base, "6_final.v"))
    assert not os.path.exists(os.path.join(ws, base, "mem.json"))
    assert not os.path.exists(os.path.join(ws, base, "route.guide"))
    # Kept: markers/reports, a NON-mem .json, inputs/source .v.
    assert os.path.isfile(os.path.join(ws, base, "5_route.sdc"))
    assert os.path.isfile(os.path.join(ws, base, "1_synth.json"))
    assert os.path.isfile(os.path.join(ws, "synth_runs/s1/orfs_reports/sky130hd/top/base/6_finish.rpt"))
    assert os.path.isfile(os.path.join(ws, "synth_runs/s1/inputs/top.v"))
    assert os.path.isfile(os.path.join(ws, "top.v"))


def test_apply_is_idempotent(tmp_path):
    ws = _make_bundle(str(tmp_path))
    bundle = os.path.dirname(ws)
    S.split_bundle(bundle, apply=True)
    manifest_after_first = open(os.path.join(ws, S.SC_BINARIES_NAME), encoding="utf-8").read()

    # Second apply: no binaries remain, so nothing to move and the manifest is
    # left byte-identical (idempotent).
    second = S.split_bundle(bundle, apply=True)
    assert second == []
    assert open(os.path.join(ws, S.SC_BINARIES_NAME), encoding="utf-8").read() == manifest_after_first


def test_bundle_without_binaries_is_untouched(tmp_path):
    # sync_fifo shape: a workspace with no orfs_results/orfs_reports payload.
    ws = os.path.join(str(tmp_path), "sync_fifo", "workspace")
    _write(os.path.join(ws, "fifo.v"), "module fifo(); endmodule\n")
    _write(os.path.join(ws, "manifest.json"), "{}\n")
    bundle = os.path.dirname(ws)
    assert S.split_bundle(bundle, apply=True) == []
    assert not os.path.exists(os.path.join(ws, S.SC_BINARIES_NAME))
    assert os.path.isfile(os.path.join(ws, "fifo.v"))


# ---------------------------------------------------------------------------
# A1 parity: split must not change get_synthesis_metrics / stage completion
# ---------------------------------------------------------------------------


def _real_bundle_dir():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "examples", "aes_invsbox")


def test_split_preserves_metrics_and_stage_status(tmp_path):
    """Copy a real bundle, inject dummy binaries, and assert the split leaves
    ``get_synthesis_metrics`` and the stage-completion set byte-identical."""
    from src.tools.synthesis_manager import (
        get_synthesis_metrics,
        _find_stage_completion_marker,
        PD_STAGE_SEQUENCE,
    )

    src_bundle = _real_bundle_dir()
    if not os.path.isdir(src_bundle):
        pytest.skip("aes_invsbox example bundle not present")

    bundle = os.path.join(str(tmp_path), "aes_invsbox")
    shutil.copytree(src_bundle, bundle)
    ws = os.path.join(bundle, "workspace")
    run_dir = os.path.join(ws, "synth_runs", "synth_0001")
    base_res = os.path.join(run_dir, "orfs_results", "sky130hd", "sbox_aesinv", "base")
    base_rep = os.path.join(run_dir, "orfs_reports", "sky130hd", "sbox_aesinv", "base")

    # Guarantee the split has heavy files to remove regardless of whether the
    # committed tree is already split — these types are never read by metrics.
    os.makedirs(base_res, exist_ok=True)
    os.makedirs(base_rep, exist_ok=True)
    _write(os.path.join(base_res, "6_final.gds"), b"DUMMYGDS" * 1000)
    _write(os.path.join(base_res, "6_final.v"), b"module x(); endmodule\n")
    _write(os.path.join(base_rep, "injected.webp"), b"DUMMYWEBP" * 100)

    def snapshot():
        metrics = get_synthesis_metrics(ws, "synth_0001").get("metrics")
        stages = {s: _find_stage_completion_marker(run_dir, s) is not None for s in PD_STAGE_SEQUENCE}
        return metrics, stages

    before = snapshot()
    entries = S.split_bundle(bundle, apply=True)
    # The injected heavy files were actually moved (test is meaningful).
    moved = {e["path"] for e in entries}
    assert any(p.endswith("6_final.gds") for p in moved)
    assert any(p.endswith("injected.webp") for p in moved)
    after = snapshot()

    assert before == after
