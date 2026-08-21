"""F2 regression — a sessionless MCP skill call must know who is asking.

``list_skills`` and ``read_skill`` declare ``requires_session=False``: a
stranger's client asks what knowledge exists before it has a design to apply it
to. That branch dispatched under ``session_host`` alone, which supplies the
server but binds no ``SessionContext`` — so both tools resolved their owner
through ``current_owner()``, read ``None``, and served the built-in layer.

``None`` is self-host. On hosted it meant an authenticated caller who had
REPLACED a built-in skill was handed the built-in instead, and a caller who had
switched one OFF was offered it as though it were on. Neither call failed;
both answered wrongly, with nothing to show that they had (invariant 4), and
the owner-scoped answer went to whoever asked (invariant 8).

These drive ``call_tool`` directly against a server whose ``scoped_user_id`` is
stubbed per actor, over a real local user-skill store — no live hosted stack.
Each asserts the POST-FIX behavior and fails on pre-fix code.
"""
from __future__ import annotations

import asyncio

import pytest

from src.platform_engines import user_skill_store as store_mod
from src.platform_engines.user_skill_store import LocalUserSkillStore, set_user_skill_store
from src.utils import skills as sk


def _text(results):
    return " ".join(getattr(r, "text", "") for r in results)


def _skill_text(name, description="Does a thing when a thing is needed.", body="MINE"):
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A hosted MCP server with no active session, over a real skill store."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    import importlib

    import mcp_server as mcp_mod
    importlib.reload(mcp_mod)

    srv = mcp_mod.RTLDesignMCPServer(codex_tools=False)
    srv._hosted = True
    actor = {"uid": "alice"}
    srv.scoped_user_id = lambda: actor["uid"]
    # monkeypatch records the process-wide store before we swap it, and puts it
    # back at teardown, so no later test inherits this tmp layer.
    monkeypatch.setattr(store_mod, "_STORE", None, raising=False)
    set_user_skill_store(LocalUserSkillStore(tmp_path / "layer"))
    # No session is selected — these two tools are meant to work without one.
    assert not srv.current_session
    return srv, (lambda uid: actor.__setitem__("uid", uid))


def _a_builtin():
    return sk.discover_skills(sk.SKILLS_ROOT)[0].name


def test_read_skill_serves_the_callers_replacement_not_the_builtin(server):
    srv, set_actor = server
    name = _a_builtin()
    shipped = sk.read_skill_file(name, user_id=None)
    sk.save_user_skill(_skill_text(name, body="ALICE-REPLACED-THIS"), user_id="alice")

    set_actor("alice")
    out = _text(asyncio.run(srv.call_tool("read_skill", {"name": name})))
    assert "ALICE-REPLACED-THIS" in out, (
        "alice replaced this skill and was handed the shipped one instead — "
        "silently, with nothing in the answer to say so"
    )
    assert out.strip() != shipped.strip()

    # And it is HER layer, not a process-wide one: bob still gets the built-in.
    set_actor("bob")
    out = _text(asyncio.run(srv.call_tool("read_skill", {"name": name})))
    assert "ALICE-REPLACED-THIS" not in out


def test_list_skills_reflects_the_callers_own_layer(server):
    srv, set_actor = server
    sk.save_user_skill(_skill_text("alices-own-procedure"), user_id="alice")

    set_actor("alice")
    out = _text(asyncio.run(srv.call_tool("list_skills", {})))
    assert "alices-own-procedure" in out

    set_actor("bob")
    out = _text(asyncio.run(srv.call_tool("list_skills", {})))
    assert "alices-own-procedure" not in out


def test_a_skill_the_caller_switched_off_is_not_offered(server):
    """The worst reading of the pre-fix behavior: a skill the owner turned OFF
    was still advertised and still readable."""
    srv, set_actor = server
    name = _a_builtin()
    sk.set_skill_enabled(name, False, user_id="alice")

    set_actor("alice")
    listed = _text(asyncio.run(srv.call_tool("list_skills", {})))
    assert f"- {name}:" not in listed
    body = _text(asyncio.run(srv.call_tool("read_skill", {"name": name})))
    assert body.startswith("❌"), body[:200]

    set_actor("bob")
    assert f"- {name}:" in _text(asyncio.run(srv.call_tool("list_skills", {})))


def test_binding_the_caller_does_not_give_a_sessionless_call_a_workspace(server):
    """Identity only. The context bound for these calls carries no session and
    no workspace, so nothing about WHERE a sessionless tool acts changes — the
    session tools still refuse or answer exactly as before."""
    from src.utils.session_context import current_session_id, current_workspace

    srv, _set_actor = server
    ctx = srv._sessionless_context()
    assert ctx.user_id == "alice"
    assert ctx.session_id == "" and ctx.workspace == ""

    out = _text(asyncio.run(srv.call_tool("get_current_session", {})))
    assert "no active session" in out.lower(), out
    # Nothing leaks out of the call.
    assert current_session_id() == "" and current_workspace() is None
