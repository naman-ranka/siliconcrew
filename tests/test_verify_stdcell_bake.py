import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.verify_stdcell_bake import MIN_MODELS, main  # noqa: E402


def _write_manifest(workspace, platform, *, files=None, failed=None):
    cache = os.path.join(workspace, "_stdcells", platform, "sim")
    os.makedirs(cache, exist_ok=True)
    manifest = {
        "platform": platform,
        "sources": {"pinned_source": {"failed": failed or []}},
        "files": [{"name": f"m{i}.v", "sha256": "x"} for i in range(files or 0)],
    }
    with open(os.path.join(cache, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)


def _run(workspace):
    argv = sys.argv
    sys.argv = ["verify_stdcell_bake.py", "--workspace", str(workspace)]
    try:
        return main()
    finally:
        sys.argv = argv


def _write_clean(workspace):
    for platform, minimum in MIN_MODELS.items():
        _write_manifest(workspace, platform, files=minimum + 2)


def test_clean_manifests_pass(tmp_path):
    _write_clean(tmp_path)
    assert _run(tmp_path) == 0


def test_partial_download_failures_fail(tmp_path):
    _write_clean(tmp_path)
    _write_manifest(tmp_path, "sky130hd", files=600, failed=["sky130_fd_sc_hd.v: HTTP 404"])
    assert _run(tmp_path) == 1


def test_below_platform_floor_fails(tmp_path):
    _write_clean(tmp_path)
    _write_manifest(tmp_path, "sky130hd", files=MIN_MODELS["sky130hd"] - 1)
    assert _run(tmp_path) == 1


def test_missing_manifest_fails(tmp_path):
    _write_manifest(tmp_path, "asap7", files=MIN_MODELS["asap7"] + 1)
    # sky130hd manifest absent entirely
    assert _run(tmp_path) == 1


def test_corrupt_manifest_fails_cleanly(tmp_path, capsys):
    _write_clean(tmp_path)
    truncated = os.path.join(tmp_path, "_stdcells", "asap7", "sim", "manifest.json")
    with open(truncated, "w", encoding="utf-8") as f:
        f.write('{"sources": {"pinned')
    assert _run(tmp_path) == 1
    assert "manifest unreadable" in capsys.readouterr().out


def test_floors_match_known_platform_counts():
    # Guard the per-platform floors themselves: asap7 legitimately ships only
    # 7 models — a shared floor of 100 would fail every good build.
    assert MIN_MODELS["asap7"] <= 7
    assert MIN_MODELS["sky130hd"] <= 622
