"""B2 (dev#43 + invariants 3/9) — the MCP server must report and LOG the
workspace its tools actually act on.

Every MCP reply that names a workspace, and the path fed to the activity log,
came from ``SessionManager.get_workspace_path`` — the *logical* layout
(``<base>/<session_id>``). Tools do not run there on hosted: ``run_in_session``
binds ``WorkspaceProvider.workspace_for(...)``, which for the cloud provider is
the scratch materialization (``WORKSPACE_SCRATCH_DIR/<session_id>``). So:

* the agent was told to work in a directory nothing reads or writes (dev#43);
* worse, ``mcp_server.call_tool`` logged ``attempt_events.jsonl`` there, where
  ``attempt_logger`` either drops the event (dir absent) or writes it to
  never-synced instance disk — MCP activity silently missing from the one event
  log every surface renders (invariant 3) and violating twelve-factor (9).

These drive the server object directly (``asyncio.run``, no live transport) with
a provider injected via ``set_workspace_provider``. Self-host parity is asserted
behaviorally (the file a tool writes lands under the reported path), never by
string equality with ``get_workspace_path`` — that equality is coincidence.
"""
import asyncio
import importlib
import json
import os

import pytest


def _text(results):
    return " ".join(getattr(r, "text", "") for r in results)


def _workspace_line(text, marker="Workspace:"):
    """Extract the path a reply reports after ``marker``."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(marker):
            return stripped[len(marker):].strip()
    raise AssertionError(f"no {marker!r} line in reply:\n{text}")


@pytest.fixture
def provider_reset():
    """The workspace provider is memoized module-globally; restore it.

    ``importlib.reload(mcp_server)`` does NOT reset ``_PROVIDER``, so a fake left
    behind here would leak into every later test in the session.
    """
    from src.platform_engines import workspace_provider as wp

    original = wp._PROVIDER
    wp.set_workspace_provider(None)  # re-derive from this test's env
    try:
        yield wp
    finally:
        wp.set_workspace_provider(original)


@pytest.fixture
def server(tmp_path, monkeypatch, provider_reset):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    import mcp_server as mcp_mod

    importlib.reload(mcp_mod)
    return mcp_mod.RTLDesignMCPServer(codex_tools=False)


class ScratchProvider:
    """Stands in for ``CloudWorkspaceProvider``: tools run in a scratch tree that
    is NOT the session manager's logical layout."""

    def __init__(self, scratch_dir):
        self.scratch_dir = str(scratch_dir)

    def workspace_path_for(self, session_id):
        return os.path.join(self.scratch_dir, session_id)

    def workspace_for(self, session_id):
        path = self.workspace_path_for(session_id)
        os.makedirs(path, exist_ok=True)
        return path


class LegacyProvider:
    """A duck-typed fake predating the pure accessor (the shape a dozen existing
    tests inject) — the resolver must fall back, not crash."""

    def __init__(self, scratch_dir):
        self.scratch_dir = str(scratch_dir)

    def workspace_for(self, session_id):
        path = os.path.join(self.scratch_dir, session_id)
        os.makedirs(path, exist_ok=True)
        return path


# ---------------------------------------------------------------------------
# 1. Self-host: the reported path is where work actually lands (behavior, not
#    string equality). No-regression leg — passes pre-fix.
# ---------------------------------------------------------------------------


def test_self_host_reported_workspace_is_where_files_land(server):
    out = _text(asyncio.run(server.call_tool("create_session_tool", {"session_name": "d1"})))
    reported = _workspace_line(out)

    asyncio.run(server.call_tool("write_file", {"filename": "design.v", "content": "module d; endmodule\n"}))

    assert os.path.isfile(os.path.join(reported, "design.v"))


# ---------------------------------------------------------------------------
# 2. Provider-backed (hosted shape): every reply AND the activity log must use
#    the provider's path, not the logical one. Fails pre-fix.
# ---------------------------------------------------------------------------


def test_replies_report_provider_workspace(server, tmp_path, provider_reset):
    provider = ScratchProvider(tmp_path / "scratch")
    provider_reset.set_workspace_provider(provider)

    out = _text(asyncio.run(server.call_tool("create_session_tool", {"session_name": "d1"})))
    sid = server.current_session
    scratch = provider.workspace_path_for(sid)
    logical = server.session_manager.get_workspace_path(sid)
    assert scratch != logical

    assert _workspace_line(out) == scratch  # create_session_tool

    out = _text(asyncio.run(server.call_tool("set_active_session", {"session_id": sid})))
    assert _workspace_line(out) == scratch

    out = _text(asyncio.run(server.call_tool("get_current_session", {})))
    assert json.loads(out)["workspace"] == scratch

    out = _text(asyncio.run(server.call_tool("inject_architect_prompt", {"session_id": sid})))
    assert _workspace_line(out, "WORKSPACE:") == scratch

    prompt = asyncio.run(server.get_prompt("rtl_design_workflow", {"session_id": sid}))
    prompt_text = " ".join(
        getattr(m.content, "text", "") for m in prompt.messages
    )
    assert _workspace_line(prompt_text, "**WORKSPACE**:") == provider.workspace_path_for(
        server.current_session
    )


def test_activity_events_land_in_the_provider_workspace(server, tmp_path, provider_reset):
    """THE key fix: log_tool_call/log_tool_result must target the path the tool
    ran in, or hosted MCP activity vanishes (invariants 3 + 9)."""
    provider = ScratchProvider(tmp_path / "scratch")
    provider_reset.set_workspace_provider(provider)

    asyncio.run(server.call_tool("create_session_tool", {"session_name": "d1"}))
    sid = server.current_session
    scratch = provider.workspace_path_for(sid)
    logical = server.session_manager.get_workspace_path(sid)

    asyncio.run(server.call_tool("write_file", {"filename": "design.v", "content": "module d; endmodule\n"}))

    events = os.path.join(scratch, "attempt_events.jsonl")
    assert os.path.isfile(events), "MCP activity did not reach the workspace tools ran in"
    # BOTH events must land: the call event is logged inside the bound scope
    # (after materialization) precisely so a cold instance can't drop it — a
    # result-only log here means the call event regressed to pre-scope logging.
    kinds = [
        json.loads(line)["event_type"]
        for line in open(events, encoding="utf-8")
        if line.strip()
    ]
    assert kinds.count("tool_call") >= 1 and kinds.count("tool_result") >= 1
    assert "write_file" in open(events, encoding="utf-8").read()
    # Pre-fix the log went here — never synced, and not where the run lives.
    assert not os.path.exists(os.path.join(logical, "attempt_events.jsonl"))


def test_resource_reads_use_the_provider_workspace(server, tmp_path, provider_reset):
    provider = ScratchProvider(tmp_path / "scratch")
    provider_reset.set_workspace_provider(provider)

    asyncio.run(server.call_tool("create_session_tool", {"session_name": "d1"}))
    sid = server.current_session
    asyncio.run(server.call_tool("write_file", {"filename": "design.v", "content": "module d; endmodule\n"}))

    from urllib.parse import quote

    uri = f"rtl://session/{quote(sid, safe='')}"
    result = asyncio.run(server.read_resource(uri))
    info = json.loads(result.contents[0].text)
    assert info["workspace"] == provider.workspace_path_for(sid)
    assert "design.v" in info["files"]  # pre-fix: reads the empty logical dir

    listed = asyncio.run(server.list_resources())
    assert any("design.v" in (r.name or "") for r in listed)


# ---------------------------------------------------------------------------
# 3. Fallback: providers without the pure accessor keep working.
# ---------------------------------------------------------------------------


def test_provider_without_workspace_path_for_falls_back(server, tmp_path, provider_reset):
    provider_reset.set_workspace_provider(LegacyProvider(tmp_path / "legacy"))

    out = _text(asyncio.run(server.call_tool("create_session_tool", {"session_name": "d1"})))
    sid = server.current_session
    assert _workspace_line(out) == server.session_manager.get_workspace_path(sid)


# ---------------------------------------------------------------------------
# 4. The accessor itself is pure on both real providers.
# ---------------------------------------------------------------------------


def test_local_provider_path_accessor_does_not_create(tmp_path):
    from src.utils.session_context import LocalWorkspaceProvider

    provider = LocalWorkspaceProvider(str(tmp_path / "base"))
    path = provider.workspace_path_for("s1")
    assert path == os.path.join(str(tmp_path / "base"), "s1")
    assert not os.path.exists(path)
    assert provider.workspace_for("s1") == path
    assert os.path.isdir(path)


def test_cloud_provider_path_accessor_does_not_touch_the_store(tmp_path):
    from src.platform_engines.workspace_provider import CloudWorkspaceProvider

    class ExplodingStore:
        def __getattr__(self, name):
            raise AssertionError(f"store touched: {name}")

    provider = CloudWorkspaceProvider(ExplodingStore(), str(tmp_path / "scratch"))
    path = provider.workspace_path_for("s1")
    assert path == os.path.join(str(tmp_path / "scratch"), "s1")
    assert not os.path.exists(path)
