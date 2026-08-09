"""Module-declaration syntax the regex must survive (IEEE 1800).

`module_keyword [lifetime] module_identifier`: without the lifetime branch,
`module automatic core` declared a phantom module named 'automatic' that could
win synthTop — dev#77's failure through a different vector. `extern module`
is a legal prototype beside the definition (§23.2.4) and must not read as a
second declaration (it produced bogus collision warnings).
"""
import os

from src.tools import manifest as m


def _write(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path) or ws, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_lifetime_qualifier_is_not_a_module_name():
    text = "module automatic core (input clk, output q);\n  assign q = clk;\nendmodule\n"
    assert m._modules_in(m._strip_comments(text)) == ["core"]
    text = "module static helper (input a);\nendmodule\n"
    assert m._modules_in(m._strip_comments(text)) == ["helper"]


def test_module_automatic_does_not_poison_synth_top(tmp_path):
    ws = str(tmp_path)
    _write(ws, "core.v", "module automatic core (input clk, output q);\n  assign q = clk;\nendmodule\n")
    _write(ws, "core_tb.v", "module core_tb;\n  reg clk;\n  core dut(.clk(clk), .q());\nendmodule\n")
    manifest = m.build_manifest(ws)
    assert manifest.synthTop == "core"
    assert manifest.simTop == "core_tb"
    assert manifest.warnings == []


def test_extern_module_prototype_is_not_a_declaration(tmp_path):
    ws = str(tmp_path)
    _write(ws, "gcn.v", "module gcn (input clk, output q);\n  assign q = clk;\nendmodule\n")
    _write(ws, "protos.v", "extern module gcn (input clk, output q);\nmodule user_of (input clk, output q);\n  gcn u (.clk(clk), .q(q));\nendmodule\n")
    manifest = m.build_manifest(ws)
    # A prototype plus the one real definition is NOT a collision.
    assert manifest.warnings == []
    assert manifest.synthTop == "user_of"


def test_lifetime_qualifier_does_not_flip_role_to_tb(tmp_path):
    """_HAS_PORTS_RE must skip the lifetime too: a ported `module automatic`
    read as port-less, the file derived as tb, and the module silently left
    the synthesis compile set (files_for_stage synth = rtl + sdc)."""
    ws = str(tmp_path)
    _write(ws, "sub.v", "module sub (input a);\nendmodule\n")
    _write(ws, "core.v", "module automatic core (input clk, output q);\n  sub u1 (.a(clk));\nendmodule\n")
    manifest = m.build_manifest(ws)
    core = next(f for f in manifest.files if f.path == "core.v")
    assert core.role == "rtl"
    assert "core.v" in m.files_for_stage(manifest, "synth")
