"""Workbench v2 backend surface: activity feed, lazy dir tree, smart file
reads, UI-source event logging, and the immutable-artifact cache policy.

Follows test_actions_api.py's pattern: mount ``build_actions_router`` on a bare
FastAPI app over a temp workspace — no agent stack, no EDA toolchain. Tool
functions that would need iverilog/ORFS are monkeypatched at the actions-module
seam (the closures resolve them as module globals).
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.actions as actions_mod
from src.api.actions import build_actions_router
from src.api.activity import build_activity_events, read_activity
from src.api import workspace_fs
from src.utils.attempt_logger import EVENTS_FILE, log_tool_call, log_tool_result

SID = "proj/sess"

DUT = "module counter(input clk, output reg [7:0] q); initial q=0; always @(posedge clk) q<=q+1; endmodule\n"
TB = ('module counter_tb; reg clk=0; wire [7:0] q; counter d(.clk(clk),.q(q));\n'
     'always #5 clk=~clk;\n'
     'initial begin $dumpfile("dump.vcd"); $dumpvars(0,counter_tb); #40 $display("TEST PASSED"); $finish; end endmodule\n')


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


def _iso(offset_sec: float = 0.0) -> str:
    return (datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=offset_sec)).isoformat()


# --- Activity pairing (pure) -------------------------------------------------

def test_pairing_by_tool_call_id():
    events = build_activity_events([
        {"event_type": "tool_call", "source": "api_ws", "tool": "linter_tool",
         "tool_call_id": "c1", "ts": _iso(0), "arguments": {"verilog_files": ["a.v"]}},
        {"event_type": "tool_result", "source": "api_ws", "tool": "linter_tool",
         "tool_call_id": "c1", "ts": _iso(1.5), "status": "success", "result": "Syntax OK."},
    ])
    assert len(events) == 1
    ev = events[0]
    assert ev["id"] == "c1"
    assert ev["source"] == "agent"
    assert ev["status"] == "ok"
    assert ev["resultSummary"] == "Syntax OK."
    assert ev["durationMs"] == 1500
    assert ev["args"] == {"verilog_files": ["a.v"]}


def test_pairing_without_call_id_uses_most_recent_same_tool():
    events = build_activity_events([
        {"event_type": "tool_call", "source": "mcp", "tool": "write_file", "ts": _iso(0), "arguments": {"filename": "a.v"}},
        {"event_type": "tool_call", "source": "mcp", "tool": "write_file", "ts": _iso(1), "arguments": {"filename": "b.v"}},
        {"event_type": "tool_result", "source": "mcp", "tool": "write_file", "ts": _iso(2), "status": "success", "result": "wrote b.v"},
    ])
    assert len(events) == 2
    # Result closed the MOST RECENT unpaired call (b.v); the first stays running.
    assert events[0]["status"] == "running"
    assert events[0]["args"] == {"filename": "a.v"}
    assert events[1]["status"] == "ok"
    assert events[1]["source"] == "mcp"


def test_unpaired_call_running_and_orphan_result_standalone():
    events = build_activity_events([
        {"event_type": "tool_call", "source": "api_ws", "tool": "start_synthesis", "tool_call_id": "s1", "ts": _iso(0)},
        {"event_type": "tool_result", "source": "api_ws", "tool": "simulation_tool", "ts": _iso(1),
         "status": "error", "result": json.dumps({"run_id": "sim_0003", "status": "failed"})},
    ])
    assert len(events) == 2
    assert events[0]["status"] == "running" and events[0]["durationMs"] is None
    assert events[1]["status"] == "error"
    assert events[1]["runId"] == "sim_0003"


def test_run_id_extraction_from_args_and_result_text():
    events = build_activity_events([
        {"event_type": "tool_call", "source": "ui", "tool": "retry_pd", "tool_call_id": "r1",
         "ts": _iso(0), "arguments": {"run_id": "synth_0002"}},
        {"event_type": "tool_result", "source": "ui", "tool": "retry_pd", "tool_call_id": "r1",
         "ts": _iso(3), "status": "success", "result": "dispatched synth_0003"},
    ])
    ev = events[0]
    # result text wins (the retry's CHILD run), source ui → user
    assert ev["runId"] == "synth_0003"
    assert ev["source"] == "user"


def test_read_activity_pagination_and_corrupt_lines(tmp_path):
    ws = str(tmp_path)
    path = os.path.join(ws, EVENTS_FILE)
    with open(path, "w") as f:
        f.write("{not json}\n")  # corrupt line: skipped, never raises
        for i in range(5):
            f.write(json.dumps({"event_type": "tool_call", "source": "api_ws", "tool": "write_file",
                                "tool_call_id": f"c{i}", "ts": _iso(i)}) + "\n")
            f.write(json.dumps({"event_type": "tool_result", "source": "api_ws", "tool": "write_file",
                                "tool_call_id": f"c{i}", "ts": _iso(i + 0.5), "status": "success",
                                "result": f"wrote {i}"}) + "\n")

    page1 = read_activity(ws, limit=2)
    assert [e["id"] for e in page1["events"]] == ["c4", "c3"]  # newest first
    assert page1["nextBefore"] == "c3"

    page2 = read_activity(ws, limit=2, before=page1["nextBefore"])
    assert [e["id"] for e in page2["events"]] == ["c2", "c1"]

    page3 = read_activity(ws, limit=2, before=page2["nextBefore"])
    assert [e["id"] for e in page3["events"]] == ["c0"]
    assert page3["nextBefore"] is None


def test_read_activity_missing_log(tmp_path):
    out = read_activity(str(tmp_path))
    assert out == {"events": [], "nextBefore": None}


# --- Activity endpoint + UI-source logging -----------------------------------

def test_activity_endpoint_pages(client):
    c, ws = client
    log_tool_call(ws, SID, "api_ws", "write_file", {"filename": "a.v"}, tool_call_id="w1")
    log_tool_result(ws, SID, "api_ws", "write_file", "wrote a.v", tool_call_id="w1")

    r = c.get(f"/api/workspace/{SID}/activity")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["nextBefore"] is None
    assert len(body["events"]) == 1
    assert body["events"][0]["tool"] == "write_file"
    assert body["events"][0]["status"] == "ok"


def test_lint_action_logs_ui_event(client, monkeypatch):
    c, ws = client
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    monkeypatch.setattr(actions_mod, "run_linter",
                        lambda files, cwd, engine="auto": {
                            "success": True, "stderr": "", "command": "iverilog -t null counter.v",
                            "engine": "iverilog", "diagnostics": [],
                        })

    r = c.post(f"/api/workspace/{SID}/lint")
    assert r.status_code == 200 and r.json()["status"] == "passed"

    events = c.get(f"/api/workspace/{SID}/activity").json()["events"]
    assert len(events) == 1
    ev = events[0]
    assert ev["tool"] == "linter_tool"
    assert ev["source"] == "user"
    assert ev["status"] == "ok"
    assert ev["args"]["verilog_files"] == ["counter.v"]
    assert ev["durationMs"] is not None


def test_simulate_action_logs_ui_event_with_run_id(client, monkeypatch):
    c, ws = client
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    with open(os.path.join(ws, "counter_tb.v"), "w") as f:
        f.write(TB)
    fake_run = {"id": "sim_0001", "kind": "sim", "status": "failed",
                "vcdPath": "sim_runs/sim_0001/dump.vcd"}
    monkeypatch.setattr(actions_mod, "run_sim_isolated", lambda **kw: dict(fake_run))

    r = c.post(f"/api/workspace/{SID}/simulate", json={})
    assert r.status_code == 200 and r.json()["run"]["id"] == "sim_0001"

    events = c.get(f"/api/workspace/{SID}/activity").json()["events"]
    ev = events[0]
    assert ev["tool"] == "run_isolated_simulation"
    assert ev["source"] == "user"
    assert ev["status"] == "error"  # failed sim surfaces as an error row
    assert ev["runId"] == "sim_0001"


def test_synthesize_action_logs_dispatch(client, monkeypatch):
    c, ws = client
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    monkeypatch.setattr(actions_mod, "start_synthesis_job",
                        lambda **kw: {"job_id": "job_ab12", "run_id": "synth_0001", "status": "queued"})

    r = c.post(f"/api/workspace/{SID}/synthesize", json={})
    assert r.status_code == 200 and r.json()["runId"] == "synth_0001"

    ev = c.get(f"/api/workspace/{SID}/activity").json()["events"][0]
    assert ev["tool"] == "start_synthesis"
    assert ev["source"] == "user"
    assert ev["status"] == "ok"
    assert ev["runId"] == "synth_0001"
    assert ev["args"]["top_module"] == "counter"  # manifest-resolved args logged


# --- Directory listing --------------------------------------------------------

def _seed_tree(ws):
    os.makedirs(os.path.join(ws, "sim_runs", "sim_0001"), exist_ok=True)
    os.makedirs(os.path.join(ws, "__pycache__"), exist_ok=True)
    os.makedirs(os.path.join(ws, ".hidden"), exist_ok=True)
    for rel in ["counter.v", "counter_tb.v", "sim_runs/sim_0001/dump.vcd", "__pycache__/x.pyc", ".secret"]:
        p = os.path.join(ws, rel)
        with open(p, "w") as f:
            f.write("x")


def test_dir_root_listing_sorted_and_filtered(client):
    c, ws = client
    _seed_tree(ws)
    r = c.get(f"/api/workspace/{SID}/dir")
    assert r.status_code == 200
    entries = r.json()["entries"]
    names = [e["name"] for e in entries]
    assert names == ["sim_runs", "counter.v", "counter_tb.v"]  # dirs first; dot/__pycache__ excluded
    assert entries[0]["kind"] == "dir" and "size" not in entries[0]
    assert entries[1]["kind"] == "file" and entries[1]["size"] == 1 and entries[1]["modified"]


def test_dir_nested_and_errors(client):
    c, ws = client
    _seed_tree(ws)
    r = c.get(f"/api/workspace/{SID}/dir", params={"path": "sim_runs/sim_0001"})
    assert [e["name"] for e in r.json()["entries"]] == ["dump.vcd"]
    assert r.json()["entries"][0]["path"] == "sim_runs/sim_0001/dump.vcd"

    assert c.get(f"/api/workspace/{SID}/dir", params={"path": "nope"}).status_code == 404
    assert c.get(f"/api/workspace/{SID}/dir", params={"path": "../../etc"}).status_code == 404
    assert c.get(f"/api/workspace/{SID}/dir", params={"path": "counter.v"}).status_code == 404


def test_dir_recursive_paths(client):
    c, ws = client
    _seed_tree(ws)
    r = c.get(f"/api/workspace/{SID}/dir", params={"recursive": "paths"})
    body = r.json()
    assert body["truncated"] is False
    assert body["paths"] == ["counter.v", "counter_tb.v", "sim_runs/sim_0001/dump.vcd"]


def test_walk_paths_cap(tmp_path, monkeypatch):
    ws = str(tmp_path)
    for i in range(5):
        with open(os.path.join(ws, f"f{i}.txt"), "w") as f:
            f.write("x")
    monkeypatch.setattr(workspace_fs, "RECURSIVE_PATHS_CAP", 3)
    out = workspace_fs.walk_paths(ws)
    assert len(out["paths"]) == 3 and out["truncated"] is True


# --- Smart file read + cache policy (pure helpers) ----------------------------

def test_read_smart_file_text_binary_toolarge(tmp_path, monkeypatch):
    ws = str(tmp_path)
    text = os.path.join(ws, "a.v")
    with open(text, "w") as f:
        f.write(DUT)
    out = workspace_fs.read_smart_file(ws, text, "a.v")
    assert out["content"] == DUT and out["binary"] is False and out["tooLarge"] is False

    binary = os.path.join(ws, "a.gds")
    with open(binary, "wb") as f:
        f.write(b"GDS\x00\x01\x02")
    out = workspace_fs.read_smart_file(ws, binary, "a.gds")
    assert out["content"] is None and out["binary"] is True and out["size"] == 6

    monkeypatch.setattr(workspace_fs, "TEXT_CONTENT_CAP", 10)
    big = os.path.join(ws, "big.log")
    with open(big, "w") as f:
        f.write("y" * 100)
    out = workspace_fs.read_smart_file(ws, big, "big.log")
    assert out["content"] is None and out["tooLarge"] is True and out["size"] == 100


def _make_run(ws, kind, run_id, status):
    run_dir = os.path.join(ws, kind, run_id)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "run_meta.json"), "w") as f:
        json.dump({"status": status}, f)
    artifact = os.path.join(run_dir, "dump.vcd")
    with open(artifact, "w") as f:
        f.write("$date\n")
    return artifact


def test_cache_control_terminal_vs_running_vs_loose(tmp_path):
    ws = str(tmp_path)
    done = _make_run(ws, "sim_runs", "sim_0001", "passed")
    assert workspace_fs.artifact_cache_control(ws, done) == workspace_fs.CACHE_IMMUTABLE

    failed = _make_run(ws, "synth_runs", "synth_0001", "failed")
    assert workspace_fs.artifact_cache_control(ws, failed) == workspace_fs.CACHE_IMMUTABLE

    running = _make_run(ws, "synth_runs", "synth_0002", "running")
    assert workspace_fs.artifact_cache_control(ws, running) == workspace_fs.CACHE_NO_STORE

    loose = os.path.join(ws, "dump.vcd")
    with open(loose, "w") as f:
        f.write("$date\n")
    assert workspace_fs.artifact_cache_control(ws, loose) == workspace_fs.CACHE_NO_STORE

    # unreadable meta → honest fallback: no caching
    broken = _make_run(ws, "sim_runs", "sim_0002", "passed")
    with open(os.path.join(ws, "sim_runs", "sim_0002", "run_meta.json"), "w") as f:
        f.write("{broken")
    assert workspace_fs.artifact_cache_control(ws, broken) == workspace_fs.CACHE_NO_STORE


# --- Snapshot extensions --------------------------------------------------------

def test_workbench_snapshot_includes_activity_and_rootdir(client):
    c, ws = client
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    log_tool_call(ws, SID, "api_ws", "write_file", {"filename": "counter.v"}, tool_call_id="w1")
    log_tool_result(ws, SID, "api_ws", "write_file", "wrote counter.v", tool_call_id="w1")

    r = c.get(f"/api/workspace/{SID}/workbench")
    assert r.status_code == 200
    body = r.json()
    assert body["activity"][0]["tool"] == "write_file"
    root_names = [e["name"] for e in body["rootDir"]]
    assert "counter.v" in root_names
    # the event log itself is visible in the tree (real structure, no lies)
    assert any(e["name"] == "attempt_events.jsonl" for e in body["rootDir"])


# --- Schema-driven tool platform (/tools + /invoke) ----------------------------
# These exercise the introspected registry (LangChain wrappers), so they skip
# cleanly where the agent stack isn't installed.

pytest.importorskip("langchain_core")


def test_tools_catalog_exposes_real_schemas(client):
    c, ws = client
    r = c.get(f"/api/workspace/{SID}/tools")
    assert r.status_code == 200
    tools = {t["name"]: t for t in r.json()["tools"]}
    # The catalog is the SAME registry the agent/MCP use — spot-check breadth.
    for name in ("linter_tool", "waveform_tool", "start_synthesis", "run_xls_flow", "update_manifest"):
        assert name in tools, name
    wave = tools["waveform_tool"]
    props = wave["argsSchema"]["properties"]
    assert props["signals"]["type"] == "array"
    assert "vcd_file" in wave["argsSchema"].get("required", [])
    assert wave["requiresSignIn"] is False and wave["mutates"] is False
    synth = tools["start_synthesis"]
    assert synth["async"] is True and synth["requiresSignIn"] is True and synth["mutates"] is True
    # Blocking poll-loop tool is not surfaced to the UI.
    assert "wait_for_synthesis" not in tools


def test_invoke_unknown_tool_404(client):
    c, ws = client
    r = c.post(f"/api/workspace/{SID}/invoke", json={"tool": "rm_rf", "arguments": {}})
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "unknown_tool"


def test_invoke_schema_validation_400_with_fields(client):
    c, ws = client
    # waveform_tool requires vcd_file + signals — omit both.
    r = c.post(f"/api/workspace/{SID}/invoke", json={"tool": "waveform_tool", "arguments": {}})
    assert r.status_code == 400
    err = r.json()["detail"]["error"]
    assert err["code"] == "invalid_arguments"
    fields = {f["field"] for f in err["details"]["fields"]}
    assert "vcd_file" in fields


def test_invoke_waveform_executes_real_wrapper(client):
    c, ws = client
    vcd = (
        "$timescale 1ns $end\n"
        "$scope module tb $end\n"
        "$var wire 1 ! clk $end\n"
        "$upscope $end\n$enddefinitions $end\n"
        "#0\n0!\n#5\n1!\n#10\n0!\n"
    )
    with open(os.path.join(ws, "dump.vcd"), "w") as f:
        f.write(vcd)

    r = c.post(f"/api/workspace/{SID}/invoke", json={
        "tool": "waveform_tool",
        "arguments": {"vcd_file": "dump.vcd", "signals": ["clk"], "start_time": 0, "end_time": 20},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["tool"] == "waveform_tool"
    assert "clk" in str(body["result"])

    # ...and it landed in the unified activity feed as a user event.
    ev = c.get(f"/api/workspace/{SID}/activity").json()["events"][0]
    assert ev["tool"] == "waveform_tool" and ev["source"] == "user" and ev["status"] == "ok"


def test_invoke_file_arg_containment(client):
    c, ws = client
    r = c.post(f"/api/workspace/{SID}/invoke", json={
        "tool": "waveform_tool",
        "arguments": {"vcd_file": "../../etc/passwd", "signals": ["clk"]},
    })
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "invalid_arguments"


def test_invoke_structured_result_parsed_not_double_encoded(client):
    c, ws = client
    # get_manifest returns a JSON string from the wrapper; the endpoint returns
    # the STRUCTURE, so the UI never renders escaped JSON-in-JSON.
    with open(os.path.join(ws, "counter.v"), "w") as f:
        f.write(DUT)
    r = c.post(f"/api/workspace/{SID}/invoke", json={"tool": "get_manifest", "arguments": {}})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert isinstance(result, dict)
    assert result.get("synthTop") == "counter"


def test_invoke_signed_in_gate(tmp_path):
    """Anonymous identities are refused for sign-in-gated tools (hosted trial)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    class Anon:
        anonymous = True
        tier = "anonymous"

    base = str(tmp_path)

    def resolve(session_id: str) -> str:
        ws = os.path.join(base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve, get_identity=lambda: Anon()))
    c = TestClient(app)
    r = c.post(f"/api/workspace/{SID}/invoke", json={"tool": "save_metrics_tool", "arguments": {"wns_ns": 0.1}})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "signin_required"


def test_shared_policy_single_source():
    """mcp_server's protection policy IS the catalog's (no drift)."""
    from src.api.tool_catalog import PROTECTED_TOOLS, TOOL_CATEGORIES
    assert "start_synthesis" in PROTECTED_TOOLS
    assert "update_manifest" in PROTECTED_TOOLS
    assert "linter_tool" not in PROTECTED_TOOLS
    flat = {n for names in TOOL_CATEGORIES.values() for n in names}
    assert "get_manifest" in flat and "run_isolated_simulation" in flat
