"""Read-time reconciliation of a synthesis run stuck at a non-terminal status.

On serverless (Cloud Run) the worker that writes the terminal status can be
killed after the HTTP response returns, leaving run_meta at "running" even though
ORFS finished and its artifacts synced. _reconcile_stale_status adopts the
on-disk finish-stage PPA as the source of truth on read. Fail-safe: no metrics →
status untouched.
"""
import os

from src.tools import synthesis_manager as sm


def test_reconciles_stuck_running_when_finish_metrics_present(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_compute_summary_metrics",
                        lambda rd, m: {"area_um2": 337.8, "cell_count": 43})
    meta = {"status": "running", "run_id": "synth_0001"}

    out = sm._reconcile_stale_status(str(tmp_path), meta)

    assert out["status"] == "completed"
    assert out["summary_metrics"]["area_um2"] == 337.8
    assert out["finished_at"]  # stamped
    # terminal state was persisted so subsequent reads are cheap + consistent
    assert os.path.exists(os.path.join(str(tmp_path), sm.RUN_META_FILENAME))


def test_leaves_running_when_no_finish_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_compute_summary_metrics",
                        lambda rd, m: {"area_um2": None, "cell_count": None})
    meta = {"status": "running"}

    out = sm._reconcile_stale_status(str(tmp_path), meta)

    assert out["status"] == "running"  # not demonstrably finished
    assert not os.path.exists(os.path.join(str(tmp_path), sm.RUN_META_FILENAME))


def test_does_not_touch_already_terminal_runs(tmp_path, monkeypatch):
    calls = {"n": 0}

    def _spy(rd, m):
        calls["n"] += 1
        return {"area_um2": 1.0}

    monkeypatch.setattr(sm, "_compute_summary_metrics", _spy)

    for status in ("completed", "failed"):
        out = sm._reconcile_stale_status(str(tmp_path), {"status": status})
        assert out["status"] == status

    assert calls["n"] == 0  # short-circuits before touching disk
