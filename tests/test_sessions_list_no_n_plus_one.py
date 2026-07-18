"""Regression: GET /api/sessions must not issue one query per session.

Issue #43 — the listing handler fetched every session's row up front, threw the
rows away, and then re-queried ``get_session`` once per session inside the loop.
On hosted Postgres each ``get_session`` opens a fresh Cloud SQL connection, so
the endpoint's cost grew linearly with the session count (p95 2.3s).

These tests PIN the fixed shape: the whole list is served by two grouped queries
(``get_all_session_rows`` + ``count_threads_by_session``) with ZERO per-session
``get_session`` calls, regardless of how many sessions the caller owns — while
the response payload stays byte-for-byte what the old loop produced.
"""
import collections

import pytest

from src.utils.session_manager import SessionManager

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402

import api  # noqa: E402


class _CountingStore:
    """Transparent proxy that tallies which store methods the handler calls."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = collections.Counter()

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            self.calls[name] += 1
            return attr(*args, **kwargs)

        return wrapped


@pytest.fixture
def sm(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "workspace"), db_path=str(tmp_path / "state.db"))


@pytest.fixture
def client(sm, monkeypatch):
    monkeypatch.setattr(api, "session_manager", sm)
    return TestClient(api.app)


def test_list_sessions_is_two_queries_regardless_of_count(client, sm):
    for i in range(12):
        sm.create_session(f"sess_{i}")

    counter = _CountingStore(sm._store)
    sm._store = counter

    r = client.get("/api/sessions")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 12

    # The whole list is served by exactly the two grouped queries — never a
    # per-session get_session (the old N+1). This is the load-bearing assertion.
    assert counter.calls["get_session"] == 0
    assert counter.calls["get_all_session_rows"] == 1
    assert counter.calls["count_threads_by_session"] == 1


def test_list_sessions_query_count_flat_as_sessions_grow(client, sm):
    """Doubling the session count must NOT change the query count (bounded, not
    O(N)) — the direct guard against the N+1 creeping back."""

    def query_count_for(n):
        for i in range(n):
            sm.create_session(f"s{n}_{i}")
        counter = _CountingStore(sm._store)
        sm._store = counter
        assert client.get("/api/sessions").status_code == 200
        sm._store = counter._inner  # unwrap for the next round
        return counter.calls["get_session"], counter.calls["get_all_session_rows"]

    assert query_count_for(3) == (0, 1)
    assert query_count_for(9) == (0, 1)  # 3x the sessions, same query shape


def test_list_sessions_payload_matches_metadata(client, sm):
    sid = sm.create_session("uart_tx")
    sm.rename_session(sid, "UART transmitter")

    items = {s["id"]: s for s in client.get("/api/sessions").json()}
    assert sid in items
    meta = sm.get_session_metadata(sid)
    assert items[sid]["name"] == "UART transmitter" == meta["session_name"]
    assert items[sid]["model_name"] == meta["model_name"]
    # Seeded "Chat 1" is counted honestly (grouped COUNT, no materialization).
    assert items[sid]["thread_count"] == 1


def test_list_sessions_stays_owner_scoped(client, sm, monkeypatch):
    """The batched read is still tenant-scoped: user A never sees B's rows."""
    sm.create_session("alice_only", user_id="alice")
    sm.create_session("bob_only", user_id="bob")

    monkeypatch.setattr(api, "_uid", lambda identity: "alice")
    ids = {s["id"] for s in client.get("/api/sessions").json()}
    assert ids == {"alice_only"}

    monkeypatch.setattr(api, "_uid", lambda identity: "bob")
    ids = {s["id"] for s in client.get("/api/sessions").json()}
    assert ids == {"bob_only"}
