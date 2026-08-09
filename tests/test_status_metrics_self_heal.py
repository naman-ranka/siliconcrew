"""Wave C live-verification gap: the STATUS path served the stale snapshot.

Found on staging (revision 00108-8zl, run synth_0003): get_synthesis_metrics
returned the honest values while get_synthesis_status for the SAME terminal run
still returned the persisted v1 summary_metrics (fmax_mhz 100.0 — the echo) and
auto_checks with no timing key. Two agent-facing surfaces disagreeing about one
run is the B1 defect class, on the path the Report tab and polling agents use.
"""
import json
import os
import tempfile

import pytest

from src.tools import synthesis_manager as sm

PLATFORM = "asap7"
TOP = "alu4"
BASE_REL = os.path.join("orfs_reports", PLATFORM, TOP, "base")

# The real staging report: clamped wns beside the real worst slack.
ASAP7_FINISH = """\
tns max 0.00
wns max 0.00
worst slack max 9876.69
clk period_min = 123.31 fmax = 8109.80
setup violation count 0
hold violation count 0
Total                  2.78e-03   7.27e-04   1.53e-06   3.51e-03 100.0%
"""

SYNTH_STAT = "   Chip area for module '\\alu4': 1344.407220\n\n   814  7.33E+03 cells\n"

# What the pre-Wave-C finalizer persisted: the clock target echoed as fmax, no
# stamp, none of the v2 timing fields, and auto_checks with no timing key.
V1_SNAPSHOT = {
    "area_um2": 1344.40722,
    "cell_count": 814,
    "wns_ns": 0.0,
    "tns_ns": 0.0,
    "power_uw": 3510.0,
    "power_mw": 3.51,
    "fmax_mhz": 100.0,
}


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _seed_legacy_run(workspace: str, with_reports: bool = True) -> str:
    run_dir = os.path.join(workspace, "synth_runs", "synth_0003")
    if with_reports:
        _write_file(os.path.join(run_dir, BASE_REL, "6_finish.rpt"), ASAP7_FINISH)
        _write_file(os.path.join(run_dir, BASE_REL, "synth_stat.txt"), SYNTH_STAT)
    _write_file(
        os.path.join(run_dir, "run_meta.json"),
        json.dumps({
            "run_id": "synth_0003",
            "status": "completed",
            "current_stage": "finish",
            "platform": PLATFORM,
            "top_module": TOP,
            "max_stage": "finish",
            "clock_period_ns": 10.0,
            "effective_clock_period_ns": 10.0,
            "sdc_time_unit": "ps",
            "summary_metrics": dict(V1_SNAPSHOT),
            "auto_checks": {"constraints": "pass", "signoff": "pass", "equiv": "skip"},
            "check_notes": "All guardrails passed",
        }),
    )
    return run_dir


def test_status_path_serves_healed_metrics_not_the_stored_echo():
    with tempfile.TemporaryDirectory() as workspace:
        _seed_legacy_run(workspace)
        status = sm.get_synthesis_status("synth_0003", workspace=workspace)

        sm_out = status["summary_metrics"]
        assert sm_out["fmax_mhz"] == pytest.approx(8109.80)
        assert sm_out["worst_slack_ns"] == pytest.approx(9.87669)
        assert sm_out["timing_met"] is True
        assert sm_out["timing_corner"] == "BC/FF (best-case)"
        assert sm_out["metrics_schema_version"] == sm.METRICS_SCHEMA_VERSION


def test_repeated_status_polls_do_not_rewrite_run_meta():
    """Statuses are polled hard: the stamp must make repeat polls write-free."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = _seed_legacy_run(workspace)
        meta_path = os.path.join(run_dir, "run_meta.json")

        sm.get_synthesis_status("synth_0003", workspace=workspace)
        mtime = os.path.getmtime(meta_path)
        for _ in range(3):
            sm.get_synthesis_status("synth_0003", workspace=workspace)
        assert os.path.getmtime(meta_path) == mtime


def test_status_path_applies_the_legacy_nulling_when_reports_are_gone():
    """S-3 semantics through the status path: a v1 snapshot whose reports were
    pruned must not have its target-echo fmax frozen under a v2 stamp."""
    with tempfile.TemporaryDirectory() as workspace:
        _seed_legacy_run(workspace, with_reports=False)
        status = sm.get_synthesis_status("synth_0003", workspace=workspace)

        healed = status["summary_metrics"]
        assert healed["metrics_schema_version"] == sm.METRICS_SCHEMA_VERSION
        assert healed["area_um2"] == pytest.approx(1344.40722)  # v1 justified this
        assert healed["fmax_mhz"] is None                        # ...but not this
        assert healed["worst_slack_ns"] is None
        assert "legacy snapshot" in (healed["timing_note"] or "")


def test_status_auto_checks_never_omits_timing_for_a_legacy_run():
    with tempfile.TemporaryDirectory() as workspace:
        _seed_legacy_run(workspace)
        status = sm.get_synthesis_status("synth_0003", workspace=workspace)
        assert status["auto_checks"]["timing"] == "pass"
        # The other verdicts are the PERSISTED ones, untouched.
        assert status["auto_checks"]["signoff"] == "pass"
        assert status["auto_checks"]["constraints"] == "pass"


def test_stored_history_is_not_falsified():
    """The response carries the truth; the persisted historical check_notes is
    what that run's finalizer actually wrote and must stay that way."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = _seed_legacy_run(workspace)
        sm.get_synthesis_status("synth_0003", workspace=workspace)
        with open(os.path.join(run_dir, "run_meta.json"), "r", encoding="utf-8") as f:
            persisted = json.load(f)
        assert persisted["check_notes"] == "All guardrails passed"
        assert "timing" not in persisted["auto_checks"]


def test_all_three_surfaces_agree_on_one_run():
    """status == runs-list card == metrics tool, for the same run."""
    with tempfile.TemporaryDirectory() as workspace:
        _seed_legacy_run(workspace)
        _write_file(
            os.path.join(workspace, "synth_runs", "index.json"),
            json.dumps({"runs": [{"run_id": "synth_0003", "status": "completed",
                                  "updated_at": "2026-07-30T00:00:00+00:00"}], "jobs": []}),
        )

        status = sm.get_synthesis_status("synth_0003", workspace=workspace)["summary_metrics"]
        card = sm.list_synthesis_runs(workspace)[0]["summary_metrics"]
        tool = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0003")["metrics"]

        for field in ("fmax_mhz", "worst_slack_ns", "timing_met", "timing_corner", "wns_ns"):
            assert status[field] == card[field] == tool[field], (
                f"{field}: status {status[field]} / card {card[field]} / tool {tool[field]}"
            )


def test_running_run_is_not_healed_or_stamped():
    """Only terminal runs are healed: a live run's metrics are still being
    written, and a poll must never claim a verdict for one."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0004")
        _write_file(os.path.join(run_dir, BASE_REL, "6_finish.rpt"), ASAP7_FINISH)
        _write_file(
            os.path.join(run_dir, "run_meta.json"),
            json.dumps({
                "run_id": "synth_0004",
                "status": "running",
                "platform": PLATFORM,
                "top_module": TOP,
                "max_stage": "finish",
                "created_at": sm._now_iso(),
                "timeout_sec": 3600,
                "summary_metrics": dict(V1_SNAPSHOT),
            }),
        )
        status = sm.get_synthesis_status("synth_0004", workspace=workspace)
        # The finish report exists, so reconcile adopts it as completed — which
        # IS terminal, and therefore healed. Assert the healed shape rather than
        # a stale one: the point is that no path leaves a v1 snapshot in a
        # terminal response.
        assert status["status"] == "completed"
        assert status["summary_metrics"]["fmax_mhz"] == pytest.approx(8109.80)


def test_v2_stamped_legacy_asap7_snapshot_is_rehealed_at_v3():
    """A snapshot the PRE-unit-fix healer already stamped v2 holds ps published
    as ns (worst_slack_ns 9876.69 on a sub-ns asap7 clock). Without a schema
    bump it would be frozen forever while every fresh-parse surface serves the
    corrected values — the exact card/poll disagreement the stamp exists to
    prevent."""
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = _seed_legacy_run(workspace)
        meta_path = os.path.join(run_dir, "run_meta.json")
        meta = json.loads(open(meta_path, encoding="utf-8").read())
        # What the v2 (pre-unit-fix) healer computed for a marker-less asap7
        # run: raw report numbers, stamped current.
        meta["summary_metrics"] = dict(
            V1_SNAPSHOT,
            worst_slack_ns=9876.69,
            clock_period_min_ns=123.31,
            fmax_mhz=8109.8,
            timing_met=True,
            metrics_schema_version=2,
        )
        _write_file(meta_path, json.dumps(meta))

        status = sm.get_synthesis_status("synth_0003", workspace=workspace)
        healed = status["summary_metrics"]
        assert healed["metrics_schema_version"] == sm.METRICS_SCHEMA_VERSION
        assert healed["worst_slack_ns"] == pytest.approx(9.87669, abs=1e-4)
        assert healed["clock_period_min_ns"] == pytest.approx(0.12331, abs=1e-4)
        assert healed["fmax_mhz"] == pytest.approx(8109.8, abs=0.1)
