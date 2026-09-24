"""A retry_pd child run records what it actually ran with.

Two defects seen by the overnight run of 2026-09-23 (L1 counter, L2 arbiter; both
agents reported them):
- the child's run_meta said `utilization: 20` while its config.mk exported 20 then
  the CORE_UTILIZATION=15 override, and make used 15;
- the child had no synth_stat.txt, so area_um2 / cell_count came back null for a
  completed run built from its parent's synthesized netlist.
"""
import json
import os
import shutil
import time

from src.tools import synthesis_manager as sm

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "retry_pd_workspace")
STAT = "Chip area for module '\\demo_top': 172.67\n16 1.0 cells\n"


def _workspace(tmp_path) -> str:
    ws = str(tmp_path / "ws")
    shutil.copytree(FIXTURE, ws)
    parent = os.path.join(ws, "synth_runs", "synth_0001")
    reports = os.path.join(parent, "orfs_reports", "sky130hd", "demo_top", "base")
    os.makedirs(reports, exist_ok=True)
    with open(os.path.join(reports, "synth_stat.txt"), "w", encoding="utf-8") as f:
        f.write(STAT)
    return ws


def _fake_targets(**kwargs):
    base = os.path.join(kwargs["run_dir"], "orfs_%s", "sky130hd", "demo_top", "base")
    for scope, name, body in [
        ("reports", "6_finish.rpt", "wns max 0.05\n"),
        ("reports", "5_route_drc.rpt", ""),
        ("results", "5_route.odb", ""),
        ("results", "6_final.v", "module demo_top(input clk, output y); endmodule"),
    ]:
        d = base % scope
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(body)
    return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}


def _retry(ws, overrides):
    started = sm.retry_pd_job(workspace=ws, source_run_id="synth_0001", start_stage="cts",
                              max_stage="finish", orfs_overrides_json=json.dumps(overrides))
    assert started["status"] == "queued", started
    for _ in range(80):
        st = sm.get_synthesis_status(started["run_id"], workspace=ws)
        if st["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    with open(os.path.join(ws, "synth_runs", started["run_id"], "run_meta.json"), encoding="utf-8") as f:
        return json.load(f)


def test_retry_records_the_utilization_make_used(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_run_orfs_targets", _fake_targets)
    meta = _retry(_workspace(tmp_path), {"CORE_UTILIZATION": 15})

    assert meta["status"] == "completed"
    assert meta["utilization"] == 15
    assert meta["pd_parameters"]["utilization"] == 15


def test_retry_child_reports_its_parents_synth_area_and_cells(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_run_orfs_targets", _fake_targets)
    meta = _retry(_workspace(tmp_path), {})

    assert meta["status"] == "completed"
    assert meta["summary_metrics"]["cell_count"] == 16
    assert meta["summary_metrics"]["area_um2"] == 172.67


def test_config_mk_reads_the_last_export_like_make(tmp_path):
    run_dir = str(tmp_path)
    with open(os.path.join(run_dir, "config.mk"), "w", encoding="utf-8") as f:
        f.write("export CORE_UTILIZATION = 20\nexport CORE_MARGIN = 6\nexport CORE_UTILIZATION = 15\n")

    assert sm._read_config_mk_pd_parameters(run_dir) == {"utilization": 15, "core_margin": 6.0}


def test_a_fractional_utilization_survives_a_retry_of_a_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_run_orfs_targets", _fake_targets)
    ws = _workspace(tmp_path)
    child = _retry(ws, {"CORE_UTILIZATION": 15.5})
    assert child["utilization"] == 15.5

    # No new override: the grandchild must run what its parent ran.
    grandchild = sm._pd_parameters_from_run(os.path.join(ws, "synth_runs", child["run_id"]), child)
    assert grandchild["utilization"] == 15.5
