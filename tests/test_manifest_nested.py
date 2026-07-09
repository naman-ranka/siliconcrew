"""Recursive manifest scan: nested discovery, exclusions, derived testbenches.

Item 2 of plans/verification-loop-v1.md. The manifest walks the workspace
(excluding run dirs / dot-dirs / user ``ignore`` globs, depth-capped), keys all
role/top logic by workspace-relative POSIX path, and derives a ``testbenches``
list from role=="tb" files. Snapshot/listing endpoints follow the same policy.
"""
import importlib.util
import json
import os

import pytest

from src.tools import manifest as m

_HAS_FASTAPI = importlib.util.find_spec("fastapi") is not None
_HAS_APP_STACK = _HAS_FASTAPI and importlib.util.find_spec("langchain_core") is not None


def _write(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path) or ws, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
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

TB2 = """
module counter_stress_tb;
    reg clk, rst;
    wire [7:0] count;
    counter dut(.clk(clk), .rst(rst), .count(count));
    initial begin #500 $finish; end
endmodule
"""


# --------------------------------------------------------------------------- #
# Discovery + roles + tops across directories
# --------------------------------------------------------------------------- #

def test_nested_discovery_roles_and_tops(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "tb/counter_tb.v", TB)
    _write(ws, "constraints/clock.sdc", "create_clock -period 10 [get_ports clk]\n")
    _write(ws, "rtl/defs.vh", "`define WIDTH 8\n")

    manifest = m.build_manifest(ws, session_id="s1")
    roles = {f.path: f.role for f in manifest.files}
    assert roles == {
        "rtl/counter.v": "rtl",
        "tb/counter_tb.v": "tb",
        "constraints/clock.sdc": "sdc",
        "rtl/defs.vh": "include",
    }
    # name stays the basename for display.
    names = {f.path: f.name for f in manifest.files}
    assert names["rtl/counter.v"] == "counter.v"
    assert names["tb/counter_tb.v"] == "counter_tb.v"
    # Tops inferred across directories.
    assert manifest.synthTop == "counter"
    assert manifest.simTop == "counter_tb"


def test_files_for_stage_returns_nested_paths(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "tb/counter_tb.v", TB)
    _write(ws, "constraints/clock.sdc", "create_clock -period 10\n")
    _write(ws, "rtl/defs.vh", "`define WIDTH 8\n")
    manifest = m.read_manifest(ws, session_id="s1")

    assert set(m.files_for_stage(manifest, "lint")) == {"rtl/counter.v", "rtl/defs.vh"}
    assert set(m.files_for_stage(manifest, "simulate")) == {
        "rtl/counter.v", "tb/counter_tb.v", "rtl/defs.vh"}
    assert set(m.files_for_stage(manifest, "synthesize")) == {
        "rtl/counter.v", "constraints/clock.sdc"}


# --------------------------------------------------------------------------- #
# Exclusion policy
# --------------------------------------------------------------------------- #

def test_run_dirs_and_dot_dirs_excluded(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "sim_runs/run_1/dump.v", "module junk1; endmodule\n")
    _write(ws, "synth_runs/run_2/netlist.v", "module junk2; endmodule\n")
    _write(ws, ".git/objects/fake.v", "module junk3; endmodule\n")
    _write(ws, "node_modules/pkg/x.v", "module junk4; endmodule\n")
    _write(ws, "__pycache__/y.v", "module junk5; endmodule\n")

    manifest = m.build_manifest(ws)
    assert [f.path for f in manifest.files] == ["rtl/counter.v"]
    assert manifest.synthTop == "counter"  # junk never pollutes top inference


def test_ignore_globs_exclude_vendor(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "vendor/cells/sky130_fd_sc.v", "module sky130_inv; endmodule\n")
    m.read_manifest(ws)  # persist a manifest to update

    updated = m.write_manifest(ws, {"ignore": ["vendor/**"]})
    assert updated.ignore == ["vendor/**"]
    # Takes effect immediately (write reconciles) and on subsequent reads.
    assert [f.path for f in updated.files] == ["rtl/counter.v"]
    assert [f.path for f in m.read_manifest(ws).files] == ["rtl/counter.v"]


def test_ignore_bare_dir_glob_prunes(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "vendor/cells/model.v", "module model; endmodule\n")
    m.read_manifest(ws)
    updated = m.write_manifest(ws, {"ignore": ["vendor"]})
    assert [f.path for f in updated.files] == ["rtl/counter.v"]


def test_depth_cap(tmp_path):
    ws = str(tmp_path)
    ok_rel = "a/b/c/d/e/f/ok.v"          # 6 dirs deep — inside the cap
    deep_rel = "a/b/c/d/e/f/g/deep.v"    # 7 dirs deep — pruned
    _write(ws, ok_rel, "module ok(input x, output y); assign y = x; endmodule\n")
    _write(ws, deep_rel, "module deep; endmodule\n")

    paths = [f.path for f in m.build_manifest(ws).files]
    assert ok_rel in paths
    assert deep_rel not in paths


# --------------------------------------------------------------------------- #
# Derived testbenches
# --------------------------------------------------------------------------- #

def test_testbenches_derivation_two_tbs(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "tb/counter_tb.v", TB)
    _write(ws, "tb/stress/counter_stress_tb.v", TB2)

    manifest = m.read_manifest(ws)
    tbs = {t["file"]: t["module"] for t in manifest.testbenches}
    assert tbs == {
        "tb/counter_tb.v": "counter_tb",
        "tb/stress/counter_stress_tb.v": "counter_stress_tb",
    }
    # simTop is still the first tb file's top (sorted scan order).
    assert manifest.simTop == "counter_tb"


def test_testbenches_is_derived_user_edit_overwritten(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "tb/counter_tb.v", TB)
    m.read_manifest(ws)

    # Attempted user edit via write_manifest is ignored (recomputed) …
    out = m.write_manifest(ws, {"testbenches": [{"file": "fake.v", "module": "nope"}]})
    assert out.testbenches == [{"file": "tb/counter_tb.v", "module": "counter_tb"}]

    # … and even a hand-edited manifest.json is overwritten on the next read.
    raw = json.load(open(os.path.join(ws, m.MANIFEST_FILENAME)))
    raw["testbenches"] = [{"file": "fake.v", "module": "nope"}]
    json.dump(raw, open(os.path.join(ws, m.MANIFEST_FILENAME), "w"))
    reread = m.read_manifest(ws)
    assert reread.testbenches == [{"file": "tb/counter_tb.v", "module": "counter_tb"}]


def test_role_change_updates_testbenches(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "tb/counter_tb.v", TB)
    m.read_manifest(ws)

    out = m.write_manifest(ws, {"files": [{"path": "tb/counter_tb.v", "role": "other"}]})
    assert out.testbenches == []


# --------------------------------------------------------------------------- #
# Legacy manifests + role updates by path / basename
# --------------------------------------------------------------------------- #

def test_legacy_root_only_manifest_reconciles_unchanged(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", DUT)
    _write(ws, "counter_tb.v", TB)
    # A pre-recursion manifest: root files (path == name), no ignore/testbenches
    # fields, plus a user role override that must survive.
    legacy = {
        "sessionId": "legacy",
        "files": [
            {"name": "counter.v", "role": "include", "path": "counter.v"},
            {"name": "counter_tb.v", "role": "tb", "path": "counter_tb.v"},
        ],
        "synthTop": "counter",
        "simTop": "counter_tb",
        "clockPeriodNs": 8.0,
        "platform": "asap7",
    }
    with open(os.path.join(ws, m.MANIFEST_FILENAME), "w") as f:
        json.dump(legacy, f)

    manifest = m.read_manifest(ws)
    assert [(f.name, f.path, f.role) for f in manifest.files] == [
        ("counter.v", "counter.v", "include"),
        ("counter_tb.v", "counter_tb.v", "tb"),
    ]
    assert manifest.synthTop == "counter"
    assert manifest.simTop == "counter_tb"
    assert manifest.platform == "asap7"
    assert manifest.ignore == []  # new fields default in
    assert manifest.testbenches == [{"file": "counter_tb.v", "module": "counter_tb"}]


def test_write_manifest_role_update_by_path(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    m.read_manifest(ws)
    out = m.write_manifest(ws, {"files": [{"path": "rtl/counter.v", "role": "tb"}]})
    assert {f.path: f.role for f in out.files} == {"rtl/counter.v": "tb"}
    # Survives reconciliation.
    assert {f.path: f.role for f in m.read_manifest(ws).files} == {"rtl/counter.v": "tb"}


def test_write_manifest_role_update_by_unique_basename(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/counter.v", DUT)
    m.read_manifest(ws)
    # Backward-compat: name-only entry addresses the file when unambiguous.
    out = m.write_manifest(ws, {"files": [{"name": "counter.v", "role": "tb"}]})
    assert {f.path: f.role for f in out.files} == {"rtl/counter.v": "tb"}


def test_write_manifest_ambiguous_basename_is_noop(tmp_path):
    ws = str(tmp_path)
    _write(ws, "rtl/x.v", "module a(input i, output o); assign o=i; endmodule\n")
    _write(ws, "alt/x.v", "module b(input i, output o); assign o=i; endmodule\n")
    m.read_manifest(ws)
    out = m.write_manifest(ws, {"files": [{"name": "x.v", "role": "tb"}]})
    # Ambiguous name-only update changes nothing (logged no-op).
    assert {f.path: f.role for f in out.files} == {"rtl/x.v": "rtl", "alt/x.v": "rtl"}


# --------------------------------------------------------------------------- #
# Snapshots + endpoints (actions router / api.py)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _HAS_FASTAPI, reason="needs fastapi")
def test_workbench_snapshot_includes_nested_files_and_code(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.actions import build_actions_router

    sid = "proj/nested"
    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    ws = resolve(sid)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "tb/counter_tb.v", TB)
    _write(ws, "sim_runs/r1/junk.v", "module junk; endmodule\n")

    app = FastAPI()
    app.include_router(build_actions_router(resolve))
    c = TestClient(app)

    r = c.get(f"/api/workspace/{sid}/workbench")
    assert r.status_code == 200, r.text
    snap = r.json()

    files = {f["path"]: f for f in snap["files"]}
    assert files["rtl/counter.v"]["role"] == "rtl"
    assert files["rtl/counter.v"]["name"] == "counter.v"
    assert files["tb/counter_tb.v"]["role"] == "tb"
    assert not any(p.startswith("sim_runs/") for p in files)

    code = {cf["filename"]: cf for cf in snap["code"]}
    assert "rtl/counter.v" in code and "module counter" in code["rtl/counter.v"]["content"]
    assert "tb/counter_tb.v" in code
    assert "sim_runs/r1/junk.v" not in code

    tbs = snap["manifest"]["testbenches"]
    assert tbs == [{"file": "tb/counter_tb.v", "module": "counter_tb"}]


@pytest.mark.skipif(not _HAS_FASTAPI, reason="needs fastapi")
def test_put_manifest_accepts_ignore(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.actions import build_actions_router

    sid = "proj/ig"
    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    ws = resolve(sid)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "vendor/model.v", "module model; endmodule\n")

    app = FastAPI()
    app.include_router(build_actions_router(resolve))
    c = TestClient(app)

    r = c.put(f"/api/workspace/{sid}/manifest", json={"ignore": ["vendor/**"]})
    assert r.status_code == 200, r.text
    man = r.json()["manifest"]
    assert man["ignore"] == ["vendor/**"]
    assert [f["path"] for f in man["files"]] == ["rtl/counter.v"]


@pytest.mark.skipif(not _HAS_APP_STACK, reason="needs full app stack (langchain)")
def test_api_get_code_returns_nested_relative_filenames(monkeypatch, tmp_path):
    """GET /code (api.py) must list nested files with filename = relative path —
    the frontend store reloads /code after saves, and a nested new file must not
    vanish from that list."""
    from fastapi.testclient import TestClient
    import api

    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _write(ws, "rtl/counter.v", DUT)
    _write(ws, "tb/counter_tb.v", TB)
    _write(ws, "synth_runs/r1/netlist.v", "module junk; endmodule\n")

    monkeypatch.setattr(api, "_resolve_workspace", lambda sid: ws)
    api.app.dependency_overrides[api.verify_session_access] = lambda: None
    try:
        c = TestClient(api.app)
        r = c.get("/api/workspace/s1/code")
        assert r.status_code == 200, r.text
        by_name = {cf["filename"]: cf for cf in r.json()}
        assert "rtl/counter.v" in by_name
        assert "tb/counter_tb.v" in by_name
        assert "synth_runs/r1/netlist.v" not in by_name
        assert by_name["rtl/counter.v"]["language"] == "verilog"

        # GET /code/{filename} serves the nested path too.
        r2 = c.get("/api/workspace/s1/code/rtl/counter.v")
        assert r2.status_code == 200
        assert r2.json()["filename"] == "rtl/counter.v"
        assert "module counter" in r2.json()["content"]

        # GET /files: relative paths, roles keyed by path, run dirs excluded.
        r3 = c.get("/api/workspace/s1/files")
        assert r3.status_code == 200
        files = {f["path"]: f for f in r3.json()}
        assert files["rtl/counter.v"]["role"] == "rtl"
        assert files["rtl/counter.v"]["name"] == "counter.v"
        assert not any(p.startswith("synth_runs/") for p in files)
    finally:
        api.app.dependency_overrides.pop(api.verify_session_access, None)
