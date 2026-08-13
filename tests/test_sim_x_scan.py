"""dev#76: X-propagation is surfaced honestly on the sim run record.

``x !== x`` evaluates FALSE, so a testbench comparing an undefined expected
value against an undefined DUT output silently counts the vector as checked
and still prints its pass marker. The post-run VCD scan turns the one
artifact that shows the undefinedness into honest fields (``xDetected``,
``xScan``) beside the verdict — it never changes the verdict itself.
"""
import os
import tempfile

import src.tools.sim_manager as sm
from src.tools.read_waveform import read_waveform, scan_vcd_for_x


# Header: tb.clk (!), tb.data ("), tb.dut.out (#). x values in the t=0 initial
# dump (universal for uninitialized regs — must NOT count), then real x
# propagation at t=10 on both the vector and the scalar.
VCD_WITH_X = """$date today $end
$timescale 1ns $end
$scope module tb $end
$var wire 1 ! clk $end
$var wire 8 " data $end
$scope module dut $end
$var wire 1 # out $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
bxxxxxxxx "
x#
$end
#5
1!
b00000001 "
0#
#10
0!
bxxxx0101 "
x#
#15
1!
"""

# Same shape, but after t=0 every value is defined.
VCD_CLEAN = """$date today $end
$timescale 1ns $end
$scope module tb $end
$var wire 1 ! clk $end
$var wire 8 " data $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
bxxxxxxxx "
$end
#5
1!
b00000001 "
#10
0!
b00000010 "
"""


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def test_scan_detects_x_after_t0(tmp_path):
    vcd = _write(str(tmp_path / "dump.vcd"), VCD_WITH_X)
    result = scan_vcd_for_x(vcd)
    assert result["status"] == "scanned"
    assert result["xDetected"] is True
    assert result["xEventCount"] == 2          # b-vector + scalar at t=10
    assert result["xSignalCount"] == 2
    assert set(result["xSignals"]) == {"tb.data", "tb.dut.out"}


def test_scan_excludes_t0_initial_dump(tmp_path):
    vcd = _write(str(tmp_path / "dump.vcd"), VCD_CLEAN)
    result = scan_vcd_for_x(vcd)
    assert result["status"] == "scanned"
    assert result["xDetected"] is False        # t=0 x dump alone must not flag
    assert result["xEventCount"] == 0
    assert result["xSignals"] == []


def test_scan_bails_honestly_on_oversized_vcd(tmp_path):
    vcd = _write(str(tmp_path / "dump.vcd"), VCD_WITH_X)
    result = scan_vcd_for_x(vcd, max_bytes=10)
    assert result["status"] == "skipped (size)"
    assert result["sizeBytes"] > 10
    assert "xDetected" not in result           # no fake verdict on a skip


def test_scan_missing_file_is_skipped_not_false(tmp_path):
    result = scan_vcd_for_x(str(tmp_path / "nope.vcd"))
    assert result["status"] == "skipped (unreadable)"
    assert "xDetected" not in result


def _fake_runner(vcd_text=None, status="test_passed"):
    def runner(verilog_files, top_module, cwd, mode, run_id, netlist_file,
               platform, sim_profile, pass_marker, timeout, log_path=None):
        if vcd_text is not None:
            _write(os.path.join(cwd, "dump.vcd"), vcd_text)
        return {
            "status": status,
            "pass_marker_found": status == "test_passed",
            "stdout_tail": "TEST PASSED" if status == "test_passed" else "",
            "stderr_tail": "", "log_truncated": False,
            "compile_returncode": 0, "sim_returncode": 0,
        }
    return runner


def test_run_record_carries_x_fields_without_changing_verdict():
    with tempfile.TemporaryDirectory() as ws:
        _write(os.path.join(ws, "tb.v"), "module tb; endmodule")
        run = sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner(VCD_WITH_X))
        # Verdict stays what the testbench printed — x is a warning, not a fail.
        assert run["status"] == "passed"
        assert run["xDetected"] is True
        assert run["xScan"]["status"] == "scanned"
        assert set(run["xScan"]["xSignals"]) == {"tb.data", "tb.dut.out"}
        # ... and it persists on the run record (the run dir is the database).
        persisted = sm.get_sim_run(ws, run["id"])
        assert persisted["xDetected"] is True


def test_run_record_without_vcd_reports_unknown_not_false():
    with tempfile.TemporaryDirectory() as ws:
        _write(os.path.join(ws, "tb.v"), "module tb; endmodule")
        run = sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner(None))
        assert run["xDetected"] is None
        assert run["xScan"] is None


def test_run_record_clean_vcd_reports_false():
    with tempfile.TemporaryDirectory() as ws:
        _write(os.path.join(ws, "tb.v"), "module tb; endmodule")
        run = sm.run_sim_isolated(ws, ["tb.v"], "tb", _runner=_fake_runner(VCD_CLEAN))
        assert run["xDetected"] is False
        assert run["xScan"]["status"] == "scanned"


def test_read_waveform_still_reads_after_header_extraction(tmp_path):
    """The shared header parser must not change read_waveform behavior."""
    vcd = _write(str(tmp_path / "dump.vcd"), VCD_WITH_X)
    out = read_waveform(vcd, ["clk"])
    assert "Time\tSignal\tValue" in out
    assert "5\tclk\t1" in out
    # Hierarchical resolution through the extracted parser:
    out = read_waveform(vcd, ["tb.dut.out"])
    assert "10\ttb.dut.out\tx" in out
