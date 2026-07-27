"""#43 — the MCP server must name the workspace where work actually happens.

``session_manager.get_workspace_path`` returns ``RTL_WORKSPACE/<sid>``. In
hosted that directory is never materialized: the real workspace is the cloud
provider's scratch (``/tmp/siliconcrew-scratch/<sid>``), hydrated from object
storage and synced back. Three consequences, one root cause:

  A. ``set_active_session`` / ``create_session_tool`` / ``get_current_session``
     / ``inject_architect_prompt`` / the workflow prompt reported a path nothing
     writes to (the filed issue).
  B. the activity log was written to that path, so ``attempt_events.jsonl`` for
     hosted MCP tool calls never reached the synced workspace — invisible in the
     Activity dock, lost on instance recycle (invariants 3 + 9).
  C. resources listed/read from that path — always empty / "File not found".

The fix routes every reported path through the workspace-provider seam
(``describe_workspace``, non-materializing), logs activity inside the session
scope (the workspace the tool ran in), and reads resources through
``workspace_for``. Self-host must be bit-for-bit unchanged: there the provider
path IS ``RTL_WORKSPACE/<sid>``.

No live GCS here — ``InMemoryObjectStore`` stands in for the bucket, which is
the established pattern for hosted legs in this suite.
"""
import asyncio
import json
import os
from urllib.parse import quote

import pytest

from src.platform_engines.workspace_provider import (
    CloudWorkspaceProvider,
    InMemoryObjectStore,
    describe_workspace,
    set_workspace_provider,
)
from src.utils.session_context import LocalWorkspaceProvider


def _text(results):
    return " ".join(getattr(r, "text", "") for r in results)


def _fresh_mcp_module(tmp_path, monkeypatch):
    """An mcp_server bound to temp data/workspace dirs (test_mcp_bound_session
    fixture pattern)."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    import importlib
    import mcp_server as mcp_mod

    return importlib.reload(mcp_mod)


@pytest.fixture
def hosted_mcp(tmp_path, monkeypatch):
    """A server whose workspaces live in cloud scratch, NOT in RTL_WORKSPACE."""
    mcp_mod = _fresh_mcp_module(tmp_path, monkeypatch)
    scratch = str(tmp_path / "scratch")
    provider = CloudWorkspaceProvider(InMemoryObjectStore(), scratch)
    set_workspace_provider(provider)
    try:
        server = mcp_mod.RTLDesignMCPServer(codex_tools=True)
        server._hosted = True
        sid = server.session_manager.create_session("designA", user_id=None)
        yield server, sid, os.path.join(scratch, sid), str(tmp_path / "ws" / sid)
    finally:
        set_workspace_provider(None)  # restore the module singleton for other tests


@pytest.fixture
def selfhost_mcp(tmp_path, monkeypatch):
    """Self-host: the provider path and the session manager's path are one dir."""
    mcp_mod = _fresh_mcp_module(tmp_path, monkeypatch)
    set_workspace_provider(LocalWorkspaceProvider(str(tmp_path / "ws")))
    try:
        server = mcp_mod.RTLDesignMCPServer(codex_tools=True)
        sid = server.session_manager.create_session("designA", user_id=None)
        yield server, sid, str(tmp_path / "ws" / sid)
    finally:
        set_workspace_provider(None)


# --- LEG A: reported paths ---------------------------------------------------


def test_set_active_session_reports_provider_path(hosted_mcp):
    """The filed issue: the response named RTL_WORKSPACE/<sid>, a directory the
    hosted deployment never materializes."""
    server, sid, scratch_ws, stale_ws = hosted_mcp

    out = _text(asyncio.run(server.call_tool("set_active_session", {"session_id": sid})))

    assert scratch_ws in out, "set_active_session must report the provider's workspace"
    assert stale_ws not in out, "reported a workspace that is never written to"


def test_current_session_and_prompt_report_provider_path(hosted_mcp):
    """The same path leak in get_current_session / inject_architect_prompt /
    the rtl_design_workflow prompt."""
    server, sid, scratch_ws, stale_ws = hosted_mcp
    server.current_session = sid

    info = json.loads(_text(asyncio.run(server.call_tool("get_current_session", {}))))
    assert info["workspace"] == scratch_ws

    payload = _text(asyncio.run(server.call_tool("inject_architect_prompt", {"session_id": sid})))
    assert f"WORKSPACE: {scratch_ws}" in payload
    assert stale_ws not in payload

    prompt = asyncio.run(server.get_prompt("rtl_design_workflow", {"session_id": sid}))
    prompt_text = " ".join(m.content.text for m in prompt.messages)
    assert scratch_ws in prompt_text
    assert stale_ws not in prompt_text


def test_created_session_reports_provider_path(hosted_mcp):
    server, _sid, _scratch_ws, _stale_ws = hosted_mcp
    out = _text(asyncio.run(server.call_tool("create_session_tool", {"session_name": "designB"})))
    new_sid = server.current_session
    assert describe_workspace(new_sid) in out


# --- LEG B: the activity log lands in the synced workspace -------------------


def test_activity_events_land_in_the_provider_workspace(hosted_mcp):
    """Invariant 3: an MCP tool call is an event in the workspace it ran in.

    Pre-fix the events went to RTL_WORKSPACE/<sid> (or nowhere at all, since
    attempt_logger drops writes to a non-existent dir), so hosted MCP activity
    never reached the synced workspace.
    """
    server, sid, scratch_ws, stale_ws = hosted_mcp
    server.current_session = sid

    asyncio.run(server.call_tool("write_file", {"filename": "a.v", "content": "module a; endmodule"}))
    asyncio.run(server.call_tool("list_files_tool", {}))

    events_path = os.path.join(scratch_ws, "attempt_events.jsonl")
    assert os.path.exists(events_path), "activity log missing from the workspace tools ran in"
    events = [json.loads(line) for line in open(events_path, encoding="utf-8") if line.strip()]
    assert {e["tool"] for e in events} == {"write_file", "list_files_tool"}
    assert {e["event_type"] for e in events} == {"tool_call", "tool_result"}
    assert all(e["source"] == "mcp" for e in events)

    # ...and NOT in the never-materialized session-manager path.
    assert not os.path.exists(os.path.join(stale_ws, "attempt_events.jsonl"))


def test_activity_events_are_synced_with_the_mutation(hosted_mcp, tmp_path):
    """The events must be IN the object store after a mutating call (they are
    logged inside the session scope, before its exit sync) — otherwise they die
    with the instance."""
    server, sid, _scratch_ws, _stale = hosted_mcp
    server.current_session = sid
    asyncio.run(server.call_tool("write_file", {"filename": "a.v", "content": "module a; endmodule"}))

    # A "different instance": same store, fresh scratch → hydrate and look.
    from src.platform_engines.workspace_provider import get_workspace_provider

    store = get_workspace_provider()._store
    cold = CloudWorkspaceProvider(store, str(tmp_path / "other-instance"))
    hydrated = cold.workspace_for(sid)
    assert os.path.exists(os.path.join(hydrated, "attempt_events.jsonl"))


def test_tool_error_is_logged_in_the_provider_workspace(hosted_mcp):
    """An error is an event too, and it belongs in the same log."""
    server, sid, scratch_ws, _stale = hosted_mcp
    server.current_session = sid

    asyncio.run(server.call_tool("read_file", {"filename": "../escape.v"}))

    events_path = os.path.join(scratch_ws, "attempt_events.jsonl")
    assert os.path.exists(events_path)
    events = [json.loads(line) for line in open(events_path, encoding="utf-8") if line.strip()]
    assert [e["tool"] for e in events] == ["read_file", "read_file"]


# --- LEG C: resources ---------------------------------------------------------


def test_read_resource_serves_a_file_written_through_the_tool_path(hosted_mcp):
    """Pre-fix: 'File not found' — the resource path read RTL_WORKSPACE/<sid>
    while write_file wrote into the provider's scratch."""
    server, sid, _scratch_ws, _stale = hosted_mcp
    server.current_session = sid
    asyncio.run(server.call_tool("write_file", {"filename": "top.v", "content": "module top; endmodule"}))

    enc = quote(sid, safe="")
    result = asyncio.run(server.read_resource(f"rtl://session/{enc}/file/top.v"))
    assert "module top; endmodule" in result.contents[0].text


def test_list_resources_sees_files_written_through_the_tool_path(hosted_mcp):
    server, sid, scratch_ws, _stale = hosted_mcp
    server.current_session = sid
    asyncio.run(server.call_tool("write_file", {"filename": "top.v", "content": "module top; endmodule"}))

    uris = " ".join(str(r.uri) for r in asyncio.run(server.list_resources()))
    assert "top.v" in uris  # pre-fix: the session listed no files at all

    info = json.loads(
        _text_contents(asyncio.run(server.read_resource(f"rtl://session/{quote(sid, safe='')}")))
    )
    assert info["workspace"] == scratch_ws
    assert "top.v" in info["files"]


def _text_contents(result):
    return result.contents[0].text


# --- Self-host regression: nothing moves -------------------------------------


def test_selfhost_paths_unchanged(selfhost_mcp):
    """Self-host reports exactly today's path (RTL_WORKSPACE/<sid> — which IS
    the provider's path there), logs activity there, and reads resources there."""
    server, sid, ws = selfhost_mcp
    assert server.session_manager.get_workspace_path(sid) == ws

    out = _text(asyncio.run(server.call_tool("set_active_session", {"session_id": sid})))
    assert ws in out

    asyncio.run(server.call_tool("write_file", {"filename": "a.v", "content": "module a; endmodule"}))
    assert os.path.exists(os.path.join(ws, "a.v"))
    assert os.path.exists(os.path.join(ws, "attempt_events.jsonl"))

    result = asyncio.run(server.read_resource(f"rtl://session/{quote(sid, safe='')}/file/a.v"))
    assert "module a; endmodule" in result.contents[0].text


def test_describe_workspace_does_not_materialize(tmp_path):
    """The accessor is a path computation: no hydration, no mkdir. (A reporting
    call that materialized would defeat the point — and in hosted would download
    a workspace just to print its name.)"""
    scratch = str(tmp_path / "scratch")
    provider = CloudWorkspaceProvider(InMemoryObjectStore(), scratch)
    path = describe_workspace("sess_x", provider=provider)
    assert path == os.path.join(scratch, "sess_x")
    assert not os.path.exists(path)

    local = LocalWorkspaceProvider(str(tmp_path / "ws"))
    assert describe_workspace("sess_y", provider=local) == os.path.join(str(tmp_path / "ws"), "sess_y")
    assert not os.path.exists(os.path.join(str(tmp_path / "ws"), "sess_y"))


def test_describe_workspace_refuses_to_guess(tmp_path):
    """A provider that can't describe a path without materializing must say so
    loudly rather than have a wrong path invented for it."""

    class Opaque:
        def workspace_for(self, session_id):
            return "/nowhere"

    with pytest.raises(TypeError):
        describe_workspace("s", provider=Opaque())
