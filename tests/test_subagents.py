"""Subagents: one event log, derived tool subsets, no free spending, depth 1.

The mechanism is ~200 lines and every one of its promises is the kind that
fails silently. A child whose tool calls do not reach ``attempt_events.jsonl``
looks fine until someone asks what the agent did. A child that resolves its own
key looks fine until the bill. A child that can delegate looks fine until it
does. So each promise is asserted against a REAL child — a real
``create_agent`` graph over a scripted model, running real tools in a real
workspace — not against a fake of the mechanism.
"""
from __future__ import annotations

import json
import os

import pytest

from src.agents import subagents
from src.api import tool_catalog as tc
from src.api.activity import build_activity_events
from src.utils.attempt_logger import EVENTS_FILE, _read_events, log_tool_call
from src.utils.session_context import SessionContext, session_scope
from tests.support.scripted_graph import ScriptedChatModel, ai


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "sess-1"
    ws.mkdir()
    (ws / "design.v").write_text("module design(); endmodule\n", encoding="utf-8")
    return str(ws)


@pytest.fixture
def ctx(workspace):
    return SessionContext(session_id="sess-1", workspace=workspace, user_id="owner-1")


def _script_factory(script, sink):
    """A ``create_llm`` replacement: one fresh scripted model per child."""

    def create_llm(model_name=None, temperature=None, api_key=None, **kwargs):
        model = ScriptedChatModel(script=list(script), calls=[], seen=[])
        sink.append({"model_name": model_name, "api_key": api_key, "model": model})
        return model

    return create_llm


def _patch_model(monkeypatch, script, sink):
    import src.llm

    monkeypatch.setattr(src.llm, "create_llm", _script_factory(script, sink))


# --- the event log -----------------------------------------------------------

def test_a_childs_tool_calls_land_in_the_same_event_log(monkeypatch, ctx):
    """Invariant 3, for the newest actor. One choke point (``wrap_tool_call``),
    so this holds by construction rather than by remembering."""
    sink = []
    _patch_model(monkeypatch, [
        ai("", tool_calls=[{"id": "c1", "name": "list_files_tool", "args": {}}]),
        ai('done {"knob": "clk", "status": "ok"}'),
    ], sink)

    with session_scope(ctx):
        out = subagents.run_role("pd-sweep", ["measure clk=5ns"], model_name="m", api_key=None)

    records = _read_events(os.path.join(ctx.workspace, EVENTS_FILE))
    assert [r["event_type"] for r in records] == ["tool_call", "tool_result"]
    assert {r["source"] for r in records} == {"subagent:pd-sweep"}
    assert {r["tool"] for r in records} == {"list_files_tool"}
    assert records[0]["session_id"] == "sess-1"
    assert out["children"][0]["result"] == {"knob": "clk", "status": "ok"}


def test_a_childs_rows_are_distinguishable_from_its_parents(monkeypatch, ctx):
    """activity.py used to collapse every non-user source into "agent", so a
    fan-out read as one very busy parent. The role now survives into the feed."""
    sink = []
    _patch_model(monkeypatch, [
        ai("", tool_calls=[{"id": "c1", "name": "list_files_tool", "args": {}}]),
        ai("done"),
    ], sink)

    log_tool_call(ctx.workspace, ctx.session_id, "api_ws", "read_file", {}, tool_call_id="parent-1")
    with session_scope(ctx):
        subagents.run_role("pd-sweep", ["a", "b"], model_name="m", api_key=None)

    events = build_activity_events(_read_events(os.path.join(ctx.workspace, EVENTS_FILE)))
    parent = [e for e in events if e["tool"] == "read_file"]
    children = [e for e in events if e["source"] == "subagent"]
    assert parent and parent[0]["source"] == "agent" and parent[0]["subagent"] is None
    assert len(children) == 2, events
    assert {e["subagent"] for e in children} == {"pd-sweep"}
    # Two children, two separately identifiable rows -- ids cannot collide even
    # though both models generated the same tool_call_id.
    assert len({e["id"] for e in children}) == 2


def test_a_failing_child_tool_is_logged_as_an_error_not_swallowed(monkeypatch, ctx):
    sink = []
    _patch_model(monkeypatch, [
        ai("", tool_calls=[{"id": "c1", "name": "read_file", "args": {"filename": "nope.v"}}]),
        ai("could not read it"),
    ], sink)
    with session_scope(ctx):
        subagents.run_role("pd-sweep", ["read a missing file"], model_name="m", api_key=None)
    records = _read_events(os.path.join(ctx.workspace, EVENTS_FILE))
    assert records[-1]["event_type"] == "tool_result"
    assert records[-1]["tool"] == "read_file"


# --- tool subsets are derived ------------------------------------------------

def test_every_role_takes_its_tools_from_the_declared_policy():
    """No role hand-writes a tool list. Its set resolves through the same
    category/surface data every other consumer reads."""
    for role, spec in tc.subagent_roles().items():
        names = tc.tool_names_in_set(spec["tool_set"])
        assert names, role
        for name in names:
            assert tc.policy_for(name)  # a live registry tool, or this raises


def test_a_child_is_offered_strictly_less_than_its_parent():
    parent = set(tc.tool_names_in_set("architect"))
    for spec in tc.subagent_roles().values():
        child = set(tc.tool_names_in_set(spec["tool_set"]))
        assert child < parent, spec["tool_set"]


def test_a_sweep_child_cannot_edit_the_design_it_is_measuring():
    """The one behavioural claim the pd-sweep set makes, asserted through the
    ``mutates`` flag rather than by naming tools."""
    names = tc.tool_names_in_set(tc.subagent_roles()["pd-sweep"]["tool_set"])
    writers = {n for n in names if tc.policy_for(n).mutates and tc.policy_for(n).category != "synthesis"}
    assert not writers, writers


def test_roles_are_skills_not_a_new_file_format():
    """L5. Every role's procedure comes out of ``skills/`` — there is no
    subagent file format in this repo, and the prompt proves it."""
    from src.utils.skills import skills_by_name

    store = skills_by_name()
    for role, spec in tc.subagent_roles().items():
        assert spec["skills"], role
        for skill in spec["skills"]:
            assert skill in store, (role, skill)
        prompt = subagents.child_prompt(role, spec, "a task")
        for skill in spec["skills"]:
            assert store[skill].body in prompt


# --- depth ------------------------------------------------------------------

def test_a_child_may_not_delegate(ctx):
    token = subagents._depth.set(subagents.DEPTH_LIMIT)
    try:
        with session_scope(ctx):
            with pytest.raises(subagents.ToolSetError) as exc:
                subagents.run_role("pd-sweep", ["x"], model_name="m", api_key=None)
        assert "depth limit" in str(exc.value)
    finally:
        subagents._depth.reset(token)


def test_no_child_set_contains_the_delegation_tool():
    """The structural half of the depth limit: the tool is not in any registry,
    so it cannot appear in any set."""
    for name in tc.tool_set_names():
        assert not set(tc.tool_names_in_set(name)) & set(subagents.subagent_tool_names())


# --- reach: native agent only ------------------------------------------------

def test_subagents_never_reach_mcp_or_the_ui():
    from src.tools.wrappers import ALL_TOOLS

    registry = {t.name for t in ALL_TOOLS}
    for name in subagents.subagent_tool_names():
        assert name not in registry
    assert not tc.is_invocable("run_subagents")


def test_the_architect_is_the_only_agent_that_gets_them():
    from src.agents.architect import architect_tool_list

    names = [t.name for t in architect_tool_list("m", None, read_only=False)]
    assert set(subagents.subagent_tool_names()) <= set(names)


# --- spend -------------------------------------------------------------------

def test_a_child_never_resolves_its_own_key_or_model(monkeypatch, ctx):
    """The parent's already-resolved key and already-pinned model are what the
    child is built with — the whole reason the delegation tool is closed over
    them instead of being a registry tool."""
    sink = []
    _patch_model(monkeypatch, [ai("done")], sink)
    with session_scope(ctx):
        subagents.run_role("pd-sweep", ["a", "b"], model_name="pinned-model", api_key="parent-key")
    assert len(sink) == 2
    assert {c["model_name"] for c in sink} == {"pinned-model"}
    assert {c["api_key"] for c in sink} == {"parent-key"}


def test_no_key_provider_is_reachable_from_the_subagent_module():
    source = open(subagents.__file__, encoding="utf-8").read()
    for forbidden in ("build_llm_key_provider", "LlmKeyProvider", "HostedTierLimiter",
                      "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        assert forbidden not in source, forbidden


def test_a_childs_tokens_are_charged_to_the_sessions_own_row(monkeypatch, tmp_path):
    """Not a second ledger: the same session row the parent's turn writes."""
    from src.utils.session_manager import SessionManager

    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    os.makedirs(tmp_path / "data", exist_ok=True)
    manager = SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "data" / "state.db"))
    session = manager.create_session("child-spend", user_id="owner-1")
    sid = session["id"] if isinstance(session, dict) else session
    ws = manager.get_session_path(sid) if hasattr(manager, "get_session_path") else os.path.join(str(tmp_path / "ws"), sid)
    os.makedirs(ws, exist_ok=True)

    sink = []
    _patch_model(monkeypatch, [ai("done", usage={"input_tokens": 100, "output_tokens": 20})], sink)
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    ctx = SessionContext(session_id=sid, workspace=ws, user_id="owner-1")
    with session_scope(ctx):
        out = subagents.run_role("pd-sweep", ["a", "b"], model_name="gemini-3.1-flash-lite", api_key=None)

    assert out["tokens"] == {"input": 200, "output": 40}
    meta = manager.get_session_metadata(sid, user_id="owner-1")
    assert meta["input_tokens"] == 200 and meta["output_tokens"] == 40
    assert meta["total_cost"] > 0


def test_hosted_has_no_children(monkeypatch, ctx):
    """A child's tokens are invisible to the hosted free-tier limiter, so
    hosted has no children at all rather than uncapped ones."""
    from src.platform_engines.settings import reset_settings_cache

    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    reset_settings_cache()
    assert subagents.subagent_tools(model_name="m", api_key=None) == []
    with session_scope(ctx):
        with pytest.raises(subagents.ToolSetError) as exc:
            subagents.run_role("pd-sweep", ["x"], model_name="m", api_key=None)
    assert "hosted" in str(exc.value)
    reset_settings_cache()


def test_a_child_has_a_step_ceiling_of_its_own(monkeypatch, ctx):
    """A child that keeps calling tools stops. 24 graph steps = 12 model calls
    (model+tools per round, wrap-style middleware only, same arithmetic as
    CHAT_RECURSION_LIMIT). The number is what a user's money buys per child."""
    from src.platform_engines.settings import get_settings

    if os.environ.get("SUBAGENT_RECURSION_LIMIT"):
        pytest.skip("overridden in this environment; this pins the shipped default")
    sink = []
    _patch_model(monkeypatch, [ai("", tool_calls=[{"id": "c", "name": "list_files_tool", "args": {}}])], sink)
    with session_scope(ctx):
        out = subagents.run_role("pd-sweep", ["loop forever"], model_name="m", api_key=None)
    assert "error" in out["children"][0]
    assert len(sink[0]["model"].calls) == 12, (
        f"a child at SUBAGENT_RECURSION_LIMIT={get_settings().subagent_recursion_limit} "
        f"gets {len(sink[0]['model'].calls)} model calls, not 12"
    )


def test_the_event_log_hook_costs_no_graph_step(monkeypatch, ctx):
    """``wrap_tool_call`` is wrap-style, so the child graph is still model+tools.
    A node-style hook would cost one step per model call and halve the child's
    budget silently — the same trap CHAT_RECURSION_LIMIT was re-derived for."""
    from langchain.agents import create_agent

    from src.agents.architect import MODEL_NODE, TOOLS_NODE, ReasoningStripMiddleware

    graph = create_agent(
        model=ScriptedChatModel(script=[ai("hi")], calls=[], seen=[]),
        tools=tc.tools_in_set("pd-sweep"),
        middleware=[ReasoningStripMiddleware(),
                    subagents.SubagentActivityMiddleware("pd-sweep", 0, ctx)],
    )
    assert set(graph.get_graph().nodes) == {"__start__", MODEL_NODE, TOOLS_NODE, "__end__"}


def test_the_parent_graph_is_untouched_by_this_wave():
    """P6 adds a TOOL to the architect, not a node and not a middleware, so the
    turn's step budget is unchanged: CHAT_RECURSION_LIMIT stays 54 = 27 model
    calls. Pinned here as well as in test_ws_golden_frames because "we added no
    step" is exactly the claim a later change quietly breaks."""
    from src.agents.architect import architect_middleware
    from src.platform_engines.settings import get_settings

    node_style = {"before_model", "after_model", "before_agent", "after_agent",
                  "abefore_model", "aafter_model", "abefore_agent", "aafter_agent"}
    assert get_settings().chat_recursion_limit == 54
    for mw in architect_middleware() + [subagents.SubagentActivityMiddleware("r", 0, None)]:
        for klass in type(mw).__mro__:
            if klass.__module__.startswith("langchain"):
                break
            overridden = node_style & set(klass.__dict__)
            assert not overridden, (klass.__name__, overridden)


def test_the_fan_out_is_capped(monkeypatch, ctx):
    from src.platform_engines.settings import get_settings

    sink = []
    _patch_model(monkeypatch, [ai("done")], sink)
    cap = get_settings().subagent_max_children
    with session_scope(ctx):
        out = subagents.run_role("pd-sweep", [f"t{i}" for i in range(cap + 3)],
                                 model_name="m", api_key=None)
    assert len(out["children"]) == cap


def test_there_must_be_a_session(monkeypatch):
    with pytest.raises(subagents.ToolSetError) as exc:
        subagents.run_role("pd-sweep", ["x"], model_name="m", api_key=None)
    assert "session" in str(exc.value)


def test_an_unknown_role_is_refused():
    with pytest.raises(subagents.ToolSetError):
        subagents.run_role("nonesuch", ["x"], model_name="m", api_key=None)


# --- the structured answer ---------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ('prose\n{"a": 1}', {"a": 1}),
    ('```json\n{"a": {"b": 2}}\n```', {"a": {"b": 2}}),
    ("no json here", None),
    ("[1, 2]", None),
    ("{not json}", None),
])
def test_a_child_that_ignores_the_contract_reports_prose_not_a_fabrication(text, expected):
    assert subagents._trailing_json(text) == expected


def test_read_only_offers_no_role_whose_work_is_writing(monkeypatch):
    """Derived, not decided: a role survives read-only mode only if its own set
    needs nothing that mutates."""
    assert subagents.subagent_tools(model_name="m", api_key=None, read_only=True) == []
    assert subagents.subagent_tools(model_name="m", api_key=None, read_only=False)


def test_the_delegation_tool_describes_the_roles_from_data():
    tools = subagents.subagent_tools(model_name="m", api_key=None)
    description = tools[0].description
    for role, spec in tc.subagent_roles().items():
        assert role in description
        assert spec["description"].strip().split("\n")[0][:40] in description


def test_the_delegation_tool_returns_json(monkeypatch, ctx):
    sink = []
    _patch_model(monkeypatch, [ai('{"status": "ok"}')], sink)
    tool = subagents.subagent_tools(model_name="m", api_key=None)[0]
    with session_scope(ctx):
        raw = tool.func(role="pd-sweep", tasks=["a"])
    assert json.loads(raw)["children"][0]["result"] == {"status": "ok"}


# --- provenance: a child is its own experiment (F3) --------------------------

def test_a_childs_run_records_the_childs_identity_not_the_parents(monkeypatch, ctx):
    """A child stamps what drove IT — its prompt, its role skills, its tool set.

    ``start_synthesis`` dispatched from inside a child reads the provenance
    ContextVar to decide what ``run_meta.json`` says produced the numbers.
    ``ThreadPoolExecutor`` carries no ContextVar into its workers, so with no
    stamp bound in the child the read finds nothing and ``collect_provenance``
    falls back to the MAIN architect prompt — filing a pd-sweep run under a
    prompt the child never read, with none of the role skills that produced it.

    What this asserts is the recorded stamp itself, through the same
    ``collect_provenance`` call the synthesis worker makes, from inside a tool
    the child really called.
    """
    from langchain_core.tools import tool as lc_tool

    from src.platform_engines.provenance import (
        agent_provenance_scope,
        collect_provenance,
        resolve_agent_provenance,
    )

    recorded = []

    @lc_tool
    def capture_stamp() -> str:
        """Record what a run dispatched from this child would be stamped with."""
        recorded.append(collect_provenance().as_dict())
        return "captured"

    monkeypatch.setattr(subagents, "tools_in_set", lambda *a, **k: [capture_stamp])
    sink = []
    _patch_model(monkeypatch, [
        ai("", tool_calls=[{"id": "c1", "name": "capture_stamp", "args": {}}]),
        ai("done"),
    ], sink)

    parent = resolve_agent_provenance(user_id="owner-1")
    with session_scope(ctx), agent_provenance_scope(parent):
        subagents.run_role("pd-sweep", ["measure clk=5ns"], model_name="m", api_key=None)

    assert len(recorded) == 1
    stamp = recorded[0]
    spec = tc.subagent_roles()["pd-sweep"]
    assert stamp["prompt_version"] == "subagent:pd-sweep", (
        "a run dispatched by a pd-sweep child was stamped with "
        f"{stamp['prompt_version']!r} — the identity of whatever ran it, not of "
        "the child that actually did"
    )
    assert stamp["prompt_sha"] and stamp["prompt_sha"] != parent.prompt_sha
    assert stamp["tool_set"] == spec["tool_set"]
    assert stamp["skills_loaded"] == sorted(spec["skills"])
    assert stamp["skills_sha"] and stamp["skills_sha"] != parent.skills_sha
    # A resolver looked: a child's set is fixed by its role, nothing is off.
    assert stamp["skills_disabled"] == []


def test_a_childs_stamp_does_not_outlive_it_on_a_pooled_thread(monkeypatch, ctx):
    """Bind, and unbind in ``finally`` — the discipline the job runner learned.

    Children run on a pool, so a stamp left bound is read by whatever the next
    job on that worker turns out to be.
    """
    from concurrent.futures import ThreadPoolExecutor

    from src.platform_engines.provenance import current_agent_provenance

    sink = []
    _patch_model(monkeypatch, [ai("done")], sink)
    spec = tc.subagent_roles()["pd-sweep"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        out = pool.submit(subagents._run_one, "pd-sweep", spec, "a", 0, ctx,
                          "m", None, False).result()
        assert "error" not in out, out
        # The SAME worker, handed the next job: it must carry nothing over.
        assert pool.submit(current_agent_provenance).result() is None


# --- spend: a failed child still costs money (F4) ----------------------------

def test_a_child_that_fails_still_reports_what_it_spent(monkeypatch, ctx):
    """The default recursion-limit case makes twelve model calls and used to
    record none of them. Session token and cost totals understated real usage by
    a whole child. Money spent is not conditional on success."""
    sink = []
    _patch_model(monkeypatch, [
        ai("", tool_calls=[{"id": "c", "name": "list_files_tool", "args": {}}],
           usage={"input_tokens": 90, "output_tokens": 7}),
    ], sink)
    with session_scope(ctx):
        out = subagents.run_role("pd-sweep", ["loop forever"], model_name="m", api_key=None)

    child = out["children"][0]
    assert "error" in child, "this child is meant to hit its ceiling"
    calls = len(sink[0]["model"].calls)
    assert calls >= 2, calls
    assert child["tokens"] == {"input": 90 * calls, "output": 7 * calls}, (
        f"the child made {calls} model calls and reported {child['tokens']}"
    )
    assert out["tokens"] == child["tokens"]


def test_a_failed_childs_spend_reaches_the_sessions_own_row(monkeypatch, tmp_path):
    """The aggregate handed to ``_charge`` must carry it, or the ledger is short."""
    from src.utils.session_manager import SessionManager

    monkeypatch.setenv("RTL_DATA_DIR", str(tmp_path / "data"))
    os.makedirs(tmp_path / "data", exist_ok=True)
    manager = SessionManager(base_dir=str(tmp_path / "ws"),
                             db_path=str(tmp_path / "data" / "state.db"))
    session = manager.create_session("failed-child-spend", user_id="owner-1")
    sid = session["id"] if isinstance(session, dict) else session
    ws = os.path.join(str(tmp_path / "ws"), sid)
    os.makedirs(ws, exist_ok=True)

    sink = []
    _patch_model(monkeypatch, [
        ai("", tool_calls=[{"id": "c", "name": "list_files_tool", "args": {}}],
           usage={"input_tokens": 90, "output_tokens": 7}),
    ], sink)
    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path / "ws"))
    ctx = SessionContext(session_id=sid, workspace=ws, user_id="owner-1")
    with session_scope(ctx):
        out = subagents.run_role("pd-sweep", ["loop forever"],
                                 model_name="gemini-3.1-flash-lite", api_key=None)

    assert "error" in out["children"][0]
    meta = manager.get_session_metadata(sid, user_id="owner-1")
    calls = len(sink[0]["model"].calls)
    assert meta["input_tokens"] == 90 * calls
    assert meta["output_tokens"] == 7 * calls
    assert meta["total_cost"] > 0
