"""Model selector — catalog metadata, model-on-thread, inheritance (Task 2).

Backend-only (no LangChain). The GET /api/models availability + the WS reading
the active thread's model are exercised at the unit level (the registry + the
SessionManager model storage); the live HTTP/WS wiring runs in the integration
env.
"""
import datetime

import pytest

from src.model_catalog import (
    CATALOG,
    CODEX_CATALOG,
    CODEX_DEFAULT_MODEL,
    DEFAULT_MODEL,
    PRICING,
    codex_catalog_entries,
    model_catalog_entries,
    normalize_model_name,
)
from src.platform_engines.metadata_store import SqliteMetadataStore
from src.utils.session_manager import SessionManager


# --- catalog ----------------------------------------------------------------


def test_catalog_entries_have_required_fields_and_pricing():
    entries = model_catalog_entries()
    assert entries, "catalog must not be empty"
    providers = set()
    for e in entries:
        assert {"id", "label", "provider", "tier", "hint"} <= set(e)
        assert e["tier"] in ("fast", "balanced", "capable")
        providers.add(e["provider"])
        # Pricing is merged when known.
        if e["id"] in PRICING:
            assert e["pricing"] == PRICING[e["id"]]
    assert providers == {"gemini", "openai", "anthropic"}


def test_default_model_is_in_catalog():
    assert any(e["id"] == DEFAULT_MODEL for e in CATALOG)


# --- codex catalog (maintained separately from the native CATALOG) -----------


def test_codex_catalog_is_openai_only_with_required_fields_and_pricing():
    entries = codex_catalog_entries()
    assert entries, "codex catalog must not be empty"
    for e in entries:
        assert {"id", "label", "provider", "tier", "hint"} <= set(e)
        assert e["provider"] == "openai"
        assert e["tier"] in ("fast", "balanced", "capable")
        # Every codex id must be priced so cost accounting keeps working.
        assert e["id"] in PRICING
        assert e["pricing"] == PRICING[e["id"]]


def test_codex_default_model_is_in_codex_catalog():
    assert any(e["id"] == CODEX_DEFAULT_MODEL for e in CODEX_CATALOG)


# --- model on thread + inheritance ------------------------------------------


@pytest.fixture
def mgr(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"))


def test_thread_stores_and_updates_model(mgr):
    mgr.create_session("s1", user_id="alice")
    t = mgr.create_thread("s1", user_id="alice", model="claude-opus-4-6")
    assert t["model"] == "claude-opus-4-6"
    mgr.set_thread_model(t["id"], "gpt-5.4", user_id="alice")
    assert mgr.get_thread(t["id"], user_id="alice")["model"] == "gpt-5.4"


def test_thread_stores_reasoning_effort(mgr):
    mgr.create_session("s1", user_id="alice")
    thread = mgr.create_thread("s1", user_id="alice", model="gpt-5.6-sol")
    assert thread["reasoning_effort"] is None
    mgr.set_thread_reasoning_effort(thread["id"], "high", user_id="alice")
    assert mgr.get_thread(thread["id"], user_id="alice")["reasoning_effort"] == "high"


def test_new_thread_inherits_last_used_model(mgr):
    mgr.create_session("s1", user_id="alice")
    # Set a model on the first explicit thread...
    t1 = mgr.create_thread("s1", user_id="alice", model="gpt-5.4")
    # ...a brand-new thread (no model given) inherits the last-used one.
    t2 = mgr.create_thread("s1", user_id="alice")
    assert t2["model"] == "gpt-5.4"


def test_inherits_session_model_when_no_thread_model(tmp_path):
    store = SqliteMetadataStore(str(tmp_path / "state.db"))
    store.init_schema()
    now = datetime.datetime.now()
    store.upsert_session("s1", "alice", "S1", "claude-sonnet-4-6", None, now)
    mgr = SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"),
                         metadata_store=store)
    import os
    os.makedirs(os.path.join(mgr.base_dir, "s1"), exist_ok=True)
    t = mgr.create_thread("s1", user_id="alice")
    assert t["model"] == "claude-sonnet-4-6"  # falls back to the session's model


def test_thread_model_is_tenant_scoped(mgr):
    mgr.create_session("s1", user_id="alice")
    t = mgr.create_thread("s1", user_id="alice", model="gpt-5.4")
    # A different tenant cannot read/change the model.
    assert mgr.get_thread(t["id"], user_id="bob") is None
    mgr.set_thread_model(t["id"], "claude-opus-4-6", user_id="bob")  # no-op
    assert mgr.get_thread(t["id"], user_id="alice")["model"] == "gpt-5.4"


def test_model_normalization_alias():
    # Compat + retired ids resolve to their GA successors.
    assert normalize_model_name("gemini-3.1-flash") == "gemini-3.5-flash"
    assert normalize_model_name("gemini-3-flash-preview") == "gemini-3.5-flash"
    assert normalize_model_name("gemini-3.1-flash-lite-preview") == "gemini-3.1-flash-lite"
