"""Manifest role-derivation, top inference, persistence + reconciliation."""
import os

from src.tools import manifest as m


def _write(ws, name, text):
    with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
        f.write(text)


DUT = """
module counter (
    input clk,
    input rst,
    output reg [7:0] count
);
    always @(posedge clk) count <= rst ? 8'b0 : count + 1;
endmodule
"""

TB = """
module counter_tb;
    reg clk, rst;
    wire [7:0] count;
    counter dut(.clk(clk), .rst(rst), .count(count));
    initial begin $dumpfile("dump.vcd"); #100 $finish; end
endmodule
"""


def test_role_derivation_by_name_and_content(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", DUT)
    _write(ws, "counter_tb.v", TB)
    _write(ws, "constraints.sdc", "create_clock -period 10 [get_ports clk]\n")
    _write(ws, "defs.vh", "`define WIDTH 8\n")

    assert m.derive_role("counter.v", DUT) == "rtl"
    assert m.derive_role("counter_tb.v", TB) == "tb"
    assert m.derive_role("constraints.sdc") == "sdc"
    assert m.derive_role("defs.vh") == "include"


def test_portless_instantiating_module_is_tb(tmp_path):
    ws = str(tmp_path)
    # No "_tb" in the name, but it has no ports and instantiates another module.
    harness = "module harness;\n counter dut(.clk(c));\nendmodule\n"
    assert m.derive_role("harness.v", harness) == "tb"


def test_build_manifest_infers_tops(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", DUT)
    _write(ws, "counter_tb.v", TB)

    manifest = m.build_manifest(ws, session_id="s1")
    assert manifest.sessionId == "s1"
    assert manifest.simTop == "counter_tb"
    assert manifest.synthTop == "counter"
    roles = {f.name: f.role for f in manifest.files}
    assert roles == {"counter.v": "rtl", "counter_tb.v": "tb"}


def test_read_persists_and_write_overrides_role(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", DUT)
    _write(ws, "counter_tb.v", TB)

    first = m.read_manifest(ws, session_id="s1")
    assert os.path.exists(os.path.join(ws, m.MANIFEST_FILENAME))

    # User overrides a role; it must persist and survive reconciliation.
    m.write_manifest(ws, {"files": [{"name": "counter.v", "role": "tb"}], "platform": "asap7"})
    reread = m.read_manifest(ws, session_id="s1")
    roles = {f.name: f.role for f in reread.files}
    assert roles["counter.v"] == "tb"
    assert reread.platform == "asap7"


def test_reconcile_adds_new_and_drops_missing(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", DUT)
    m.read_manifest(ws, session_id="s1")

    # Add a file outside the manifest API, then re-read.
    _write(ws, "counter_tb.v", TB)
    reread = m.read_manifest(ws, session_id="s1")
    names = {f.name for f in reread.files}
    assert names == {"counter.v", "counter_tb.v"}

    # Remove a file; reconciliation drops it.
    os.remove(os.path.join(ws, "counter.v"))
    reread2 = m.read_manifest(ws, session_id="s1")
    assert {f.name for f in reread2.files} == {"counter_tb.v"}


def test_synthtop_is_hierarchy_root_not_submodule(tmp_path):
    # Regression: multi-module design where the tb's DUT (`top`) instantiates a
    # submodule (`mux2`). synthTop must be the root `top`, never the leaf `mux2`.
    ws = str(tmp_path)
    _write(ws, "mux2.v", "module mux2(input a, input b, input s, output y); assign y = s?b:a; endmodule\n")
    _write(ws, "top.v",
           "module top(input [1:0] a, input [1:0] b, input s, output [1:0] y);\n"
           "  mux2 m0(.a(a[0]),.b(b[0]),.s(s),.y(y[0]));\n"
           "  mux2 m1(.a(a[1]),.b(b[1]),.s(s),.y(y[1]));\n"
           "endmodule\n")
    _write(ws, "top_tb.v",
           "module top_tb; reg [1:0] a,b; reg s; wire [1:0] y;\n"
           "  top dut(.a(a),.b(b),.s(s),.y(y));\n"
           "  initial begin a=1;b=2;s=0; #1 $finish; end\nendmodule\n")
    mani = m.build_manifest(ws, "t")
    assert mani.simTop == "top_tb"
    assert mani.synthTop == "top"  # not "mux2"


def test_files_for_stage(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", DUT)
    _write(ws, "counter_tb.v", TB)
    _write(ws, "constraints.sdc", "create_clock -period 10 [get_ports clk]\n")
    _write(ws, "defs.vh", "`define WIDTH 8\n")
    manifest = m.read_manifest(ws, session_id="s1")

    lint = set(m.files_for_stage(manifest, "lint"))
    assert lint == {"counter.v", "defs.vh"}

    sim = set(m.files_for_stage(manifest, "simulate"))
    assert sim == {"counter.v", "counter_tb.v", "defs.vh"}

    synth = set(m.files_for_stage(manifest, "synthesize"))
    assert synth == {"counter.v", "constraints.sdc"}
