"""Wave C adversarial review: the defects the first pass introduced or missed.

Each test here reproduces a concrete failure sequence found by reviewing the
finished Wave C diff, not a hypothetical.
"""
import json
import os
import tempfile

import pytest

from src.tools import synthesis_manager as sm

PLATFORM = "sky130hd"
TOP = "counter"
BASE_REL = os.path.join(PLATFORM, TOP, "base")

MET_FINISH = """\
wns max 0.00
tns max 0.00
worst slack max 1.75
clk period_min = 8.25 fmax = 121.21
setup violation count 0
hold violation count 0
"""

# A combinational block: no register-to-register path, so ORFS reports an
# unbounded fmax — but the IO-constrained paths still have real, negative slack
# and ORFS still counts the setup violations.
COMBINATIONAL_FINISH = """\
wns max -1.20
tns max -4.80
worst slack max -1.20
clk period_min = 0.00 fmax = inf
setup violation count 3
hold violation count 0
"""

MULTI_CLOCK_FINISH = """\
wns max 0.00
tns max 0.00
worst slack max 2.00
clk_a period_min = 8.00 fmax = 125.00
clk_b period_min = 4.00 fmax = 250.00
setup violation count 0
hold violation count 0
"""


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _seed_parent(workspace: str, **meta_overrides) -> None:
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


def _run_retry(workspace: str, monkeypatch, finish_rpt: str, overrides=None) -> dict:
    child_dir = os.path.join(workspace, "synth_runs", "synth_0002")
    os.makedirs(child_dir, exist_ok=True)
    monkeypatch.setattr(sm, "_run_orfs_targets", _fake_targets(finish_rpt))
    return sm._retry_pd_worker(
        workspace,
        child_dir,
        {
            "run_id": "synth_0002",
            "source_run_id": "synth_0001",
            "start_stage": "cts",
            "max_stage": "finish",
            "orfs_overrides": overrides or {},
            "platform": PLATFORM,
            "top_module": TOP,
            "utilization": 5,
            "aspect_ratio": 1.0,
            "core_margin": 2.0,
            "timeout": 60,
        },
    )


# --- S-1: the retry gate must not treat "skip" as failure --------------------

def test_retry_of_an_adopted_parent_is_not_declared_failed(monkeypatch):
    """auto_checks.constraints is THREE-valued, and Wave C's own B3 change now
    writes a literal "skip" onto adopted runs (_finalize_completed). Gating on
    == "pass" therefore fails a retry that produced a GDS, passed signoff and
    MET timing, with self-contradicting notes."""
    with tempfile.TemporaryDirectory() as workspace:
        _seed_parent(workspace, auto_checks={"constraints": "skip", "signoff": "skip", "equiv": "skip", "timing": "pass"})
        run_meta = _run_retry(workspace, monkeypatch, MET_FINISH)

        assert run_meta["auto_checks"]["signoff"] == "pass"
        assert run_meta["auto_checks"]["timing"] == "pass"
        assert run_meta["status"] == "completed"
        assert "run failed on" not in run_meta["check_notes"]


def test_retry_of_a_constraints_failed_parent_still_fails(monkeypatch):
    """The S-1 fix must not weaken the real gate: an explicit "fail" still fails."""
    with tempfile.TemporaryDirectory() as workspace:
        _seed_parent(workspace, auto_checks={"constraints": "fail", "signoff": "pass", "equiv": "skip"})
        run_meta = _run_retry(workspace, monkeypatch, MET_FINISH)
        assert run_meta["status"] == "failed"
        assert "run failed on: constraints" in run_meta["check_notes"]


# --- S-2: a CORNER override makes the platform-default label WRONG -----------

def test_corner_override_is_not_labelled_with_the_platform_default(monkeypatch):
    """retry_pd(orfs_overrides={"CORNER": "WC"}) genuinely writes CORNER into
    config.mk, so reporting sky130hd's default "TT (typical)" mislabels a
    worst-case run — worse than no label at all."""
    with tempfile.TemporaryDirectory() as workspace:
        _seed_parent(workspace)
        run_meta = _run_retry(workspace, monkeypatch, MET_FINISH, overrides={"CORNER": "WC"})
        assert run_meta["summary_metrics"]["timing_corner"] == "overridden: WC"


def test_corner_override_matching_the_default_keeps_the_normal_label(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        _seed_parent(workspace)
        run_meta = _run_retry(workspace, monkeypatch, MET_FINISH, overrides={"CORNER": "TT"})
        assert run_meta["summary_metrics"]["timing_corner"] == "TT (typical)"


# --- S-3: never stamp an unhealable v1 snapshot as v2 ------------------------

def test_unrecomputable_legacy_snapshot_is_not_stamped_as_truthful():
    """The else branch of the self-heal: with the reports gone there is nothing
    to recompute, so stamping the v1 snapshot as v2 would freeze its target-echo
    fmax in place forever — the exact lie the wave removes, made permanent."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        meta = {
            "run_id": "synth_0001",
            "status": "completed",
            "platform": PLATFORM,
            "top_module": TOP,
            "clock_period_ns": 10.0,
            "summary_metrics": {
                "area_um2": 1234.0,
                "cell_count": 814,
                "wns_ns": 0.0,
                "tns_ns": 0.0,
                "power_uw": 3510.0,
                "power_mw": 3.51,
                "fmax_mhz": 100.0,  # = 1000/target: the echo
            },
        }
        _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(meta))
        _write_file(
            os.path.join(workspace, "synth_runs", "index.json"),
            json.dumps({"runs": [{"run_id": "synth_0001", "status": "completed",
                                  "updated_at": "2026-07-30T00:00:00+00:00"}], "jobs": []}),
        )

        healed = sm.list_synthesis_runs(workspace)[0]["summary_metrics"]
        assert healed["metrics_schema_version"] == sm.METRICS_SCHEMA_VERSION
        # The values the v1 snapshot genuinely justifies survive...
        assert healed["area_um2"] == 1234.0
        assert healed["cell_count"] == 814
        # ...the ones it cannot do not.
        assert healed["fmax_mhz"] is None
        assert healed["worst_slack_ns"] is None
        assert healed["timing_met"] is None
        assert "legacy snapshot" in (healed["timing_note"] or "")

        # Still stamped exactly once (the write-amplification cure holds).
        meta_path = os.path.join(run_dir, "run_meta.json")
        mtime = os.path.getmtime(meta_path)
        sm.list_synthesis_runs(workspace)
        assert os.path.getmtime(meta_path) == mtime


# --- S-4: fmax = inf is not the same fact as worst slack = INF ---------------

def test_unbounded_fmax_does_not_suppress_a_real_violation():
    """A combinational block has no reg-to-reg path (fmax = inf) yet still has
    finite IO slack and ORFS-counted violations. Treating fmax=inf as
    "unconstrained" silently downgraded a failing design to "no timing data"."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        _write_file(os.path.join(run_dir, "orfs_reports", BASE_REL, "6_finish.rpt"), COMBINATIONAL_FINISH)
        meta = {"run_id": "synth_0001", "platform": PLATFORM, "top_module": TOP,
                "sdc_time_unit": "ns", "clock_period_ns": 10.0}
        _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(meta))

        verdict = sm._timing_guardrail(run_dir, meta)
        assert verdict["status"] == "fail"
        assert "3 setup violations" in verdict["note"]

        m = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")["metrics"]
        assert m["worst_slack_ns"] == pytest.approx(-1.20)
        assert m["timing_met"] is False
        # No maximum frequency exists for a design with no reg-to-reg path: say
        # so, never invent one by dividing.
        assert m["fmax_mhz"] is None


def test_truly_unconstrained_report_still_skips_but_counts_violations():
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        _write_file(
            os.path.join(run_dir, "orfs_reports", BASE_REL, "6_finish.rpt"),
            "wns max 0.00\nworst slack max INF\nclk period_min = 0.00 fmax = INF\n"
            "setup violation count 0\nhold violation count 0\n",
        )
        meta = {"run_id": "synth_0001", "platform": PLATFORM, "top_module": TOP, "sdc_time_unit": "ns"}
        _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(meta))
        assert sm._timing_guardrail(run_dir, meta)["status"] == "skip"

        # ...but violation counts are checked BEFORE that skip, so an
        # unconstrained report that nonetheless counted violations still fails.
        _write_file(
            os.path.join(run_dir, "orfs_reports", BASE_REL, "6_finish.rpt"),
            "wns max 0.00\nworst slack max INF\nsetup violation count 0\nhold violation count 2\n",
        )
        verdict = sm._timing_guardrail(run_dir, meta)
        assert verdict["status"] == "fail"
        assert "2 hold violations" in verdict["note"]


# --- Notes: multi-clock caveat, compare preference, sources honesty ----------

def test_multi_clock_report_discloses_the_first_match_caveat():
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        _write_file(os.path.join(run_dir, "orfs_reports", BASE_REL, "6_finish.rpt"), MULTI_CLOCK_FINISH)
        meta = {"run_id": "synth_0001", "platform": PLATFORM, "top_module": TOP,
                "sdc_time_unit": "ns", "clock_period_ns": 10.0}
        _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(meta))
        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        assert result["metrics"]["fmax_mhz"] == pytest.approx(125.00)  # the FIRST clock
        assert any("clock" in n.lower() and "first" in n.lower() for n in result["parse_notes"])


def test_sources_does_not_claim_a_corner_it_never_derived():
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
        _write_file(os.path.join(run_dir, "orfs_reports", "nangate45", TOP, "base", "6_finish.rpt"), MET_FINISH)
        meta = {"run_id": "synth_0001", "platform": "nangate45", "top_module": TOP, "sdc_time_unit": "ns"}
        _write_file(os.path.join(run_dir, "run_meta.json"), json.dumps(meta))
        result = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")
        assert result["metrics"]["timing_corner"] is None
        assert result["sources"]["timing_corner"] is None


def test_compare_pd_runs_ranks_real_slack():
    """Two runs that both MET timing have identical clamped wns (0.00), so the
    comparison was neutral on the only number that differed."""
    with tempfile.TemporaryDirectory() as workspace:
        for run_id, slack in (("synth_0001", 1.75), ("synth_0002", 3.25)):
            run_dir = os.path.join(workspace, "synth_runs", run_id)
            _write_file(
                os.path.join(run_dir, "orfs_reports", BASE_REL, "6_finish.rpt"),
                f"wns max 0.00\ntns max 0.00\nworst slack max {slack}\n"
                "setup violation count 0\nhold violation count 0\n",
            )
            _write_file(
                os.path.join(run_dir, "run_meta.json"),
                json.dumps({"run_id": run_id, "status": "completed", "platform": PLATFORM,
                            "top_module": TOP, "sdc_time_unit": "ns", "clock_period_ns": 10.0,
                            "parent_run_id": "synth_0001" if run_id == "synth_0002" else None}),
            )
        result = sm.compare_pd_runs(workspace=workspace, child_run_id="synth_0002",
                                    parent_run_id="synth_0001")
        assert result["status"] == "ok"
        comp = result["comparisons"]["worst_slack_ns"]
        assert comp["parent"] == pytest.approx(1.75)
        assert comp["child"] == pytest.approx(3.25)
        assert comp["classification"] == "improved"
        # The clamped field it used to rank on cannot tell these two apart.
        assert result["comparisons"]["wns_ns"]["classification"] == "unchanged"
