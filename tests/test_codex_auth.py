"""Codex ChatGPT-account auth manager — durable credential lifecycle (gap #2).

Covers the hosted-durability seam: a per-user login persisted to an injected
credential store (in hosted, the encrypted BYOK vault) survives a fresh instance
with no local auth.json, is restored to local disk before a turn, re-persisted
after a (token-refreshing) turn, and dropped on disconnect. Self-host (no store)
keeps the local-file-only behavior.
"""
from pathlib import Path

from src.agents.codex.codex_auth import CodexAccountAuthManager, VaultCodexCredentialStore


class FakeCredStore:
    """In-memory stand-in for VaultCodexCredentialStore (uid -> auth.json)."""

    def __init__(self):
        self.d = {}

    def save(self, uid, blob):
        self.d[uid] = blob

    def load(self, uid):
        return self.d.get(uid)

    def has(self, uid):
        return uid in self.d

    def delete(self, uid):
        self.d.pop(uid, None)


def _write_local(mgr, uid, content):
    home = Path(mgr.auth_home(uid))
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_text(content, encoding="utf-8")


def test_is_connected_is_durable_aware(tmp_path):
    creds = FakeCredStore()
    mgr = CodexAccountAuthManager(str(tmp_path), credential_store=creds)
    assert not mgr.is_connected("alice")
    creds.save("alice", '{"tokens": "x"}')
    # A fresh instance has the durable copy but NO local file yet — still connected.
    assert mgr.is_connected("alice")
    assert not (Path(mgr.auth_home("alice")) / "auth.json").exists()


def test_ensure_local_restores_from_durable(tmp_path):
    creds = FakeCredStore()
    creds.save("alice", '{"tokens": "x"}')
    mgr = CodexAccountAuthManager(str(tmp_path), credential_store=creds)
    home = mgr.ensure_local("alice")
    assert home and (Path(home) / "auth.json").read_text(encoding="utf-8") == '{"tokens": "x"}'


def test_persist_saves_local_to_durable(tmp_path):
    creds = FakeCredStore()
    mgr = CodexAccountAuthManager(str(tmp_path), credential_store=creds)
    _write_local(mgr, "alice", '{"tokens": "refreshed"}')
    mgr.persist("alice")
    assert creds.load("alice") == '{"tokens": "refreshed"}'


def test_ensure_local_prefers_durable_over_stale_local(tmp_path):
    # Durable store is the source of truth: restore it OVER a stale local copy.
    creds = FakeCredStore()
    creds.save("alice", '{"tokens": "durable_new"}')
    mgr = CodexAccountAuthManager(str(tmp_path), credential_store=creds)
    _write_local(mgr, "alice", '{"tokens": "local_stale"}')
    home = mgr.ensure_local("alice")
    assert (Path(home) / "auth.json").read_text(encoding="utf-8") == '{"tokens": "durable_new"}'


def test_persist_does_not_clobber_concurrent_refresh(tmp_path):
    # A restores T0; another instance refreshes to T1; A's non-refreshing turn
    # must NOT overwrite T1 with the unchanged T0.
    creds = FakeCredStore()
    creds.save("alice", '{"tokens": "T0"}')
    mgr = CodexAccountAuthManager(str(tmp_path), credential_store=creds)
    mgr.ensure_local("alice")                      # restore T0, record its hash
    creds.save("alice", '{"tokens": "T1"}')        # another instance refreshed
    mgr.persist("alice")                           # local still T0 (unchanged)
    assert creds.load("alice") == '{"tokens": "T1"}'   # T1 not clobbered


def test_persist_saves_when_token_changed_since_restore(tmp_path):
    creds = FakeCredStore()
    creds.save("alice", '{"tokens": "T0"}')
    mgr = CodexAccountAuthManager(str(tmp_path), credential_store=creds)
    mgr.ensure_local("alice")                      # restore T0
    _write_local(mgr, "alice", '{"tokens": "T1_refreshed"}')  # this instance refreshed
    mgr.persist("alice")
    assert creds.load("alice") == '{"tokens": "T1_refreshed"}'


def test_disconnect_clears_local_and_durable(tmp_path):
    creds = FakeCredStore()
    creds.save("alice", '{"t": "x"}')
    mgr = CodexAccountAuthManager(str(tmp_path), credential_store=creds)
    _write_local(mgr, "alice", '{"t": "x"}')
    mgr.disconnect("alice")
    assert not creds.has("alice")
    assert not (Path(mgr.auth_home("alice")) / "auth.json").exists()


def test_selfhost_no_store_uses_local_file_only(tmp_path):
    mgr = CodexAccountAuthManager(str(tmp_path))  # no credential store
    assert not mgr.is_connected("bob")
    _write_local(mgr, "bob", '{"t": "y"}')
    assert mgr.is_connected("bob")
    mgr.persist("bob")       # no-op without a store — must not raise
    mgr.disconnect("bob")
    assert not mgr.is_connected("bob")


def test_vault_adapter_maps_to_reserved_provider_slot():
    """The adapter stores under a reserved provider slot on the shared vault."""
    calls = []

    class FakeVault:
        def store_key(self, uid, provider, blob):
            calls.append(("store", uid, provider, blob))

        def get_key(self, uid, provider):
            calls.append(("get", uid, provider))
            return '{"t": "z"}'

        def has_key(self, uid, provider):
            return True

        def delete_key(self, uid, provider):
            calls.append(("delete", uid, provider))

    store = VaultCodexCredentialStore(FakeVault())
    store.save("alice", '{"t": "z"}')
    assert store.load("alice") == '{"t": "z"}'
    assert store.has("alice")
    store.delete("alice")
    # Every op is namespaced under the codex_account provider (not a real LLM one).
    assert all(c[2] == "codex_account" for c in calls if len(c) >= 3)
