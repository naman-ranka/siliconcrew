import json
import os

import pytest

from src.tools import wrappers
from src.tools.synthesis_manager import compare_pd_runs


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _write_run(
    workspace: str,
    run_id: str,
    *,
    wns: float,
    tns: float,
    area: float,
    cells: int,
    setup_violations: int,
    drc_lines: list[str],
    overflow: int,
    parent_run_id: str | None = None,
) -> None:
    run_dir = os.path.join(workspace, "synth_runs", run_id)
    report_dir = os.path.join(run_dir, "orfs_reports", "sky130hd", "demo_top", "base")
    os.makedirs(report_dir, exist_ok=True)
    meta = {
        "run_id": run_id,
        "top_module": "demo_top",
        "platform": "sky130hd",
        "status": "completed",
    }
    if parent_run_id:
        meta.update(
            {
                "mode": "pd_retry",
                "parent_run_id": parent_run_id,
                "retry_start_stage": "cts",
                "retry_max_stage": "finish",
                "orfs_overrides": {"CTS_BUF_DISTANCE": 100},
            }
        )

    _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(meta))
    _write_file(
        os.path.join(report_dir, "6_finish.rpt"),
        (
            f"tns max {tns}\n"
            f"wns max {wns}\n"
            f"setup violation count {setup_violations}\n"
            "hold violation count 0\n"
            "Total 1.00e-04 2.00e-04 3.00e-09 3.00e-04 100.0%\n"
        ),
    )
    _write_file(
        os.path.join(report_dir, "synth_stat.txt"),
        f"      {cells} {area} cells\nChip area for module '\\demo_top': {area}\n",
    )
    _write_file(os.path.join(report_dir, "5_route_drc.rpt"), "\n".join(drc_lines))
    _write_file(
        os.path.join(report_dir, "congestion.rpt"),
        (
            f"met1 100 70 70.0% 0 / 0 / {overflow}\n"
            f"Total 100 70 70.0% 0 / 0 / {overflow}\n"
            "Total wirelength: 123.4 um\n"
            "Routed nets: 12\n"
        ),
    )


def test_compare_pd_runs_infers_parent_and_reports_improvements(tmp_path):
    workspace = str(tmp_path)
    _write_file(os.path.join(workspace, "synth_runs", "LATEST"), "synth_0002")
    _write_run(
        workspace,
        "synth_0001",
        wns=-0.10,
        tns=-0.20,
        area=120.0,
        cells=30,
        setup_violations=2,
        drc_lines=["short met1", "spacing met2"],
        overflow=4,
    )
    _write_run(
        workspace,
        "synth_0002",
        wns=0.05,
        tns=0.0,
        area=100.0,
        cells=24,
        setup_violations=0,
        drc_lines=[],
        overflow=0,
        parent_run_id="synth_0001",
    )

    result = compare_pd_runs(workspace=workspace, child_run_id="synth_0002")

    assert result["status"] == "ok"
    assert result["parent_run_id"] == "synth_0001"
    assert result["verdict"] == "closed"
    assert result["signoff_clean"] is True
    assert result["timing_closed"] is True
    assert result["route_clean"] is True
    assert result["comparisons"]["wns_ns"]["delta"] == pytest.approx(0.15)
    assert result["comparisons"]["timing_violation_total"]["classification"] == "improved"
    assert result["route_drc_comparison"]["violation_count"]["classification"] == "improved"
    assert result["congestion_comparison"]["total_overflow"]["classification"] == "improved"
    assert result["lineage"]["orfs_overrides"] == {"CTS_BUF_DISTANCE": 100}


def test_compare_pd_runs_requires_parent_when_lineage_is_absent(tmp_path):
    workspace = str(tmp_path)
    _write_run(
        workspace,
        "synth_0002",
        wns=0.0,
        tns=0.0,
        area=100.0,
        cells=10,
        setup_violations=0,
        drc_lines=[],
        overflow=0,
    )

    result = compare_pd_runs(workspace=workspace, child_run_id="synth_0002")

    assert result["status"] == "error"
    assert "parent_run_id is required" in result["message"]


def test_compare_pd_runs_wrapper_returns_json(tmp_path, monkeypatch):
    workspace = str(tmp_path)
    _write_run(
        workspace,
        "synth_0001",
        wns=-0.01,
        tns=-0.01,
        area=100.0,
        cells=10,
        setup_violations=1,
        drc_lines=["short"],
        overflow=1,
    )
    _write_run(
        workspace,
        "synth_0002",
        wns=0.02,
        tns=0.0,
        area=90.0,
        cells=9,
        setup_violations=0,
        drc_lines=[],
        overflow=0,
        parent_run_id="synth_0001",
    )
    monkeypatch.setenv("RTL_WORKSPACE", workspace)

    out = wrappers.compare_pd_runs.invoke({"child_run_id": "synth_0002"})
    data = json.loads(out)

    assert data["status"] == "ok"
    assert data["verdict"] == "closed"
