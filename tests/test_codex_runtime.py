"""Codex runtime handler end-to-end against a FAKE SDK (Phase 2a/2b).

Drives CodexRuntimeHandler.run_turn with an injected fake Codex SDK, proving the
whole path without live creds: SDK-event translation -> shared presentation
contract frames -> transcript persistence -> external_thread_id (only on
success) -> registry cleanup wiring. The real beta-SDK surface is the only thing
these can't confirm (plans/codex-engine-reference.md §8).
"""
import asyncio
import datetime
import types

import pytest

from src.agents import runtime_registry as rr
from src.agents.codex.codex_engine import CodexEngine
from src.agents.codex.codex_runtime import CodexRuntimeHandler
from src.agents.codex.codex_store import SqliteCodexStore
from src.agents.codex.register import register_codex_runtime
from src.agents.runtime_registry import RuntimeTurnContext
from src.platform_engines.metadata_store import SqliteMetadataStore
from src.utils.session_manager import SessionManager


# --- a fake openai_codex SDK ------------------------------------------------

def _ev(method, **payload):
    return types.SimpleNamespace(method=method, payload=types.SimpleNamespace(**payload))


class _FakeTurnHandle:
    def __init__(self, events):
        self._events = events

    async def stream(self):
        for e in self._events:
            yield e


class _FakeThread:
    def __init__(self, events, thread_id="ext-thread-1"):
        self.id = thread_id
        self._events = events

    async def turn(self, message, **kw):
        return _FakeTurnHandle(self._events)


class _FakeCodex:
    def __init__(self, events, resume_fails=False, **kw):
        self._events = events
        self.logged_in = False
        self.resume_fails = resume_fails
        self.thread_start_calls = []  # each entry is the kwargs dict

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def login_api_key(self, key):
        self.logged_in = True

    async def thread_start(self, **kw):
        self.thread_start_calls.append(kw)
        return _FakeThread(self._events)

    async def thread_resume(self, ext_id, **kw):
        if self.resume_fails:
            raise RuntimeError("no rollout for this thread on this instance")
        return _FakeThread(self._events, thread_id=ext_id)


def _sdk_factory_for(events):
    return lambda config=None: _FakeCodex(events)


def _sdk_factory_returning(fake_codex):
    """Always hand back the SAME fake Codex instance, so a test can inspect
    calls made to it (e.g. thread_start_calls) after run_turn completes."""
    return lambda config=None: fake_codex


# token-usage payload shaped like the SDK's nested object
def _usage_event(inp, out):
    last = types.SimpleNamespace(input_tokens=inp, output_tokens=out)
    return types.SimpleNamespace(
        method="thread/tokenUsage/updated",
        payload=types.SimpleNamespace(token_usage=types.SimpleNamespace(last=last)),
    )


# --- fixtures ---------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_registry():
    rr.clear_extensions()
    yield
    rr.clear_extensions()


@pytest.fixture
def wiring(tmp_path):
    db = str(tmp_path / "state.db")
    meta = SqliteMetadataStore(db)
    meta.init_schema()
    now = datetime.datetime.now()
    meta.upsert_session("s1", "alice", "S", "gpt-5.5", None, now)
    meta.create_thread("th1", "s1", "alice", "Codex chat", "gpt-5.5", now, runtime="codex")
    mgr = SessionManager(base_dir=str(tmp_path / "ws"), db_path=db, metadata_store=meta)
    store = SqliteCodexStore(db)
    store.init_schema()
    ws = tmp_path / "ws" / "s1"
    ws.mkdir(parents=True, exist_ok=True)
    return types.SimpleNamespace(db=db, meta=meta, mgr=mgr, store=store, workspace=str(ws),
                                 state_dir=str(tmp_path / "codex-state"))


def _handler(wiring, events, *, key="sk-test", account_home=None, sdk_factory=None):
    fake_key = types.SimpleNamespace(api_key=key, model=None, source="byok")
    return CodexRuntimeHandler(
        codex_store=wiring.store,
        session_manager=wiring.mgr,
        llm_key_resolve=lambda uid, model: fake_key,
        account_home_for=lambda uid: account_home,
        system_prompt_loader=lambda: "system",
        default_model="gpt-5.5",
        normalize_model=lambda m: m,
        enabled=True,
        engine_factory=lambda: CodexEngine(
            enabled=True, sdk_factory=sdk_factory or _sdk_factory_for(events),
            state_dir=wiring.state_dir, local_sqlite_dir=wiring.state_dir),
    )


def _ctx(wiring, frames):
    async def send(f):
        frames.append(f)
    return RuntimeTurnContext(
        message="hi codex", turn_id="t1", thread_id="th1", session_id="s1",
        workspace=wiring.workspace, send=send, user_id="alice",
        thread_row={"runtime": "codex", "model": "gpt-5.5"}, tier=None, auth_token="tok")


# --- a plain text turn ------------------------------------------------------

def test_text_turn_streams_persists_and_records_external_id(wiring):
    events = [
        _ev("item/agentMessage/delta", delta="Hello "),
        _ev("item/agentMessage/delta", delta="world"),
        _usage_event(7, 3),
        _ev("turn/completed"),
    ]
    frames = []
    asyncio.run(_handler(wiring, events).run_turn(_ctx(wiring, frames)))

    types_seen = [f["type"] for f in frames]
    assert types_seen[0] == "start"
    assert "text_delta" in types_seen
    assert types_seen[-1] == "done"
    # cumulative delta then authoritative text
    assert frames[-2]["type"] == "text" and frames[-2]["content"] == "Hello world"
    assert frames[-1]["tokens"] == {"input": 7, "output": 3}

    # transcript persisted (user + assistant), external id recorded on success
    msgs = wiring.store.list_messages("th1")
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Hello world"
    assert wiring.store.get_external_thread_id("th1") == "ext-thread-1"


# --- a tool-call turn -------------------------------------------------------

def test_tool_call_turn_maps_and_persists(wiring):
    tool_item = types.SimpleNamespace(type="mcptoolcall", id="c1", tool="read_file",
                                      arguments={"path": "a.v"})
    done_item = types.SimpleNamespace(type="mcptoolcall", id="c1",
                                      status="completed",
                                      result=types.SimpleNamespace(content="module a; endmodule"),
                                      error=None)
    events = [
        _ev("item/started", item=tool_item),
        _ev("item/completed", item=done_item),
        _ev("item/agentMessage/delta", delta="done reading"),
        _usage_event(4, 2),
        _ev("turn/completed"),
    ]
    frames = []
    asyncio.run(_handler(wiring, events).run_turn(_ctx(wiring, frames)))

    types_seen = [f["type"] for f in frames]
    assert "tool_call" in types_seen and "tool_result" in types_seen
    tc = next(f for f in frames if f["type"] == "tool_call")
    assert tc["tool"]["name"] == "read_file"
    tr = next(f for f in frames if f["type"] == "tool_result")
    assert tr["status"] == "success" and "module a" in tr["content"]

    # assistant transcript carries the tool metadata
    assistant = wiring.store.list_messages("th1")[-1]
    assert assistant["tool_metadata"]["tool_calls"][0]["name"] == "read_file"
    assert assistant["tool_metadata"]["tool_results"][0]["tool_call_id"] == "c1"


# --- server-side timing instrumentation (Cloud Run observability) -----------

def test_tool_call_turn_logs_timing_lines(wiring, capsys):
    """[CODEX-TIMING] lines are the only server-side signal for how long each
    tool call and the overall turn take (nothing else is logged/printed from
    run_turn today). This asserts the tag, tool name, and thread/turn id are
    present — loose on exact timing values, strict on presence/shape."""
    tool_item = types.SimpleNamespace(type="mcptoolcall", id="c1", tool="get_cts_summary",
                                      arguments={})
    done_item = types.SimpleNamespace(type="mcptoolcall", id="c1",
                                      status="completed",
                                      result=types.SimpleNamespace(content="cts ok"),
                                      error=None)
    events = [
        _ev("item/started", item=tool_item),
        _ev("item/completed", item=done_item),
        _ev("item/agentMessage/delta", delta="done"),
        _usage_event(4, 2),
        _ev("turn/completed"),
    ]
    frames = []
    asyncio.run(_handler(wiring, events).run_turn(_ctx(wiring, frames)))

    err = capsys.readouterr().err
    all_lines = [l for l in err.splitlines() if l.startswith("[CODEX-TIMING]")]
    assert all_lines, "expected at least one [CODEX-TIMING] line"
    # codex_engine.py's optional setup-timing lines carry thread= but no per-
    # turn turn= (CodexTurn has no turn_id) — the run_turn-level lines below
    # are the primary, must-have instrumentation and carry both.
    lines = [l for l in all_lines if "turn=" in l]

    # thread/turn id present on every run_turn-level line (multiple
    # concurrent/sequential turns in a shared log stream must be
    # distinguishable).
    assert lines, "expected at least one run_turn-level [CODEX-TIMING] line"
    assert all("thread=th1" in l and "turn=t1" in l for l in lines)

    # turn_start at the top, turn_end (with a real elapsed=...s) at the end.
    assert any("event=turn_start" in l for l in lines)
    assert sum("event=first_model_response" in l for l in lines) == 1
    assert sum("event=first_token" in l for l in lines) == 1
    assert any("after_setup=" in l for l in lines if "event=first_token" in l)
    end_lines = [l for l in lines if "event=turn_end" in l]
    assert end_lines and "status=completed" in end_lines[0]
    assert "elapsed=" in end_lines[0] and end_lines[0].rstrip().endswith("s")

    # the tool_call_start / tool_result pair for the actual tool, matched by
    # call_id, with a numeric elapsed duration on the result line.
    start_lines = [l for l in lines if "event=tool_call_start" in l]
    assert start_lines and "tool=get_cts_summary" in start_lines[0] and "call_id=c1" in start_lines[0]
    result_lines = [l for l in lines if "tool=get_cts_summary" in l and "call_id=c1" in l and "status=" in l]
    assert result_lines
    assert "elapsed=" in result_lines[0] and result_lines[0].rstrip().endswith("s")


# --- resume-failure fallback replays prior history into base_instructions ---

def test_resume_failure_seeds_fresh_thread_with_prior_history(wiring):
    # Simulate a thread that already had a turn (external_thread_id + prior
    # transcript), but whose Codex-side rollout is gone on this instance (e.g.
    # a fresh Cloud Run cold start after scale-to-zero) — thread_resume raises.
    wiring.store.append_message("th1", "user", "let's build a fifo")
    wiring.store.append_message("th1", "assistant", "Sure, I'll scaffold fifo.sv")
    wiring.store.set_external_thread_id("th1", "ext-thread-1")

    events = [_ev("item/agentMessage/delta", delta="back again"), _ev("turn/completed")]
    fake_codex = _FakeCodex(events, resume_fails=True)
    frames = []
    asyncio.run(_handler(wiring, events, sdk_factory=_sdk_factory_returning(fake_codex))
                .run_turn(_ctx(wiring, frames)))

    # The turn still completes fine via the fresh thread_start fallback.
    assert frames[-1]["type"] == "done"
    assert len(fake_codex.thread_start_calls) == 1
    base = fake_codex.thread_start_calls[0]["base_instructions"]
    assert "Prior conversation" in base
    assert "let's build a fifo" in base
    assert "Sure, I'll scaffold fifo.sv" in base
    # The original system prompt is still present, appended after the replay.
    assert "system" in base

    # The CURRENT turn's own user message (persisted before stream_turn runs)
    # must not leak into the replayed history block (it's passed separately as
    # the turn message, not as history).
    assert "hi codex" not in base


def test_resume_failure_without_prior_history_is_unchanged(wiring):
    # A thread with an external_thread_id but no transcript rows yet (edge
    # case) — the fallback must behave exactly like today: base_instructions
    # is just the original system prompt, no history block added.
    wiring.store.set_external_thread_id("th1", "ext-thread-1")

    events = [_ev("item/agentMessage/delta", delta="hi"), _ev("turn/completed")]
    fake_codex = _FakeCodex(events, resume_fails=True)
    frames = []
    asyncio.run(_handler(wiring, events, sdk_factory=_sdk_factory_returning(fake_codex))
                .run_turn(_ctx(wiring, frames)))

    assert len(fake_codex.thread_start_calls) == 1
    base = fake_codex.thread_start_calls[0]["base_instructions"]
    assert "Prior conversation" not in base
    assert base.startswith("system")


def test_successful_resume_never_calls_thread_start(wiring):
    # Happy path: resume succeeds, so the fallback (and any history replay)
    # must never trigger, and no thread_start call is made at all.
    wiring.store.append_message("th1", "user", "earlier turn")
    wiring.store.append_message("th1", "assistant", "earlier reply")
    wiring.store.set_external_thread_id("th1", "ext-thread-1")

    events = [_ev("item/agentMessage/delta", delta="hi"), _ev("turn/completed")]
    fake_codex = _FakeCodex(events, resume_fails=False)
    frames = []
    asyncio.run(_handler(wiring, events, sdk_factory=_sdk_factory_returning(fake_codex))
                .run_turn(_ctx(wiring, frames)))

    assert fake_codex.thread_start_calls == []


# --- no key + no account => structured error, nothing persisted -------------

def test_no_key_no_account_emits_structured_error(wiring):
    frames = []
    asyncio.run(_handler(wiring, [], key=None).run_turn(_ctx(wiring, frames)))
    assert frames == [] or frames[-1]["type"] == "error"
    err = [f for f in frames if f["type"] == "error"]
    assert err and err[0].get("code") == "no_key"
    # a failed turn must not record an external id
    assert wiring.store.get_external_thread_id("th1") is None


# --- registration + cleanup hook (removability) -----------------------------

def test_register_wires_cleanup_hook(tmp_path):
    db = str(tmp_path / "state.db")
    meta = SqliteMetadataStore(db)
    meta.init_schema()
    mgr = SessionManager(base_dir=str(tmp_path / "ws"), db_path=db, metadata_store=meta)
    key = types.SimpleNamespace(api_key="sk", model=None, source="byok")

    store = register_codex_runtime(
        db_path=db, session_manager=mgr,
        llm_key_resolve=lambda uid, model: key,
        account_home_for=lambda uid: None,
        system_prompt_loader=lambda: "s",
        default_model="gpt-5.5", normalize_model=lambda m: m, enabled=True)

    assert rr.is_registered("codex")
    store.append_message("thX", "user", "hi")
    store.set_external_thread_id("thX", "ext")
    # Deleting a thread notifies the registry, which fires codex's cleanup hook.
    rr.notify_thread_deleted("thX", "alice")
    assert store.list_messages("thX") == []
    assert store.get_external_thread_id("thX") is None
