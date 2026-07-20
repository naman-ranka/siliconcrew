import json
import os
import tempfile
import time

import pytest

from src.tools.search_logs import search_logs
from src.tools import stdcells as std
from src.tools import synthesis_manager as sm
from src.tools.stdcells import resolve_stdcell_models, stdcell_root
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def test_search_logs_with_run_id_scope():
    with tempfile.TemporaryDirectory() as workspace:
        run_logs = os.path.join(workspace, "synth_runs", "synth_0001", "orfs_logs")
        other_logs = os.path.join(workspace, "synth_runs", "synth_0002", "orfs_logs")
        os.makedirs(run_logs, exist_ok=True)
        os.makedirs(other_logs, exist_ok=True)

        with open(os.path.join(run_logs, "a.log"), "w", encoding="utf-8") as f:
            f.write("WNS 0.10\n")
        with open(os.path.join(other_logs, "b.log"), "w", encoding="utf-8") as f:
            f.write("WNS -9.99\n")

        out = search_logs("WNS", workspace_dir=workspace, run_id="synth_0001")
        assert "synth_0001" in out
        assert "synth_0002" not in out


def test_resolve_stdcell_models_missing_cache_raises():
    with tempfile.TemporaryDirectory() as workspace:
        with pytest.raises(FileNotFoundError):
            resolve_stdcell_models(workspace, "asap7")


def test_resolve_stdcell_models_from_manifest_cache():
    with tempfile.TemporaryDirectory() as workspace:
        sim_dir = os.path.join(workspace, "_stdcells", "asap7", "sim")
        os.makedirs(sim_dir, exist_ok=True)
        with open(os.path.join(sim_dir, "a.v"), "w", encoding="utf-8") as f:
            f.write("module a; endmodule")
        with open(os.path.join(sim_dir, "b.v"), "w", encoding="utf-8") as f:
            f.write("module b; endmodule")
        with open(os.path.join(sim_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"platform": "asap7", "files": [{"name": "a.v"}, {"name": "b.v"}]}, f)

        files, manifest = resolve_stdcell_models(workspace, "asap7")
        assert [os.path.basename(x) for x in files] == ["a.v", "b.v"]
        assert manifest["platform"] == "asap7"


def test_stdcell_root_is_the_code_anchored_install_root():
    # The PDK location is a property of the install, anchored on the code
    # (repo root, from __file__) — the fixed path every caller shares by
    # construction. The cache lives at <repo_root>/_stdcells/<platform>/sim.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(std.__file__), "..", ".."))
    assert stdcell_root() == repo_root
    assert std.stdcell_cache_dir(stdcell_root(), "asap7") == os.path.join(
        repo_root, "_stdcells", "asap7", "sim"
    )


def test_stdcell_root_ignores_rtl_workspace_and_legacy_override(monkeypatch):
    # Issue #59: RTL_WORKSPACE means "where session workspaces live" and is
    # legitimately re-pointed per session (the codex agent does this). It — and
    # the removed RTL_STDCELL_WORKSPACE escape hatch — must have ZERO influence
    # on where the immutable PDK models resolve from.
    baseline = stdcell_root()
    monkeypatch.setenv("RTL_WORKSPACE", "/tmp/siliconcrew-scratch")
    monkeypatch.setenv("RTL_STDCELL_WORKSPACE", "/some/legacy/override")
    assert stdcell_root() == baseline
    monkeypatch.setenv("RTL_WORKSPACE", "/completely/different")
    assert stdcell_root() == baseline


def test_bootstrap_stdcells_writes_manifest(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        def fake_pinned(cache_dir):
            p = os.path.join(cache_dir, "asap7sc7p5t_AO_RVT_TT_201020.v")
            with open(p, "w", encoding="utf-8") as f:
                f.write("module AO; endmodule")
            return {"added": ["asap7sc7p5t_AO_RVT_TT_201020.v"], "failed": [], "attempted_urls": ["fake://pinned"]}

        monkeypatch.setattr(std, "_populate_asap7_pinned", fake_pinned)

        result = std.bootstrap_stdcells(workspace=workspace, platform="asap7", image="fake:image")
        assert result["file_count"] >= 1
        assert os.path.exists(result["manifest"])


# ---------------------------------------------------------------------------
# The completed-run guardrail rollup (sc#64): the checks cover artifacts, logs
# and the netlist and have NO timing term, so the rollup must not read as a
# verdict on the design — and a run the flow marked FAILED must never be
# summarized as one where everything passed.
# ---------------------------------------------------------------------------

def _fake_orfs_writing_artifacts(top: str, platform: str = "sky130hd"):
    def fake_orfs(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", platform, top, "base")
        results = os.path.join(run_dir, "orfs_results", platform, top, "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        with open(os.path.join(reports, "6_finish.rpt"), "w", encoding="utf-8") as f:
            # A real run that met no timing whatsoever: WNS -1137 ns. The
            # worst-slack / min-period / violation-count lines are the ones a
            # real 6_finish.rpt carries alongside wns — without them the suite
            # exercises only the fallback chain and proves nothing about timing.
            f.write(
                f"Chip area for module '{top}': 12.34\n"
                "Number of cells: 9\n"
                "wns max -1137.0\n"
                "tns max -9999.0\n"
                "worst slack max -1137.0\n"
                "clk period_min = 1147.0 fmax = 0.87\n"
                "setup violation count 8\n"
                "hold violation count 0\n"
            )
        with open(os.path.join(results, "6_final.v"), "w", encoding="utf-8") as f:
            f.write(f"module {top}(input clk, input rst, output [3:0] q); endmodule")
        return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

    return fake_orfs


def _run_to_completion(workspace: str, **kwargs) -> dict:
    started = sm.start_synthesis_job(workspace=workspace, **kwargs)
    for _ in range(60):
        status = sm.get_synthesis_status(started["run_id"], workspace=workspace)
        if status["status"] in {"completed", "failed"}:
            return status
        time.sleep(0.05)
    raise AssertionError("run never reached a terminal state")


def _counter_workspace(workspace: str) -> str:
    design = os.path.join(workspace, "counter.v")
    with open(design, "w", encoding="utf-8") as f:
        f.write(
            "module counter(input clk, input rst, output reg [3:0] q);"
            " always @(posedge clk) if(rst) q<=0; else q<=q+1; endmodule"
        )
    spec = DesignSpec(
        module_name="counter",
        description="counter",
        clock_period_ns=10.0,
        ports=[PortSpec(name="clk", direction="input"), PortSpec(name="rst", direction="input")],
    )
    save_yaml_file(spec, os.path.join(workspace, "counter_spec.yaml"))
    return design


def test_completed_rollup_names_what_was_actually_checked(monkeypatch):
    """A run with WNS -1137 ns used to be summarized "All guardrails passed"."""
    with tempfile.TemporaryDirectory() as workspace:
        design = _counter_workspace(workspace)
        monkeypatch.setattr(sm, "_run_orfs", _fake_orfs_writing_artifacts("counter"))

        final = _run_to_completion(workspace, verilog_files=[design], top_module="counter")

        assert final["status"] == "completed"
        notes = final["check_notes"].lower()
        assert "all guardrails passed" not in notes
        # Scope stated: what the artifact/log guardrails covered — and, since
        # Wave C, the timing verdict itself instead of a disclaimer that timing
        # was never looked at.
        assert "artifact" in notes and "log" in notes
        assert "timing not evaluated" not in notes
        assert "timing not met: setup slack -1137.00 ns, 8 setup violations" in notes
        assert final["auto_checks"]["timing"] == "fail"
        # The raw numbers are still there for the reader to judge.
        assert final["summary_metrics"]["wns_ns"] == pytest.approx(-1137.0)


def test_failed_run_rollup_does_not_claim_guardrails_passed(monkeypatch):
    """signoff can pass while the run FAILS on another check (here: equivalence).

    The rollup branched on signoff alone, so a failed run still carried a
    passing summary.
    """
    with tempfile.TemporaryDirectory() as workspace:
        design = _counter_workspace(workspace)
        monkeypatch.setattr(sm, "_run_orfs", _fake_orfs_writing_artifacts("counter"))
        monkeypatch.setattr(
            sm,
            "_run_equiv_check",
            lambda *a, **k: {"status": "fail", "note": "equivalence check failed"},
        )

        final = _run_to_completion(
            workspace, verilog_files=[design], top_module="counter", run_equiv=True
        )

        assert final["status"] == "failed"
        assert final["auto_checks"]["signoff"] == "pass"
        assert final["auto_checks"]["equiv"] == "fail"
        notes = final["check_notes"].lower()
        assert "all guardrails passed" not in notes
        # The summary of a failed run must name what failed.
        assert "equiv" in notes


def test_bootstrap_stdcells_successful_and_resolvable(monkeypatch):
    with tempfile.TemporaryDirectory() as workspace:
        def fake_pinned(cache_dir):
            names = [
                "asap7sc7p5t_AO_RVT_TT_201020.v",
                "asap7sc7p5t_INVBUF_RVT_TT_201020.v",
                "asap7sc7p5t_OA_RVT_TT_201020.v",
                "asap7sc7p5t_SEQ_RVT_TT_220101.v",
                "asap7sc7p5t_SIMPLE_RVT_TT_201020.v",
                "dff.v",
                "empty.v",
            ]
            for name in names:
                with open(os.path.join(cache_dir, name), "w", encoding="utf-8") as f:
                    f.write(f"module {name.replace('.v', '')}; endmodule")
            return {"added": names, "failed": [], "attempted_urls": ["fake://pinned"]}

        monkeypatch.setattr(std, "_populate_asap7_pinned", fake_pinned)

        result = std.bootstrap_stdcells(workspace=workspace, platform="asap7", image="fake:image")
        files, manifest = resolve_stdcell_models(workspace, "asap7")
        assert result["file_count"] >= 5
        assert len(files) >= 5
        assert manifest["platform"] == "asap7"
