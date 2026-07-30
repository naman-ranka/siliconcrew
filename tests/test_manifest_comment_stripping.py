"""Manifest parsing ignores Verilog comments (dev#77).

The module/instance/port regexes used to run over raw file text, so prose like
``// …provable on this module alone…`` injected a phantom module ``alone`` that
could win ``simTop`` (``mods[-1]``) or ``synthTop``, and a commented-out port
list could flip a testbench's role to ``rtl``.
"""
import os

from src.tools import manifest as m


def _write(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path) or ws, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


COUNTER = """
module counter (
    input clk,
    output reg [7:0] count
);
    always @(posedge clk) count <= count + 1;
endmodule
"""


def test_line_comment_module_is_not_extracted(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", "// This property is provable on this module alone\n" + COUNTER)

    manifest = m.build_manifest(ws)
    assert manifest.synthTop == "counter"


def test_block_comment_module_is_not_extracted(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", "/*\n * module phantom (input a);\n */\n" + COUNTER)

    manifest = m.build_manifest(ws)
    assert manifest.synthTop == "counter"


def test_trailing_comment_does_not_win_sim_top(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", COUNTER)
    _write(ws, "counter_tb.v", """
module counter_tb;
    reg clk;
    counter dut(.clk(clk));
    initial begin #100 $finish; end
endmodule
// TODO: prove this module alone
""")

    manifest = m.build_manifest(ws)
    assert manifest.simTop == "counter_tb"
    assert manifest.testbenches == [{"file": "counter_tb.v", "module": "counter_tb"}]


def test_commented_out_instance_does_not_poison_the_hierarchy(tmp_path):
    ws = str(tmp_path)
    # The commented-out instantiation of `top` must not make `top` look like a
    # non-root (which would leave the design with no root at all).
    _write(ws, "sub.v", """
module sub (input clk, output q);
/* disabled for now:
top u_top (.clk(clk), .q(q));
*/
    assign q = clk;
endmodule
""")
    _write(ws, "top.v", """
module top (input clk, output q);
    sub u_sub (.clk(clk), .q(q));
endmodule
""")

    manifest = m.build_manifest(ws)
    assert manifest.synthTop == "top"


def test_block_comment_removal_preserves_line_boundaries(tmp_path):
    ws = str(tmp_path)
    _write(ws, "sub.v", "module sub (input clk, output q);\n  assign q = clk;\nendmodule\n")
    # The instance regex is ``^\\s*``-anchored per line: collapsing the block
    # comment to "" would splice `sub u_sub (…)` onto the `reg unused;` line and
    # the instantiation would be lost.
    _write(ws, "top.v", """
module top (input clk, output q);
    reg unused; /* a note that
    spans lines */ sub u_sub (.clk(clk), .q(q));
endmodule
""")

    manifest = m.build_manifest(ws)
    assert manifest.synthTop == "top"


def test_commented_port_list_does_not_flip_tb_role():
    # No `_tb` naming, no real ports, instantiates a module -> testbench. The
    # only port list in the file is inside a comment.
    text = """
// module fake_dut (input a, output b);
module harness;
    reg clk;
    counter dut(.clk(clk));
endmodule
"""
    assert m.derive_role("harness.v", text) == "tb"
