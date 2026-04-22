import json
import os
import shutil
import tempfile

from src.tools import wrappers
from src.tools.synthesis_manager import get_synthesis_metrics, read_stage_report


def _repo_local_tempdir(test_name: str) -> str:
    root = os.path.join(os.path.dirname(__file__), "_tmp")
    os.makedirs(root, exist_ok=True)
    return tempfile.mkdtemp(prefix=f"{test_name}_", dir=root)


def test_wait_for_synthesis_bounded_loop(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        old = os.environ.get("RTL_WORKSPACE")
        os.environ["RTL_WORKSPACE"] = workspace
        try:
            calls = {"n": 0}

            def _fake_status(job_id, workspace=None):
                calls["n"] += 1
                if calls["n"] < 3:
                    return {"job_id": job_id, "status": "running", "poll_after_sec": 1, "next_action": "wait/poll"}
                return {"job_id": job_id, "status": "completed", "poll_after_sec": 0, "next_action": "done"}

            monkeypatch.setattr(wrappers, "get_synthesis_job_status", _fake_status)
            monkeypatch.setattr(wrappers.time, "sleep", lambda *_: None)

            out = wrappers.wait_for_synthesis.invoke({"job_id": "job_x", "max_wait_sec": 10, "poll_interval_sec": 1})
            data = json.loads(out)
            assert data["status"] == "completed"
            assert data["timed_out"] is False
            assert calls["n"] >= 3
        finally:
            if old is None:
                os.environ.pop("RTL_WORKSPACE", None)
            else:
                os.environ["RTL_WORKSPACE"] = old


def test_get_synthesis_metrics_parses_finish_and_stat_reports():
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0002")
        report_dir = os.path.join(run_dir, "orfs_reports", "sky130hd", "exp_fixed_point", "base")
        os.makedirs(report_dir, exist_ok=True)

        with open(os.path.join(workspace, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
            f.write("synth_0002")
        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "synth_0002", "top_module": "exp_fixed_point", "platform": "sky130hd"}, f)

        with open(os.path.join(report_dir, "6_finish.rpt"), "w", encoding="utf-8") as f:
            f.write(
                "tns max 0.00\n"
                "wns max 0.31\n"
                "setup violation count 0\n"
                "hold violation count 0\n"
                "Total                  1.64e-03   1.11e-03   3.80e-09   2.75e-03 100.0%\n"
            )
        with open(os.path.join(report_dir, "synth_stat.txt"), "w", encoding="utf-8") as f:
            f.write(
                "      814 7.33E+03 cells\n"
                "Chip area for module '\\exp_fixed_point': 7332.032000\n"
            )

        metrics = get_synthesis_metrics(workspace=workspace, run_id="synth_0002")
        assert metrics["status"] == "ok"
        assert metrics["metrics"]["area_um2"] == 7332.032
        assert metrics["metrics"]["cell_count"] == 814
        assert metrics["metrics"]["wns_ns"] == 0.31
        assert metrics["metrics"]["tns_ns"] == 0.0
        assert round(metrics["metrics"]["power_uw"], 1) == 2750.0
        assert metrics["complete"] is True


def test_read_stage_report_reads_floorplan_report():
    workspace = _repo_local_tempdir("stage_floorplan")
    try:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0003")
        report_dir = os.path.join(run_dir, "orfs_reports", "sky130hd", "demo_top", "base")
        os.makedirs(report_dir, exist_ok=True)

        with open(os.path.join(workspace, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
            f.write("synth_0003")
        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "synth_0003", "top_module": "demo_top", "platform": "sky130hd"}, f)
        with open(os.path.join(report_dir, "2_floorplan_final.rpt"), "w", encoding="utf-8") as f:
            f.write("floorplan summary\ncore_area 123.4\n")

        report = read_stage_report(workspace=workspace, run_id="synth_0003", stage="floorplan")
        assert report["status"] == "ok"
        assert report["stage"] == "floorplan"
        assert report["artifact_name"] == "2_floorplan_final.rpt"
        assert "floorplan summary" in report["content_excerpt"]
        assert report["content_truncated"] is False
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_read_stage_report_reads_place_log():
    workspace = _repo_local_tempdir("stage_place")
    try:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0004")
        log_dir = os.path.join(run_dir, "orfs_logs", "sky130hd", "demo_top", "base")
        os.makedirs(log_dir, exist_ok=True)

        with open(os.path.join(workspace, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
            f.write("synth_0004")
        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "synth_0004", "top_module": "demo_top", "platform": "sky130hd"}, f)
        with open(os.path.join(log_dir, "3_3_place_gp.json"), "w", encoding="utf-8") as f:
            f.write("{\"stage\":\"place\",\"overflow\":0}")

        report = read_stage_report(workspace=workspace, run_id="synth_0004", stage="place")
        assert report["status"] == "ok"
        assert report["artifact_scope"] == "orfs_logs"
        assert report["artifact_name"] == "3_3_place_gp.json"
        assert "\"overflow\":0" in report["content_excerpt"]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_run_synthesis_and_wait_combines_start_and_wait(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        old = os.environ.get("RTL_WORKSPACE")
        os.environ["RTL_WORKSPACE"] = workspace
        try:
            design = os.path.join(workspace, "counter.v")
            with open(design, "w", encoding="utf-8") as f:
                f.write("module counter(input clk, output reg [3:0] q); always @(posedge clk) q<=q+1; endmodule")

            monkeypatch.setattr(
                wrappers,
                "start_synthesis_job",
                lambda **kwargs: {"job_id": "job_abc", "run_id": "synth_0001", "status": "queued", "stage": "unknown"},
            )
            monkeypatch.setattr(
                wrappers,
                "get_synthesis_job_status",
                lambda *args, **kwargs: {"job_id": "job_abc", "status": "completed", "poll_after_sec": 0},
            )
            monkeypatch.setattr(wrappers.time, "sleep", lambda *_: None)

            out = wrappers.run_synthesis_and_wait.invoke(
                {"verilog_files": ["counter.v"], "top_module": "counter", "max_wait_sec": 10}
            )
            data = json.loads(out)
            assert data["start"]["job_id"] == "job_abc"
            assert data["result"]["status"] == "completed"
        finally:
            if old is None:
                os.environ.pop("RTL_WORKSPACE", None)
            else:
                os.environ["RTL_WORKSPACE"] = old
