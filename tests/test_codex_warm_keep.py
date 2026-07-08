"""TTFT warm-keep + pre-warm (plans/codex-ttft-remediation.md, 3A/3B).

Fake-SDK tests proving the lifecycle without live creds: a thread's worker
(app-server + SDK thread) is spawned once and reused across turns; pre-warm
starts it early and an early send coalesces onto the same spawn; tenant
isolation holds by construction (full-key lookup only); crashes/cancels retire
the worker honestly; idle timeout and the cap bound memory; thread delete
cleans up. The real beta-SDK surface is the only thing these can't confirm.
"""
import asyncio
import datetime
import time
import types

import pytest

from src.agents.codex.codex_engine import CodexEngine, CodexTurnError
from src.agents.codex.codex_runtime import CodexRuntimeHandler
from src.agents.codex.codex_store import SqliteCodexStore
from src.agents.codex.codex_warm import (
    STATE_COLD,
    STATE_READY,
    STATE_STARTING,
    STATE_UNAVAILABLE,
    CodexWorkerPool,
    worker_fingerprint,
)
from src.agents.runtime_registry import RuntimeTurnContext
from src.platform_engines.metadata_store import SqliteMetadataStore
from src.utils.session_manager import SessionManager


# --- fake SDK (mirrors test_codex_runtime.py) --------------------------------

def _ev(method, **payload):
    return types.SimpleNamespace(method=method, payload=types.SimpleNamespace(**payload))


def _events():
    return [
        _ev("item/agentMessage/delta", delta="hello"),
        _ev("turn/completed"),
    ]


class _FakeTurnHandle:
    def __init__(self, events, fail=False):
        self._events = events
        self._fail = fail

    async def stream(self):
        for e in self._events:
            yield e
        if self._fail:
            raise RuntimeError("SDK stream died")


class _FakeThread:
    def __init__(self, owner, thread_id="ext-1"):
        self.id = thread_id
        self.owner = owner
        self.turns = 0

    async def turn(self, message, **kw):
        self.turns += 1
        return _FakeTurnHandle(_events(), fail=self.owner.fail_next_stream)


class _FakeCodex:
    def __init__(self):
        self.entered = 0
        self.exited = 0
        self.fail_next_stream = False
        self.thread = _FakeThread(self)

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, *a):
        self.exited += 1
        return False

    async def login_api_key(self, key):
        pass

    async def thread_start(self, **kw):
        return self.thread

    async def thread_resume(self, ext_id, **kw):
        self.thread.id = ext_id
        return self.thread


class _CountingFactory:
    def __init__(self):
        self.instances = []

    def __call__(self, config=None):
        fake = _FakeCodex()
        self.instances.append(fake)
        return fake

    @property
    def spawns(self):
        return len(self.instances)


# --- wiring -------------------------------------------------------------------

@pytest.fixture
def wiring(tmp_path):
    db = str(tmp_path / "state.db")
    meta = SqliteMetadataStore(db)
    meta.init_schema()
    now = datetime.datetime.now()
    meta.upsert_session("s1", "alice", "S", "gpt-5.5", None, now)
    meta.create_thread("th1", "s1", "alice", "Codex chat", "gpt-5.5", now, runtime="codex")
    meta.create_thread("th2", "s1", "alice", "Codex chat 2", "gpt-5.5", now, runtime="codex")
    mgr = SessionManager(base_dir=str(tmp_path / "ws"), db_path=db, metadata_store=meta)
    store = SqliteCodexStore(db)
    store.init_schema()
    ws = tmp_path / "ws" / "s1"
    ws.mkdir(parents=True, exist_ok=True)
    return types.SimpleNamespace(mgr=mgr, store=store, workspace=str(ws),
                                 state_dir=str(tmp_path / "codex-state"))


def _handler(wiring, factory, pool):
    fake_key = types.SimpleNamespace(api_key="sk-test", model=None, source="byok")
    return CodexRuntimeHandler(
        codex_store=wiring.store,
        session_manager=wiring.mgr,
        llm_key_resolve=lambda uid, model: fake_key,
        account_home_for=lambda uid: None,
        system_prompt_loader=lambda: "system",
        default_model="gpt-5.5",
        normalize_model=lambda m: m,
        enabled=True,
        warm_pool=pool,
        engine_factory=lambda: CodexEngine(
            enabled=True, sdk_factory=factory, warm_pool=pool,
            state_dir=wiring.state_dir, local_sqlite_dir=wiring.state_dir),
    )


def _ctx(wiring, frames, thread_id="th1", message="hi"):
    async def send(f):
        frames.append(f)
    return RuntimeTurnContext(
        message=message, turn_id="t1", thread_id=thread_id, session_id="s1",
        workspace=wiring.workspace, send=send, user_id="alice",
        thread_row={"runtime": "codex", "model": "gpt-5.5"}, tier=None, auth_token="tok")


def _fp(**over):
    base = dict(api_key="k", account_home=None, sandbox="read-only", system_prompt="p")
    base.update(over)
    return worker_fingerprint(**base)


# --- 3A: warm-keep across turns ------------------------------------------------

def test_second_turn_reuses_the_warm_worker(wiring):
    """The headline: turn 2 must NOT rebuild the app-server/MCP/thread."""
    factory = _CountingFactory()
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    handler = _handler(wiring, factory, pool)

    async def main():
        f1, f2 = [], []
        await handler.run_turn(_ctx(wiring, f1))
        await handler.run_turn(_ctx(wiring, f2, message="again"))
        return f1, f2

    f1, f2 = asyncio.run(main())
    assert f1[-1]["type"] == "done" and f2[-1]["type"] == "done"
    assert factory.spawns == 1, "the worker must be spawned once and reused"
    assert factory.instances[0].thread.turns == 2
    assert factory.instances[0].exited == 0, "warm worker must stay alive between turns"


def test_transcripts_identical_warm_vs_cold(wiring):
    """Behavior/results identical (constraint 7): the persisted transcript of a
    warm second turn matches what a cold turn would persist."""
    factory = _CountingFactory()
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    handler = _handler(wiring, factory, pool)

    async def main():
        await handler.run_turn(_ctx(wiring, []))
        await handler.run_turn(_ctx(wiring, [], message="again"))

    asyncio.run(main())
    msgs = wiring.store.list_messages("th1")
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[1]["content"] == "hello" and msgs[3]["content"] == "hello"
    assert wiring.store.get_external_thread_id("th1") == "ext-1"


def test_crashed_stream_retires_worker_and_next_turn_respawns(wiring):
    factory = _CountingFactory()
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    handler = _handler(wiring, factory, pool)

    async def main():
        f1, f2, f3 = [], [], []
        await handler.run_turn(_ctx(wiring, f1))
        factory.instances[0].fail_next_stream = True
        await handler.run_turn(_ctx(wiring, f2, message="boom"))
        await handler.run_turn(_ctx(wiring, f3, message="recover"))
        return f1, f2, f3

    f1, f2, f3 = asyncio.run(main())
    assert f2[-1]["type"] == "error"  # the failed turn reports honestly
    assert factory.instances[0].exited == 1, "crashed worker must be closed"
    assert factory.spawns == 2, "next turn must cold-start a fresh worker"
    assert f3[-1]["type"] == "done"


def test_engine_cancellation_retires_worker(wiring):
    """A user stop (cancellation) leaves the SDK stream state unknown — the
    worker is retired, never reused in doubt."""
    factory = _CountingFactory()
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)

    async def main():
        engine = CodexEngine(enabled=True, sdk_factory=factory, warm_pool=pool,
                             state_dir=wiring.state_dir, local_sqlite_dir=wiring.state_dir)
        from src.agents.codex.codex_engine import CodexTurn

        turn = CodexTurn(session_id="s1", thread_id="th1", message="hi",
                         workspace=wiring.workspace, user_id="alice",
                         model_name="gpt-5.5", api_key="k")

        async def drive():
            async for _ in engine.stream_turn(turn):
                raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await drive()

    asyncio.run(main())
    assert factory.instances[0].exited == 1
    assert pool.state_for(("s1", "th1", "alice")) == STATE_COLD


# --- F-TTFT-1: resume-failure must accept the fresh external id, not wedge ------

class _ResumeFailsCodex:
    """A returning user on a NEW instance: the SDK rollout for the persisted
    external id is gone, so ``thread_resume`` raises and spawn falls back to
    ``thread_start`` — which mints a DIFFERENT external id."""

    def __init__(self, start_id="ext-2"):
        self.entered = 0
        self.exited = 0
        self.fail_next_stream = False
        self.resume_calls = 0
        self.start_calls = 0
        self._start_id = start_id
        self.thread = _FakeThread(self, thread_id=start_id)

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, *a):
        self.exited += 1
        return False

    async def login_api_key(self, key):
        pass

    async def thread_start(self, **kw):
        self.start_calls += 1
        self.thread.id = self._start_id
        return self.thread

    async def thread_resume(self, ext_id, **kw):
        self.resume_calls += 1
        raise RuntimeError(f"rollout for {ext_id} lived on a now-dead instance")


class _ResumeFailsFactory:
    def __init__(self, start_id="ext-2"):
        self.instances = []
        self._start_id = start_id

    def __call__(self, config=None):
        fake = _ResumeFailsCodex(start_id=self._start_id)
        self.instances.append(fake)
        return fake

    @property
    def spawns(self):
        return len(self.instances)


def test_resume_failure_accepts_fresh_external_id_and_does_not_wedge(wiring):
    """F-TTFT-1: persisted external id E1 whose rollout is gone → resume raises
    → thread_start returns a NEW id E2. The pool must ACCEPT the fresh worker
    (E2 is authoritative), NOT reject it against E1. Prove the turn completes,
    E2 is persisted, there is exactly one spawn (no respawn storm), and the
    next turn does not wedge.

    Pre-fix this wedged: the post-spawn revalidation applied expected_external
    to the fresh worker (E2 != E1), looped 4× → RuntimeError → turn failed →
    E2 never persisted → every retry repeated the failure."""
    wiring.store.set_external_thread_id("th1", "ext-1")  # created on a dead instance

    factory = _ResumeFailsFactory(start_id="ext-2")
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    handler = _handler(wiring, factory, pool)

    async def main():
        f1, f2 = [], []
        await handler.run_turn(_ctx(wiring, f1))
        await handler.run_turn(_ctx(wiring, f2, message="again"))
        return f1, f2

    f1, f2 = asyncio.run(main())
    # (a) the turn COMPLETES — no RuntimeError / churn mapped to an error frame
    assert f1[-1]["type"] == "done", f1[-1]
    # (b) the fresh external id is persisted
    assert wiring.store.get_external_thread_id("th1") == "ext-2"
    # (d) exactly one spawn: one resume attempt, one thread_start fallback
    assert factory.spawns == 1, "no respawn storm"
    assert factory.instances[0].resume_calls == 1
    assert factory.instances[0].start_calls == 1
    # (c) the next turn does NOT wedge — it reuses the warm worker and completes
    assert f2[-1]["type"] == "done", f2[-1]
    assert factory.spawns == 1, "turn 2 must reuse the warm worker"


# --- tenant isolation (the must-pass test) --------------------------------------

def test_workers_never_shared_across_sessions_threads_or_owners(wiring):
    """Isolation by construction: the pool key is the FULL (session, thread,
    user) triple — any difference yields a different worker, and a worker
    handed back always carries exactly its own key's spawn identity."""
    pool = CodexWorkerPool(max_workers=10, idle_sec=60)

    def spawn_for(tag):
        async def spawn():
            cm = _FakeCodex()
            client = await cm.__aenter__()
            client.tag = tag  # who this worker was spawned for
            return {"cm": cm, "client": client, "thread": client.thread,
                    "external_thread_id": f"ext-{tag}"}
        return spawn

    keys = [
        ("sess-a", "th-1", "alice"),
        ("sess-a", "th-1", "mallory"),   # same session+thread, DIFFERENT owner
        ("sess-a", "th-2", "alice"),     # different thread
        ("sess-b", "th-1", "alice"),     # different session
    ]

    async def main():
        workers = {}
        for key in keys:
            tag = "|".join(key)
            workers[key] = await pool.acquire(key, _fp(), spawn_for(tag))
        return workers

    workers = asyncio.run(main())
    assert len({id(w) for w in workers.values()}) == len(keys), "no sharing, ever"
    for key, w in workers.items():
        assert w.client.tag == "|".join(key), (
            f"worker for {key} carries a different tenant's spawn identity"
        )
        assert w.key == key


def test_fingerprint_change_respawns_instead_of_reusing(wiring):
    """Changed auth material (e.g. a new BYOK key) must never reuse a worker
    spawned with the old credentials."""
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    spawned = []

    def spawn_with(tag):
        async def spawn():
            cm = _FakeCodex()
            client = await cm.__aenter__()
            spawned.append((tag, cm))
            return {"cm": cm, "client": client, "thread": client.thread,
                    "external_thread_id": "ext-1"}
        return spawn

    async def main():
        key = ("s1", "th1", "alice")
        w1 = await pool.acquire(key, _fp(api_key="old"), spawn_with("old"))
        w2 = await pool.acquire(key, _fp(api_key="new"), spawn_with("new"))
        return w1, w2

    w1, w2 = asyncio.run(main())
    assert w1 is not w2
    assert [t for t, _ in spawned] == ["old", "new"]
    assert spawned[0][1].exited == 1, "the stale-credential worker must be closed"


# --- 3B: pre-warm + coalescing ---------------------------------------------------

def test_prewarm_then_first_send_uses_the_same_single_spawn(wiring):
    factory = _CountingFactory()
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    handler = _handler(wiring, factory, pool)

    async def main():
        state = await handler.prewarm(
            session_id="s1", thread_id="th1", user_id="alice",
            workspace=wiring.workspace, thread_row={"runtime": "codex", "model": "gpt-5.5"})
        assert state in (STATE_STARTING, STATE_READY)
        # The user sends immediately — before the spawn necessarily finished.
        frames = []
        await handler.run_turn(_ctx(wiring, frames))
        return frames

    frames = asyncio.run(main())
    assert frames[-1]["type"] == "done"
    assert factory.spawns == 1, "an early send must coalesce onto the pre-warm spawn"


def test_prewarm_without_key_is_unavailable_and_spawns_nothing(wiring):
    factory = _CountingFactory()
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    handler = CodexRuntimeHandler(
        codex_store=wiring.store, session_manager=wiring.mgr,
        llm_key_resolve=lambda uid, model: (_ for _ in ()).throw(RuntimeError("no key")),
        account_home_for=lambda uid: None,
        system_prompt_loader=lambda: "system", default_model="gpt-5.5",
        normalize_model=lambda m: m, enabled=True, warm_pool=pool,
        engine_factory=lambda: CodexEngine(
            enabled=True, sdk_factory=factory, warm_pool=pool,
            state_dir=wiring.state_dir, local_sqlite_dir=wiring.state_dir))

    async def main():
        return await handler.prewarm(
            session_id="s1", thread_id="th1", user_id="alice",
            workspace=wiring.workspace, thread_row={"runtime": "codex"})

    assert asyncio.run(main()) == STATE_UNAVAILABLE
    assert factory.spawns == 0


def test_worker_state_reports_honestly(wiring):
    factory = _CountingFactory()
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    handler = _handler(wiring, factory, pool)

    async def main():
        cold = handler.worker_state(session_id="s1", thread_id="th1", user_id="alice")
        await handler.prewarm(
            session_id="s1", thread_id="th1", user_id="alice",
            workspace=wiring.workspace, thread_row={"runtime": "codex"})
        await asyncio.sleep(0)  # let the spawn task run to completion
        await asyncio.sleep(0)
        ready = handler.worker_state(session_id="s1", thread_id="th1", user_id="alice")
        return cold, ready

    cold, ready = asyncio.run(main())
    assert cold == STATE_COLD
    assert ready == STATE_READY


# --- lifecycle bounds --------------------------------------------------------------

def test_cap_evicts_least_recently_used_idle_worker(wiring):
    pool = CodexWorkerPool(max_workers=1, idle_sec=60)
    cms = []

    def spawn():
        async def _s():
            cm = _FakeCodex()
            client = await cm.__aenter__()
            cms.append(cm)
            return {"cm": cm, "client": client, "thread": client.thread,
                    "external_thread_id": "e"}
        return _s

    async def main():
        await pool.acquire(("s1", "th1", "u"), _fp(), spawn())
        await pool.acquire(("s1", "th2", "u"), _fp(), spawn())

    asyncio.run(main())
    assert cms[0].exited == 1, "over-cap: LRU idle worker must be closed"
    assert cms[1].exited == 0


def test_idle_timeout_reaps_workers(wiring):
    pool = CodexWorkerPool(max_workers=3, idle_sec=0.1)
    cms = []

    async def spawn():
        cm = _FakeCodex()
        client = await cm.__aenter__()
        cms.append(cm)
        return {"cm": cm, "client": client, "thread": client.thread,
                "external_thread_id": "e"}

    async def main():
        await pool.acquire(("s1", "th1", "u"), _fp(), spawn)
        deadline = time.monotonic() + 3
        while pool.state_for(("s1", "th1", "u")) != STATE_COLD and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        return pool.state_for(("s1", "th1", "u"))

    assert asyncio.run(main()) == STATE_COLD
    assert cms[0].exited == 1


def test_thread_delete_closes_worker(wiring):
    factory = _CountingFactory()
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    handler = _handler(wiring, factory, pool)

    async def main():
        await handler.run_turn(_ctx(wiring, []))
        handler.on_thread_deleted("th1")
        for _ in range(4):  # the close is scheduled on the loop
            await asyncio.sleep(0)
        return pool.state_for(("s1", "th1", "alice"))

    state = asyncio.run(main())
    assert state == STATE_COLD
    assert factory.instances[0].exited == 1
