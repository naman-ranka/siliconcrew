"""F1 regression — a native chat turn must stamp what drove it.

``session_request_scope`` resolves the provenance stamp for everyone who enters
it: the REST action router, the MCP per-call scope, ``run_in_session``. The
native WebSocket chat path enters none of them. It binds its ``SessionContext``
once at connect with ``set_current_session`` and runs the agent inline, so
``_submit_with_quota_release`` captured nothing at dispatch and ``run_meta.json``
recorded ``skills_loaded`` / ``skills_sha`` / ``skills_disabled`` as ABSENT —
even for a turn whose skills are exactly what produced the number.

``None`` means nobody looked; ``[]`` means a resolver looked and found none. A
turn that really ran with skills in force must record neither as absent, which
is what these assert.

Driven through the REAL websocket handler over a REAL ``create_agent`` graph, so
what the tool observes is what a ``start_synthesis`` dispatched mid-turn would
observe. The stamp is read through ``collect_provenance`` — the same call the
synthesis worker makes to fill ``run_meta.json``.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import tool as lc_tool

import api
from src.platform_engines import user_skill_store as store_mod
from src.platform_engines.user_skill_store import LocalUserSkillStore, set_user_skill_store
from src.utils import skills as sk
from tests.support.scripted_graph import ai, build_real_graph


class _Key:
    api_key = "test-key"
    model = None


class _Provider:
    def resolve(self, uid, model_name):
        return _Key()


def _wire(monkeypatch, tmp_path, recorded, thread_row=lambda *a, **k: {}, constructed=None):
    """The chat WS handler over a fake provider, key provider and manager.

    ``constructed`` collects the ``skills`` argument agent construction was
    handed, so a test can compare what the model was given against what the
    run recorded.
    """

    @lc_tool
    def capture_stamp() -> str:
        """Record what a run dispatched from this turn would be stamped with."""
        from src.platform_engines.provenance import collect_provenance

        recorded.append(collect_provenance().as_dict())
        return "captured"

    def fake_create_agent(checkpointer=None, model_name=None, api_key=None, skills=None):
        if constructed is not None:
            constructed.append(skills)
        return build_real_graph([
            ai("", tool_calls=[{"id": "c1", "name": "capture_stamp", "args": {}}]),
            ai("done"),
        ], tools=[capture_stamp])

    @asynccontextmanager
    async def fake_ckpt(_path):
        yield None

    class _WS:
        def workspace_for(self, sid):
            return str(tmp_path)

        def workspace_path_for(self, sid):
            return str(tmp_path)

        def sync(self, sid):
            pass

    monkeypatch.setattr(api, "create_architect_agent", fake_create_agent)
    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)
    monkeypatch.setattr(api, "get_workspace_provider", lambda: _WS())
    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", _Provider())

    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: True)
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", thread_row)
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": "claude-sonnet-4-6"})
    monkeypatch.setattr(store_mod, "_STORE", None, raising=False)
    set_user_skill_store(LocalUserSkillStore(tmp_path / "layer"))

    def _run(messages=("go",)):
        with TestClient(api.app).websocket_connect("/api/chat/sess-prov") as ws:
            for message in messages:
                ws.send_json({"message": message})
                while True:
                    frame = ws.receive_json()
                    if frame.get("type") in ("done", "error", "stopped"):
                        break

    return _run


@pytest.fixture()
def turn(monkeypatch, tmp_path):
    """Run native chat turns whose agent calls a stamp-capturing tool."""
    recorded = []
    run = _wire(monkeypatch, tmp_path, recorded)

    def _run(messages=("go",)):
        recorded.clear()
        run(messages)
        return list(recorded)

    return _run


def _a_builtin():
    return sk.discover_skills(sk.SKILLS_ROOT)[0].name


def test_a_native_turn_stamps_the_skills_that_drove_it(turn):
    stamps = turn()
    assert len(stamps) == 1
    stamp = stamps[0]
    assert stamp["skills_loaded"] is not None, (
        "a native chat turn dispatched a run and recorded skills_loaded as ABSENT. "
        "None means nobody looked — but skills were in force for this turn."
    )
    assert stamp["skills_loaded"], "the shipped pack is not empty"
    assert stamp["skills_sha"], stamp
    assert stamp["skills_disabled"] == []
    assert stamp["prompt_version"] and stamp["prompt_sha"]
    assert stamp["context_edit"]


def test_a_skill_switched_off_before_the_turn_is_recorded_as_off(turn):
    """The absence a list of what was ON can never show. A benchmark from a
    session with the safety net removed must not look like one with it in
    place — which is only true if the native path records it at all."""
    name = _a_builtin()
    sk.set_skill_enabled(name, False, user_id=None)

    stamp = turn()[0]
    assert stamp["skills_disabled"] == [name], stamp
    assert name not in (stamp["skills_loaded"] or [])


def test_the_stamp_is_resolved_per_turn_not_once_per_connection(turn):
    """A user can switch a skill off between two messages on one socket. The
    second turn must stamp what the second turn actually ran on."""
    name = _a_builtin()
    first, second = turn(messages=("one", "two"))
    assert first["skills_loaded"] == second["skills_loaded"]

    sk.set_skill_enabled(name, False, user_id=None)
    third = turn(messages=("three",))[0]
    assert third["skills_disabled"] == [name]
    assert third["skills_loaded"] != first["skills_loaded"]


def test_an_extension_turn_does_not_inherit_the_native_turns_stamp(monkeypatch, tmp_path):
    """A second message on the same socket may belong to another runtime.

    An extension turn resolves its own stamp inside ``session_request_scope``,
    and that scope will not re-resolve over one already bound — the outermost
    turn's stamp wins. So a native stamp still bound when the runtime dispatch
    runs would become the stamp the extension's run recorded: a Codex run filed
    under the LangChain turn that happened to precede it. The native binding is
    released before the dispatch decides whose turn this is.
    """
    from src.agents import runtime_registry
    from src.platform_engines.provenance import current_agent_provenance

    seen = []

    class _StampReadingRuntime:
        runtime_id = "prov_ext"

        async def run_turn(self, ctx):
            seen.append(current_agent_provenance())
            await ctx.emit(runtime_registry.RuntimeEvent.start())
            await ctx.emit(runtime_registry.RuntimeEvent.done())

    rows = [{}, {"runtime": "prov_ext"}]

    def thread_row(*_a, **_k):
        return rows[min(len(seen) + len(recorded), len(rows) - 1)]

    recorded = []
    run = _wire(monkeypatch, tmp_path, recorded, thread_row=thread_row)
    runtime_registry.register_runtime(
        runtime_registry.RuntimeDescriptor(id="prov_ext", display_name="Prov"),
        _StampReadingRuntime(),
    )
    try:
        run(messages=("native first", "extension second"))
    finally:
        runtime_registry.unregister_runtime("prov_ext")

    assert len(recorded) == 1, "the first message must have taken the native path"
    assert recorded[0]["skills_loaded"], recorded[0]
    assert seen == [None], (
        "the extension turn started with the previous native turn's stamp still "
        "bound; session_request_scope would then never resolve its own"
    )


def test_the_prompt_and_the_stamp_describe_one_resolution(monkeypatch, tmp_path):
    """The set the model reads and the set the run records are one object.

    The turn stamped the skills it resolved for the owner, then agent
    construction called ``load_system_prompt`` -> ``compose_skills_block``,
    which resolved the store a SECOND time. A skill replaced or switched off
    between those two reads reached the model while the run recorded the digest
    of what it replaced — a stamp that disagrees with the prompt it claims to
    describe, which is the one thing a provenance field must never do.

    So construction is handed the resolved set. Being handed nothing is the
    failure: it means construction went and resolved for itself.
    """
    recorded, constructed = [], []
    _wire(monkeypatch, tmp_path, recorded, constructed=constructed)()

    assert len(constructed) == 1
    handed = constructed[0]
    assert handed is not None, (
        "agent construction resolved the skill store for itself; the turn's "
        "stamp and the model's prompt can then describe different sets"
    )
    stamp = recorded[0]
    # Through the one recipe, never a copy of it here: the digest covers a
    # skill's reference files as well as its body.
    _, digest = sk.skills_provenance(handed.active)
    assert digest == stamp["skills_sha"], (digest, stamp["skills_sha"])
    assert sorted(s.name for s in handed.active) == sorted(stamp["skills_loaded"])
    assert list(handed.disabled) == stamp["skills_disabled"]
