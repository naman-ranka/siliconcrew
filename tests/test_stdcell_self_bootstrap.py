"""Post-synth sim on a self-host checkout bootstraps a missing stdcell cache.

The models are baked into the hosted image only. A self-host checkout starts
with no ``_stdcells/`` and nothing else populates it, so post-synth sim used to
return ``stdcell_cache_missing`` forever while its recovery text claimed the
next run would retry the bootstrap. Found by the overnight run of 2026-09-23
(headless Claude over MCP, fresh worktree).
"""
import os

import pytest

from src.tools import run_simulation as rs
from src.tools import sim_contract as sc
from src.tools import stdcells as std


class _CompileReached(Exception):
    pass


def _setup(monkeypatch, tmp_path, *, hosted, bootstrap):
    ws = tmp_path / "ws"
    ws.mkdir()
    netlist = ws / "6_final.v"
    netlist.write_text("module top(); endmodule\n", encoding="utf-8")
    install_root = tmp_path / "install"  # no _stdcells/ inside: a fresh checkout
    install_root.mkdir()

    monkeypatch.setattr(sc, "resolve_post_synth", lambda **_: (
        sc.PostSynthResolution(netlist_abs=str(netlist), platform="sky130hd"), None))
    monkeypatch.setattr(rs, "stdcell_root", lambda: str(install_root))
    monkeypatch.setattr(rs, "_hosted", lambda: hosted, raising=False)
    calls = []

    def fake_bootstrap(workspace, platform):
        calls.append((workspace, platform))
        return bootstrap(workspace, platform)

    monkeypatch.setattr(rs, "bootstrap_stdcells", fake_bootstrap, raising=False)
    compiled = {}

    def fake_compile(compile_files, **_):
        compiled["files"] = compile_files
        raise _CompileReached()

    monkeypatch.setattr(rs, "_compile", fake_compile)
    return str(ws), str(install_root), calls, compiled


def _populate(workspace, platform):
    cache = std.stdcell_cache_dir(workspace, platform)
    os.makedirs(cache, exist_ok=True)
    with open(os.path.join(cache, "sky130_fd_sc_hd__inv_1.v"), "w", encoding="utf-8") as f:
        f.write("module sky130_fd_sc_hd__inv_1(input A, output Y); assign Y = ~A; endmodule\n")
    return {"platform": platform, "file_count": 1}


def test_self_host_cache_miss_bootstraps_and_compiles_with_the_models(monkeypatch, tmp_path):
    ws, root, calls, compiled = _setup(monkeypatch, tmp_path, hosted=False, bootstrap=_populate)

    with pytest.raises(_CompileReached):
        rs.run_simulation(verilog_files=[], top_module="tb", cwd=ws, workspace=ws, mode="post_synth")

    assert calls == [(root, "sky130hd")]
    assert any(p.endswith("sky130_fd_sc_hd__inv_1.v") for p in compiled["files"])


def test_self_host_bootstrap_failure_is_reported_honestly(monkeypatch, tmp_path):
    def offline(workspace, platform):
        raise OSError("network unreachable")

    ws, _, calls, _ = _setup(monkeypatch, tmp_path, hosted=False, bootstrap=offline)

    out = rs.run_simulation(verilog_files=[], top_module="tb", cwd=ws, workspace=ws, mode="post_synth")

    assert len(calls) == 1
    assert out["outcome"] == "stdcell_cache_missing"
    assert out["stdcell_bootstrap_attempted"] is True
    assert "network unreachable" in out["stdcell_bootstrap_result"]["error"]
    assert "retries the bootstrap" not in out["recovery"]["detail"]


def test_hosted_cache_miss_is_reported_not_bootstrapped(monkeypatch, tmp_path):
    ws, _, calls, _ = _setup(monkeypatch, tmp_path, hosted=True, bootstrap=_populate)

    out = rs.run_simulation(verilog_files=[], top_module="tb", cwd=ws, workspace=ws, mode="post_synth")

    assert calls == []
    assert out["outcome"] == "stdcell_cache_missing"
    assert out["stdcell_bootstrap_attempted"] is False
