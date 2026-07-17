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
    provider = ByokHostedLlmKeyProvider(vault, hosted_gemini_key="HOSTED")
    # BYOK wins even for the allowlisted free model.
    key = provider.resolve("u1", "gemini-3.1-flash-lite")
    assert key.source == "byok" and key.api_key == "user-own-gemini-key"


def test_provider_falls_back_to_hosted_for_allowed_model_only():
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED")
    key = provider.resolve("u1", "gemini-3.1-flash-lite")
    assert key.source == "hosted" and key.api_key == "HOSTED"
    # The pin is the VALIDATED requested model — never a separately configured
    # hosted model that could silently upgrade the turn to a costlier model.
    assert key.model == "gemini-3.1-flash-lite"


def test_disallowed_gemini_model_requires_byok():
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED")
    with pytest.raises(ValueError, match="free model"):
        provider.resolve("u1", "gemini-3.5-flash")


def test_env_keys_never_serve_end_users_in_hosted(monkeypatch):
    # The old blanket env fallback served ANY model, uncapped, bypassing the
    # limiter (the E5 leak). With a container env key present: allowed models
    # still resolve through the CAPPED hosted branch, and disallowed models
    # still require BYOK.
    monkeypatch.setenv("GOOGLE_API_KEY", "env-leak")
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED")
    key = provider.resolve("u1", "gemini-3.1-flash-lite")
    assert key.source == "hosted" and key.api_key == "HOSTED"
    with pytest.raises(ValueError):
        provider.resolve("u1", "gemini-3.5-flash")


def test_allowlist_and_request_aliases_normalize():
    # A deprecated alias in env config still matches the normalized request,
    # and an aliased request matches the canonical allowlist.
    provider = ByokHostedLlmKeyProvider(
        _vault(), hosted_gemini_key="HOSTED",
        allowed_fallback_models=("gemini-3.1-flash-lite-preview",),
    )
    key = provider.resolve("u1", "gemini-3.1-flash-lite")
    assert key.source == "hosted" and key.model == "gemini-3.1-flash-lite"


def test_no_platform_key_reads_all_byok():
    # Platform key pulled → every model (including the free one) honestly
    # reads as bring-your-own-key, with no mention of a free tier.
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="")
    with pytest.raises(ValueError) as ei:
        provider.resolve("u1", "gemini-3.1-flash-lite")
    assert "free model" not in str(ei.value)


def test_provider_requires_byok_for_non_gemini_without_key():
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED")
    with pytest.raises(ValueError, match="No key available"):
        provider.resolve("u1", "claude-opus-4-8")


def test_hosted_tier_daily_token_cap():
    limiter = HostedTierLimiter(HostedTierLimits(tokens_per_day=100, global_cost_ceiling_usd=1000))
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED", limiter=limiter)
    provider.resolve("u1", "gemini-3.1-flash-lite")  # ok
    limiter.record("u1", tokens=100, cost_usd=0.01)
    with pytest.raises(HostedTierExhausted) as ei:
        provider.resolve("u1", "gemini-3.1-flash-lite")
    assert ei.value.code == "hosted_tier_exhausted"


def test_hosted_tier_global_cost_ceiling():
    limiter = HostedTierLimiter(HostedTierLimits(tokens_per_day=10**9, global_cost_ceiling_usd=1.0))
    provider = ByokHostedLlmKeyProvider(_vault(), hosted_gemini_key="HOSTED", limiter=limiter)
    limiter.record("whoever", tokens=1, cost_usd=1.0)  # exhaust global budget
    with pytest.raises(HostedTierExhausted):
        provider.resolve("u2", "gemini-3.1-flash-lite")


def test_env_provider_reads_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic")
    key = EnvLlmKeyProvider().resolve(None, "claude-opus-4-8")
    assert key.source == "env" and key.api_key == "env-anthropic" and key.provider == "anthropic"
