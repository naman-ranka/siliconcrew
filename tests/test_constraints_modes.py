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
