"""dev#44: the manifest carries the design's pass marker.

Precedence chain, verified end to end:
    explicit per-call ``pass_marker``  >  manifest ``passMarker``  >  "TEST PASSED"

The per-call default silently disagreeing with what agent testbenches actually
print ("TEST_PASS" vs "TEST PASSED") reported genuine passes as failures. A
design's pass criterion is a property of the design (invariant 1), so it now
lives on the manifest; every surface funnels through run_simulation, which is
where the resolution happens.
"""
import json
import os
import tempfile

import src.tools.manifest as mf
import src.tools.run_simulation as rs
import src.tools.sim_manager as sm


def _fake_toolchain(monkeypatch, stdout):
    monkeypatch.setattr(
        rs, "_compile",
        lambda **kw: {"returncode": 0, "stdout": "", "stderr": "", "command": "iverilog"},
    )
    monkeypatch.setattr(
        rs, "_simulate",
        lambda **kw: {"returncode": 0, "stdout": stdout, "stderr": "", "command": "vvp"},
    )


def _ws_with_marker(ws, marker):
    with open(os.path.join(ws, "tb.v"), "w", encoding="utf-8") as f:
        f.write("module tb; endmodule")
    mf.read_manifest(ws, "s")
    if marker is not None:
        mf.write_manifest(ws, {"passMarker": marker}, session_id="s")


def test_default_when_no_manifest_marker(monkeypatch):
    _fake_toolchain(monkeypatch, "TEST PASSED\n")
    with tempfile.TemporaryDirectory() as ws:
        _ws_with_marker(ws, None)
        result = rs.run_simulation(verilog_files=[], top_module="tb", cwd=ws, workspace=ws)
        assert result["status"] == "test_passed"
        assert result["pass_marker"] == "TEST PASSED"


def test_manifest_marker_used_when_call_omits_it(monkeypatch):
    _fake_toolchain(monkeypatch, "TEST_PASS\n")
    with tempfile.TemporaryDirectory() as ws:
        _ws_with_marker(ws, "TEST_PASS")
        result = rs.run_simulation(verilog_files=[], top_module="tb", cwd=ws, workspace=ws)
        assert result["status"] == "test_passed"
        assert result["pass_marker_found"] is True
        assert result["pass_marker"] == "TEST_PASS"


def test_manifest_marker_not_printed_is_honest_failure(monkeypatch):
    # The manifest says TEST_PASS; the TB printed something else -> not passed,
    # and the result names the exact marker that was grepped.
    _fake_toolchain(monkeypatch, "TEST PASSED\n")
    with tempfile.TemporaryDirectory() as ws:
        _ws_with_marker(ws, "TEST_PASS")
        result = rs.run_simulation(verilog_files=[], top_module="tb", cwd=ws, workspace=ws)
        assert result["status"] == "test_failed"
        assert result["pass_marker"] == "TEST_PASS"


def test_explicit_arg_beats_manifest_marker(monkeypatch):
    _fake_toolchain(monkeypatch, "ALL GOOD\n")
    with tempfile.TemporaryDirectory() as ws:
        _ws_with_marker(ws, "TEST_PASS")
        result = rs.run_simulation(
            verilog_files=[], top_module="tb", cwd=ws, workspace=ws,
            pass_marker="ALL GOOD",
        )
        assert result["status"] == "test_passed"
        assert result["pass_marker"] == "ALL GOOD"

        # ... and the explicit arg wins even when the manifest marker WOULD
        # have matched: precedence, not first-match.
        result = rs.run_simulation(
            verilog_files=[], top_module="tb", cwd=ws, workspace=ws,
            pass_marker="NOT PRINTED",
        )
        assert result["status"] == "test_failed"
        assert result["pass_marker"] == "NOT PRINTED"


def test_isolated_run_resolves_manifest_marker(monkeypatch):
    """run_sim_isolated (agent tool + IDE Simulate) forwards no marker; the
    run record must carry the manifest-resolved one."""
    _fake_toolchain(monkeypatch, "TEST_PASS\n")
    with tempfile.TemporaryDirectory() as ws:
        _ws_with_marker(ws, "TEST_PASS")
        sim_run = sm.run_sim_isolated(
            workspace=ws, verilog_files=["tb.v"], top_module="tb", mode="rtl",
        )
        assert sim_run["status"] == "passed"
        assert sim_run["passMarkerFound"] is True
        assert sim_run["passMarker"] == "TEST_PASS"
        persisted = sm.get_sim_run(ws, sim_run["id"])
        assert persisted["passMarker"] == "TEST_PASS"


def test_pass_marker_round_trips_through_manifest(tmp_path):
    ws = str(tmp_path)
    with open(os.path.join(ws, "tb.v"), "w", encoding="utf-8") as f:
        f.write("module tb; endmodule")
    mf.write_manifest(ws, {"passMarker": "TEST_PASS"}, session_id="s")

    with open(os.path.join(ws, mf.MANIFEST_FILENAME), "r", encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["passMarker"] == "TEST_PASS"
    assert mf.read_manifest(ws, "s").passMarker == "TEST_PASS"
    assert mf.stored_pass_marker(ws) == "TEST_PASS"

    # Clearing back to the default is a legitimate edit (empty string sets).
    mf.write_manifest(ws, {"passMarker": ""}, session_id="s")
    assert mf.stored_pass_marker(ws) == ""


def test_stored_pass_marker_without_manifest_is_empty(tmp_path):
    assert mf.stored_pass_marker(str(tmp_path)) == ""
