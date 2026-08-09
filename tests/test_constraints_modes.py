"""constraints_mode behavior: auto / strict / bypass (sc#73).

Two defects: a synthesis-only top (`GCN_synth` wrapping `GCN`) hard-failed the
dispatch because the spec's module name differed, and the advertised `bypass`
escape hatch was accepted, named in an error message, and never branched on.

The dangerous part of softening the mismatch is the SDC itself: the generated
constraints guard `create_clock` behind `[llength $_sc_clk_ports] > 0`, so a
clock port that does not exist in the netlist is a SILENT no-op — an entirely
unconstrained ORFS run that still reports "completed". A port taken from a spec
describing a DIFFERENT module is exactly that hazard, so the mismatch and bypass
paths use the conventional literal port and say out loud that it was never
verified against the netlist.
"""
import os

import pytest

from src.tools import synthesis_manager as sm
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


def _spec(workspace: str, module_name: str = "GCN", clock_port: str = "clk_i") -> str:
    spec = DesignSpec(
        module_name=module_name,
        description="graph convolution block",
        clock_period_ns=4.0,
        ports=[
            PortSpec(name=clock_port, direction="input"),
            PortSpec(name="data_in", direction="input"),
            PortSpec(name="data_out", direction="output"),
        ],
    )
    path = os.path.join(workspace, f"{module_name}_spec.yaml")
    save_yaml_file(spec, path)
    return path


def _spec_without_a_clock(workspace: str, module_name: str = "GCN") -> str:
    """A spec whose inputs contain NO clk/clock/clk_i — the fallback-port case.

    ``rst`` is deliberately first: this is the shape that makes the fallback
    dangerous, because the port DOES exist in the netlist, so create_clock fires
    and the design is constrained on the reset.
    """
    spec = DesignSpec(
        module_name=module_name,
        description="no clock named in the spec",
        clock_period_ns=4.0,
        ports=[
            PortSpec(name="rst", direction="input"),
            PortSpec(name="data_in", direction="input"),
            PortSpec(name="data_out", direction="output"),
        ],
    )
    path = os.path.join(workspace, f"{module_name}_spec.yaml")
    save_yaml_file(spec, path)
    return path


def _dirs(tmp_path):
    workspace = tmp_path / "ws"
    run_dir = workspace / "synth_runs" / "synth_0001"
    run_dir.mkdir(parents=True)
    return str(workspace), str(run_dir)


def _sdc_text(result: dict) -> str:
    with open(result["sdc_path"], "r", encoding="utf-8") as f:
        return f.read()


def test_auto_mode_survives_a_module_name_mismatch(tmp_path):
    """A synthesis-only top is a normal design choice, not a dispatch error."""
    workspace, run_dir = _dirs(tmp_path)
    _spec(workspace)

    result = sm._constraints_guardrail(workspace, run_dir, "GCN_synth", 8.0, constraints_mode="auto")

    assert result["status"] == "pass"
    assert result["sdc_path"] and os.path.exists(result["sdc_path"])
    assert "GCN" in result["note"] and "GCN_synth" in result["note"]


def test_mismatch_sdc_uses_the_literal_clk_port_not_a_spec_port(tmp_path):
    """THE dangerous case. `create_clock` is guarded by `[llength] > 0`, so a
    port name borrowed from another module's spec produces a silently
    unconstrained run. Only the conventional port name is defensible here."""
    workspace, run_dir = _dirs(tmp_path)
    _spec(workspace, clock_port="clk_i")

    result = sm._constraints_guardrail(workspace, run_dir, "GCN_synth", 8.0, constraints_mode="auto")
    sdc = _sdc_text(result)

    assert "get_ports {clk}" in sdc
    assert "clk_i" not in sdc
    # A distinct source so run_meta records HOW this clock was chosen.
    assert result["clock_source"] == "default_module_mismatch"
    # And the note admits the port is unverified rather than implying it was checked.
    assert "not verified" in result["note"].lower()


def test_strict_mode_still_hard_fails_on_a_mismatch(tmp_path):
    workspace, run_dir = _dirs(tmp_path)
    _spec(workspace)

    result = sm._constraints_guardrail(workspace, run_dir, "GCN_synth", 8.0, constraints_mode="strict")

    assert result["status"] == "fail"
    assert result["sdc_path"] is None
    assert not os.path.exists(os.path.join(run_dir, "constraints.sdc"))


def test_bypass_ignores_a_perfectly_valid_spec(tmp_path):
    """`bypass` means "do not read the spec" — it must not silently behave like
    `auto` just because a matching spec happens to be present."""
    workspace, run_dir = _dirs(tmp_path)
    _spec(workspace, module_name="GCN", clock_port="clk_i")

    result = sm._constraints_guardrail(workspace, run_dir, "GCN", 8.0, constraints_mode="bypass")
    sdc = _sdc_text(result)

    assert result["status"] == "pass"
    assert "get_ports {clk}" in sdc
    assert "clk_i" not in sdc
    # The explicit request wins; the spec's 4.0 ns is never consulted.
    assert result["clock_period_ns"] == 8.0
    assert result["effective_clock_period_ns"] == 8.0
    assert result["clock_source"] == "bypass_default"
    assert "not verified" in result["note"].lower()


def test_bypass_without_a_spec_and_with_an_explicit_clock_passes(tmp_path):
    workspace, run_dir = _dirs(tmp_path)

    result = sm._constraints_guardrail(workspace, run_dir, "GCN", 5.0, constraints_mode="bypass")

    assert result["status"] == "pass"
    assert result["clock_period_ns"] == 5.0
    assert "get_ports {clk}" in _sdc_text(result)


def test_bypass_without_a_spec_or_a_clock_uses_the_default_period(tmp_path):
    workspace, run_dir = _dirs(tmp_path)

    result = sm._constraints_guardrail(workspace, run_dir, "GCN", None, constraints_mode="bypass")

    assert result["status"] == "pass"
    assert result["clock_period_ns"] == 10.0
    assert "create_clock -period 10.0" in _sdc_text(result)


def test_matching_spec_still_drives_the_constraints(tmp_path):
    """Regression fence: none of the above weakens the normal path."""
    workspace, run_dir = _dirs(tmp_path)
    _spec(workspace, module_name="GCN", clock_port="clk_i")

    result = sm._constraints_guardrail(workspace, run_dir, "GCN", None, constraints_mode="auto")

    assert result["status"] == "pass"
    assert result["clock_source"] == "spec"
    assert result["clock_period_ns"] == pytest.approx(4.0)
    assert "get_ports {clk_i}" in _sdc_text(result)


# ---------------------------------------------------------------------------
# The warning must SURVIVE the run that produced it. check_notes is rewritten
# at finalization and the guardrail dict is never persisted, so without a
# durable constraints_note + clock_source in the status payload, a mismatch
# run completed looking fully constrained (adversarial review finding B1).
# ---------------------------------------------------------------------------

def _fake_orfs_writing_artifacts(top: str, platform: str = "sky130hd"):
    def fake_orfs(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", platform, top, "base")
        results = os.path.join(run_dir, "orfs_results", platform, top, "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        with open(os.path.join(reports, "6_finish.rpt"), "w", encoding="utf-8") as f:
            f.write(f"Chip area for module '{top}': 12.34\nNumber of cells: 9\nwns max 0.0\ntns max 0.0\n")
        with open(os.path.join(results, "6_final.v"), "w", encoding="utf-8") as f:
            f.write(f"module {top}(input clk, output [3:0] q); endmodule")
        return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

    return fake_orfs


def test_mismatch_warning_survives_to_the_final_status(tmp_path, monkeypatch):
    import time

    workspace = str(tmp_path / "ws2")
    os.makedirs(workspace, exist_ok=True)
    _spec(workspace, module_name="GCN", clock_port="clk_i")
    design = os.path.join(workspace, "gcn_top.v")
    with open(design, "w", encoding="utf-8") as f:
        f.write("module GCN_synth(input clk, output [3:0] q); endmodule")
    monkeypatch.setattr(sm, "_run_orfs", _fake_orfs_writing_artifacts("GCN_synth"))

    started = sm.start_synthesis_job(
        workspace=workspace, verilog_files=[design], top_module="GCN_synth"
    )
    final = None
    for _ in range(60):
        final = sm.get_synthesis_status(started["run_id"], workspace=workspace)
        if final["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert final["status"] == "completed"
    # The payload names the clock's provenance...
    assert final["clock_source"] == "default_module_mismatch"
    assert "not verified" in (final["constraints_note"] or "").lower()
    # ...and the finalized rollup carries the warning instead of replacing it.
    assert "not verified" in final["check_notes"].lower()
    assert "timing not evaluated" in final["check_notes"].lower()


def test_mismatch_warning_survives_a_partial_flow_too(tmp_path, monkeypatch):
    """max_stage-limited runs take a different completion branch than the full
    flow; its rollup must carry the unverified-clock warning the same way
    (found live on staging: the partial branch replaced it)."""
    import time

    workspace = str(tmp_path / "ws3")
    os.makedirs(workspace, exist_ok=True)
    _spec(workspace, module_name="GCN", clock_port="clk_i")
    design = os.path.join(workspace, "gcn_top.v")
    with open(design, "w", encoding="utf-8") as f:
        f.write("module GCN_synth(input clk, output [3:0] q); endmodule")

    def fake_orfs(**kwargs):
        run_dir = kwargs["run_dir"]
        reports = os.path.join(run_dir, "orfs_reports", "sky130hd", "GCN_synth", "base")
        results = os.path.join(run_dir, "orfs_results", "sky130hd", "GCN_synth", "base")
        os.makedirs(reports, exist_ok=True)
        os.makedirs(results, exist_ok=True)
        with open(os.path.join(reports, "synth_stat.txt"), "w", encoding="utf-8") as f:
            f.write("Chip area for module '\GCN_synth': 12.34\nNumber of cells: 9\n")
        with open(os.path.join(results, "1_synth.odb"), "w", encoding="utf-8") as f:
            f.write("odb")
        with open(os.path.join(results, "1_synth.v"), "w", encoding="utf-8") as f:
            f.write("module GCN_synth(); endmodule")
        return {"success": True, "stdout": "", "stderr": "", "command": "fake"}

    # A bounded (max_stage) run does NOT go through _run_orfs: _job_worker calls
    # _run_orfs_targets, which goes straight to docker. Patching only _run_orfs
    # left this test running real ORFS and failing on every machine without it —
    # the whole point of the test (the partial-flow branch) was never exercised.
    monkeypatch.setattr(sm, "_run_orfs", fake_orfs)
    monkeypatch.setattr(sm, "_run_orfs_targets", fake_orfs)

    started = sm.start_synthesis_job(
        workspace=workspace, verilog_files=[design], top_module="GCN_synth",
        max_stage="synth",
    )
    final = None
    for _ in range(400):
        final = sm.get_synthesis_status(started["run_id"], workspace=workspace)
        if final["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert final["status"] == "completed"
    assert final["clock_source"] == "default_module_mismatch"
    assert "partial flow" in final["check_notes"].lower()
    assert "not verified" in final["check_notes"].lower()


# ---------------------------------------------------------------------------
# The fallback PORT is the worst of the guesses, and it did not warn at all.
# input_ports[0] is an arbitrary first input — usually a reset. Unlike the
# literal-"clk" branches (a silent no-op when the guess is wrong), this port
# generally EXISTS, so create_clock fires and the design is constrained on the
# wrong net: confidently wrong beats absent only in the sense of being worse.
# ---------------------------------------------------------------------------

def test_first_input_port_fallback_is_an_unverified_clock(tmp_path):
    workspace, run_dir = _dirs(tmp_path)
    _spec_without_a_clock(workspace)

    result = sm._constraints_guardrail(workspace, run_dir, "GCN", None, constraints_mode="auto")

    assert result["status"] == "pass"
    assert result["clock_source"] == "spec_fallback_port"
    assert result["clock_source"] in sm._UNVERIFIED_CLOCK_SOURCES
    # The SDC really did land on the reset.
    assert "get_ports {rst}" in _sdc_text(result)
    assert "not verified" in result["note"].lower()
    assert "first input port" in result["note"].lower()


def test_a_requested_period_does_not_make_a_guessed_port_verified(tmp_path):
    """clock_source said "requested" while the note said the port was a guess:
    the field and the note disagreed about what had been checked. The PERIOD was
    requested; the PORT was not, and the source name now says exactly that."""
    workspace, run_dir = _dirs(tmp_path)
    _spec_without_a_clock(workspace)

    result = sm._constraints_guardrail(workspace, run_dir, "GCN", 8.0, constraints_mode="auto")

    assert result["clock_source"] == "requested_period_fallback_port"
    assert result["clock_source"] in sm._UNVERIFIED_CLOCK_SOURCES
    assert result["clock_period_ns"] == 8.0
    assert "get_ports {rst}" in _sdc_text(result)
    assert "not verified" in result["note"].lower()


def test_a_named_spec_clock_port_with_a_requested_period_stays_verified(tmp_path):
    """Regression fence: plain "requested" keeps its meaning where the port
    itself came from the spec's own clock declaration."""
    workspace, run_dir = _dirs(tmp_path)
    _spec(workspace, module_name="GCN", clock_port="clk_i")

    result = sm._constraints_guardrail(workspace, run_dir, "GCN", 8.0, constraints_mode="auto")

    assert result["clock_source"] == "requested"
    assert result["clock_source"] not in sm._UNVERIFIED_CLOCK_SOURCES
    assert "get_ports {clk_i}" in _sdc_text(result)


def test_fallback_port_warning_survives_to_the_final_status(tmp_path, monkeypatch):
    """End to end: the warning has to reach check_notes, not just the guardrail
    dict that is never persisted."""
    import time

    workspace = str(tmp_path / "ws4")
    os.makedirs(workspace, exist_ok=True)
    _spec_without_a_clock(workspace, module_name="GCN")
    design = os.path.join(workspace, "gcn.v")
    with open(design, "w", encoding="utf-8") as f:
        f.write("module GCN(input rst, input data_in, output [3:0] data_out); endmodule")
    monkeypatch.setattr(sm, "_run_orfs", _fake_orfs_writing_artifacts("GCN"))

    started = sm.start_synthesis_job(workspace=workspace, verilog_files=[design], top_module="GCN")
    final = None
    for _ in range(60):
        final = sm.get_synthesis_status(started["run_id"], workspace=workspace)
        if final["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert final["status"] == "completed"
    # start_synthesis_job defaults clock_period_ns to 10.0, so the PERIOD is
    # "requested" here — the PORT is still the spec's first input.
    assert final["clock_source"] == "requested_period_fallback_port"
    assert final["clock_source"] in sm._UNVERIFIED_CLOCK_SOURCES
    assert "not verified" in (final["constraints_note"] or "").lower()
    assert "not verified" in final["check_notes"].lower()


def test_the_partial_flow_FAILED_leg_carries_the_warning_too(tmp_path, monkeypatch):
    """The rule lived as three verbatim copies, so it was already missing from
    the partial-flow failure branch: a run that ended on the wrong clock AND
    failed its target stage reported only the stage failure."""
    import time

    workspace = str(tmp_path / "ws5")
    os.makedirs(workspace, exist_ok=True)
    _spec(workspace, module_name="GCN", clock_port="clk_i")
    design = os.path.join(workspace, "gcn_top.v")
    with open(design, "w", encoding="utf-8") as f:
        f.write("module GCN_synth(input clk, output [3:0] q); endmodule")

    def fake_orfs_producing_nothing(**kwargs):
        # No completion artifact for the target stage -> the failed leg.
        return {"success": False, "stdout": "", "stderr": "boom", "command": "fake"}

    monkeypatch.setattr(sm, "_run_orfs", fake_orfs_producing_nothing)
    monkeypatch.setattr(sm, "_run_orfs_targets", fake_orfs_producing_nothing)

    started = sm.start_synthesis_job(
        workspace=workspace, verilog_files=[design], top_module="GCN_synth", max_stage="synth",
    )
    final = None
    for _ in range(400):
        final = sm.get_synthesis_status(started["run_id"], workspace=workspace)
        if final["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert final["status"] == "failed"
    assert final["clock_source"] == "default_module_mismatch"
    assert "partial flow failed" in final["check_notes"].lower()
    assert "not verified" in final["check_notes"].lower()


def test_carry_helper_is_idempotent_and_silent_on_a_verified_clock():
    """Every terminal write routes through the one helper, so it has to be safe
    to apply twice (adoption re-finalizes a meta whose check_notes already
    carries the note) and to apply to a run that earned no warning."""
    unverified = {"clock_source": "spec_fallback_port", "constraints_note": "port NOT verified."}
    once = sm._carry_unverified_clock_note(unverified, "Artifact/log guardrails passed")
    assert once == "Artifact/log guardrails passed | port NOT verified."
    assert sm._carry_unverified_clock_note(unverified, once) == once

    verified = {"clock_source": "spec", "constraints_note": "Spec-driven constraints validated."}
    assert sm._carry_unverified_clock_note(verified, "rollup") == "rollup"
    # No note recorded at all (legacy meta): nothing to carry, nothing invented.
    assert sm._carry_unverified_clock_note({"clock_source": "bypass_default"}, "rollup") == "rollup"


def test_no_spec_explicit_period_is_an_unverified_clock(tmp_path):
    """No spec + explicit period guesses the literal port 'clk' — the same
    unverified guess as bypass_default, and _write_default_sdc yields NO
    create_clock when the guess is wrong. The source must warn."""
    workspace = str(tmp_path / "ws_nospec")
    os.makedirs(workspace, exist_ok=True)
    run_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    os.makedirs(run_dir, exist_ok=True)

    result = sm._constraints_guardrail(
        workspace=workspace, run_dir=run_dir, top_module="counter",
        fallback_clock_period_ns=5.0, platform="sky130hd",
    )
    assert result["status"] == "pass"
    assert result["clock_source"] == "requested_period_default_port"
    assert result["clock_source"] in sm._UNVERIFIED_CLOCK_SOURCES
    assert "not verified" in result["note"].lower()
