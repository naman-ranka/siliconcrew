import json
import os
import tempfile
import shutil

import pytest

from src.tools.search_logs import search_logs
from src.tools import stdcells as std
from src.tools.stdcells import resolve_stdcell_models


def test_search_logs_with_run_id_scope():
    with tempfile.TemporaryDirectory() as workspace:
        run_logs = os.path.join(workspace, "synth_runs", "synth_0001", "orfs_logs")
        other_logs = os.path.join(workspace, "synth_runs", "synth_0002", "orfs_logs")
        os.makedirs(run_logs, exist_ok=True)
        os.makedirs(other_logs, exist_ok=True)

        with open(os.path.join(run_logs, "a.log"), "w", encoding="utf-8") as f:
            f.write("WNS 0.10\n")
        with open(os.path.join(other_logs, "b.log"), "w", encoding="utf-8") as f:
            f.write("WNS -9.99\n")

        out = search_logs("WNS", workspace_dir=workspace, run_id="synth_0001")
        assert "synth_0001" in out
        assert "synth_0002" not in out


def test_resolve_stdcell_models_missing_cache_raises():
    with tempfile.TemporaryDirectory() as workspace:
        with pytest.raises(FileNotFoundError):
            resolve_stdcell_models(workspace, "asap7")


def test_resolve_stdcell_models_from_manifest_cache():
    with tempfile.TemporaryDirectory() as workspace:
        sim_dir = os.path.join(workspace, "_stdcells", "asap7", "sim")
        os.makedirs(sim_dir, exist_ok=True)
        with open(os.path.join(sim_dir, "a.v"), "w", encoding="utf-8") as f:
            f.write("module a; endmodule")
        with open(os.path.join(sim_dir, "b.v"), "w", encoding="utf-8") as f:
            f.write("module b; endmodule")
        with open(os.path.join(sim_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"platform": "asap7", "files": [{"name": "a.v"}, {"name": "b.v"}]}, f)

        files, manifest = resolve_stdcell_models(workspace, "asap7")
        assert [os.path.basename(x) for x in files] == ["a.v", "b.v"]
        assert manifest["platform"] == "asap7"


def test_bootstrap_stdcells_writes_manifest(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        copied_tree = tempfile.mkdtemp()
        src_dir = os.path.join(copied_tree, "stdcell")
        os.makedirs(src_dir, exist_ok=True)
        with open(os.path.join(src_dir, "NAND2X1.v"), "w", encoding="utf-8") as f:
            f.write("module NAND2X1; endmodule")

        monkeypatch.setattr(std, "_docker_container_create", lambda image: "cid-test")
        monkeypatch.setattr(std.subprocess, "run", lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})())

        def fake_cp(container_id, src, dst):
            shutil.copytree(src_dir, os.path.join(dst, "stdcell"), dirs_exist_ok=True)
            return True

        monkeypatch.setattr(std, "_docker_cp", fake_cp)

        result = std.bootstrap_stdcells(workspace=workspace, platform="asap7", image="fake:image")
        assert result["file_count"] >= 1
        assert os.path.exists(result["manifest"])
