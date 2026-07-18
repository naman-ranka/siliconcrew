"""Account-auth model gate (followups #1).

Under a connected ChatGPT **account** (no BYOK key), the Codex model picker was
decorative: the engine omitted the model entirely, so any picked id silently
fell back to the account default. It couldn't just pass the id either — an id
the account rejects returns 0 tokens. The honest fix queries the SDK's own
``model/list`` for this account and passes the picked id ONLY when the account
reports it as valid/non-hidden; otherwise it omits (safe default). BYOK keeps
passing the id verbatim.

These drive CodexEngine against a fake SDK whose ``models()`` returns a known
set, and assert which model reaches ``thread.turn``. No live creds; the real
beta-SDK ``model/list`` surface is the only thing they can't confirm.
"""
import asyncio
import sys
import types

from src.agents.codex.codex_engine import CodexEngine, CodexTurn, discover_codex_models
from src.agents.codex.codex_warm import CodexWorkerPool


# --- fake SDK ----------------------------------------------------------------

def _ev(method, **payload):
    return types.SimpleNamespace(method=method, payload=types.SimpleNamespace(**payload))


def _events():
    return [
        _ev("item/agentMessage/delta", delta="hello"),
        _ev("turn/completed"),
    ]


def _model(mid, hidden=False):
    return types.SimpleNamespace(id=mid, hidden=hidden)


class _FakeTurnHandle:
    def __init__(self, events):
        self._events = events

    async def stream(self):
        for e in self._events:
            yield e


class _FakeThread:
    def __init__(self, owner, thread_id="ext-1"):
        self.id = thread_id
        self.owner = owner

    async def turn(self, message, **kw):
        self.owner.turn_inputs.append(message)
        self.owner.turn_kwargs.append(kw)
        return _FakeTurnHandle(_events())


class _FakeCodex:
    def __init__(self, *, models=None, models_raises=False):
        self._models = models
        self._models_raises = models_raises
        self.models_calls = 0
        self.turn_inputs = []           # values passed as the SDK RunInput
        self.turn_kwargs = []          # kwargs passed to thread.turn()
        self.thread_start_kwargs = []  # kwargs passed to thread_start()
        self.thread = _FakeThread(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def login_api_key(self, key):
        pass

    async def models(self):
        self.models_calls += 1
        if self._models_raises:
            raise RuntimeError("model/list RPC failed")
        return list(self._models or [])

    async def thread_start(self, **kw):
        self.thread_start_kwargs.append(kw)
        return self.thread

    async def thread_resume(self, ext_id, **kw):
        self.thread.id = ext_id
        return self.thread


class _Factory:
    def __init__(self, *, models=None, models_raises=False):
        self.instances = []
        self._models = models
        self._models_raises = models_raises

    def __call__(self, config=None):
        fake = _FakeCodex(models=self._models, models_raises=self._models_raises)
        self.instances.append(fake)
        return fake

    @property
    def spawns(self):
        return len(self.instances)


# --- helpers -----------------------------------------------------------------

# The exploration's live account listed exactly these non-hidden ids; note
# gpt-5.3-codex (CODEX_DEFAULT_MODEL) is NOT among them — the exact case that
# breaks a naive "pass it if it's in CODEX_CATALOG" rule.
_ACCOUNT_MODELS = [_model("gpt-5.5"), _model("gpt-5.4"), _model("gpt-5.4-mini")]


def _engine(factory, tmp_path, pool=None):
    return CodexEngine(
        enabled=True, sdk_factory=factory, warm_pool=pool,
        state_dir=str(tmp_path / "state"), local_sqlite_dir=str(tmp_path / "sqlite"))


def _turn(model_name, *, api_key=None, workspace="/tmp/ws", reasoning_effort=None, images=()):
    return CodexTurn(
        session_id="s1", thread_id="th1", message="hi", workspace=workspace,
        user_id="alice", model_name=model_name, api_key=api_key,
        reasoning_effort=reasoning_effort, images=images)


def _run_turn(engine, turn):
    async def main():
        events = []
        async for ev in engine.stream_turn(turn):
            events.append(ev)
        return events
    return asyncio.run(main())


# --- (a) account auth passes a valid picked id (FAILS on pre-fix code) --------

def test_account_auth_passes_valid_picked_id(tmp_path):
    """The headline fix: under account auth, a picked id the account reports as
    valid reaches the SDK. Pre-fix, effective_model was always None under
    account auth, so this model kwarg was never passed — this asserts the new
    behavior and FAILS on the old code."""
    factory = _Factory(models=_ACCOUNT_MODELS)
    engine = _engine(factory, tmp_path)
    events = _run_turn(engine, _turn("gpt-5.4"))
    assert events[-1].type == "done"
    fake = factory.instances[0]
    assert fake.turn_kwargs[-1].get("model") == "gpt-5.4"
    assert fake.thread_start_kwargs[-1].get("model") == "gpt-5.4"
    assert fake.models_calls == 1


# --- (b) account auth OMITS an invalid picked id (no 0-token trap) ------------

def test_account_auth_omits_invalid_picked_id(tmp_path):
    """gpt-5.3-codex is CODEX_DEFAULT_MODEL but NOT in the account list — it must
    be omitted (account default), never passed (which would 0-token the turn)."""
    factory = _Factory(models=_ACCOUNT_MODELS)
    engine = _engine(factory, tmp_path)
    events = _run_turn(engine, _turn("gpt-5.3-codex"))
    assert events[-1].type == "done"
    assert "model" not in factory.instances[0].turn_kwargs[-1]


def test_account_auth_omits_hidden_model(tmp_path):
    """A hidden/internal id (e.g. codex-auto-review) is not user-selectable —
    even if picked it must be omitted, not passed."""
    factory = _Factory(models=[_model("gpt-5.5"), _model("codex-auto-review", hidden=True)])
    engine = _engine(factory, tmp_path)
    _run_turn(engine, _turn("codex-auto-review"))
    assert "model" not in factory.instances[0].turn_kwargs[-1]


# --- (c) a models() failure omits safely, never breaks the turn --------------

def test_account_auth_models_failure_omits_safely(tmp_path):
    factory = _Factory(models_raises=True)
    engine = _engine(factory, tmp_path)
    events = _run_turn(engine, _turn("gpt-5.4"))
    assert events[-1].type == "done"  # honest degradation, not a failed turn
    assert "model" not in factory.instances[0].turn_kwargs[-1]


def test_account_auth_empty_model_list_omits(tmp_path):
    factory = _Factory(models=[])
    engine = _engine(factory, tmp_path)
    _run_turn(engine, _turn("gpt-5.4"))
    assert "model" not in factory.instances[0].turn_kwargs[-1]


# --- (d) BYOK key auth passes the model unchanged (no model/list query) -------

def test_byok_passes_model_unchanged(tmp_path):
    """With a BYOK key the picked id passes verbatim — even an id absent from any
    account list — and model/list is never queried (nothing to gate against)."""
    factory = _Factory(models=[_model("gpt-5.5")])
    engine = _engine(factory, tmp_path)
    _run_turn(engine, _turn("gpt-5.3-codex", api_key="sk-byok"))
    fake = factory.instances[0]
    assert fake.turn_kwargs[-1].get("model") == "gpt-5.3-codex"
    assert fake.models_calls == 0


def test_turn_passes_reasoning_effort_and_multimodal_input(tmp_path):
    """Current SDK controls belong on Thread.turn, and image attachments use
    the SDK's structured RunInput rather than being embedded in prompt text."""
    factory = _Factory()
    engine = _engine(factory, tmp_path)
    _run_turn(engine, _turn(
        "gpt-5.6-sol", api_key="sk-byok", reasoning_effort="high",
        images=("data:image/png;base64,aA==",),
    ))
    fake = factory.instances[0]
    assert fake.turn_kwargs[-1]["effort"] == "high"
    assert fake.turn_kwargs[-1]["model"] == "gpt-5.6-sol"
    assert fake.turn_inputs[-1] == [
        {"type": "text", "text": "hi"},
        {"type": "image", "url": "data:image/png;base64,aA=="},
    ]


def test_current_sdk_notifications_are_preserved_for_the_ui(tmp_path):
    events = [
        _ev("turn/diff/updated", diff="@@ -1 +1 @@"),
        _ev("thread/compacted", thread_id="ext-1", turn_id="turn-1"),
        _ev(
            "model/rerouted", from_model="gpt-5.6-sol", to_model="gpt-5.6-terra",
            reason=types.SimpleNamespace(root="highRiskCyberActivity"),
        ),
        _ev("turn/completed"),
    ]
    handle = _FakeTurnHandle(events)
    engine = _engine(_Factory(), tmp_path)

    async def collect():
        return [event async for event in engine._stream_sdk_events(handle)]

    translated = asyncio.run(collect())
    assert [event.type for event in translated] == [
        "diff", "compaction", "model_rerouted", "done",
    ]
    assert translated[2].metadata == {
        "from_model": "gpt-5.6-sol",
        "to_model": "gpt-5.6-terra",
        "reason": "highRiskCyberActivity",
    }


def test_model_discovery_maps_sdk_capabilities(monkeypatch, tmp_path):
    class DiscoveryClient:
        logged_in = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def login_api_key(self, key):
            self.logged_in = key

        async def models(self):
            effort = types.SimpleNamespace(reasoning_effort="high", description="Deep")
            model = types.SimpleNamespace(
                model="gpt-5.6-sol", id="gpt-5.6-sol", display_name="GPT-5.6 Sol",
                description="Flagship", hidden=False, is_default=True,
                default_reasoning_effort="high", supported_reasoning_efforts=[effort],
                input_modalities=["text", "image"], upgrade=None,
            )
            hidden = types.SimpleNamespace(
                model="internal", id="internal", display_name="Internal",
                description="", hidden=True, is_default=False,
                default_reasoning_effort="medium", supported_reasoning_efforts=[],
                input_modalities=["text"], upgrade=None,
            )
            return types.SimpleNamespace(data=[model, hidden])

    client = DiscoveryClient()
    fake_module = types.SimpleNamespace(
        CodexConfig=lambda **kwargs: kwargs,
        AsyncCodex=lambda config=None: client,
    )
    monkeypatch.setitem(sys.modules, "openai_codex", fake_module)
    catalog = asyncio.run(discover_codex_models(
        api_key="sk-test", account_home=str(tmp_path / "home"),
        sqlite_home=str(tmp_path / "sqlite"),
    ))

    assert client.logged_in == "sk-test"
    assert catalog == [{
        "id": "gpt-5.6-sol", "label": "GPT-5.6 Sol", "provider": "openai",
        "hint": "Flagship", "available": True, "is_default": True,
        "default_reasoning_effort": "high",
        "reasoning_efforts": [{"id": "high", "description": "Deep"}],
        "input_modalities": ["text", "image"], "upgrade": None,
    }]


# --- (e) the model list is cached per worker (queried once across turns) ------

def test_model_list_cached_across_turns(tmp_path):
    """With the warm pool, the worker is spawned once and reused; model/list is
    queried once at spawn and the picked id keeps flowing on every turn from the
    cached set — not re-fetched per turn."""
    factory = _Factory(models=_ACCOUNT_MODELS)
    pool = CodexWorkerPool(max_workers=3, idle_sec=60)
    engine = _engine(factory, tmp_path, pool=pool)

    async def main():
        async for _ in engine.stream_turn(_turn("gpt-5.4")):
            pass
        async for _ in engine.stream_turn(_turn("gpt-5.4")):
            pass

    asyncio.run(main())
    assert factory.spawns == 1, "the worker must be spawned once and reused"
    fake = factory.instances[0]
    assert fake.models_calls == 1, "model/list must be cached, not re-fetched per turn"
    assert len(fake.turn_kwargs) == 2
    assert all(k.get("model") == "gpt-5.4" for k in fake.turn_kwargs), (
        "the cached set must keep gating turns correctly after the first")
