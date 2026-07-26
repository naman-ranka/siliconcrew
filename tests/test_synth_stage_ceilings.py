"""Stage-aware run ceilings (Fix B).

Replaces the flat 1200s cap that killed healthy full-flow runs at 20 min. A
synth-only run gets the short budget; anything reaching place-and-route (incl.
the full RTL->GDS flow) gets the long one. Both are settings-backed and
persisted per run as timeout_sec so a reconciling read judges a run by the
ceiling it was DISPATCHED with (invariant #5).
"""
import json
import os
from datetime import datetime, timedelta, timezone

from src.platform_engines import settings as settings_mod
from src.tools import synthesis_manager as sm


def _iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _age_files(root: str, seconds_ago: float) -> None:
    import time as _time

    ts = _time.time() - seconds_ago
    for r, _dirs, files in os.walk(root):
        for name in files:
            os.utime(os.path.join(r, name), (ts, ts))


# ---- ceiling selection --------------------------------------------------------


def test_stage_ceiling_selection_defaults(monkeypatch):
    # Isolate from any env another test left set, then read pure defaults.
    monkeypatch.delenv("ORFS_TIMEOUT_SYNTH_SEC", raising=False)
    monkeypatch.delenv("ORFS_TIMEOUT_FULL_SEC", raising=False)
    settings_mod.reset_settings_cache()
    try:
        # constraints/synth = fast synth-only budget.
        assert sm._stage_ceiling_sec("constraints") == 900
        assert sm._stage_ceiling_sec("synth") == 900
        assert sm._stage_ceiling_sec(" SYNTH ") == 900
        # floorplan and later, incl. the full flow, pay place-and-route.
        for stage in ["floorplan", "place", "cts", "grt", "route", "finish"]:
            assert sm._stage_ceiling_sec(stage) == 3600, stage
        # Unknown/None defaults to the full budget (never under-budgets a run).
        assert sm._stage_ceiling_sec(None) == 3600
        assert sm._stage_ceiling_sec("bogus") == 3600
    finally:
        settings_mod.reset_settings_cache()


def test_resolve_timeout_caps_and_floors(monkeypatch):
    monkeypatch.delenv("ORFS_TIMEOUT_SYNTH_SEC", raising=False)
    monkeypatch.delenv("ORFS_TIMEOUT_FULL_SEC", raising=False)
    settings_mod.reset_settings_cache()
    try:
        # None / non-positive → the stage budget as-is.
        assert sm._resolve_timeout_sec("synth", None) == 900
        assert sm._resolve_timeout_sec("finish", 0) == 3600
        assert sm._resolve_timeout_sec("finish", -5) == 3600
        # An explicit request only LOWERS the ceiling, never raises it.
        assert sm._resolve_timeout_sec("finish", 1200) == 1200
        assert sm._resolve_timeout_sec("synth", 99999) == 900
        # Never below the hard floor.
        assert sm._resolve_timeout_sec("finish", 5) == sm.MIN_TIMEOUT_SEC
    finally:
        settings_mod.reset_settings_cache()


def test_env_overrides_budgets(monkeypatch):
    monkeypatch.setenv("ORFS_TIMEOUT_SYNTH_SEC", "123")
    monkeypatch.setenv("ORFS_TIMEOUT_FULL_SEC", "4567")
    settings_mod.reset_settings_cache()
    try:
        assert sm._stage_ceiling_sec("synth") == 123
        assert sm._stage_ceiling_sec("finish") == 4567
    finally:
        settings_mod.reset_settings_cache()


# ---- dispatch persists the stage ceiling (regression on the flat cap) ----------


class _HeldExecutor:
    """Accepts submissions but never runs them — dispatch stays queued."""

    def submit(self, fn, *args):
        from concurrent.futures import Future

        return Future()


def _dispatched_timeout(workspace: str, max_stage: str) -> int:
    sm.set_job_executor(_HeldExecutor())
    try:
        started = sm.start_synthesis_job(
            workspace=workspace,
            verilog_files=["counter.v"],
            top_module="counter",
            platform="sky130hd",
            max_stage=max_stage,
        )
    finally:
        sm.set_job_executor(None)
    return started["timeout_sec"]


def test_dispatch_persists_stage_ceiling(tmp_path, monkeypatch):
    monkeypatch.delenv("ORFS_TIMEOUT_SYNTH_SEC", raising=False)
    monkeypatch.delenv("ORFS_TIMEOUT_FULL_SEC", raising=False)
    settings_mod.reset_settings_cache()
    try:
        # Synth-only → short budget; full flow → long budget. Pre-fix code
        # capped BOTH at the flat 1200s, so these assertions fail on it.
        assert _dispatched_timeout(str(tmp_path / "a"), "synth") == 900
        assert _dispatched_timeout(str(tmp_path / "b"), "finish") == 3600
    finally:
        settings_mod.reset_settings_cache()


# ---- reconcile honors the DISPATCHED ceiling, not a live default ---------------


def _stale_run(workspace: str, meta_extra: dict, dispatched_ago: float) -> tuple:
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    os.makedirs(run_dir, exist_ok=True)
    meta = {
        "run_id": "synth_0001",
        "status": "running",
        "dispatched_at": _iso_ago(dispatched_ago),
        "top_module": "counter",
        "platform": "sky130hd",
    }
    meta.update(meta_extra)
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    _age_files(run_dir, dispatched_ago)  # idle since dispatch — liveness cold
    return run_dir, meta


def test_reconcile_uses_persisted_timeout_sec(tmp_path):
    # A short persisted ceiling past its deadline → failed, regardless of the
    # (much larger) current default.
    run_dir, meta = _stale_run(str(tmp_path), {"timeout_sec": 100, "max_stage": "finish"}, 2000.0)
    out = sm._reconcile_stale_status(run_dir, dict(meta))
    assert out["status"] == "failed"
    assert "orchestrator lost" in out["check_notes"]


def test_reconcile_fallback_uses_stage_bound_not_flat_default(tmp_path):
    # Legacy meta with NO timeout_sec: a full-flow run 2000s in must NOT be
    # failed — the fallback ceiling is the stage bound (3600s), not the old flat
    # 1200s. FAILS on pre-fix code (which used the 1200s constant → failed).
    run_dir, meta = _stale_run(str(tmp_path), {"max_stage": "finish"}, 2000.0)
    assert "timeout_sec" not in meta
    out = sm._reconcile_stale_status(run_dir, dict(meta))
    assert out["status"] == "running"
