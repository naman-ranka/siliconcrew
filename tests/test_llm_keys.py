"""LlmKeyProvider: BYOK envelope encryption + capped hosted tier (slice 5).

The real AEAD (Fernet) and KEK (Cloud KMS) are deploy-time concerns; here we
inject reversible fakes to prove the envelope *orchestration*: plaintext keys
are never stored, the DEK is wrapped by the KEK, round-trip works, and tenants
are isolated. Then the hosted-tier fallback + caps.
"""
import json

import pytest

from src.platform_engines.llm_keys import (
    ByokHostedLlmKeyProvider,
    EnvLlmKeyProvider,
    EnvelopeKeyVault,
    HostedTierExhausted,
    HostedTierLimiter,
    HostedTierLimits,
    InMemoryWrappedKeyStore,
)


class ReversibleCipher:
    """Test-only 'AEAD': prefixes with the key so we can prove key separation."""

    def encrypt(self, key: bytes, plaintext: bytes) -> bytes:
        return key + b"||" + plaintext

    def decrypt(self, key: bytes, token: bytes) -> bytes:
        k, _, pt = token.partition(b"||")
        assert k == key, "DEK mismatch on decrypt"
        return pt


class FakeKek:
    """Test-only KEK: a reversible wrap that tags the DEK as wrapped."""

    def wrap_dek(self, dek: bytes) -> bytes:
        return b"KEK(" + dek + b")"

    def unwrap_dek(self, wrapped: bytes) -> bytes:
        assert wrapped.startswith(b"KEK(") and wrapped.endswith(b")")
        return wrapped[4:-1]


def _vault():
    return EnvelopeKeyVault(InMemoryWrappedKeyStore(), ReversibleCipher(), FakeKek())


def test_byok_round_trips_and_never_stores_plaintext():
    store = InMemoryWrappedKeyStore()
    vault = EnvelopeKeyVault(store, ReversibleCipher(), FakeKek())
    secret = "sk-super-secret-anthropic-key"

    vault.store_key("google_1", "anthropic", secret)
    assert vault.get_key("google_1", "anthropic") == secret

    # The persisted blob must contain neither the plaintext key nor a raw DEK.
    blob = store.get("google_1", "anthropic")
    assert secret not in blob
    data = json.loads(blob)
    assert set(data) >= {"wrapped_dek", "ciphertext"}
    # The stored DEK is wrapped by the KEK (envelope property).
    import base64

    assert base64.b64decode(data["wrapped_dek"]).startswith(b"KEK(")


def test_byok_isolated_per_user_and_provider():
    vault = _vault()
    vault.store_key("alice", "openai", "sk-alice")
    vault.store_key("bob", "openai", "sk-bob")
    assert vault.get_key("alice", "openai") == "sk-alice"
    assert vault.get_key("bob", "openai") == "sk-bob"
    assert vault.get_key("alice", "anthropic") is None  # different provider


def test_each_store_uses_a_fresh_dek():
    vault = _vault()
    vault.store_key("u", "openai", "same-key")
    blob1 = json.loads(InMemoryWrappedKeyStore().get("u", "openai") or "{}")  # sanity: empty store
    # Store twice into the same vault and confirm ciphertext differs (fresh DEK).
    store = InMemoryWrappedKeyStore()
    v = EnvelopeKeyVault(store, ReversibleCipher(), FakeKek())
    v.store_key("u", "openai", "same-key")
    c1 = json.loads(store.get("u", "openai"))["ciphertext"]
    v.store_key("u", "openai", "same-key")
    c2 = json.loads(store.get("u", "openai"))["ciphertext"]
    assert c1 != c2  # different DEK → different ciphertext for identical plaintext


def test_provider_prefers_byok_over_hosted():
    vault = _vault()
    vault.store_key("u1", "gemini", "user-own-gemini-key")
    provider = ByokHostedLlmKeyProvider(vault, hosted_gemini_key="HOSTED", hosted_model="gemini-3-flash-preview")
    key = provider.resolve("u1", "gemini-3-flash-preview")
    assert key.source == "byok" and key.api_key == "user-own-gemini-key"


def test_provider_falls_back_to_hosted_gemini(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED", hosted_model="gemini-3.1-flash-lite")
    key = provider.resolve("u1", "gemini-3.1-flash-lite")
    assert key.source == "hosted" and key.api_key == "HOSTED"


def test_hosted_served_model_is_always_flash_lite(monkeypatch):
    # Honest state: even if an operator misconfigures HOSTED_GEMINI_MODEL to a
    # non-free model, a keyless flash-lite request must be SERVED flash-lite,
    # never silently upgraded to the operator's model. (Fails pre-fix, where the
    # served model was self._hosted_model.)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    provider = ByokHostedLlmKeyProvider(
        _vault(), hosted_gemini_key="HOSTED", hosted_model="gemini-3.5-flash"
    )
    key = provider.resolve("u1", "gemini-3.1-flash-lite")
    assert key.source == "hosted"
    assert key.model == "gemini-3.1-flash-lite"


def test_provider_requires_byok_for_non_gemini_without_key():
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED")
    with pytest.raises(ValueError, match="need your own"):
        provider.resolve("u1", "claude-opus-4-8")


def test_keyless_non_flashlite_gemini_requires_byok(monkeypatch):
    # Only the free default (flash-lite) rides the shared key; other Gemini
    # models need the user's own key.
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED")
    with pytest.raises(ValueError, match="need your own"):
        provider.resolve("u1", "gemini-3.5-flash")


def test_keyless_env_does_not_serve_non_gemini(monkeypatch):
    # A container OpenAI/Anthropic key must NOT silently serve a keyless user —
    # that was the source of the raw "credit balance too low" error on hosted.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai")
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED")
    with pytest.raises(ValueError, match="need your own"):
        provider.resolve("u1", "claude-opus-4-8")
    with pytest.raises(ValueError, match="need your own"):
        provider.resolve("u1", "gpt-5.5")


def test_keyless_env_gemini_serves_flashlite_only(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "env-gemini")
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED")
    key = provider.resolve("u1", "gemini-3.1-flash-lite")
    assert key.source == "env" and key.api_key == "env-gemini"
    with pytest.raises(ValueError, match="need your own"):
        provider.resolve("u1", "gemini-3.5-flash")


def test_byok_wins_for_any_model(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    vault = _vault()
    vault.store_key("u1", "anthropic", "user-claude-key")
    provider = ByokHostedLlmKeyProvider(vault, hosted_gemini_key="HOSTED")
    key = provider.resolve("u1", "claude-opus-4-8")
    assert key.source == "byok" and key.api_key == "user-claude-key"


def test_hosted_tier_daily_token_cap(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    limiter = HostedTierLimiter(HostedTierLimits(tokens_per_day=100, global_cost_ceiling_usd=1000))
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED", limiter=limiter)
    provider.resolve("u1", "gemini-3.1-flash-lite")  # ok
    limiter.record("u1", tokens=100, cost_usd=0.01)
    with pytest.raises(HostedTierExhausted) as ei:
        provider.resolve("u1", "gemini-3.1-flash-lite")
    assert ei.value.code == "hosted_tier_exhausted"


def test_hosted_tier_global_cost_ceiling(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    limiter = HostedTierLimiter(HostedTierLimits(tokens_per_day=10**9, global_cost_ceiling_usd=1.0))
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED", limiter=limiter)
    limiter.record("whoever", tokens=1, cost_usd=1.0)  # exhaust global budget
    with pytest.raises(HostedTierExhausted):
        provider.resolve("u2", "gemini-3.1-flash-lite")


def test_env_provider_reads_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic")
    key = EnvLlmKeyProvider().resolve(None, "claude-opus-4-8")
    assert key.source == "env" and key.api_key == "env-anthropic" and key.provider == "anthropic"
