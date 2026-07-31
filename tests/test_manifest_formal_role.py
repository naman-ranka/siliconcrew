"""The `formal` role (D2, dev#77 half 2 / dev#80 error 2).

A formal harness roled `rtl` poisons every compile set: iverilog refuses the
whole compile over one concurrent assertion. The derivation is filename-primary
with content as a NEGATIVE gate only — inline SVA in production RTL is normal
practice and must stay `rtl`, because dropping a real module from synthesis is
far worse than leaving a harness in.
"""
import os
import shutil
import subprocess

import pytest

from src.tools import manifest as m
from src.tools.run_simulation import run_simulation


FIFO = """
module fifo (input clk, input rst, input push, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= rst ? 8'h00 : (push ? din : dout);
endmodule
"""

# A formal harness: name says so AND it carries properties.
FIFO_PROPS = """
module fifo_props (input clk, input rst, input push, input [7:0] din, input [7:0] dout);
    assert property (@(posedge clk) rst |-> 1'b1);
    assume property (@(posedge clk) !(rst && push));
    cover property (@(posedge clk) push);
endmodule
"""

# Production RTL that happens to carry an inline concurrent assertion. THE
# critical fence: this must stay `rtl` and must still simulate.
ARBITER_WITH_INLINE_SVA = """
module arbiter (input clk, input rst, input req, output reg gnt);
    always @(posedge clk) begin
        if (rst) gnt <= 1'b0;
        else     gnt <= req;
    end
    assert property (@(posedge clk) !(rst && gnt));
endmodule
"""

ARBITER_TB = """
module arbiter_tb;
    reg clk = 0, rst = 1, req = 0;
    wire gnt;
    arbiter dut(.clk(clk), .rst(rst), .req(req), .gnt(gnt));
    always #5 clk = ~clk;
    initial begin #12 rst = 0; req = 1; #20 $display("TEST PASSED"); $finish; end
endmodule
"""


def _write(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_named_and_propertied_file_is_formal(tmp_path):
    assert m.derive_role("fifo_props.sv", FIFO_PROPS) == "formal"
    assert m.derive_role("fifo_properties.sv", FIFO_PROPS) == "formal"
    assert m.derive_role("fifo_fpv.sv", FIFO_PROPS) == "formal"
    assert m.derive_role("fifo_bind_fpv.sv", FIFO_PROPS) == "formal"
    assert m.derive_role("fifo_formal.v", FIFO_PROPS) == "formal"


def test_formal_name_without_properties_stays_rtl(tmp_path):
    """Content is a negative gate: the name alone never demotes a file."""
    assert m.derive_role("fifo_props.sv", FIFO) == "rtl"


def test_inline_assertions_in_rtl_stay_rtl(tmp_path):
    """The fence. Misreading this file as formal DROPS the module from synthesis."""
    assert m.derive_role("arbiter.v", ARBITER_WITH_INLINE_SVA) == "rtl"
    assert m.derive_role("arbiter.sv", ARBITER_WITH_INLINE_SVA) == "rtl"


def test_formal_is_excluded_from_every_stage_set(tmp_path):
    ws = str(tmp_path)
    _write(ws, "fifo.v", FIFO)
    _write(ws, "fifo_props.sv", FIFO_PROPS)
    _write(ws, "fifo_tb.v", "module fifo_tb; fifo d(); initial #1 $finish; endmodule\n")

    manifest = m.read_manifest(ws, session_id="s1")
    roles = {f.path: f.role for f in manifest.files}
    assert roles["fifo_props.sv"] == "formal"

    for stage in ("lint", "simulate", "synthesize"):
        assert "fifo_props.sv" not in m.files_for_stage(manifest, stage)
    assert "fifo.v" in m.files_for_stage(manifest, "synthesize")


def test_stored_role_override_survives_reconcile(tmp_path):
    """A user who says a formal-named file is rtl keeps that (invariant 1)."""
    ws = str(tmp_path)
    _write(ws, "fifo.v", FIFO)
    _write(ws, "fifo_props.sv", FIFO_PROPS)
    m.read_manifest(ws, session_id="s1")

    m.write_manifest(ws, {"files": [{"path": "fifo_props.sv", "role": "rtl"}]})
    reread = m.read_manifest(ws, session_id="s1")
    assert {f.path: f.role for f in reread.files}["fifo_props.sv"] == "rtl"

    # ...and the reverse override is accepted now that "formal" is a real role.
    m.write_manifest(ws, {"files": [{"path": "fifo.v", "role": "formal"}]})
    assert {f.path: f.role for f in m.read_manifest(ws).files}["fifo.v"] == "formal"


def test_role_list_reaches_the_agent_from_one_source(tmp_path):
    from src.tools import wrappers

    for role in m.ROLES:
        assert role in wrappers.update_manifest.description
    assert "formal" in wrappers.update_manifest.description


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")
def test_rtl_with_inline_sva_still_simulates(tmp_path):
    """The -gno-assertions companion fix, end to end with the real toolchain.

    Without the flag iverilog aborts the compile: "sorry: concurrent_assertion_item
    not supported" — so the fence's own critical case couldn't be simulated.
    """
    ws = str(tmp_path)
    _write(ws, "arbiter.v", ARBITER_WITH_INLINE_SVA)
    _write(ws, "arbiter_tb.v", ARBITER_TB)

    result = run_simulation(
        verilog_files=[os.path.join(ws, "arbiter.v"), os.path.join(ws, "arbiter_tb.v")],
        top_module="arbiter_tb",
        cwd=ws,
    )
    assert "-gno-assertions" in result["compile_command"]
    assert result["status"] == "test_passed", result

    # Proof the flag is what did it: the same compile without it fails.
    bare = subprocess.run(
        ["iverilog", "-g2012", "-s", "arbiter_tb", "-o", os.path.join(ws, "bare.out"),
         os.path.join(ws, "arbiter.v"), os.path.join(ws, "arbiter_tb.v")],
        capture_output=True, text=True,
    )
    assert bare.returncode != 0
    assert "concurrent_assertion_item" in (bare.stderr + bare.stdout)


def test_report_lists_formal_under_verification_and_is_honest_about_lint(tmp_path):
    from src.tools.design_report import generate_design_report

    ws = str(tmp_path)
    _write(ws, "fifo.v", FIFO)
    _write(ws, "fifo_props.sv", FIFO_PROPS)

    report = generate_design_report(ws)
    assert "| Verification — Formal properties | fifo_props.sv |" in report
    assert "| Design — RTL | fifo.v |" in report
    # The fabricated pass is gone: no lint ran, so the report cannot claim one.
    assert "| Syntax (Lint) | ✅ Pass |" not in report
    assert "Not run" in report


def test_report_files_section_sees_nested_files(tmp_path):
    """The old root-only listdir filed a nested RTL file nowhere at all."""
    from src.tools.design_report import generate_design_report

    ws = str(tmp_path)
    _write(ws, "rtl/alu.v", "module alu(input a, output b); assign b = a; endmodule\n")

    assert "rtl/alu.v" in generate_design_report(ws)
