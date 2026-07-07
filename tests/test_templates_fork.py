"""Wave 11 — session templates (bundles) & forks.

Covers the fork backend (create-first ordering, workspace copy, provenance,
netlist/manifest rewrites, rollback, hosted gate, copy ceilings), the export
utility round-trip, the pure transcript renderer, and the REST surface — all
following the existing test patterns (SessionManager over a tmp workspace, no
pytest-asyncio: async is driven with asyncio.run inside the utilities).
"""
import asyncio
import json
import os

import pytest

from src.utils.session_manager import SessionManager
from src.utils import templates as T
from src.utils.bundles import BundleTooLarge, copytree_guarded, scan_for_secrets
from src.utils.transcript import render_transcript, slugify


# ---------------------------------------------------------------------------
# Fixtures: a SessionManager + a hand-built example bundle on disk
# ---------------------------------------------------------------------------


@pytest.fixture
def sm(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "workspace"), db_path=str(tmp_path / "state.db"))


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content))


def _make_bundle(examples_dir, template_id="demo_fifo", *, with_synth=True):
    """A minimal but realistic bundle: template.json + workspace snapshot."""
    bundle = os.path.join(examples_dir, template_id)
    ws = os.path.join(bundle, "workspace")
    _write(os.path.join(bundle, "template.json"), {
        "id": template_id,
        "name": "Demo FIFO",
        "description": "A tiny FIFO example.",
        "highlights": ["Lints clean", "Sim passes"],
        "top_module": "fifo",
        "platform": "sky130hd",
    })
    _write(os.path.join(ws, "fifo.v"), "module fifo(); endmodule\n")
    _write(os.path.join(ws, "fifo_tb.v"), "module fifo_tb(); endmodule\n")
    # manifest carries the SOURCE session id (must be cleared on fork).
    _write(os.path.join(ws, "manifest.json"), {
        "sessionId": "ORIGINAL_SOURCE_SESSION",
        "files": [
            {"name": "fifo.v", "role": "rtl", "path": "fifo.v"},
            {"name": "fifo_tb.v", "role": "tb", "path": "fifo_tb.v"},
        ],
        "synthTop": "fifo",
        "simTop": "fifo_tb",
    })
    _write(os.path.join(ws, "attempt_events.jsonl"),
           '{"event_type":"tool_call","tool":"linter_tool","session_id":"ORIGINAL_SOURCE_SESSION"}\n')
    if with_synth:
        run_dir = os.path.join(ws, "synth_runs", "synth_0001")
        # netlist lives where _find_netlist looks (orfs_results/), absolute path
        # pointing at the SOURCE machine — must be re-derived on fork.
        netlist = os.path.join(run_dir, "orfs_results", "fifo_final.v")
        _write(netlist, "module fifo(); endmodule\n")
        _write(os.path.join(run_dir, "run_meta.json"), {
            "id": "synth_0001", "status": "completed", "top_module": "fifo",
            "netlist_path": r"C:\some\other\machine\workspace\ORIGINAL\synth_runs\synth_0001\orfs_results\fifo_final.v",
        })
        # A terminal run's completion marker — copied verbatim so it never
        # re-announces (its presence blocks a fresh completion event).
        _write(os.path.join(run_dir, "completion.event"), "")
    return bundle, ws


@pytest.fixture
def examples_dir(tmp_path):
    d = str(tmp_path / "examples")
    _make_bundle(d)
    return d


# ---------------------------------------------------------------------------
# copytree guard (A6 net-new util)
# ---------------------------------------------------------------------------


def test_copytree_guarded_enforces_file_ceiling(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for i in range(5):
        (src / f"f{i}.txt").write_text("x")
    dst = tmp_path / "dst"
    with pytest.raises(BundleTooLarge):
        copytree_guarded(str(src), str(dst), max_files=3)
    # Partial destination is cleaned up — no debris.
    assert not dst.exists()


def test_copytree_guarded_enforces_byte_ceiling(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "big.bin").write_bytes(b"0" * 2048)
    dst = tmp_path / "dst"
    with pytest.raises(BundleTooLarge):
        copytree_guarded(str(src), str(dst), max_bytes=1024)
    assert not dst.exists()


def test_scan_for_secrets_flags_by_name(tmp_path):
    (tmp_path / ".env").write_text("SECRET=1")
    (tmp_path / "design.v").write_text("module m(); endmodule")
    sub = tmp_path / "keys"
    sub.mkdir()
    (sub / "id_rsa").write_text("x")
    hits = scan_for_secrets(str(tmp_path))
    assert ".env" in hits
    assert "keys/id_rsa" in hits
    assert "design.v" not in hits


# ---------------------------------------------------------------------------
# Listing / preview
# ---------------------------------------------------------------------------


def test_list_templates_shape(examples_dir):
    items = T.list_templates(examples_dir)
    assert len(items) == 1
    t = items[0]
    assert t["id"] == "demo_fifo"
    assert t["name"] == "Demo FIFO"
    assert t["highlights"] == ["Lints clean", "Sim passes"]
    assert t["file_count"] >= 4
    assert t["run_count"] == 1


def test_get_template_preview(examples_dir):
    detail = T.get_template("demo_fifo", examples_dir)
    assert "fifo.v" in detail["files"]
    assert "manifest.json" in detail["files"]
    assert detail["conversations"] == []  # none authored in this fixture


def test_get_unknown_template_raises(examples_dir):
    with pytest.raises(T.TemplateNotFound):
        T.get_template("nope", examples_dir)


def test_get_template_rejects_traversal(examples_dir):
    with pytest.raises(T.TemplateNotFound):
        T.get_template("../secrets", examples_dir)


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


def test_fork_copies_workspace_seeds_chat_and_stamps_provenance(sm, examples_dir):
    fid = T.fork_from_template(sm, "demo_fifo", user_id=None, examples_dir=examples_dir)
    ws = sm.get_workspace_path(fid)
    # Workspace copied.
    assert os.path.isfile(os.path.join(ws, "fifo.v"))
    assert os.path.isfile(os.path.join(ws, "attempt_events.jsonl"))
    # Chat 1 seeded (Wave 9) — count is 1 from birth.
    assert sm.count_threads(fid) == 1
    # Provenance stamped with an AWARE UTC timestamp.
    prov = T.read_provenance(ws)
    assert prov["id"] == "demo_fifo" and prov["name"] == "Demo FIFO"
    assert prov["forked_at"].endswith("+00:00")


def test_fork_clears_manifest_session_id(sm, examples_dir):
    fid = T.fork_from_template(sm, "demo_fifo", examples_dir=examples_dir)
    manifest = json.load(open(os.path.join(sm.get_workspace_path(fid), "manifest.json")))
    # Source id blanked (reconcile re-seeds the fork's own on next read) — the
    # source id must NOT survive into the fork.
    assert manifest["sessionId"] == ""
    assert manifest["sessionId"] != "ORIGINAL_SOURCE_SESSION"


def test_fork_rewrites_netlist_path_into_fork_run_dir(sm, examples_dir):
    fid = T.fork_from_template(sm, "demo_fifo", examples_dir=examples_dir)
    ws = sm.get_workspace_path(fid)
    meta = json.load(open(os.path.join(ws, "synth_runs", "synth_0001", "run_meta.json")))
    np = meta["netlist_path"]
    # Re-derived against the fork's own run dir — absolute, present, and NOT the
    # stale source-machine path.
    assert np and os.path.exists(np)
    assert os.path.abspath(ws) in os.path.abspath(np)
    assert "other\\machine" not in np and "ORIGINAL" not in np


def test_fork_preserves_completion_marker_and_terminal_status(sm, examples_dir):
    """Copied completion.event + terminal status → the run never re-announces."""
    fid = T.fork_from_template(sm, "demo_fifo", examples_dir=examples_dir)
    run_dir = os.path.join(sm.get_workspace_path(fid), "synth_runs", "synth_0001")
    assert os.path.isfile(os.path.join(run_dir, "completion.event"))
    meta = json.load(open(os.path.join(run_dir, "run_meta.json")))
    assert meta["status"] == "completed"  # terminal → reconcile short-circuits


def test_fork_is_owned_by_caller_not_template(sm, examples_dir):
    fid = T.fork_from_template(sm, "demo_fifo", user_id="alice", examples_dir=examples_dir)
    # Owned by the forking user…
    assert sm.owns_session(fid, "alice")
    # …and invisible to another tenant.
    assert sm.get_session_metadata(fid, user_id="bob") is None


def test_fork_unknown_template_raises(sm, examples_dir):
    with pytest.raises(T.TemplateNotFound):
        T.fork_from_template(sm, "ghost", examples_dir=examples_dir)


def test_fork_twice_does_not_collide(sm, examples_dir):
    a = T.fork_from_template(sm, "demo_fifo", examples_dir=examples_dir)
    b = T.fork_from_template(sm, "demo_fifo", examples_dir=examples_dir)
    assert a != b
    assert os.path.isdir(sm.get_workspace_path(a))
    assert os.path.isdir(sm.get_workspace_path(b))


def test_half_fork_rolls_back_dir_and_metadata(sm, examples_dir):
    """A copy failure after create_session must leave NO partial workspace and
    NO orphan metadata (A6)."""
    before = set(sm.get_all_sessions())
    # max_files=0 forces copytree_guarded to abort on the first file.
    with pytest.raises(BundleTooLarge):
        T.fork_from_template(sm, "demo_fifo", examples_dir=examples_dir, max_files=0)
    after = set(sm.get_all_sessions())
    assert after == before  # rolled back: no orphan session row
    # No leftover workspace dir for the base tag.
    assert not os.path.isdir(os.path.join(sm.base_dir, "demo-fifo"))


def test_fork_hosted_is_gated(sm, examples_dir, monkeypatch):
    """Level 1 is self-host only — a cloud workspace engine hard-gates (A5)."""
    monkeypatch.setattr(T, "_is_cloud_workspace", lambda: True)
    with pytest.raises(T.TemplatesUnavailable):
        T.fork_from_template(sm, "demo_fifo", examples_dir=examples_dir)
    # And nothing was created.
    assert sm.get_all_sessions() == []


# ---------------------------------------------------------------------------
# Transcript renderer (pure)
# ---------------------------------------------------------------------------


class _Msg:
    """Minimal LangChain-message stand-in for the renderer's duck typing."""

    def __init__(self, type, content="", tool_calls=None, tool_call_id=None):
        self.type = type
        self.content = content
        self.tool_calls = tool_calls or []
        self.tool_call_id = tool_call_id


def test_render_transcript_summarizes_turns_and_tool_calls():
    messages = [
        _Msg("system", "you are an agent"),
        _Msg("human", "Design a FIFO"),
        _Msg("ai", "On it.", tool_calls=[{"id": "c1", "name": "run_isolated_simulation", "args": {"top_module": "fifo_tb"}}]),
        _Msg("tool", '{"status": "passed"}', tool_call_id="c1"),
        _Msg("ai", "Simulation passed."),
    ]
    md = render_transcript(messages, title="Chat 1", template_name="Demo FIFO")
    assert "# Chat 1" in md
    assert "Demo FIFO" in md
    assert "## User" in md and "Design a FIFO" in md
    assert "## Assistant" in md
    assert "run_isolated_simulation" in md
    assert "top_module=fifo_tb" in md
    assert "passed" in md  # tool result summarized under the call
    # System prompt is never rendered.
    assert "you are an agent" not in md


def test_render_transcript_empty():
    md = render_transcript([], title="Empty")
    assert "no conversation recorded" in md


def test_render_transcript_redacts_author_paths():
    """F16: a tool result echoing an absolute host path must not survive into a
    PUBLIC transcript."""
    home = r"C:\Users\naman"
    ws = r"C:\Users\naman\Desktop\Projects\endgame\workspace\uart"
    messages = [
        _Msg("human", f"look at {ws}/uart.v"),
        _Msg("ai", "ok", tool_calls=[{"id": "c1", "name": "read_file", "args": {"path": f"{ws}/uart.v"}}]),
        _Msg("tool", f'compiled {ws}/sim_runs/sim_0001/a.out ok', tool_call_id="c1"),
    ]
    md = render_transcript(messages, title="Chat 1", redact_paths=[ws, home])
    assert "naman" not in md
    assert r"C:\Users" not in md and "C:/Users" not in md
    assert "<workspace>" in md
    # Without redaction the path would be present (sanity that the test bites).
    raw = render_transcript(messages, title="Chat 1")
    assert "naman" in raw


def test_slugify():
    assert slugify("Chat 1: The FIFO!") == "chat-1-the-fifo"
    assert slugify("") == "chat"


# ---------------------------------------------------------------------------
# Export round-trip: session → bundle → forkable
# ---------------------------------------------------------------------------


def test_export_then_fork_round_trip(sm, tmp_path):
    # Build a source session with real files + a synth run carrying an absolute
    # netlist path and a foreign manifest sessionId.
    sid = sm.create_session("uart")
    ws = sm.get_workspace_path(sid)
    _write(os.path.join(ws, "uart.v"), "module uart(); endmodule\n")
    run_dir = os.path.join(ws, "sim_runs", "sim_0001")
    _write(os.path.join(run_dir, "run_meta.json"),
           {"id": "sim_0001", "status": "passed", "compileCommand": f"iverilog -I {ws} uart.v"})
    _write(os.path.join(run_dir, "uart_tb.out"), "COMPILED-BINARY-WITH-" + ws)
    # F16: the actor event logs also carry the absolute workspace path in tool
    # args/results — the exported bundle must not leak them.
    _write(os.path.join(ws, "attempt_events.jsonl"),
           '{"tool":"linter_tool","arguments":{"verilog_files":["' + ws.replace("\\", "\\\\") + '/uart.v"]}}\n')
    _write(os.path.join(ws, "attempt_log.json"),
           {"events": [{"tool": "read_file", "path": ws + "/uart.v"}]})
    _write(os.path.join(ws, "manifest.json"), {"sessionId": sid, "files": [{"name": "uart.v", "role": "rtl", "path": "uart.v"}], "synthTop": "uart"})

    out = str(tmp_path / "examples" / "uart_demo")
    result = T.export_session_bundle(sm, sid, out, db_path=sm.db_path, name="UART Demo", description="d", highlights=["h"])

    # Bundle exists and is sanitized.
    tmpl = json.load(open(os.path.join(out, "template.json")))
    assert tmpl["name"] == "UART Demo"
    bws = os.path.join(out, "workspace")
    assert json.load(open(os.path.join(bws, "manifest.json")))["sessionId"] == ""
    # Author's absolute path redacted from the run command; compiled .out dropped.
    meta = json.load(open(os.path.join(bws, "sim_runs", "sim_0001", "run_meta.json")))
    assert ws not in meta["compileCommand"]
    assert not os.path.exists(os.path.join(bws, "sim_runs", "sim_0001", "uart_tb.out"))
    # F16: the actor event logs are redacted too — no author path survives.
    for log_name in ("attempt_events.jsonl", "attempt_log.json"):
        with open(os.path.join(bws, log_name), encoding="utf-8") as f:
            log_text = f.read()
        assert ws not in log_text and ws.replace("\\", "/") not in log_text
        assert "<workspace>" in log_text

    # The exported bundle is itself listable + forkable.
    assert T.list_templates(str(tmp_path / "examples"))[0]["id"] == "uart_demo"
    fid = T.fork_from_template(sm, "uart_demo", examples_dir=str(tmp_path / "examples"))
    assert os.path.isfile(os.path.join(sm.get_workspace_path(fid), "uart.v"))


# ---------------------------------------------------------------------------
# The real shipped bundle (examples/sync_fifo) is valid + forkable
# ---------------------------------------------------------------------------


def test_shipped_sync_fifo_bundle_is_forkable(sm):
    items = {t["id"]: t for t in T.list_templates()}  # default examples dir (repo root)
    if "sync_fifo" not in items:
        pytest.skip("sync_fifo bundle not present")
    assert items["sync_fifo"]["run_count"] >= 2  # the fail + pass sims
    fid = T.fork_from_template(sm, "sync_fifo")
    ws = sm.get_workspace_path(fid)
    assert os.path.isfile(os.path.join(ws, "sync_fifo.v"))
    assert os.path.isfile(os.path.join(ws, "attempt_events.jsonl"))
    assert os.path.isdir(os.path.join(ws, "sim_runs"))


# ---------------------------------------------------------------------------
# REST surface (TestClient over api.app with a temp SessionManager)
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402
import api  # noqa: E402


@pytest.fixture
def client(sm, examples_dir, monkeypatch):
    monkeypatch.setattr(api, "session_manager", sm)
    # Point the routes at the fixture bundle dir.
    monkeypatch.setattr(api.templates_mod, "default_examples_dir", lambda: examples_dir)
    return TestClient(api.app)


def test_api_list_and_get_templates(client):
    r = client.get("/api/templates")
    assert r.status_code == 200
    assert r.json()["templates"][0]["id"] == "demo_fifo"
    r = client.get("/api/templates/demo_fifo")
    assert r.status_code == 200
    assert "fifo.v" in r.json()["files"]


def test_api_get_unknown_template_404(client):
    assert client.get("/api/templates/ghost").status_code == 404


def test_api_fork_returns_session_id(client, sm):
    r = client.post("/api/templates/demo_fifo/fork")
    assert r.status_code == 200, r.text
    sid = r.json()["sessionId"]
    assert os.path.isfile(os.path.join(sm.get_workspace_path(sid), "fifo.v"))
    # The single-session GET now surfaces provenance for the chip.
    meta = client.get(f"/api/sessions/{sid}").json()
    assert meta["source_template"]["id"] == "demo_fifo"


def test_api_fork_unknown_404(client):
    assert client.post("/api/templates/ghost/fork").status_code == 404


def test_api_patch_session_preserves_provenance(client, sm):
    """F17: rename/move must NOT blank the forked-from chip (invariant 7). The
    store replaces currentSession with the PATCH response, so it must carry
    source_template."""
    sid = client.post("/api/templates/demo_fifo/fork").json()["sessionId"]
    # Rename → provenance still present in the response.
    r = client.patch(f"/api/sessions/{sid}", json={"name": "My FIFO"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "My FIFO"
    assert r.json()["source_template"]["id"] == "demo_fifo"
    # And the list keeps it too (chip survives a launcher refresh).
    listed = {s["id"]: s for s in client.get("/api/sessions").json()}
    assert listed[sid]["source_template"]["id"] == "demo_fifo"


def test_api_fork_hosted_400(client, monkeypatch):
    monkeypatch.setattr(api.templates_mod, "_is_cloud_workspace", lambda: True)
    r = client.post("/api/templates/demo_fifo/fork")
    assert r.status_code == 400
    assert "self-host" in r.json()["detail"]
