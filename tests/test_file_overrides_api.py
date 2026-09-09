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
        seen["file_scoped"] = kw.get("file_scoped")
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
    note rides the same manifestWarnings channel."""
    c, ws = client
    _seed_nested(ws)
    with open(os.path.join(ws, "rtl", "top.v"), "w") as f:
        f.write("module top(input clk); counter c(.clk(clk), .q()); endmodule\n")
    seen = {}

    def fake_linter(files, cwd, engine="auto", file_scoped=False):
        seen["file_scoped"] = file_scoped
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "",
                "diagnostics": [], "notes": ["File-scoped lint: counter not in the linted file set."]}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["top.v"]})
    assert r.status_code == 200, r.text
    assert seen["file_scoped"] is True
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

    def fake_linter(files, cwd, engine="auto", file_scoped=False):
        seen["file_scoped"] = file_scoped
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": [], "notes": []}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    r = c.post(f"/api/workspace/{SID}/lint", json={"files": ["counter.v", "counter_tb.v"]})
    assert r.status_code == 200, r.text
    assert seen["file_scoped"] is False


def test_lint_without_override_is_never_file_scoped(client, monkeypatch):
    c, ws = client
    _seed_nested(ws)
    seen = {}

    def fake_linter(files, cwd, engine="auto", file_scoped=False):
        seen["file_scoped"] = file_scoped
        return {"success": True, "engine": "iverilog", "stderr": "", "command": "", "diagnostics": [], "notes": []}

    monkeypatch.setattr(actions_mod, "run_linter", fake_linter)
    assert c.post(f"/api/workspace/{SID}/lint").status_code == 200
    assert seen["file_scoped"] is False


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
        seen["file_scoped"] = kw.get("file_scoped")
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
    # And the extension set they hand the resolver is the one definition (B12).
    assert actions_mod.manifest_mod.RTL_EXTS is manifest.RTL_EXTS
    assert wrappers.RTL_EXTS is manifest.RTL_EXTS
