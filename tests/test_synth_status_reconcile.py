"""Read-time reconciliation of a synthesis run stuck at a non-terminal status.

On serverless (Cloud Run) the worker that writes the terminal status can be
killed after the HTTP response returns, leaving run_meta at "running" even though
ORFS finished and its artifacts synced. _reconcile_stale_status adopts
"completed" ONLY when the finish-stage report (6_finish.rpt) is present — the one
artifact that proves the full flow finished. synth_stat.txt (area/cells) alone is
NOT enough (a run that failed after logic synthesis has it too), so a failed run
must not be mis-marked as completed.
"""
import os

from src.tools import synthesis_manager as sm


def test_reconciles_when_finish_report_present(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_find_report_file",
                        lambda rd, name: os.path.join(rd, name) if name == "6_finish.rpt" else None)
    monkeypatch.setattr(sm, "_compute_summary_metrics",
                        lambda rd, m: {"area_um2": 337.8, "cell_count": 43})
    meta = {"status": "running", "run_id": "synth_0001"}

    out = sm._reconcile_stale_status(str(tmp_path), meta)

    assert out["status"] == "completed"
    assert out["summary_metrics"]["area_um2"] == 337.8
    assert out["finished_at"]
    assert os.path.exists(os.path.join(str(tmp_path), sm.RUN_META_FILENAME))


def test_does_not_mark_completed_on_synth_stat_alone(tmp_path, monkeypatch):
    """Regression: a run that reached logic synthesis (area/cells) but failed
    before finish (no 6_finish.rpt) must NOT be reported as completed."""
    monkeypatch.setattr(sm, "_find_report_file", lambda rd, name: None)  # no finish report
    # Even if metrics would parse, absence of the finish report must win.
    monkeypatch.setattr(sm, "_compute_summary_metrics",
                        lambda rd, m: {"area_um2": 337.8, "cell_count": 43})
    meta = {"status": "running"}

    out = sm._reconcile_stale_status(str(tmp_path), meta)

    assert out["status"] == "running"
    assert not os.path.exists(os.path.join(str(tmp_path), sm.RUN_META_FILENAME))


def test_does_not_touch_already_terminal_runs(tmp_path, monkeypatch):
    calls = {"n": 0}

    def _spy(rd, name):
        calls["n"] += 1
        return os.path.join(rd, name)

    monkeypatch.setattr(sm, "_find_report_file", _spy)

    for status in ("completed", "failed"):
        out = sm._reconcile_stale_status(str(tmp_path), {"status": status})
        assert out["status"] == status

    assert calls["n"] == 0  # short-circuits before touching disk
