"""Codex runtime handler end-to-end against a FAKE SDK (Phase 2a/2b).

Drives CodexRuntimeHandler.run_turn with an injected fake Codex SDK, proving the
whole path without live creds: SDK-event translation -> shared presentation
contract frames -> transcript persistence -> external_thread_id (only on
success) -> registry cleanup wiring. The real beta-SDK surface is the only thing
these can't confirm (plans/codex-engine-reference.md §8).
"""
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
    def __init__(self, events, **kw):
        self._events = events
        self.logged_in = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def login_api_key(self, key):
        self.logged_in = True

    async def thread_start(self, **kw):
        return _FakeThread(self._events)

    async def thread_resume(self, ext_id, **kw):
        return _FakeThread(self._events, thread_id=ext_id)


def _sdk_factory_for(events):
    return lambda config=None: _FakeCodex(events)


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


def _handler(wiring, events, *, key="sk-test", account_home=None):
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
            enabled=True, sdk_factory=_sdk_factory_for(events),
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

@pytest.mark.asyncio
async def test_text_turn_streams_persists_and_records_external_id(wiring):
    events = [
        _ev("item/agentMessage/delta", delta="Hello "),
        _ev("item/agentMessage/delta", delta="world"),
        _usage_event(7, 3),
        _ev("turn/completed"),
    ]
    frames = []
    await _handler(wiring, events).run_turn(_ctx(wiring, frames))

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

@pytest.mark.asyncio
async def test_tool_call_turn_maps_and_persists(wiring):
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
    await _handler(wiring, events).run_turn(_ctx(wiring, frames))

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


# --- no key + no account => structured error, nothing persisted -------------

@pytest.mark.asyncio
async def test_no_key_no_account_emits_structured_error(wiring):
    frames = []
    await _handler(wiring, [], key=None).run_turn(_ctx(wiring, frames))
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
