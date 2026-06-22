"""Real EDA flows (no mocks) — exercised against actual iverilog/vvp.

These reproduce the hardening scenarios end-to-end through the SAME tool layer
the API and agent use: real lint, real isolated simulation, real VCDs, and the
strict status contract (test_passed / test_failed / sim_failed / compile_failed).
Skipped automatically if iverilog is not installed.
"""
import os
import shutil

import pytest

from src.tools import manifest as mf
from src.tools.run_linter import run_linter
from src.tools.sim_manager import run_sim_isolated

pytestmark = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")


def _w(ws, name, text):
    with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
        f.write(text)


COUNTER = """
module counter #(parameter WIDTH=8)(input clk, input rst, input en, output reg [WIDTH-1:0] count);
    always @(posedge clk) begin
        if (rst) count <= 0; else if (en) count <= count + 1;
    end
endmodule
"""

COUNTER_TB_PASS = """
module counter_tb;
    reg clk=0, rst=1, en=0; wire [7:0] count;
    counter dut(.clk(clk), .rst(rst), .en(en), .count(count));
    always #5 clk = ~clk;
    initial begin
        $dumpfile("counter.vcd"); $dumpvars(0, counter_tb);
        #12 rst=0; en=1; #100;
        if (count == 8'd10) $display("TEST PASSED");
        else $display("ERROR: count=%0d at t=%0dns -- TEST FAILED", count, $time);
        $finish;
    end
endmodule
"""

# Same TB but the DUT is wrong (counts by 2) → mismatch at runtime.
COUNTER_BUGGY = COUNTER.replace("count + 1", "count + 2")

# No pass marker printed at all → must be test_failed, not test_passed.
COUNTER_TB_NOMARKER = """
module counter_tb;
    reg clk=0, rst=1, en=0; wire [7:0] count;
    counter dut(.clk(clk), .rst(rst), .en(en), .count(count));
    always #5 clk = ~clk;
    initial begin $dumpfile("c.vcd"); $dumpvars(0,counter_tb); #12 rst=0; en=1; #100 $finish; end
endmodule
"""


def test_real_counter_passes_with_real_vcd(tmp_path):
    ws = str(tmp_path)
    _w(ws, "counter.v", COUNTER)
    _w(ws, "counter_tb.v", COUNTER_TB_PASS)
    m = mf.read_manifest(ws, "s")
    assert m.synthTop == "counter" and m.simTop == "counter_tb"

    r = run_sim_isolated(ws, mf.files_for_stage(m, "simulate"), m.simTop)
    assert r["status"] == "passed"
    assert r["passMarkerFound"] is True
    vcd = os.path.join(ws, r["vcdPath"])
    assert os.path.exists(vcd) and os.path.getsize(vcd) > 0
    assert r["provenance"]["iverilogVersion"]  # real version stamped


def test_real_sim_mismatch_is_test_failed_with_time(tmp_path):
    ws = str(tmp_path)
    _w(ws, "counter.v", COUNTER_BUGGY)
    _w(ws, "counter_tb.v", COUNTER_TB_PASS)
    m = mf.read_manifest(ws, "s")

    r = run_sim_isolated(ws, mf.files_for_stage(m, "simulate"), m.simTop)
    assert r["status"] == "failed"
    assert r["passMarkerFound"] is False
    assert r["failure"] is not None
    # the failure cursor time is parsed from the TB's "t=NNNns" message
    assert r["failure"]["timeNs"] is not None and r["failure"]["timeNs"] > 0


def test_real_no_pass_marker_is_test_failed_not_passed(tmp_path):
    ws = str(tmp_path)
    _w(ws, "counter.v", COUNTER)
    _w(ws, "counter_tb.v", COUNTER_TB_NOMARKER)
    m = mf.read_manifest(ws, "s")

    r = run_sim_isolated(ws, mf.files_for_stage(m, "simulate"), m.simTop)
    # rc==0 but no marker → strict contract says NOT passed
    assert r["status"] == "failed"
    assert r["passMarkerFound"] is False


def test_real_compile_failure_missing_module(tmp_path):
    ws = str(tmp_path)
    # TB instantiates `counter` but the RTL file is absent.
    _w(ws, "counter_tb.v", COUNTER_TB_PASS)
    m = mf.read_manifest(ws, "s")
    # Only the TB is present; sim must fail at compile (unknown module).
    r = run_sim_isolated(ws, ["counter_tb.v"], "counter_tb")
    assert r["status"] == "failed"
    assert r["simStatus"] == "compile_failed"
    assert (r["failure"] or {}).get("type") == "compile"


def test_real_lint_failure_reports_file_and_line(tmp_path):
    ws = str(tmp_path)
    # Missing semicolon → syntax error with a line number.
    _w(ws, "bad.v", "module bad(input a, output b);\n  assign b = a\n endmodule\n")
    res = run_linter([os.path.join(ws, "bad.v")], cwd=ws)
    assert res["success"] is False
    assert "bad.v" in res["stderr"]


def test_real_lint_passes_clean_rtl(tmp_path):
    ws = str(tmp_path)
    _w(ws, "counter.v", COUNTER)
    res = run_linter([os.path.join(ws, "counter.v")], cwd=ws)
    assert res["success"] is True


# --- Multi-module: cpu = alu + regfile + decoder + top + tb ------------------

ALU = """
module alu(input [7:0] a, input [7:0] b, input [1:0] op, output reg [7:0] y);
    always @(*) case(op)
        2'b00: y = a + b; 2'b01: y = a - b; 2'b10: y = a & b; default: y = a | b;
    endcase
endmodule
"""
REGFILE = """
module regfile(input clk, input we, input [7:0] d, output reg [7:0] q);
    always @(posedge clk) if (we) q <= d;
endmodule
"""
DECODER = """
module decoder(input [1:0] sel, output reg we, output reg [1:0] op);
    always @(*) begin we = (sel != 2'b11); op = sel; end
endmodule
"""
CPU_TOP = """
module cpu_top(input clk, input [7:0] a, input [7:0] b, input [1:0] sel, output [7:0] out);
    wire [1:0] op; wire we; wire [7:0] y;
    decoder dec(.sel(sel), .we(we), .op(op));
    alu u_alu(.a(a), .b(b), .op(op), .y(y));
    regfile rf(.clk(clk), .we(we), .d(y), .q(out));
endmodule
"""
CPU_TB = """
module cpu_tb;
    reg clk=0; reg [7:0] a, b; reg [1:0] sel; wire [7:0] out;
    cpu_top dut(.clk(clk), .a(a), .b(b), .sel(sel), .out(out));
    always #5 clk = ~clk;
    initial begin
        $dumpfile("cpu.vcd"); $dumpvars(0, cpu_tb);
        a=8'd3; b=8'd4; sel=2'b00; #10;  // add → 7, we=1
        #10;
        if (out == 8'd7) $display("TEST PASSED");
        else $display("ERROR: out=%0d at t=%0dns TEST FAILED", out, $time);
        $finish;
    end
endmodule
"""


def test_real_multimodule_roles_tops_lint_sim_synthset(tmp_path):
    ws = str(tmp_path)
    _w(ws, "alu.v", ALU); _w(ws, "regfile.v", REGFILE)
    _w(ws, "decoder.v", DECODER); _w(ws, "cpu_top.v", CPU_TOP)
    _w(ws, "cpu_tb.v", CPU_TB)
    _w(ws, "constraints.sdc", "create_clock -period 10 [get_ports clk]\n")

    m = mf.read_manifest(ws, "cpu")
    roles = {f.name: f.role for f in m.files}
    assert roles == {
        "alu.v": "rtl", "regfile.v": "rtl", "decoder.v": "rtl",
        "cpu_top.v": "rtl", "cpu_tb.v": "tb", "constraints.sdc": "sdc",
    }
    # Two tops inferred: DUT for synth, TB for sim.
    assert m.simTop == "cpu_tb"
    assert m.synthTop == "cpu_top"

    # Lint elaborates the DUT set (rtl only, no tb), and passes on real iverilog.
    lint_files = mf.files_for_stage(m, "lint")
    assert "cpu_tb.v" not in lint_files
    assert run_linter([os.path.join(ws, f) for f in lint_files], cwd=ws)["success"]

    # Synthesis set excludes the testbench but includes the sdc.
    synth_files = set(mf.files_for_stage(m, "synthesize"))
    assert "cpu_tb.v" not in synth_files
    assert "constraints.sdc" in synth_files
    assert {"alu.v", "regfile.v", "decoder.v", "cpu_top.v"} <= synth_files

    # Real hierarchical simulation passes and writes an isolated VCD.
    r = run_sim_isolated(ws, mf.files_for_stage(m, "simulate"), m.simTop)
    assert r["status"] == "passed", r.get("stdoutTail")
    assert os.path.exists(os.path.join(ws, r["vcdPath"]))
