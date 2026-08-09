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


def test_block_open_inside_line_comment_does_not_swallow_code(tmp_path):
    # `/*` inside a `//` comment must NOT open a block comment: with two-pass
    # stripping (block first) it ran to the next `*/` anywhere later in the
    # file, deleting the real module declaration in between.
    ws = str(tmp_path)
    _write(ws, "core.v", """
// disabled: /* old pipelined variant, restore after the retime fix
module vxm_core (input clk, output q);
  sub u_sub (.clk(clk), .q(q));
endmodule

/* Revision history:
 *   2026-05: added the retime fix
 */
module vxm_wrap (input clk, output q);
  vxm_core u_core (.clk(clk), .q(q));
endmodule
""")
    _write(ws, "sub.v", "module sub (input clk, output q); assign q = clk; endmodule\n")

    manifest = m.build_manifest(ws)
    # vxm_core must survive as a declared module and vxm_wrap stays the root.
    assert manifest.synthTop == "vxm_wrap"
    scans = m._scan_design_files(ws, manifest.files)
    assert "vxm_core" in scans["core.v"].modules
    assert "sub" in scans["core.v"].instances


def test_string_containing_module_keyword_is_not_a_declaration():
    text = 'module real_mod;\n  initial $display("module fake_mod booting");\nendmodule\n'
    assert m._modules_in(m._strip_comments(text)) == ["real_mod"]


def test_line_comment_url_does_not_corrupt_the_line():
    # "https://example.com" inside a string: the `//` must not be taken as a
    # comment start (it would delete the rest of the line, string quote and all).
    text = 'module a;\n  initial $display("see https://example.com/x");\n  b u_b (.c(1));\nendmodule\nmodule b(input c); endmodule\n'
    stripped = m._strip_comments(text)
    assert m._modules_in(stripped) == ["a", "b"]
    assert "u_b" not in stripped or "b" in [i for i in m._instances_in(stripped)]
