"""start_synthesis max_stage: bounded (partial) first-run flows.

A first run may now stop at any stage of PD_STAGE_SEQUENCE (constraints..finish)
instead of always paying the full RTL->GDS flow. Covers:
- max_stage validation (same rejected shape as retry_pd);
- bounded execution switches to the target-based runner (_run_orfs_targets)
  and never calls the full-flow _run_orfs;
- honest terminal metadata: run_meta carries max_stage, current_stage ends at
  the bound, stages after the bound are "skipped" (not "pending");
- read-time reconciliation keys on the TARGET stage's artifact for partial
  runs, never on 6_finish.rpt;
- signoff/equiv auto-checks are skipped-with-note for partial runs and
  next_action points at retry_pd for the continuation;
- retry_pd prerequisite validation composes with partial parents;
- REST /synthesize forwards maxStage.

ORFS/docker is never available here: the execution layer is stubbed exactly
like tests/test_synthesis_manager.py and tests/test_retry_pd_tool.py do.
"""
import json
import os
import time

import pytest

from src.tools import synthesis_manager as sm
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_counter_workspace(workspace: str) -> str:
    design = os.path.join(workspace, "counter.v")
    _write_file(
        design,
        "module counter(input clk, input rst, output reg [3:0] q); "
        "always @(posedge clk) if(rst) q<=0; else q<=q+1; endmodule",
    )
    spec = DesignSpec(
        module_name="counter",
        description="counter",
        clock_period_ns=10.0,
        ports=[PortSpec(name="clk", direction="input"), PortSpec(name="rst", direction="input")],
    )
    save_yaml_file(spec, os.path.join(workspace, "counter_spec.yaml"))
    return design


def _wait_for_terminal(run_id: str, workspace: str) -> dict:
    for _ in range(80):
        status = sm.get_synthesis_status(run_id, workspace=workspace)
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    raise AssertionError("job did not reach terminal status")


def _fake_synth_only_orfs(calls: dict):
    """Stub for _run_orfs_targets that produces synth-stage artifacts only."""

    def fake(**kwargs):
        calls["targets"] = kwargs["targets"]
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base")
        _write_file(
            os.path.join(reports, "synth_stat.txt"),
            "Chip area for module '\\counter': 123.45\n814 7.33E+03 cells\n",
        )
        _write_file(os.path.join(results, "1_synth.odb"), "odb")
        _write_file(os.path.join(results, "1_synth.sdc"), "sdc")
        _write_file(
            os.path.join(results, "1_synth.v"),
            "module counter(input clk, input rst, output [3:0] q); endmodule",
        )
        return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}

    return fake


def _forbid_full_flow(monkeypatch):
    def boom(**kwargs):
        raise AssertionError("_run_orfs (full flow) must not run for a bounded first run")

    monkeypatch.setattr(sm, "_run_orfs", boom)


# ---- validation --------------------------------------------------------------


def test_invalid_max_stage_rejected_before_any_work(tmp_path):
    workspace = str(tmp_path / "ws")
    result = sm.start_synthesis_job(
        workspace=workspace,
        verilog_files=["counter.v"],
        top_module="counter",
        max_stage="gds",
    )
    assert result["status"] == "error"
    assert "Unsupported max_stage 'gds'" in result["message"]
    # Validated against the FULL sequence (constraints..finish), same shape
    # retry_pd uses for its stage rejections.
    assert result["supported_stages"] == sm.PD_STAGE_SEQUENCE
    # Rejected before allocating a run dir (or even the workspace).
    assert not os.path.exists(os.path.join(workspace, "synth_runs"))


def test_first_run_targets_cover_synth_through_bound():
    assert sm._first_run_targets("synth") == ["do-synth"]
    assert sm._first_run_targets("cts") == ["do-synth", "do-floorplan", "do-place", "do-cts"]
    assert sm._first_run_targets("route") == [
        "do-synth", "do-floorplan", "do-place", "do-cts", "do-grt", "do-route",
    ]


# ---- bounded first run end-to-end ---------------------------------------------


def test_synth_only_run_completes_with_skipped_downstream(tmp_path, monkeypatch):
    workspace = str(tmp_path)
    design = _make_counter_workspace(workspace)
    calls: dict = {}
    monkeypatch.setattr(sm, "_run_orfs_targets", _fake_synth_only_orfs(calls))
    _forbid_full_flow(monkeypatch)

    started = sm.start_synthesis_job(
        workspace=workspace,
        verilog_files=[design],
        top_module="counter",
        platform="sky130hd",
        max_stage=" SYNTH ",  # normalized like retry_pd stage args
    )
    assert started["status"] == "queued"

    final = _wait_for_terminal(started["run_id"], workspace)
    assert final["status"] == "completed"
    assert calls["targets"] == ["do-synth"]

    # auto-checks that need finish artifacts are skipped with an explicit note.
    assert final["auto_checks"]["constraints"] == "pass"
    assert final["auto_checks"]["signoff"] == "skip"
    assert final["auto_checks"]["equiv"] == "skip"
    assert "partial flow (max_stage=synth)" in final["check_notes"]
    # next_action suggests the continuation path via retry_pd from floorplan.
    assert "retry_pd" in final["next_action"]
    assert "floorplan" in final["next_action"]

    meta_path = os.path.join(workspace, "synth_runs", started["run_id"], "run_meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["max_stage"] == "synth"
    assert data["status"] == "completed"
    # completed run ends AT its bound, not at "finish"
    assert data["current_stage"] == "synth"
    assert data["stages"]["constraints"]["status"] == "completed"
    assert data["stages"]["synth"]["status"] == "completed"
    for stage in ["floorplan", "place", "cts", "grt", "route", "finish"]:
        assert data["stages"][stage]["status"] == "skipped", stage

    # Stage table + file-derived history come from the unified status payload
    # (get_stage_status was folded into get_synthesis_status in Wave 9).
    stage_status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
    skipped = {s for s, m in stage_status["stages"].items() if m.get("status") == "skipped"}
    assert skipped == {"floorplan", "place", "cts", "grt", "route", "finish"}
    assert not any(m.get("status") == "pending" for m in stage_status["stages"].values())
    history = {h["stage"]: h["status"] for h in stage_status["stage_history"]}
    assert history["synth"] == "completed"
    for stage in ["floorplan", "place", "cts", "grt", "route", "finish"]:
        assert history[stage] == "skipped", stage

    # PPA degrades gracefully: area/cells from synth_stat.txt, timing/power
    # honestly listed as missing (no finish reports for a synth-only run).
    metrics = sm.get_synthesis_metrics(workspace=workspace, run_id=started["run_id"])
    assert metrics["status"] == "ok"
    assert metrics["metrics"]["area_um2"] == 123.45
    assert metrics["metrics"]["cell_count"] == 814
    assert metrics["metrics"]["wns_ns"] is None
    assert metrics["complete"] is False
    assert set(metrics["missing_fields"]) == {"wns_ns", "tns_ns", "power_uw"}
    assert any("partial flow (max_stage=synth)" in n for n in metrics["parse_notes"])


def test_constraints_only_run_skips_orfs_entirely(tmp_path, monkeypatch):
    """max_stage may be any stage of the sequence, including one before synth."""
    workspace = str(tmp_path)
    design = _make_counter_workspace(workspace)
    _forbid_full_flow(monkeypatch)
    monkeypatch.setattr(
        sm, "_run_orfs_targets",
        lambda **k: (_ for _ in ()).throw(AssertionError("no ORFS for constraints-only")),
    )

    started = sm.start_synthesis_job(
        workspace=workspace,
        verilog_files=[design],
        top_module="counter",
        max_stage="constraints",
    )
    final = _wait_for_terminal(started["run_id"], workspace)
    assert final["status"] == "completed"
    assert final["current_stage"] == "constraints"
    assert final["auto_checks"]["constraints"] == "pass"
    assert final["auto_checks"]["signoff"] == "skip"
    for stage in sm.PD_STAGE_SEQUENCE[1:]:
        assert final["stages"][stage]["status"] == "skipped", stage
    # "synth" is not retry-able, so the continuation is a rerun, not retry_pd.
    assert "start_synthesis" in final["next_action"]


def test_full_flow_default_still_uses_run_orfs(tmp_path, monkeypatch):
    """Default max_stage='finish' keeps the historical full-flow runner."""
    workspace = str(tmp_path)
    design = _make_counter_workspace(workspace)
    used = {"full": False}

    def fake_orfs(**kwargs):
        used["full"] = True
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base")
        _write_file(os.path.join(reports, "x.rpt"), "Chip area for module 'counter': 5.0\n")
        _write_file(
            os.path.join(results, "6_final.v"),
            "module counter(input clk,input rst,output [3:0] q);endmodule",
        )
        return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs", fake_orfs)
    monkeypatch.setattr(
        sm, "_run_orfs_targets",
        lambda **k: (_ for _ in ()).throw(AssertionError("full flow must use _run_orfs")),
    )

    started = sm.start_synthesis_job(
        workspace=workspace, verilog_files=[design], top_module="counter",
    )
    final = _wait_for_terminal(started["run_id"], workspace)
    assert final["status"] == "completed"
    assert used["full"] is True

    meta_path = os.path.join(workspace, "synth_runs", started["run_id"], "run_meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["max_stage"] == "finish"
    assert data["current_stage"] == "finish"
    assert "skipped" not in {s.get("status") for s in data["stages"].values()}


# ---- stale-status reconciliation for partial runs ------------------------------


def test_reconcile_partial_run_keys_on_target_stage_artifact(tmp_path):
    run_dir = str(tmp_path)
    _write_file(
        os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "synth_stat.txt"),
        "Chip area for module '\\counter': 12.0\n10 1.0 cells\n",
    )
    meta = {"status": "running", "run_id": "synth_0001", "max_stage": "synth"}

    out = sm._reconcile_stale_status(run_dir, meta)

    # No 6_finish.rpt anywhere — a synth-only run never produces one — yet the
    # run reconciles as completed off its own stage marker.
    assert out["status"] == "completed"
    assert out["finished_at"]
    assert out["current_stage"] == "synth"
    assert out["stages"]["finish"]["status"] == "skipped"
    assert os.path.exists(os.path.join(run_dir, sm.RUN_META_FILENAME))


def test_reconcile_partial_run_without_target_artifact_stays_nonterminal(tmp_path):
    """Fail-safe: an absent marker must NOT flip the run terminal. Reconcile
    runs on every read (runs list / status), including while a run is still
    executing — marking it failed here would kill in-flight runs. It stays
    non-terminal ("running"), i.e. it is never falsely completed."""
    run_dir = str(tmp_path)
    # A finish report from some unrelated copy must not complete a synth-bounded
    # run either: partial runs never key on 6_finish.rpt.
    meta = {"status": "running", "max_stage": "place"}
    _write_file(
        os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base", "6_finish.rpt"),
        "wns max 0.1\n",
    )

    out = sm._reconcile_stale_status(run_dir, meta)

    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(run_dir, sm.RUN_META_FILENAME))


def test_reconcile_place_bounded_run_uses_place_checkpoint(tmp_path):
    run_dir = str(tmp_path)
    _write_file(
        os.path.join(run_dir, "orfs_results", "sky130hd", "counter", "base", "3_place.odb"),
        "odb",
    )
    meta = {"status": "running", "max_stage": "place"}

    out = sm._reconcile_stale_status(run_dir, meta)

    assert out["status"] == "completed"
    assert out["current_stage"] == "place"


# ---- retry_pd composition with partial parents ---------------------------------


def _make_partial_parent(workspace: str) -> str:
    """A completed synth-only parent run (as the bounded worker leaves it)."""
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    results = os.path.join(run_dir, "orfs_results", "sky130hd", "demo_top", "base")
    _write_file(os.path.join(results, "1_synth.odb"), "odb")
    _write_file(os.path.join(results, "1_synth.sdc"), "sdc")
    _write_file(
        os.path.join(results, "1_synth.v"),
        "module demo_top(input clk, output y); endmodule",
    )
    _write_file(
        os.path.join(run_dir, "orfs_reports", "sky130hd", "demo_top", "base", "synth_stat.txt"),
        "Chip area for module '\\demo_top': 9.0\n5 1.0 cells\n",
    )
    _write_file(os.path.join(run_dir, "inputs", "demo_top.v"), "module demo_top(input clk, output y); endmodule")
    _write_file(os.path.join(run_dir, "constraints.sdc"), "create_clock -period 10 [get_ports clk]\n")
    _write_file(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps(
            {
                "run_id": "synth_0001",
                "status": "completed",
                "max_stage": "synth",
                "current_stage": "synth",
                "top_module": "demo_top",
                "platform": "sky130hd",
                "clock_period_ns": 10.0,
                "auto_checks": {"constraints": "pass", "signoff": "skip", "equiv": "skip"},
            }
        ),
    )
    return run_dir


def test_retry_pd_from_next_stage_of_partial_parent_passes_prereqs(tmp_path, monkeypatch):
    workspace = str(tmp_path)
    _make_partial_parent(workspace)

    def fake_run_targets(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "demo_top", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "demo_top", "base")
        _write_file(os.path.join(reports, "2_floorplan_final.rpt"), "floorplan\n")
        _write_file(os.path.join(results, "2_floorplan.odb"), "odb")
        _write_file(os.path.join(results, "2_floorplan.sdc"), "sdc")
        return {"success": True, "stdout": "ok", "stderr": "", "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs_targets", fake_run_targets)

    started = sm.retry_pd_job(
        workspace=workspace,
        source_run_id="synth_0001",
        start_stage="floorplan",
        max_stage="floorplan",
    )
    # Prerequisite validation accepts the synth-only parent: it DID run the
    # stage (synth) that feeds a floorplan retry.
    assert started["status"] == "queued"
    final = _wait_for_terminal(started["run_id"], workspace)
    assert final["status"] == "completed"


def test_retry_pd_beyond_partial_parent_bound_fails_honestly(tmp_path):
    workspace = str(tmp_path)
    _make_partial_parent(workspace)

    result = sm.retry_pd_job(
        workspace=workspace,
        source_run_id="synth_0001",
        start_stage="route",
        max_stage="finish",
    )
    assert result["status"] == "error"
    assert "Missing prerequisite artifacts" in result["message"]
    assert "partial flow (max_stage=synth)" in result["message"]
    assert "'floorplan'" in result["message"]  # honest continuation pointer


# ---- REST: /synthesize forwards maxStage ---------------------------------------


@pytest.fixture()
def rest_client(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.actions import build_actions_router

    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve))
    return TestClient(app), resolve("sess")


def test_rest_synthesize_passes_max_stage(rest_client, monkeypatch):
    import src.api.actions as actions_mod

    client, ws = rest_client
    with open(os.path.join(ws, "counter.v"), "w", encoding="utf-8") as f:
        f.write("module counter(input clk, output reg q); always @(posedge clk) q<=~q; endmodule\n")

    captured = {}

    def fake_start(**kwargs):
        captured.update(kwargs)
        return {"run_id": "synth_0001", "status": "queued", "poll_after_sec": 30}

    monkeypatch.setattr(actions_mod, "start_synthesis_job", fake_start)

    r = client.post("/api/workspace/sess/synthesize", json={"maxStage": "synth"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert captured["max_stage"] == "synth"


def test_rest_synthesize_surfaces_invalid_max_stage_as_400(rest_client, monkeypatch):
    import src.api.actions as actions_mod

    client, ws = rest_client
    with open(os.path.join(ws, "counter.v"), "w", encoding="utf-8") as f:
        f.write("module counter(input clk, output reg q); always @(posedge clk) q<=~q; endmodule\n")

    def fake_start(**kwargs):
        # Same rejected shape the real manager returns for a bad stage.
        return {
            "status": "error",
            "message": f"Unsupported max_stage '{kwargs.get('max_stage')}'.",
            "supported_stages": sm.PD_STAGE_SEQUENCE,
        }

    monkeypatch.setattr(actions_mod, "start_synthesis_job", fake_start)

    r = client.post("/api/workspace/sess/synthesize", json={"maxStage": "bogus"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["ok"] is False
    assert "Unsupported max_stage" in detail["error"]["message"]
