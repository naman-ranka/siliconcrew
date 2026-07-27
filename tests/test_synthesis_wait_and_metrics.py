import json
import os
import shutil
import tempfile

from src.tools import wrappers
from src.tools.synthesis_manager import get_synthesis_metrics, read_stage_report


def _repo_local_tempdir(test_name: str) -> str:
    root = os.path.join(os.path.dirname(__file__), "_tmp")
    os.makedirs(root, exist_ok=True)
    return tempfile.mkdtemp(prefix=f"{test_name}_", dir=root)


def test_wait_for_synthesis_bounded_loop(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        old = os.environ.get("RTL_WORKSPACE")
        os.environ["RTL_WORKSPACE"] = workspace
        try:
            calls = {"n": 0}

            def _fake_status(run_id, workspace=None, cheap=False):
                calls["n"] += 1
                if calls["n"] < 3:
                    return {"run_id": run_id, "status": "running", "poll_after_sec": 1, "next_action": "wait/poll"}
                return {"run_id": run_id, "status": "completed", "poll_after_sec": 0, "next_action": "done"}

            monkeypatch.setattr(wrappers, "collect_synthesis_status", _fake_status)
            monkeypatch.setattr(wrappers.time, "sleep", lambda *_: None)

            out = wrappers.wait_for_synthesis.invoke({"run_id": "synth_0001", "max_wait_sec": 10, "poll_interval_sec": 1})
            data = json.loads(out)
            assert data["status"] == "completed"
            assert data["run_id"] == "synth_0001"
            assert data["timed_out"] is False
            assert calls["n"] >= 3
        finally:
            if old is None:
                os.environ.pop("RTL_WORKSPACE", None)
            else:
                os.environ["RTL_WORKSPACE"] = old


def test_wait_for_synthesis_clamps_max_wait(monkeypatch):
    """Bounded means bounded: max_wait_sec=999 is clamped server-side to
    WAIT_MAX_WAIT_SEC (120). Fake clock — no real sleeping, no flakiness."""
    with tempfile.TemporaryDirectory() as workspace:
        old = os.environ.get("RTL_WORKSPACE")
        os.environ["RTL_WORKSPACE"] = workspace
        try:
            clock = {"t": 0.0}
            calls = {"n": 0}

            def _fake_status(run_id, workspace=None, cheap=False):
                calls["n"] += 1
                return {"run_id": run_id, "status": "running", "poll_after_sec": 10}

            monkeypatch.setattr(wrappers, "collect_synthesis_status", _fake_status)
            monkeypatch.setattr(wrappers.time, "time", lambda: clock["t"])

            def _fake_sleep(seconds):
                clock["t"] += seconds

            monkeypatch.setattr(wrappers.time, "sleep", _fake_sleep)

            out = wrappers.wait_for_synthesis.invoke({"run_id": "synth_0001", "max_wait_sec": 999})
            data = json.loads(out)
            assert data["timed_out"] is True
            assert data["status"] == "running"
            # The loop stopped at the clamp, not at the requested 999s.
            assert data["waited_sec"] <= wrappers.WAIT_MAX_WAIT_SEC
            assert calls["n"] <= (wrappers.WAIT_MAX_WAIT_SEC // 10) + 1
            assert "wait_for_synthesis" in data["next_action"] or "get_synthesis_status" in data["next_action"]
        finally:
            if old is None:
                os.environ.pop("RTL_WORKSPACE", None)
            else:
                os.environ["RTL_WORKSPACE"] = old


# ---------------------------------------------------------------------------
# siliconcrew-dev #30: the cap is on the WALL CLOCK of the call.
#
# The old loop checked the deadline only BETWEEN iterations and then took one
# more unconditional status sample after it — and each sample is real work (a
# full object-store tree pull in hosted mode). With 150s-per-read a 120s wait
# ran ~300s. These tests advance the fake clock on the READS too, which the
# pre-existing tests never did (that blind spot is why the bug survived).
# ---------------------------------------------------------------------------


def test_wait_respects_cap_when_status_reads_are_expensive(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        clock = {"t": 0.0}
        calls = {"n": 0}
        READ_COST = 90.0

        def _fake_status(run_id, workspace=None, cheap=False):
            calls["n"] += 1
            clock["t"] += READ_COST  # a status read is NOT free
            return {"run_id": run_id, "status": "running", "poll_after_sec": 10}

        monkeypatch.setattr(wrappers, "collect_synthesis_status", _fake_status)
        monkeypatch.setattr(wrappers.time, "time", lambda: clock["t"])
        monkeypatch.setattr(wrappers.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))

        result = wrappers._wait_for_synthesis_job(workspace, "synth_0001", 120, 2)

        assert result["timed_out"] is True
        # Pre-fix this returned ~280s against a 120s cap (2 in-loop reads at 90s
        # + a sleep + one more unconditional 90s read after the loop).
        assert clock["t"] <= 120 + 1e-6
        assert result["waited_sec"] <= 120 + 1e-6


def test_wait_reports_a_run_that_went_terminal_during_the_last_sleep(monkeypatch):
    """The cap must not cost the final sample when there IS budget for it:
    cheap reads leave room, so a run that completes during the last sleep is
    still reported as completed, from a FULL read."""
    with tempfile.TemporaryDirectory() as workspace:
        clock = {"t": 0.0}
        seen = []

        def _fake_status(run_id, workspace=None, cheap=False):
            seen.append(cheap)
            clock["t"] += 0.01
            # Terminal only once the clock has passed the single sleep.
            status = "completed" if clock["t"] > 4 else "running"
            return {"run_id": run_id, "status": status, "poll_after_sec": 5}

        monkeypatch.setattr(wrappers, "collect_synthesis_status", _fake_status)
        monkeypatch.setattr(wrappers.time, "time", lambda: clock["t"])
        monkeypatch.setattr(wrappers.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))

        result = wrappers._wait_for_synthesis_job(workspace, "synth_0001", 20, 2)

        assert result["status"] == "completed"
        assert result["timed_out"] is False
        assert clock["t"] <= 20 + 1e-6
        # Intermediate polls are cheap; the returned payload came from a full read.
        assert seen[0] is True
        assert seen[-1] is False


def test_wait_loop_polls_cheaply_and_reads_fully_once(tmp_path, monkeypatch):
    """End-to-end against the REAL status path with a recording object store:
    intermediate polls must not pull the logs_partial tree; the final read must."""
    from src.platform_engines.workspace_provider import InMemoryObjectStore
    from src.tools import synthesis_manager as sm
    from src.utils.session_context import SessionContext, session_scope

    class RecordingStore(InMemoryObjectStore):
        def __init__(self):
            super().__init__()
            self.tree_gets = []

        def get_tree(self, key, local_dir, subdirs=None):
            self.tree_gets.append(key)
            return super().get_tree(key, local_dir, subdirs)

    workspace = str(tmp_path / "ws")
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_id": "synth_0001",
                "status": "running",
                "top_module": "counter",
                "platform": "sky130hd",
                "max_stage": "finish",
                "backend": "cloud_job",
                "created_at": "2999-01-01T00:00:00+00:00",  # never past its ceiling
                "timeout_sec": 3600,
            },
            f,
        )

    # A partial-log snapshot the FULL read is expected to pull (and the cheap
    # polls are expected to leave alone).
    partial_src = tmp_path / "partial" / "sky130hd" / "counter" / "base"
    partial_src.mkdir(parents=True)
    (partial_src / "1_synth.log").write_text("yosys running\n")

    store = RecordingStore()
    store.put_tree("sess-wait/synth_0001/logs_partial", str(tmp_path / "partial"))
    sm.set_durable_run_store(store)

    reports_dir = os.path.join(run_dir, "orfs_reports", "sky130hd", "counter", "base")
    state = {"polls_when_run_finished": None}

    def _fake_sleep(_seconds):
        # The run finishes during the first sleep: the next poll adopts the
        # on-disk finish artifact and ends the loop.
        state["polls_when_run_finished"] = list(store.tree_gets)
        os.makedirs(reports_dir, exist_ok=True)
        with open(os.path.join(reports_dir, "6_finish.rpt"), "w", encoding="utf-8") as f:
            f.write("wns max 0.31\ntns max 0.00\n")

    monkeypatch.setattr(wrappers.time, "sleep", _fake_sleep)

    try:
        with session_scope(SessionContext("sess-wait", workspace)):
            result = wrappers._wait_for_synthesis_job(workspace, "synth_0001", 120, 1)
    finally:
        sm.set_durable_run_store(None)

    assert result["status"] == "completed"
    assert result["timed_out"] is False
    # The first (cheap) poll pulled no tree at all...
    assert state["polls_when_run_finished"] == []
    # ...and exactly one logs_partial pull happened overall — the final full read.
    partial_pulls = [k for k in store.tree_gets if k.endswith("/logs_partial")]
    assert partial_pulls == ["sess-wait/synth_0001/logs_partial"]
    assert result["last_log_source"].startswith("partial (updated ")


def test_cheap_status_read_skips_partial_logs_and_says_so(tmp_path):
    """The opt-in flag itself: default behaviour is untouched, cheap is labelled."""
    from src.platform_engines.workspace_provider import InMemoryObjectStore
    from src.tools import synthesis_manager as sm
    from src.utils.session_context import SessionContext, session_scope

    class RecordingStore(InMemoryObjectStore):
        def __init__(self):
            super().__init__()
            self.tree_gets = []

        def get_tree(self, key, local_dir, subdirs=None):
            self.tree_gets.append(key)
            return super().get_tree(key, local_dir, subdirs)

    workspace = str(tmp_path / "ws")
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    os.makedirs(run_dir, exist_ok=True)
    partial_src = tmp_path / "partial" / "sky130hd" / "counter" / "base"
    partial_src.mkdir(parents=True)
    (partial_src / "1_synth.log").write_text("Detailed Route 30%\n")

    store = RecordingStore()
    store.put_tree("sess-cheap/synth_0001/logs_partial", str(tmp_path / "partial"))
    sm.set_durable_run_store(store)
    meta = {
        "run_id": "synth_0001",
        "status": "running",
        "top_module": "counter",
        "platform": "sky130hd",
        "max_stage": "finish",
        "backend": "cloud_job",
    }
    try:
        with session_scope(SessionContext("sess-cheap", workspace)):
            cheap = sm._build_status_response(
                "synth_0001", run_dir, "running", meta, workspace=workspace, cheap=True
            )
            assert store.tree_gets == []
            assert cheap["last_log_lines"] == []
            assert cheap["last_log_source"] == "not read (cheap poll)"

            full = sm._build_status_response(
                "synth_0001", run_dir, "running", meta, workspace=workspace
            )
    finally:
        sm.set_durable_run_store(None)

    assert store.tree_gets == ["sess-cheap/synth_0001/logs_partial"]
    assert any("Detailed Route 30%" in ln for ln in full["last_log_lines"])
    assert full["last_log_source"].startswith("partial (updated ")


def test_get_synthesis_metrics_parses_finish_and_stat_reports():
    with tempfile.TemporaryDirectory() as workspace:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0002")
        report_dir = os.path.join(run_dir, "orfs_reports", "sky130hd", "exp_fixed_point", "base")
        os.makedirs(report_dir, exist_ok=True)

        with open(os.path.join(workspace, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
            f.write("synth_0002")
        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "synth_0002", "top_module": "exp_fixed_point", "platform": "sky130hd"}, f)

        with open(os.path.join(report_dir, "6_finish.rpt"), "w", encoding="utf-8") as f:
            f.write(
                "tns max 0.00\n"
                "wns max 0.31\n"
                "setup violation count 0\n"
                "hold violation count 0\n"
                "Total                  1.64e-03   1.11e-03   3.80e-09   2.75e-03 100.0%\n"
            )
        with open(os.path.join(report_dir, "synth_stat.txt"), "w", encoding="utf-8") as f:
            f.write(
                "      814 7.33E+03 cells\n"
                "Chip area for module '\\exp_fixed_point': 7332.032000\n"
            )

        metrics = get_synthesis_metrics(workspace=workspace, run_id="synth_0002")
        assert metrics["status"] == "ok"
        assert metrics["metrics"]["area_um2"] == 7332.032
        assert metrics["metrics"]["cell_count"] == 814
        assert metrics["metrics"]["wns_ns"] == 0.31
        assert metrics["metrics"]["tns_ns"] == 0.0
        assert round(metrics["metrics"]["power_uw"], 1) == 2750.0
        assert metrics["complete"] is True


def test_read_stage_report_reads_floorplan_report():
    workspace = _repo_local_tempdir("stage_floorplan")
    try:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0003")
        report_dir = os.path.join(run_dir, "orfs_reports", "sky130hd", "demo_top", "base")
        os.makedirs(report_dir, exist_ok=True)

        with open(os.path.join(workspace, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
            f.write("synth_0003")
        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "synth_0003", "top_module": "demo_top", "platform": "sky130hd"}, f)
        with open(os.path.join(report_dir, "2_floorplan_final.rpt"), "w", encoding="utf-8") as f:
            f.write("floorplan summary\ncore_area 123.4\n")

        report = read_stage_report(workspace=workspace, run_id="synth_0003", stage="floorplan")
        assert report["status"] == "ok"
        assert report["stage"] == "floorplan"
        assert report["artifact_name"] == "2_floorplan_final.rpt"
        assert "floorplan summary" in report["content_excerpt"]
        assert report["content_truncated"] is False
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_read_stage_report_reads_place_log():
    workspace = _repo_local_tempdir("stage_place")
    try:
        run_dir = os.path.join(workspace, "synth_runs", "synth_0004")
        log_dir = os.path.join(run_dir, "orfs_logs", "sky130hd", "demo_top", "base")
        os.makedirs(log_dir, exist_ok=True)

        with open(os.path.join(workspace, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
            f.write("synth_0004")
        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "synth_0004", "top_module": "demo_top", "platform": "sky130hd"}, f)
        with open(os.path.join(log_dir, "3_3_place_gp.json"), "w", encoding="utf-8") as f:
            f.write("{\"stage\":\"place\",\"overflow\":0}")

        report = read_stage_report(workspace=workspace, run_id="synth_0004", stage="place")
        assert report["status"] == "ok"
        assert report["artifact_scope"] == "orfs_logs"
        assert report["artifact_name"] == "3_3_place_gp.json"
        assert "\"overflow\":0" in report["content_excerpt"]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_no_start_and_wait_combo_tool_exists():
    """run_synthesis_and_wait was REMOVED (Wave 9 locked constraint): one
    async contract — dispatch, then bounded wait_for_synthesis loops."""
    assert not hasattr(wrappers, "run_synthesis_and_wait")
    names = {t.name for t in wrappers.mcp_tools}
    assert "run_synthesis_and_wait" not in names
    assert "wait_for_synthesis" in names
