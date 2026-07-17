"""Model-granular availability for GET /api/models.

Unit-level checks on the availability helpers so the native picker never offers
a model that ByokHostedLlmKeyProvider.resolve would reject. get_settings is
patched directly (no env/cache dance); the vault path is covered by the
resolve() tests in test_llm_keys.py.
"""
import pytest

pytest.importorskip("fastapi")
import api  # noqa: E402


class _S:
    def __init__(self, hosted, key=""):
        self.hosted = hosted
        self.hosted_gemini_key = key


class _Id:
    user_id = None


def _e(mid, prov):
    return {"id": mid, "provider": prov}


def test_hosted_keyless_offers_only_flash_lite(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _S(hosted=True, key="HOSTED"))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    byok = set()
    assert api._native_model_available(_e("gemini-3.1-flash-lite", "gemini"), byok) is True
    assert api._native_model_available(_e("gemini-3.5-flash", "gemini"), byok) is False
    assert api._native_model_available(_e("claude-opus-4-8", "anthropic"), byok) is False
    assert api._native_model_available(_e("gpt-5.5", "openai"), byok) is False


def test_hosted_byok_offers_that_provider(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _S(hosted=True, key="HOSTED"))
    byok = {"anthropic"}
    assert api._native_model_available(_e("claude-opus-4-8", "anthropic"), byok) is True
    assert api._native_model_available(_e("gpt-5.5", "openai"), byok) is False
    # flash-lite still available via the shared key regardless of BYOK.
    assert api._native_model_available(_e("gemini-3.1-flash-lite", "gemini"), byok) is True


def test_hosted_no_shared_key_is_all_byok(monkeypatch):
    # Owner rule: remove the platform key -> everything is bring-your-own-key,
    # including flash-lite.
    monkeypatch.setattr(api, "get_settings", lambda: _S(hosted=True, key=""))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert api._native_model_available(_e("gemini-3.1-flash-lite", "gemini"), set()) is False


def test_selfhost_is_provider_by_env(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _S(hosted=False))
    # self-host: flash-lite is not special; availability follows env-key provider.
    assert api._native_model_available(_e("gemini-3.1-flash-lite", "gemini"), set()) is False
    assert api._native_model_available(_e("gemini-3.1-flash-lite", "gemini"), {"gemini"}) is True


def test_byok_providers_selfhost_reads_env(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: _S(hosted=False))
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert api._byok_providers(_Id()) == {"openai"}
