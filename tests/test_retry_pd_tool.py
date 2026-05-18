import json
import os
import shutil
import time

from src.tools import synthesis_manager as sm


def _fixture_workspace() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "retry_pd_workspace")


def _reset_workspace(workspace: str) -> None:
    synth_runs = os.path.join(workspace, "synth_runs")
    for name in os.listdir(synth_runs):
        path = os.path.join(synth_runs, name)
        if name == "synth_0001":
            continue
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _wait_for_terminal(job_id: str, workspace: str) -> dict:
    for _ in range(60):
        status = sm.get_synthesis_job_status(job_id, workspace=workspace)
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    raise AssertionError("job did not reach terminal status")


def test_retry_pd_job_validates_missing_prerequisites():
    workspace = _fixture_workspace()
    result = sm.retry_pd_job(
        workspace=workspace,
        source_run_id="synth_missing",
        start_stage="cts",
        max_stage="finish",
    )
    assert result["status"] == "error"


def test_retry_pd_job_creates_child_run_and_lineage(monkeypatch):
    workspace = _fixture_workspace()
    _reset_workspace(workspace)

    calls = {}

    def fake_run_targets(**kwargs):
        calls["targets"] = kwargs["targets"]
        calls["orfs_overrides"] = kwargs["orfs_overrides"]
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "demo_top", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "demo_top", "base")
        logs = os.path.join(run_dir, "orfs_logs", "sky130hd", "demo_top", "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(reports, "4_cts_final.rpt"), "w", encoding="utf-8") as f:
            f.write("cts\n")
        with open(os.path.join(logs, "5_1_grt.log"), "w", encoding="utf-8") as f:
            f.write("[INFO GRT-0096] Final congestion report:\nTotal 10 2 20.0% 0 / 0 / 0\n")
        with open(os.path.join(reports, "5_route_drc.rpt"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(reports, "6_finish.rpt"), "w", encoding="utf-8") as f:
            f.write("wns max 0.05\n")
        with open(os.path.join(results, "4_cts.odb"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(results, "5_1_grt.odb"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(results, "5_route.odb"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(results, "6_final.v"), "w", encoding="utf-8") as f:
            f.write("module demo_top(input clk, output y); endmodule")
        return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs_targets", fake_run_targets)

    started = sm.retry_pd_job(
        workspace=workspace,
        source_run_id="synth_0001",
        start_stage="cts",
        max_stage="finish",
        orfs_overrides_json='{"CTS_BUF_DISTANCE": 100}',
    )
    assert started["status"] == "queued"
    assert started["mode"] == "pd_retry"

    final = _wait_for_terminal(started["job_id"], workspace)
    assert final["status"] == "completed"
    assert final["current_stage"] == "finish"
    assert final["stages"]["cts"]["status"] == "completed"
    assert final["stages"]["finish"]["status"] == "completed"
    assert calls["targets"] == ["do-cts", "do-grt", "do-route", "do-finish"]
    assert calls["orfs_overrides"]["CTS_BUF_DISTANCE"] == 100

    run_meta = os.path.join(workspace, "synth_runs", started["run_id"], "run_meta.json")
    with open(run_meta, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["mode"] == "pd_retry"
    assert data["parent_run_id"] == "synth_0001"
    assert data["retry_start_stage"] == "cts"
    assert data["retry_max_stage"] == "finish"


def test_retry_pd_job_copies_root_level_spec_when_present(monkeypatch):
    workspace = _fixture_workspace()
    _reset_workspace(workspace)

    parent_run = os.path.join(workspace, "synth_runs", "synth_0001")
    root_spec = os.path.join(parent_run, "demo_top_spec.yaml")
    with open(root_spec, "w", encoding="utf-8") as f:
        f.write("demo_top:\n  description: root-spec\n")

    meta_path = os.path.join(parent_run, "run_meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["spec_file"] = "demo_top_spec.yaml"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    def fake_run_targets(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "demo_top", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "demo_top", "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        with open(os.path.join(reports, "4_cts_final.rpt"), "w", encoding="utf-8") as f:
            f.write("cts\n")
        with open(os.path.join(reports, "5_route_drc.rpt"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(reports, "6_finish.rpt"), "w", encoding="utf-8") as f:
            f.write("wns max 0.05\n")
        with open(os.path.join(results, "4_cts.odb"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(results, "5_1_grt.odb"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(results, "5_route.odb"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(results, "6_final.v"), "w", encoding="utf-8") as f:
            f.write("module demo_top(input clk, output y); endmodule")
        return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs_targets", fake_run_targets)

    started = sm.retry_pd_job(
        workspace=workspace,
        source_run_id="synth_0001",
        start_stage="cts",
        max_stage="finish",
    )
    final = _wait_for_terminal(started["job_id"], workspace)
    assert final["status"] == "completed"

    run_meta = os.path.join(workspace, "synth_runs", started["run_id"], "run_meta.json")
    with open(run_meta, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["spec_file"] == "demo_top_spec.yaml"
    assert os.path.exists(os.path.join(workspace, "synth_runs", started["run_id"], "spec", "demo_top_spec.yaml"))
