"""dev#75 — agents have no clock: get_synthesis_metrics carries liveness.

The incident: a mid-flight run with null metrics read identically to a dead
one ("6_finish.rpt not found" either way), so an agent — which cannot measure
wall-clock time between its own calls — declared a healthy 8-minute run a
3-hour hang and hand-recovered mid-flow numbers as the result.

The response now answers, from that ONE payload: is this run alive
(``run_status``, reconciled on read — invariant #5), how long has it actually
been going (``elapsed_sec`` — the platform's clock, dispatch→now while live,
the persisted dispatch-to-terminal measurement once finished), and how far did
it get (``stages_completed``, from the same file trail the status path
renders). Pre-fix, none of these fields exist and every test here fails.

Same seeded-run-dir pattern as tests/test_poll_backoff.py; timezone sharp
edge (naive ISO == UTC, never ``.timestamp()`` on a naive datetime) is pinned
explicitly.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from src.tools import synthesis_manager as sm


def _iso_ago(seconds: float, naive: bool = False) -> str:
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    if naive:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()


BASE_META = {
    "run_id": "synth_0001",
    "top_module": "counter",
    "platform": "sky130hd",
    "max_stage": "finish",
    "sdc_time_unit": "ns",
    "clock_period_ns": 10.0,
}


def _seed_run(workspace: str, meta: dict, run_id: str = "synth_0001") -> str:
    run_dir = os.path.join(workspace, "synth_runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return run_dir


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _reports_base(run_dir: str) -> str:
    return os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base")


# ---------------------------------------------------------------------------
# Live run: nulls + "still running, N seconds in, M stages done" in ONE payload
# ---------------------------------------------------------------------------


def test_live_run_reports_running_elapsed_and_progress(tmp_path):
    workspace = str(tmp_path / "ws")
    meta = dict(BASE_META, status="running", dispatched_at=_iso_ago(90), timeout_sec=3600)
    run_dir = _seed_run(workspace, meta)
    # Two stages provably done (fresh markers, past the dispatch-time floor).
    _write(os.path.join(run_dir, "constraints.sdc"), "create_clock ...\n")
    _write(os.path.join(_reports_base(run_dir), "synth_stat.txt"), "Number of cells: 42\n")

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert resp["status"] == "ok"
    assert resp["run_status"] == "running"
    # The platform's clock: dispatch -> now, never null for a dispatched run.
    assert resp["elapsed_sec"] is not None
    assert 85 <= resp["elapsed_sec"] <= 400
    assert resp["stages_completed"] == "2/8"
    assert resp["complete"] is False
    # The disambiguating note the incident lacked: nulls here mean IN PROGRESS.
    assert any("in progress" in n and "authoritative clock" in n for n in resp["parse_notes"])


def test_live_run_without_timestamps_is_honest_about_not_knowing(tmp_path):
    """A meta with no timestamps yields elapsed None + 'elapsed unknown' —
    never a guessed number (honest state over fake liveness)."""
    workspace = str(tmp_path / "ws")
    _seed_run(workspace, dict(BASE_META, status="running"))

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert resp["run_status"] == "running"
    assert resp["elapsed_sec"] is None
    assert any("elapsed unknown" in n for n in resp["parse_notes"])


# ---------------------------------------------------------------------------
# Terminal runs: the persisted measurement is authoritative
# ---------------------------------------------------------------------------


def test_completed_run_reports_the_persisted_elapsed(tmp_path):
    """The ground-truth shape from the incident run (synth_0002): persisted
    elapsed_sec 485.05 is served verbatim, never recomputed to now."""
    workspace = str(tmp_path / "ws")
    meta = dict(
        BASE_META,
        status="completed",
        dispatched_at="2026-07-29T21:58:23.169368+00:00",
        finished_at="2026-07-29T22:06:28.323685+00:00",
        elapsed_sec=485.05,
    )
    _seed_run(workspace, meta)

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert resp["run_status"] == "completed"
    assert resp["elapsed_sec"] == pytest.approx(485.05)
    # Terminal + nulls -> no "still running" note.
    assert not any("in progress" in n for n in resp["parse_notes"])


def test_terminal_run_without_persisted_elapsed_uses_dispatch_to_finish(tmp_path):
    workspace = str(tmp_path / "ws")
    meta = dict(
        BASE_META,
        status="failed",
        dispatched_at="2026-07-29T21:58:23+00:00",
        finished_at="2026-07-29T22:03:23+00:00",
    )
    _seed_run(workspace, meta)

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert resp["run_status"] == "failed"
    assert resp["elapsed_sec"] == pytest.approx(300.0)


def test_naive_timestamps_are_read_as_utc(tmp_path):
    """Sharp edge: naive ISO strings are UTC. Mixing naive and aware (or
    calling .timestamp() on a naive datetime) would crash or skew by the host
    UTC offset; the fallback must compute 485.15s from these exact stamps."""
    workspace = str(tmp_path / "ws")
    meta = dict(
        BASE_META,
        status="completed",
        dispatched_at="2026-07-29T21:58:23.169368",  # naive
        finished_at="2026-07-29T22:06:28.323685+00:00",  # aware
    )
    _seed_run(workspace, meta)

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert resp["elapsed_sec"] == pytest.approx(485.15, abs=0.01)


# ---------------------------------------------------------------------------
# One clock: status and metrics report the SAME elapsed for the same run
# ---------------------------------------------------------------------------


def test_status_and_metrics_report_one_elapsed_clock(tmp_path):
    """dev#75 follow-up: a queued-then-started run (dispatched 300s ago, worker
    created_at 100s ago) must read the same elapsed from get_synthesis_status
    and get_synthesis_metrics. Pre-fix, status ticked from created_at (~100s)
    while metrics ticked from dispatched_at (~300s) — two clocks, one run."""
    workspace = str(tmp_path / "ws")
    meta = dict(
        BASE_META,
        status="running",
        dispatched_at=_iso_ago(300),
        created_at=_iso_ago(100),
        timeout_sec=3600,
    )
    _seed_run(workspace, meta)

    status_resp = sm.get_synthesis_status(run_id="synth_0001", workspace=workspace)
    metrics_resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert status_resp["status"] == "running"
    assert metrics_resp["run_status"] == "running"
    # Both cover the queued window: dispatch -> now, not worker-start -> now.
    assert 295 <= status_resp["elapsed_sec"] <= 400
    assert 295 <= metrics_resp["elapsed_sec"] <= 400
    assert abs(status_resp["elapsed_sec"] - metrics_resp["elapsed_sec"]) < 5.0


# ---------------------------------------------------------------------------
# Reconcile on read: the metrics response never serves a stale "running"
# ---------------------------------------------------------------------------


def test_stuck_run_past_its_ceiling_reads_failed_from_metrics(tmp_path):
    """A silent run past its dispatch ceiling is declared dead on THIS read —
    the caller must not be told 'running' by a payload of nulls."""
    workspace = str(tmp_path / "ws")
    long_ago = _iso_ago(5000)
    meta = dict(
        BASE_META,
        status="running",
        dispatched_at=long_ago,
        created_at=long_ago,
        timeout_sec=60,
    )
    run_dir = _seed_run(workspace, meta)
    # Kill the file-activity heartbeat: backdate everything in the run dir.
    old = (datetime.now(timezone.utc) - timedelta(seconds=5000)).timestamp()
    for root, _, files in os.walk(run_dir):
        for name in files:
            os.utime(os.path.join(root, name), (old, old))

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert resp["run_status"] == "failed"
    assert not any("in progress" in n for n in resp["parse_notes"])
    # The tombstone persisted (invariant #5): a second read agrees.
    assert sm._read_run_meta(run_dir)["status"] == "failed"
    assert sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")["run_status"] == "failed"


def test_finished_on_disk_run_is_adopted_completed_by_the_metrics_read(tmp_path):
    """The issue's open question, answered by construction: once the finish
    artifact exists on disk, a metrics poll flips to completed on that very
    response — a dead orchestrator can't leave metrics reading 'running'."""
    workspace = str(tmp_path / "ws")
    meta = dict(BASE_META, status="running", dispatched_at=_iso_ago(100), timeout_sec=3600)
    run_dir = _seed_run(workspace, meta)
    _write(os.path.join(run_dir, "constraints.sdc"), "create_clock ...\n")
    _write(
        os.path.join(_reports_base(run_dir), "synth_stat.txt"),
        "Number of cells: 42\n",
    )
    _write(
        os.path.join(_reports_base(run_dir), "6_finish.rpt"),
        "wns max -1.20\ntns max -3.40\n",
    )

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert resp["run_status"] == "completed"
    assert resp["metrics"]["wns_ns"] == pytest.approx(-1.20)
    assert not any("in progress" in n for n in resp["parse_notes"])
    assert sm._read_run_meta(run_dir)["status"] == "completed"


def test_inherited_stages_count_toward_stages_completed(tmp_path, monkeypatch):
    """PR #88 review: PD-retry stages "inherited" from the parent are completed
    upstream work — they must count toward the numerator, or a finished retry
    tops out at 5/8 and reads mid-flight forever."""
    workspace = str(tmp_path / "ws")
    meta = dict(BASE_META, status="running", dispatched_at=_iso_ago(90), timeout_sec=3600)
    _seed_run(workspace, meta)
    canned = {
        "stage_history": [
            {"stage": "constraints", "status": "inherited"},
            {"stage": "synth", "status": "inherited"},
            {"stage": "floorplan", "status": "inherited"},
            {"stage": "place", "status": "completed"},
            {"stage": "cts", "status": "completed"},
            {"stage": "grt", "status": "skipped"},
            {"stage": "route", "status": "completed"},
            {"stage": "finish", "status": "completed"},
        ]
    }
    monkeypatch.setattr(sm, "stage_progress_from_files", lambda run_dir, run_meta: canned)

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    # 3 inherited + 4 completed over 7 planned (the skipped stage is out of plan).
    assert resp["stages_completed"] == "7/7"


def test_elapsed_sec_clamped_at_zero_on_clock_skew(tmp_path):
    """PR #88 review: dispatched_at stamped by an instance whose clock runs
    ahead of ours must read 0.0, never a negative elapsed."""
    workspace = str(tmp_path / "ws")
    meta = dict(BASE_META, status="running", dispatched_at=_iso_ago(-30), timeout_sec=3600)
    _seed_run(workspace, meta)

    resp = sm.get_synthesis_metrics(workspace=workspace, run_id="synth_0001")

    assert resp["elapsed_sec"] == 0.0
