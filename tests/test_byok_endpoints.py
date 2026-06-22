"""BYOK store -> resolve -> use round-trip (Phase 2 I5).

Exercises the persistent (SQLite) wrapped-key store + EnvelopeKeyVault + the
LlmKeyProvider resolution the agent uses. The AEAD/KEK primitives are injected
(fakes) because the sandbox's Fernet backend is unavailable; the envelope
orchestration, persistence, tenant isolation, and provider fallback are real.
"""
import json
from dataclasses import dataclass

import pytest

from src.platform_engines.llm_keys import (
    ByokHostedLlmKeyProvider,
    EnvelopeKeyVault,
    PostgresWrappedKeyStore,
    SqliteWrappedKeyStore,
    build_key_vault,
    build_llm_key_provider,
)


class ReversibleCipher:
    def encrypt(self, key: bytes, plaintext: bytes) -> bytes:
        return key + b"||" + plaintext

    def decrypt(self, key: bytes, token: bytes) -> bytes:
        k, _, pt = token.partition(b"||")
        assert k == key
        return pt


class FakeKek:
    def wrap_dek(self, dek: bytes) -> bytes:
        return b"KEK(" + dek + b")"

    def unwrap_dek(self, wrapped: bytes) -> bytes:
        return wrapped[4:-1]


@dataclass
class FakeSettings:
    hosted: bool = True
    persistence_engine: str = "sqlite"
    database_url: str = ""
    kms_key_uri: str = ""
    llm_key_engine: str = "byok"
    hosted_gemini_key: str = "HOSTED_GEMINI"
    hosted_gemini_model: str = "gemini-3-flash-preview"


# --- persistent store round trip --------------------------------------------


def test_sqlite_store_persists_across_instances(tmp_path):
    db = str(tmp_path / "byok.db")
    vault = EnvelopeKeyVault(SqliteWrappedKeyStore(db), ReversibleCipher(), FakeKek())
    vault.store_key("alice", "anthropic", "sk-alice-secret")

    # A fresh store object over the same file (a different request / process).
    vault2 = EnvelopeKeyVault(SqliteWrappedKeyStore(db), ReversibleCipher(), FakeKek())
    assert vault2.get_key("alice", "anthropic") == "sk-alice-secret"

    # Plaintext never stored.
    raw = SqliteWrappedKeyStore(db).get("alice", "anthropic")
    assert "sk-alice-secret" not in raw
    assert set(json.loads(raw)) >= {"wrapped_dek", "ciphertext"}


def test_sqlite_store_tenant_isolation_and_delete(tmp_path):
    db = str(tmp_path / "byok.db")
    vault = EnvelopeKeyVault(SqliteWrappedKeyStore(db), ReversibleCipher(), FakeKek())
    vault.store_key("alice", "openai", "sk-alice")
    vault.store_key("bob", "openai", "sk-bob")
    assert vault.get_key("alice", "openai") == "sk-alice"
    assert vault.get_key("bob", "openai") == "sk-bob"
    # Delete is scoped — removing alice's key leaves bob's intact.
    vault.delete_key("alice", "openai")
    assert vault.get_key("alice", "openai") is None
    assert vault.get_key("bob", "openai") == "sk-bob"


# --- store -> resolve -> use -------------------------------------------------


def test_store_then_resolve_returns_byok_key(tmp_path):
    db = str(tmp_path / "byok.db")
    vault = EnvelopeKeyVault(SqliteWrappedKeyStore(db), ReversibleCipher(), FakeKek())
    vault.store_key("google_1", "anthropic", "sk-user-anthropic")

    provider = ByokHostedLlmKeyProvider(vault, hosted_gemini_key="HOSTED")
    key = provider.resolve("google_1", "claude-opus-4-8")
    assert key.source == "byok" and key.api_key == "sk-user-anthropic"

    # The resolved key is what create_llm(..., api_key=...) consumes (slice 5).
    from src.llm.factory import create_llm
    import inspect

    assert "api_key" in inspect.signature(create_llm).parameters


def test_resolve_falls_back_to_hosted_gemini_without_byok(tmp_path):
    db = str(tmp_path / "byok.db")
    vault = EnvelopeKeyVault(SqliteWrappedKeyStore(db), ReversibleCipher(), FakeKek())
    provider = ByokHostedLlmKeyProvider(vault, hosted_gemini_key="HOSTED")
    key = provider.resolve("google_1", "gemini-3-flash-preview")
    assert key.source == "hosted" and key.api_key == "HOSTED"


# --- factory selection logic (no Fernet/KMS invoked) ------------------------


def test_build_key_vault_disabled_without_kms_or_master(tmp_path, monkeypatch):
    monkeypatch.delenv("SILICONCREW_MASTER_KEY", raising=False)
    # No KMS, no master key, sqlite store available -> BYOK disabled (None).
    assert build_key_vault(FakeSettings(kms_key_uri=""), db_path=str(tmp_path / "k.db")) is None


def test_build_key_vault_with_master_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SILICONCREW_MASTER_KEY", "super-secret-master")
    vault = build_key_vault(FakeSettings(kms_key_uri=""), db_path=str(tmp_path / "k.db"))
    assert isinstance(vault, EnvelopeKeyVault)


def test_build_key_vault_prefers_kms(tmp_path):
    vault = build_key_vault(FakeSettings(kms_key_uri="projects/p/keys/k"), db_path=str(tmp_path / "k.db"))
    assert isinstance(vault, EnvelopeKeyVault)


def test_build_llm_key_provider_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("SILICONCREW_MASTER_KEY", "m")
    vault = build_key_vault(FakeSettings(kms_key_uri=""), db_path=str(tmp_path / "k.db"))
    # hosted+byok -> BYOK provider
    p = build_llm_key_provider(FakeSettings(llm_key_engine="byok"), vault)
    assert isinstance(p, ByokHostedLlmKeyProvider)
    # self-host env -> env provider
    from src.platform_engines.llm_keys import EnvLlmKeyProvider

    p2 = build_llm_key_provider(FakeSettings(llm_key_engine="env"), None)
    assert isinstance(p2, EnvLlmKeyProvider)


def test_postgres_wrapped_key_store_sql_shape():
    """Smoke the PG key store via a recording fake connection."""
    sink = []

    class Cur:
        description = [("blob",)]

        def execute(self, sql, params=()):
            sink.append((sql, params))

        def fetchone(self):
            return ('{"wrapped_dek":"x","ciphertext":"y"}',)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    store = PostgresWrappedKeyStore("dsn", connect=lambda d: Conn())
    store.put("u", "openai", "{}")
    assert store.get("u", "openai") is not None
    assert any("%s" in s and "byok_keys" in s for s, _ in sink)
