"""Duplicate-module collision detection (D1, sc#66).

Auto-discovery happily pulls a reference copy of a design into the compile set;
the toolchain then errors (iverilog) or silently picks one (yosys). Nothing here
auto-excludes anything — the manifest names both files and the remedy.
"""
import json
import os

from src.tools import manifest as m


def _write(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


GCN = """
module gcn (input clk, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= din;
endmodule
"""

GCN_REF = """
module gcn (input clk, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= din + 1;
endmodule
"""

TB = """
module gcn_tb;
    reg clk; reg [7:0] din; wire [7:0] dout;
    gcn dut(.clk(clk), .din(din), .dout(dout));
    initial begin clk = 0; din = 1; #10 $display("TEST PASSED"); $finish; end
endmodule
"""

# Two `ifdef-gated alternates of ONE module across two files — legal together
# (only one survives the preprocessor). This must never be reported.
SRAM_BEHAV = """
`ifndef SRAM_MACRO
module sram (input clk, input we, input [3:0] addr, input [7:0] din, output reg [7:0] dout);
    reg [7:0] mem [0:15];
    always @(posedge clk) begin
        if (we) mem[addr] <= din;
        dout <= mem[addr];
    end
endmodule
`endif
"""

SRAM_MACRO = """
`ifdef SRAM_MACRO
module sram (input clk, input we, input [3:0] addr, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= 8'h00;
endmodule
`endif
"""


def test_collision_names_both_files_and_the_remedy(tmp_path):
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "given/gcn_reference.v", GCN_REF)
    _write(ws, "gcn_tb.v", TB)

    manifest = m.read_manifest(ws, session_id="s1")

    assert len(manifest.warnings) == 1
    warning = manifest.warnings[0]
    assert "'gcn'" in warning
    assert "gcn.v" in warning and "given/gcn_reference.v" in warning
    assert "ignore" in warning  # the remedy no compiler can name


def test_ignore_glob_clears_the_collision(tmp_path):
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "given/gcn_reference.v", GCN_REF)
    _write(ws, "gcn_tb.v", TB)
    m.read_manifest(ws, session_id="s1")

    updated = m.write_manifest(ws, {"ignore": ["given/**"]})
    assert updated.warnings == []
    assert m.read_manifest(ws, session_id="s1").warnings == []


def test_role_other_clears_the_collision(tmp_path):
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "given/gcn_reference.v", GCN_REF)
    m.read_manifest(ws, session_id="s1")

    updated = m.write_manifest(ws, {"files": [{"path": "given/gcn_reference.v", "role": "other"}]})
    assert updated.warnings == []


def test_ifdef_gated_alternates_do_not_warn(tmp_path):
    ws = str(tmp_path)
    _write(ws, "sram_behav.v", SRAM_BEHAV)
    _write(ws, "sram_macro.v", SRAM_MACRO)

    manifest = m.read_manifest(ws, session_id="s1")
    assert manifest.warnings == []


INCLUDE_GUARDED_REF = """
`ifndef GCN_REF_V
`define GCN_REF_V
module gcn (input clk, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= din + 1;
endmodule
`endif
"""


def test_include_guarded_reference_copy_still_warns(tmp_path):
    """The conventional `ifndef X_V/`define/`endif wrapper is NOT an alternate.

    Its guard macro is unique to itself, so the copy is always compiled and it
    collides with the plain original — verified with iverilog ('gcn' has already
    been declared). Suppressing on "any declaration guarded" silenced sc#66's own
    scenario; suppression requires EVERY declaration to be conditional.
    """
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "given/gcn_reference.v", INCLUDE_GUARDED_REF)

    warnings = m.read_manifest(ws, session_id="s1").warnings
    assert len(warnings) == 1
    assert "gcn.v" in warnings[0] and "given/gcn_reference.v" in warnings[0]


def test_same_include_guard_in_two_copies_does_not_warn(tmp_path):
    """Both guarded by the SAME macro: the preprocessor keeps one. iverilog agrees."""
    ws = str(tmp_path)
    guarded = "`ifndef SHARED_V\n`define SHARED_V\n" + GCN + "`endif\n"
    _write(ws, "a/shared.v", guarded)
    _write(ws, "b/shared.v", guarded)

    assert m.read_manifest(ws, session_id="s1").warnings == []


def test_warning_names_the_set_it_affects(tmp_path):
    """An rtl/tb duplicate breaks simulation only — synthesis never sees the tb."""
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "gcn_tb.v", TB + GCN)  # the TB also declares gcn

    warnings = m.read_manifest(ws, session_id="s1").warnings
    assert len(warnings) == 1
    assert "the simulation compile set" in warnings[0]

    ws2 = str(tmp_path / "two")
    _write(ws2, "gcn.v", GCN)
    _write(ws2, "given/gcn_reference.v", GCN_REF)
    rtl_only = m.read_manifest(ws2, session_id="s2").warnings
    assert "every compile set" in rtl_only[0]


def test_clean_workspace_has_no_warnings(tmp_path):
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "gcn_tb.v", TB)

    assert m.read_manifest(ws, session_id="s1").warnings == []


def test_same_module_in_one_file_twice_is_not_a_collision(tmp_path):
    """Two declarations in ONE file are that file's problem, not a file-set one."""
    ws = str(tmp_path)
    _write(ws, "dup.v", GCN + GCN_REF)
    assert m.read_manifest(ws, session_id="s1").warnings == []


def test_compile_set_collisions_only_reports_files_in_the_set(tmp_path):
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "given/gcn_reference.v", GCN_REF)

    assert m.compile_set_collisions(ws, ["gcn.v"]) == []
    both = m.compile_set_collisions(ws, ["gcn.v", "given/gcn_reference.v"])
    assert len(both) == 1 and "gcn.v" in both[0]
    # Absolute paths (what start_synthesis assembles) still report relative names.
    abs_set = m.compile_set_collisions(
        ws, [os.path.join(ws, "gcn.v"), os.path.join(ws, "given", "gcn_reference.v")]
    )
    assert abs_set == both


# --- point of damage: the dispatch replies ---------------------------------

def _stub_sim_run(**_kwargs):
    return {"id": "sim_0001", "status": "failed", "simStatus": "compile_failed"}


def _patch_workspace(monkeypatch, ws):
    from src.tools import wrappers

    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")
    return wrappers


def test_sim_dispatch_reply_leads_with_the_collision(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "given/gcn_reference.v", GCN_REF)
    _write(ws, "gcn_tb.v", TB)
    wrappers = _patch_workspace(monkeypatch, ws)
    monkeypatch.setattr(wrappers, "run_sim_isolated", _stub_sim_run)

    payload = json.loads(wrappers.run_isolated_simulation.func())
    assert list(payload)[0] == "manifestWarnings"  # first thing the agent reads
    assert "gcn.v" in payload["manifestWarnings"][0]
    assert payload["id"] == "sim_0001"  # the run record is intact


def test_sim_dispatch_reply_is_clean_without_a_collision(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "gcn_tb.v", TB)
    wrappers = _patch_workspace(monkeypatch, ws)
    monkeypatch.setattr(wrappers, "run_sim_isolated", _stub_sim_run)

    payload = json.loads(wrappers.run_isolated_simulation.func())
    assert "manifestWarnings" not in payload


def test_synthesis_dispatch_reply_carries_the_collision(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _write(ws, "gcn.v", GCN)
    _write(ws, "given/gcn_reference.v", GCN_REF)
    wrappers = _patch_workspace(monkeypatch, ws)
    monkeypatch.setattr(wrappers, "start_synthesis_job", lambda **kw: {"run_id": "synth_0001"})

    payload = json.loads(wrappers.start_synthesis.func(
        verilog_files=["gcn.v", "given/gcn_reference.v"], top_module="gcn"
    ))
    assert "manifestWarnings" in payload
    assert payload["run_id"] == "synth_0001"

    clean = json.loads(wrappers.start_synthesis.func(verilog_files=["gcn.v"], top_module="gcn"))
    assert "manifestWarnings" not in clean


DISTINCT_GUARD_A = """
`ifndef GCN_V
`define GCN_V
module gcn (input clk, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= din;
endmodule
`endif
"""

DISTINCT_GUARD_B = """
`ifndef GIVEN_GCN_V
`define GIVEN_GCN_V
module gcn (input clk, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= din + 1;
endmodule
`endif
"""


def test_two_copies_with_distinct_include_guards_still_warn(tmp_path):
    """Each copy carries its OWN guard macro — both always compile, iverilog
    errors. 'Every declaration is guarded' alone must not suppress: the guard
    MACROS have to make the declarations mutually exclusive."""
    ws = str(tmp_path)
    _write(ws, "gcn.v", DISTINCT_GUARD_A)
    _write(ws, "given/gcn_reference.v", DISTINCT_GUARD_B)

    warnings = m.read_manifest(ws, session_id="s1").warnings
    assert len(warnings) == 1
    assert "gcn.v" in warnings[0] and "given/gcn_reference.v" in warnings[0]


def test_ifdef_else_alternates_do_not_warn(tmp_path):
    """`ifdef X / `else in ONE file plus `ifdef X in another: the else-branch
    condition is the complement of the macro, so at most one survives."""
    ws = str(tmp_path)
    _write(ws, "sram_sel.v", """
`ifdef SRAM_MACRO
module sram_stub (input clk); endmodule
`else
module sram (input clk, output reg [7:0] dout);
    always @(posedge clk) dout <= 8'h01;
endmodule
`endif
""")
    _write(ws, "sram_macro.v", """
`ifdef SRAM_MACRO
module sram (input clk, output reg [7:0] dout);
    always @(posedge clk) dout <= 8'h00;
endmodule
`endif
""")

    assert m.read_manifest(ws, session_id="s1").warnings == []


def test_multiline_module_declaration_inside_guard_is_seen(tmp_path):
    """`module` and its name split across lines inside a guard: the line-based
    scan missed the declaration and produced a false collision warning."""
    ws = str(tmp_path)
    guarded = "`ifndef SHARED_V\n`define SHARED_V\nmodule\n  sram (input clk, output q);\n  assign q = clk;\nendmodule\n`endif\n"
    _write(ws, "a/sram.v", guarded)
    _write(ws, "b/sram.v", guarded)

    assert m.read_manifest(ws, session_id="s1").warnings == []


def test_elsif_alternates_across_files_do_not_warn(tmp_path):
    """`ifdef A / `elsif B: the second branch's condition is (not-A and B),
    so it is mutually exclusive with another file's `ifdef A copy. Dropping
    the not-A term manufactured a collision warning for a pair the
    preprocessor can never compile together."""
    ws = str(tmp_path)
    _write(ws, "fast/gcn.v", """
`ifdef USE_FAST
module gcn (input clk, output reg [7:0] dout);
    always @(posedge clk) dout <= 8'h01;
endmodule
`endif
""")
    _write(ws, "slow/gcn.v", """
`ifdef USE_FAST
module gcn_unused_stub (input clk); endmodule
`elsif USE_SLOW
module gcn (input clk, output reg [7:0] dout);
    always @(posedge clk) dout <= 8'h02;
endmodule
`endif
""")

    assert m.read_manifest(ws, session_id="s1").warnings == []


def test_identical_plain_ifdef_guards_still_warn(tmp_path):
    """A plain `ifdef DEBUG (no `define inside) in BOTH copies is not an
    include guard: under +define+DEBUG both compile and collide. Identical
    conditions suppress only when each copy SELF-DEFINES the guard macro
    (`ifndef X + `define X — the preprocessor keeps one)."""
    ws = str(tmp_path)
    plain = """
`ifdef DEBUG
module foo (input a);
endmodule
`endif
"""
    _write(ws, "a/foo.v", plain)
    _write(ws, "b/foo.v", plain)

    warnings = m.read_manifest(ws, session_id="s1").warnings
    assert len(warnings) == 1
    assert "a/foo.v" in warnings[0] and "b/foo.v" in warnings[0]
