"""Poll backoff is derived from ELAPSED RUN TIME, not from a call counter.

dev#72 defect 3: the recommendation used to double on every status call of the
process (`POLL_BACKOFF_START_SEC * 2**(count-1)`), so a caller polling quickly
was told "wait 600s" after ~110s of wall clock, and the state was process-local
— meaningless on a second hosted instance. The recommendation is now a pure
function of how long the run has been going, so it is identical for two callers
(or two instances) looking at the same run at the same moment.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

from src.tools import synthesis_manager as sm


def _run_dir(workspace: str, run_id: str = "synth_0001") -> str:
    d = os.path.join(workspace, "synth_runs", run_id)
    os.makedirs(d, exist_ok=True)
    return d


def _iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _meta(**over) -> dict:
    meta = {
        "run_id": "synth_0001",
        "status": "running",
        "top_module": "counter",
        "platform": "sky130hd",
        "max_stage": "finish",
    }
    meta.update(over)
    return meta


@pytest.mark.parametrize(
    "elapsed_sec,expected",
    [
        (5, 30),
        (119, 30),
        (200, 60),
        (600, 120),
        (1500, 300),
        (100000, 300),
    ],
)
def test_backoff_steps_follow_elapsed(tmp_path, elapsed_sec, expected):
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)
    meta = _meta(created_at=_iso_ago(elapsed_sec))

    resp = sm._build_status_response("synth_0001", run_dir, "running", meta, workspace=workspace)

    assert resp["poll_after_sec"] == expected
    assert resp["poll_after_sec"] <= sm.POLL_BACKOFF_MAX_SEC


def test_successive_polls_at_the_same_elapsed_agree(tmp_path):
    """Two immediate polls describe the same run — so they must agree.

    Pre-fix this returned 30 then 60: the second caller was punished for the
    first caller's existence.
    """
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)
    meta = _meta(created_at=_iso_ago(30))

    first = sm._build_status_response("synth_0001", run_dir, "running", meta, workspace=workspace)
    second = sm._build_status_response("synth_0001", run_dir, "running", meta, workspace=workspace)
    third = sm._build_status_response("synth_0001", run_dir, "running", meta, workspace=workspace)

    assert first["poll_after_sec"] == second["poll_after_sec"] == third["poll_after_sec"] == 30


def test_queued_run_falls_back_to_dispatched_at(tmp_path):
    """`created_at` is written by the WORKER, so a queued run has only
    `dispatched_at` — the whole queued window must still get a sane number."""
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)
    meta = _meta(status="queued", dispatched_at=_iso_ago(600))
    meta.pop("created_at", None)

    resp = sm._build_status_response("synth_0001", run_dir, "queued", meta, workspace=workspace)

    assert resp["poll_after_sec"] == 120


def test_naive_dispatched_at_is_read_as_utc(tmp_path):
    """Naive ISO timestamps are UTC here; reading one as local time would put
    the run hours into the future (or past) and skew the recommendation."""
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)
    naive = (datetime.now(timezone.utc) - timedelta(seconds=600)).replace(tzinfo=None).isoformat()
    meta = _meta(status="queued", dispatched_at=naive)

    resp = sm._build_status_response("synth_0001", run_dir, "queued", meta, workspace=workspace)

    assert resp["poll_after_sec"] == 120


def test_no_timestamps_at_all_gives_the_start_value(tmp_path):
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)

    resp = sm._build_status_response("synth_0001", run_dir, "queued", _meta(status="queued"), workspace=workspace)

    assert resp["poll_after_sec"] == sm.POLL_BACKOFF_START_SEC


def test_terminal_runs_recommend_no_polling(tmp_path):
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)
    meta = _meta(status="completed", created_at=_iso_ago(1500), elapsed_sec=1500.0)

    resp = sm._build_status_response("synth_0001", run_dir, "completed", meta, workspace=workspace)

    assert resp["poll_after_sec"] == 0


def test_poll_hint_describes_elapsed_based_cadence(tmp_path):
    workspace = str(tmp_path / "ws")
    run_dir = _run_dir(workspace)
    meta = _meta(created_at=_iso_ago(30))

    hint = sm._build_status_response(
        "synth_0001", run_dir, "running", meta, workspace=workspace
    )["poll_hint"]

    # The old hint promised "double each subsequent poll, cap 600s" — a lie now.
    assert "double" not in hint.lower()
    assert "600" not in hint
