"""Optional file overrides on the core lint/simulate/synthesize commands
(command-surface v2, R18-R26) — REST twins AND the sim wrapper — resolved
through the ONE shared resolver, with honest notes when an override drops a
manifest-supplied file and the synthesize .v/.sv filter kept.

Empty/absent override = today's manifest-driven behavior, byte-for-byte.
"""
import json
import os

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.actions as actions_mod
from src.api.actions import build_actions_router

SID = "sess-overrides"

DUT = "module counter(input clk, output reg [7:0] q); initial q=0; always @(posedge clk) q<=q+1; endmodule\n"
TB = ('module counter_tb; reg clk=0; wire [7:0] q; counter d(.clk(clk),.q(q));\n'
      'always #5 clk=~clk;\n'
      'initial begin #40 $display("TEST PASSED"); $finish; end endmodule\n')


@pytest.fixture()
def client(tmp_path):
    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve))
    return TestClient(app), resolve(SID)


def _seed_nested(ws):
    os.makedirs(os.path.join(ws, "rtl"), exist_ok=True)
    os.makedirs(os.path.join(ws, "tb"), exist_ok=True)
    with open(os.path.join(ws, "rtl", "counter.v"), "w") as f:
        f.write(DUT)
    with open(os.path.join(ws, "tb", "counter_tb.v"), "w") as f:
        f.write(TB)


# --- lint ------------------------------------------------------------------

def test_lint_override_resolves_basenames_and_notes_dropped(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    seen = {}

    def fake_linter(files, cwd, engine="auto", **kw):
        seen["files"] = files
        seen["scope_modules"] = kw.get("scope_modules")
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "iverilog", "diagnostics": []}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["counter.v"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "passed"
    # Basename resolved to the nested manifest file, and the engine got it.
    assert body["files"] == ["rtl/counter.v"]
    assert seen["files"] == [os.path.join(ws, "rtl/counter.v")]
    # No manifest lint file was dropped (tb is not in the lint set).
    assert body["manifestWarnings"] == []


def test_lint_override_dropping_a_manifest_file_is_noted(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    monkeypatch.setattr(
        actions_mod, "run_linter",
        lambda files, cwd, engine="auto", **kw: {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": []},
    )
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["counter.v"]})
    assert r.status_code == 200, r.text
    notes = r.json()["manifestWarnings"]
    assert any("rtl/top.v" in n for n in notes)
    assert all("counter.v'" not in n for n in notes)


def test_lint_override_that_drops_manifest_files_is_file_scoped(client, monkeypatch):
    """Adversarial-review F2 (R27-R30): 'lint THIS file' on hierarchical RTL used to come
    back FAILED ("Unknown module type") — a false verdict. An override that
    leaves manifest lint files out now runs file-scoped, and the engine's scope
    note rides the same manifestWarnings channel.

    P2-1: "file-scoped" is not a flag but the SET of module names the dropped
    manifest files define (the manifest's own scan) — the linter may excuse
    exactly those, nothing else."""
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    seen = {}

    def fake_linter(files, cwd, engine="auto", scope_modules=None, **kw):
        seen["scope_modules"] = scope_modules
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "",
                "diagnostics": [], "notes": ["File-scoped lint: counter not in the linted file set."]}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["top.v"]})
    assert r.status_code == 200, r.text
    assert seen["scope_modules"] == {"counter"}   # what rtl/counter.v (dropped) defines
    body = r.json()
    assert body["status"] == "passed"
    notes = body["manifestWarnings"]
    assert any("rtl/counter.v" in n for n in notes)          # what the override dropped
    assert any("File-scoped lint" in n for n in notes)        # what that cost


def test_lint_override_covering_the_manifest_set_stays_strict(client, monkeypatch):
    """An override that drops nothing is NOT file-scoped: a module missing from
    the whole design is a real error and must keep failing."""
    c, ws = client
    _seed_nested(ws)
    seen = {}

    def fake_linter(files, cwd, engine="auto", scope_modules=None, **kw):
        seen["scope_modules"] = scope_modules
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": [], "notes": []}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["counter.v", "counter_tb.v"]})
    assert r.status_code == 200, r.text
    assert not seen["scope_modules"]


def test_lint_override_scope_is_the_dropped_files_module_set_only(client, monkeypatch):
    """P2-1 twin: with rtl/counter.v AND rtl/adder.v dropped, the linter is
    told {counter, adder}; a module defined by a file that STAYS in the set is
    not in the scope (its absence would be a real error, not a scoping one)."""
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "adder.v"), "w") as f:
        f.write("module adder(input a, output b); assign b = a; endmodule\n")
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); adder a(.a(clk), .b()); endmodule\n")
    seen = {}

    def fake_linter(files, cwd, engine="auto", scope_modules=None, **kw):
        seen["scope_modules"] = set(scope_modules or ())
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": [], "notes": []}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["top.v", "adder.v"]})
    assert r.status_code == 200, r.text
    assert seen["scope_modules"] == {"counter"}


def test_lint_override_typo_module_still_fails_file_scoped(client, monkeypatch):
    """The false-pass sequence from the review, end to end through the handler
    with a fake ENGINE (the real run_linter filter runs): top.v instantiates
    ``countr`` (typo) and drops rtl/counter.v → FAILED with the diagnostic kept;
    the genuine ``counter`` case passes with a note naming the module."""
    import src.tools.run_linter as rl

    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); countr c(.clk(clk), .q()); endmodule\n")
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else "/usr/bin/iverilog")
    stderr = {"text": "rtl/top.v:1: error: Unknown module type: countr\n"}
    monkeypatch.setattr(
        rl, "_run",
        lambda cmd, cwd, timeout: {"returncode": 1, "stdout": "", "stderr": stderr["text"], "command": " ".join(cmd)},
    )

    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["top.v"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "failed"
    assert any("countr" in e["message"] for e in body["errors"])
    assert not any("File-scoped lint" in n for n in body["manifestWarnings"])

    stderr["text"] = "rtl/top.v:1: error: Unknown module type: counter\n"
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["top.v"]})
    body = r.json()
    assert body["status"] == "passed" and body["errors"] == []
    assert any("File-scoped lint" in n and "counter" in n for n in body["manifestWarnings"])
    assert any("rtl/counter.v" in n for n in body["manifestWarnings"])


def test_lint_without_override_is_never_file_scoped(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    seen = {}

    def fake_linter(files, cwd, engine="auto", scope_modules=None, **kw):
        seen["scope_modules"] = scope_modules
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": [], "notes": []}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    assert c.post(f"/api/workspace/{SID}/lint").status_code == 200
    assert not seen["scope_modules"]


def test_lint_override_unknown_file_is_400(client):
    c, ws = client
    _seed_nested(ws)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["nope.v"]})
    assert r.status_code == 400
    err = r.json()["detail"]["error"]
    assert err["code"] == "invalid_files"
    assert "does not exist" in err["message"]


def test_lint_override_escape_is_400(client):
    c, ws = client
    _seed_nested(ws)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["../evil.v"]})
    assert r.status_code == 400
    assert "escapes the workspace" in r.json()["detail"]["error"]["message"]


def test_lint_without_override_unchanged(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    seen = {}

    def fake_linter(files, cwd, engine="auto", **kw):
        seen["files"] = files
        seen["scope_modules"] = kw.get("scope_modules")
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": []}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    r = c.post(f"/api/workspace/{SID}/lint")
    assert r.status_code == 200
    assert seen["files"] == [os.path.join(ws, "rtl/counter.v")]
    assert r.json()["manifestWarnings"] == []


# --- simulate ---------------------------------------------------------------

def test_simulate_override_resolves_and_notes_dropped(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    seen = {}

    def fake_sim(**kw):
        seen.update(kw)
        return {"id": "sim_0001", "kind": "sim", "status": "passed", "vcdPath": ""}

    monkeypatch.setattr(actions_mod, "run_sim_isolated", fake_sim)
    r = c.post(f"/api/workspace/{SID}/simulate", json={"files": ["counter_tb.v"]})
    assert r.status_code == 200, r.text
    assert seen["verilog_files"] == ["tb/counter_tb.v"]
    notes = r.json()["manifestWarnings"]
    assert any("rtl/counter.v" in n for n in notes)


def test_simulate_override_unknown_file_is_400(client):
    c, ws = client
    _seed_nested(ws)
    r = c.post(f"/api/workspace/{SID}/simulate", json={"files": ["ghost.v"]})
    assert r.status_code == 400
    err = r.json()["detail"]["error"]
    assert err["code"] == "invalid_files" and "does not exist" in err["message"]


def test_simulate_without_override_unchanged(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    seen = {}

    def fake_sim(**kw):
        seen.update(kw)
        return {"id": "sim_0001", "kind": "sim", "status": "passed", "vcdPath": ""}

    monkeypatch.setattr(actions_mod, "run_sim_isolated", fake_sim)
    r = c.post(f"/api/workspace/{SID}/simulate", json={})
    assert r.status_code == 200
    assert sorted(seen["verilog_files"]) == ["rtl/counter.v", "tb/counter_tb.v"]
    assert r.json()["manifestWarnings"] == []


# --- synthesize -------------------------------------------------------------

def test_synthesize_override_keeps_v_sv_filter_with_notes(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "constraints.sdc"), "w") as f:
        f.write("create_clock -period 10 clk\n")
    seen = {}

    def fake_job(**kw):
        seen.update(kw)
        return {"run_id": "synth_0001", "status": "queued", "poll_after_sec": 5}

    monkeypatch.setattr(actions_mod, "start_synthesis_job", fake_job)
    r = c.post(
        f"/api/workspace/{SID}/synthesize",
        json={"verilogFiles": ["counter.v", "constraints.sdc"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["runId"] == "synth_0001"
    # Resolved basename, abs paths to the engine, non-.v/.sv filtered (A14)…
    assert seen["verilog_files"] == [os.path.join(ws, "rtl/counter.v")]
    # …but the explicitly-passed .sdc must not vanish silently.
    notes = body["manifestWarnings"]
    assert any("constraints.sdc" in n and "constraintsMode" in n for n in notes)


def test_synthesize_override_dropping_manifest_rtl_is_noted(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    monkeypatch.setattr(
        actions_mod, "start_synthesis_job",
        lambda **kw: {"run_id": "synth_0002", "status": "queued", "poll_after_sec": 5},
    )
    r = c.post(f"/api/workspace/{SID}/synthesize", json={"verilogFiles": ["top.v"], "synthTop": "top"})
    assert r.status_code == 200, r.text
    notes = r.json()["manifestWarnings"]
    assert any("rtl/counter.v" in n for n in notes)


def test_synthesize_override_with_no_sources_is_honest_400(client):
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "constraints.sdc"), "w") as f:
        f.write("create_clock -period 10 clk\n")
    r = c.post(f"/api/workspace/{SID}/synthesize", json={"verilogFiles": ["constraints.sdc"]})
    assert r.status_code == 400
    err = r.json()["detail"]["error"]
    assert err["code"] == "no_files" and "override" in err["message"]


def test_synthesize_override_unknown_file_is_400(client):
    c, ws = client
    _seed_nested(ws)
    r = c.post(f"/api/workspace/{SID}/synthesize", json={"verilogFiles": ["ghost.v"]})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "invalid_files"


# --- the sim wrapper override (agent/MCP parity) ----------------------------

def test_run_simulation_wrapper_override(tmp_path, monkeypatch):
    wrappers = pytest.importorskip("src.tools.wrappers")
    ws = str(tmp_path)
    _seed_nested(ws)
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")
    seen = {}

    def fake_sim(**kw):
        seen.update(kw)
        return {"id": "sim_0001", "status": "passed"}

    monkeypatch.setattr(wrappers, "run_sim_isolated", fake_sim)
    out = json.loads(wrappers.run_simulation.func(verilog_files=["counter_tb.v"]))
    assert seen["verilog_files"] == ["tb/counter_tb.v"]
    # The dropped manifest file is named in the same manifestWarnings channel.
    assert any("rtl/counter.v" in n for n in out["manifestWarnings"])


def test_run_simulation_wrapper_without_override_unchanged(tmp_path, monkeypatch):
    wrappers = pytest.importorskip("src.tools.wrappers")
    ws = str(tmp_path)
    _seed_nested(ws)
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")
    seen = {}

    def fake_sim(**kw):
        seen.update(kw)
        return {"id": "sim_0001", "status": "passed"}

    monkeypatch.setattr(wrappers, "run_sim_isolated", fake_sim)
    out = json.loads(wrappers.run_simulation.func())
    assert sorted(seen["verilog_files"]) == ["rtl/counter.v", "tb/counter_tb.v"]
    assert "manifestWarnings" not in out


def test_run_simulation_wrapper_override_bad_file(tmp_path, monkeypatch):
    wrappers = pytest.importorskip("src.tools.wrappers")
    ws = str(tmp_path)
    _seed_nested(ws)
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")
    out = wrappers.run_simulation.func(verilog_files=["ghost.v"])
    assert out.startswith("Error:") and "does not exist" in out


# --- lint / synth wrappers narrate like their twins (adversarial-review P3-2) --

def _wrap(tmp_path, monkeypatch):
    wrappers = pytest.importorskip("src.tools.wrappers")
    ws = str(tmp_path)
    _seed_nested(ws)
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")
    return wrappers, ws


def test_linter_tool_wrapper_names_dropped_manifest_files_like_the_twin(tmp_path, monkeypatch):
    wrappers, ws = _wrap(tmp_path, monkeypatch)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    seen = {}

    def fake_linter(files, cwd, engine="auto", **kw):
        seen["files"] = files
        seen["scope_modules"] = kw.get("scope_modules")
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": [], "notes": []}

    monkeypatch.setattr(wrappers, "run_linter", fake_linter)
    out = wrappers.linter_tool.func(verilog_files=["top.v"])
    assert out.startswith("Syntax OK")
    # The SAME note text the REST twin returns as manifestWarnings.
    from src.tools.manifest import override_drop_notes
    expected = override_drop_notes("lint", ["rtl/counter.v", "rtl/top.v"], ["rtl/top.v"])
    assert expected and all(n in out for n in expected)
    # Narration only: the agent path stays strict (no scope excuses).
    assert not seen["scope_modules"]


def test_linter_tool_wrapper_covering_the_manifest_set_has_no_notes(tmp_path, monkeypatch):
    wrappers, ws = _wrap(tmp_path, monkeypatch)
    monkeypatch.setattr(
        wrappers, "run_linter",
        lambda files, cwd, engine="auto", **kw: {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": [], "notes": []},
    )
    out = wrappers.linter_tool.func(verilog_files=["counter.v"])
    assert out == "Syntax OK. (engine: iverilog)"


def test_start_synthesis_wrapper_filters_non_sources_with_the_twin_note(tmp_path, monkeypatch):
    wrappers, ws = _wrap(tmp_path, monkeypatch)
    with open(os.path.join(ws, "constraints.sdc"), "w") as f:
        f.write("create_clock -period 10 clk\n")
    seen = {}

    def fake_job(**kw):
        seen.update(kw)
        return {"run_id": "synth_0001", "status": "queued", "poll_after_sec": 5}

    monkeypatch.setattr(wrappers, "start_synthesis_job", fake_job)
    out = json.loads(wrappers.start_synthesis.func(
        verilog_files=["counter.v", "constraints.sdc"], top_module="counter"
    ))
    assert out["run_id"] == "synth_0001"
    # The .sdc never reaches yosys (the REST twin already filtered it)…
    assert seen["verilog_files"] == [os.path.join(ws, "rtl/counter.v")]
    # …and it is named, in the twin's words, in the same channel.
    from src.tools.manifest import synthesis_sources
    _, expected = synthesis_sources(["rtl/counter.v", "constraints.sdc"])
    assert expected and all(n in out["manifestWarnings"] for n in expected)


def test_start_synthesis_wrapper_names_dropped_manifest_rtl(tmp_path, monkeypatch):
    wrappers, ws = _wrap(tmp_path, monkeypatch)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    monkeypatch.setattr(
        wrappers, "start_synthesis_job",
        lambda **kw: {"run_id": "synth_0002", "status": "queued", "poll_after_sec": 5},
    )
    out = json.loads(wrappers.start_synthesis.func(verilog_files=["top.v"], top_module="top"))
    assert any("rtl/counter.v" in n for n in out["manifestWarnings"])


def test_start_synthesis_wrapper_with_no_sources_is_an_honest_error(tmp_path, monkeypatch):
    wrappers, ws = _wrap(tmp_path, monkeypatch)
    with open(os.path.join(ws, "constraints.sdc"), "w") as f:
        f.write("create_clock -period 10 clk\n")
    called = []
    monkeypatch.setattr(wrappers, "start_synthesis_job", lambda **kw: called.append(kw) or {})
    out = wrappers.start_synthesis.func(verilog_files=["constraints.sdc"], top_module="x")
    assert out.startswith("Error:") and ".v/.sv" in out
    assert called == []  # no run dispatched (the REST twin is a 400 here)


def test_twins_and_wrappers_share_one_resolver():
    """Parity is the SAME helper object, not two lookalikes (R19)."""
    from src.tools import file_resolver, manifest

    assert actions_mod.resolve_workspace_files is file_resolver.resolve_workspace_files
    wrappers = pytest.importorskip("src.tools.wrappers")
    assert wrappers.resolve_workspace_files is file_resolver.resolve_workspace_files
    # override_drop_notes lives beside files_for_stage (B10); both callers
    # reach it through the one manifest module.
    assert actions_mod.manifest_mod.override_drop_notes is manifest.override_drop_notes
    assert wrappers.manifest_mod.override_drop_notes is manifest.override_drop_notes
    # The synthesis .v/.sv filter + its note is one helper too (P3-2).
    assert actions_mod.manifest_mod.synthesis_sources is manifest.synthesis_sources
    assert wrappers.manifest_mod.synthesis_sources is manifest.synthesis_sources
    # And the extension set they hand the resolver is the one definition (B12).
    assert actions_mod.manifest_mod.RTL_EXTS is manifest.RTL_EXTS
    assert wrappers.RTL_EXTS is manifest.RTL_EXTS


# --- -I is the manifest's include dirs; drop notes tell the truth about what
# --- the engine read (staging discrepancy A, 2026-09-09) -----------------------

def _seed_include(ws, rel, text="`define W 8\n"):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _lint_result(**extra):
    return {"success": True, "engine": "verilator", "stderr": "", "command": "",
            "diagnostics": [], "notes": [], **extra}


def test_lint_handler_passes_the_manifest_include_dirs_not_source_dirs(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    _seed_include(ws, "inc/glob.vh")
    seen = {}

    def fake_linter(files, cwd, engine="auto", **kw):
        seen.update(kw)
        return _lint_result()

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    assert c.post(f"/api/workspace/{SID}/lint").status_code == 200
    from src.tools import manifest
    m = manifest.read_manifest(ws, SID)
    assert manifest.include_dirs(m) == ["inc"]
    assert seen["include_dirs"] == ["inc"]  # the helper's answer, verbatim; "rtl" is NOT there
    # Same on an explicit override.
    assert c.post(f"/api/workspace/{SID}/lint", json={"files": ["rtl/counter.v"]}).status_code == 200
    assert seen["include_dirs"] == ["inc"]


def test_lint_handler_names_a_dropped_file_the_engine_compiled_anyway(client, monkeypatch):
    """The residual case: the engine's read list shows the dropped manifest
    file was compiled after all. The note must say so (not "not part of this
    run"), its modules leave the recorded scope, and the read list reaches
    the response and the durable event."""
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    seen = {}

    def fake_linter(files, cwd, engine="auto", **kw):
        seen["scope_modules"] = set(kw.get("scope_modules") or ())
        return _lint_result(filesRead=["/usr/share/verilator/include/verilated_std.sv", "rtl/counter.v", "rtl/top.v"])

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["rtl/top.v"]})
    assert r.status_code == 200, r.text
    body = r.json()
    from src.tools.manifest import override_drop_notes
    expected = override_drop_notes("lint", ["rtl/counter.v", "rtl/top.v"], ["rtl/top.v"],
                                   compiled={"rtl/counter.v"}, engine="verilator")
    assert expected == [
        "Override omits manifest lint file 'rtl/counter.v' — verilator read it anyway "
        "(`include, or a module lookup in an include directory); the verdict covers it."
    ]
    assert body["manifestWarnings"] == expected
    assert not any("not part of this run" in n for n in body["manifestWarnings"])
    assert body["filesRead"] == ["/usr/share/verilator/include/verilated_std.sv", "rtl/counter.v", "rtl/top.v"]
    # The linter was told the pre-run scope (the only one knowable before the
    # run); the record is corrected from what was actually read.
    assert seen["scope_modules"] == {"counter"}
    ev = c.get(f"/api/workspace/{SID}/activity").json()["events"][0]
    summary = json.loads(ev["resultSummary"])
    assert summary["scopeModules"] == []
    assert summary["filesRead"] == body["filesRead"]
    assert summary["notes"] == expected


def test_lint_handler_dropped_file_with_a_diagnostic_counts_as_compiled(client, monkeypatch):
    """A failed verilator run writes no read list, but a diagnostic AT the
    dropped file proves it was read — the note still tells the truth."""
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    monkeypatch.setattr(actions_mod, "run_linter", lambda files, cwd, engine="auto", **kw: _lint_result(
        success=False,
        diagnostics=[{"file": "rtl/counter.v", "line": 1, "severity": "error",
                      "message": "Can't find definition of variable: 'x'", "code": None}],
    ))
    body = c.post(f"/api/workspace/{SID}/lint", json={"files": ["rtl/top.v"]}).json()
    assert body["status"] == "failed"
    assert body["filesRead"] is None
    assert body["manifestWarnings"] == [
        "Override omits manifest lint file 'rtl/counter.v' — verilator read it anyway "
        "(`include, or a module lookup in an include directory); the verdict covers it."
    ]


def test_lint_handler_dropped_file_not_read_keeps_the_plain_note(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    monkeypatch.setattr(actions_mod, "run_linter", lambda files, cwd, engine="auto", **kw: _lint_result(
        filesRead=["rtl/top.v"], notes=["File-scoped lint: counter instantiated but not in the linted file set."],
    ))
    body = c.post(f"/api/workspace/{SID}/lint", json={"files": ["rtl/top.v"]}).json()
    assert body["manifestWarnings"][0] == "Override omits manifest lint file 'rtl/counter.v' — it is not part of this run."
    ev = c.get(f"/api/workspace/{SID}/activity").json()["events"][0]
    assert json.loads(ev["resultSummary"])["scopeModules"] == ["counter"]


def test_linter_tool_wrapper_passes_include_dirs_and_names_compiled_anyway(tmp_path, monkeypatch):
    wrappers, ws = _wrap(tmp_path, monkeypatch)
    _seed_include(ws, "inc/glob.vh")
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    seen = {}

    def fake_linter(files, cwd, engine="auto", **kw):
        seen.update(kw)
        return _lint_result(filesRead=["rtl/counter.v", "rtl/top.v"])

    monkeypatch.setattr(wrappers, "run_linter", fake_linter)
    out = wrappers.linter_tool.func(verilog_files=["top.v"])
    assert seen["include_dirs"] == ["inc"]
    assert "scope_modules" not in seen or not seen["scope_modules"]  # still strict
    assert ("Override omits manifest lint file 'rtl/counter.v' — verilator read it anyway "
            "(`include, or a module lookup in an include directory); the verdict covers it.") in out
    assert "'rtl/counter.v' — it is not part of this run" not in out
    # The header the list left out and the engine did not read keeps the plain note.
    assert "Override omits manifest lint file 'inc/glob.vh' — it is not part of this run." in out


@pytest.mark.requires_eda
@pytest.mark.skipif(__import__("shutil").which("verilator") is None, reason="verilator not installed")
def test_lint_handler_real_verilator_residual_case_end_to_end(client):
    """No fakes: a header in rtl/ puts rtl/ on -I, so linting rtl/top.v alone
    lets verilator's library search compile rtl/alu.v — and the response says
    exactly that instead of 'not part of this run'."""
    c, ws = client
    _seed_include(ws, "rtl/defs.vh")
    _seed_include(ws, "rtl/alu.v", "module alu(input [7:0] a, b, output [7:0] y);\n  assign y = a + b;\nendmodule\n")
    _seed_include(ws, "rtl/top.v", '`include "defs.vh"\nmodule top(input [`W-1:0] a, b, output [`W-1:0] y);\n  alu u(.a(a), .b(b), .y(y));\nendmodule\n')
    body = c.post(f"/api/workspace/{SID}/lint", json={"engine": "verilator", "files": ["rtl/top.v"]}).json()
    assert body["status"] == "passed", body
    assert {"rtl/alu.v", "rtl/defs.vh", "rtl/top.v"} <= set(body["filesRead"])
    # Both dropped manifest files were read — alu.v by library lookup, defs.vh
    # by `include — and both notes say so; neither claims "not part of this run".
    assert body["manifestWarnings"] == [
        f"Override omits manifest lint file '{rel}' — verilator read it anyway "
        "(`include, or a module lookup in an include directory); the verdict covers it."
        for rel in ("rtl/alu.v", "rtl/defs.vh")
    ]
    # And with the header elsewhere, the same gesture is file-scoped for real:
    # -I names the root now, alu.v is not there, the run is honestly scoped.
    os.replace(os.path.join(ws, "rtl", "defs.vh"), os.path.join(ws, "defs.vh"))
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write('`include "../defs.vh"\nmodule top(input [`W-1:0] a, b, output [`W-1:0] y);\n  alu u(.a(a), .b(b), .y(y));\nendmodule\n')
    body = c.post(f"/api/workspace/{SID}/lint", json={"engine": "verilator", "files": ["rtl/top.v"]}).json()
    assert body["status"] == "passed", body
    assert body["filesRead"] is None  # a failed elaboration (alu unresolved) writes no read list
    assert "Override omits manifest lint file 'rtl/alu.v' — it is not part of this run." in body["manifestWarnings"]
    assert any("File-scoped lint" in n and "alu" in n for n in body["manifestWarnings"])


def test_twins_and_wrappers_share_the_include_dirs_and_files_compiled_helpers():
    """Structural parity pin, same shape as the resolver pin: both surfaces
    reach ONE include_dirs helper and ONE read-evidence helper."""
    from src.tools import manifest, run_linter
    wrappers = pytest.importorskip("src.tools.wrappers")
    assert actions_mod.manifest_mod.include_dirs is manifest.include_dirs
    assert wrappers.manifest_mod.include_dirs is manifest.include_dirs
    assert actions_mod.files_compiled is run_linter.files_compiled
    assert wrappers.files_compiled is run_linter.files_compiled
