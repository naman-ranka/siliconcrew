"""Wave C (sc#75): the PD-retry rollup must be as honest as the first run's.

A retry decided its terminal status on signoff ALONE and summarized itself as
"PD retry completed" — dropping the inherited constraints verdict, the
unverified-clock warning that makes every timing number provisional, and (until
Wave C) any timing verdict at all. A retry reuses the parent's constraints.sdc
verbatim, so those caveats are inherited facts, not the parent's problem.
"""
import json
import os

from src.tools import synthesis_manager as sm

PLATFORM = "sky130hd"
TOP = "counter"
BASE_REL = os.path.join(PLATFORM, TOP, "base")

VIOLATING_FINISH = """\
wns max -3.0
tns max -99.0
worst slack max -3.25
clk period_min = 13.25 fmax = 75.47
setup violation count 5
hold violation count 0
"""

MET_FINISH = """\
wns max 0.00
tns max 0.00
worst slack max 1.75
clk period_min = 8.25 fmax = 121.21
setup violation count 0
hold violation count 0
"""


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _seed_parent(workspace: str, **meta_overrides) -> str:
    parent_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    ckpt = os.path.join(parent_dir, "orfs_results", BASE_REL)
    _write_file(os.path.join(ckpt, "3_place.odb"), "ODB")
    _write_file(os.path.join(ckpt, "3_place.sdc"), "# sdc")
    _write_file(os.path.join(parent_dir, "inputs", f"{TOP}.v"), f"module {TOP}; endmodule\n")
    _write_file(os.path.join(parent_dir, "constraints.sdc"), "create_clock -period 10 [get_ports clk]\n")
    meta = {
        "run_id": "synth_0001",
        "status": "completed",
        "platform": PLATFORM,
        "top_module": TOP,
        "clock_period_ns": 10.0,
        "effective_clock_period_ns": 10.0,
        "sdc_time_unit": "ns",
        "auto_checks": {"constraints": "pass", "signoff": "pass", "equiv": "skip"},
    }
    meta.update(meta_overrides)
    _write_file(os.path.join(parent_dir, "run_meta.json"), json.dumps(meta))
    return parent_dir


def _retry_args() -> dict:
    return {
        "run_id": "synth_0002",
        "source_run_id": "synth_0001",
        "start_stage": "cts",
        "max_stage": "finish",
        "orfs_overrides": {},
        "platform": PLATFORM,
        "top_module": TOP,
        "utilization": 5,
        "aspect_ratio": 1.0,
        "core_margin": 2.0,
        "timeout": 60,
    }


def _fake_targets(finish_rpt: str):
    def fake(**kwargs):
        run_dir = kwargs["run_dir"]
        _write_file(os.path.join(run_dir, "orfs_reports", BASE_REL, "6_finish.rpt"), finish_rpt)
        _write_file(
            os.path.join(run_dir, "orfs_results", BASE_REL, "6_final.v"),
            f"module {TOP}(input clk); endmodule\n",
        )
        return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

    return fake


def _run_retry(tmp_path, monkeypatch, finish_rpt: str, **parent_meta) -> dict:
    workspace = str(tmp_path)
    _seed_parent(workspace, **parent_meta)
    child_dir = os.path.join(workspace, "synth_runs", "synth_0002")
    os.makedirs(child_dir, exist_ok=True)
    monkeypatch.setattr(sm, "_run_orfs_targets", _fake_targets(finish_rpt))
    return sm._retry_pd_worker(workspace, child_dir, _retry_args())


def test_retry_inheriting_a_bypass_clock_carries_the_warning(tmp_path, monkeypatch):
    """The parent's clock port was GUESSED; the retry reuses that same SDC, so
    every timing number it reports is only as real as the guess."""
    run_meta = _run_retry(
        tmp_path,
        monkeypatch,
        MET_FINISH,
        clock_source="bypass_default",
        constraints_note="Clock port not verified against the spec (bypass_default).",
    )
    assert run_meta["status"] == "completed"
    assert "not verified" in run_meta["check_notes"].lower()


def test_retry_inheriting_a_mismatched_clock_carries_the_warning(tmp_path, monkeypatch):
    run_meta = _run_retry(
        tmp_path,
        monkeypatch,
        MET_FINISH,
        clock_source="default_module_mismatch",
        constraints_note="Clock port not verified: spec module name does not match the top module.",
    )
    assert "not verified" in run_meta["check_notes"].lower()


def test_retry_with_violating_timing_says_so(tmp_path, monkeypatch):
    run_meta = _run_retry(tmp_path, monkeypatch, VIOLATING_FINISH)
    # Timing is advisory: the retry still produced its artifacts.
    assert run_meta["status"] == "completed"
    assert run_meta["auto_checks"]["timing"] == "fail"
    notes = run_meta["check_notes"].lower()
    assert "timing not met" in notes and "setup slack -3.25 ns" in notes
    assert "5 setup violations" in notes


def test_retry_met_timing_names_the_margin(tmp_path, monkeypatch):
    run_meta = _run_retry(tmp_path, monkeypatch, MET_FINISH)
    assert run_meta["auto_checks"]["timing"] == "pass"
    assert "timing met" in run_meta["check_notes"].lower()


def test_retry_does_not_claim_completion_on_an_inherited_constraints_failure(tmp_path, monkeypatch):
    """The gap sc#75 names: terminal status came from signoff alone, so a retry
    of a run whose constraints never validated reported "PD retry completed"."""
    run_meta = _run_retry(
        tmp_path,
        monkeypatch,
        MET_FINISH,
        auto_checks={"constraints": "fail", "signoff": "pass", "equiv": "skip"},
    )
    assert run_meta["auto_checks"]["constraints"] == "fail"
    assert run_meta["status"] == "failed"
    notes = run_meta["check_notes"].lower()
    assert "run failed on: constraints" in notes
    # equiv is STRUCTURALLY out of scope for a retry — never blamed.
    assert "equiv" not in notes
