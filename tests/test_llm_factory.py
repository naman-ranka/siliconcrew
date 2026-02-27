import pytest

from src.llm.factory import infer_provider_from_model, create_llm


@pytest.mark.parametrize(
    "model_name,provider",
    [
        ("gemini-3-flash-preview", "gemini"),
        ("gpt-5-mini", "openai"),
        ("o3-mini", "openai"),
        ("claude-sonnet-4-6", "anthropic"),
    ],
)
def test_infer_provider_from_model(model_name, provider):
    assert infer_provider_from_model(model_name) == provider


def test_infer_provider_unknown_model():
    with pytest.raises(ValueError, match="Unsupported model"):
        infer_provider_from_model("custom-local-model")


@pytest.mark.parametrize(
    "model_name,key_name",
    [
        ("gpt-5-mini", "OPENAI_API_KEY"),
        ("claude-sonnet-4-6", "ANTHROPIC_API_KEY"),
        ("gemini-3-flash-preview", "GOOGLE_API_KEY"),
    ],
)
def test_create_llm_requires_api_key(monkeypatch, model_name, key_name):
    monkeypatch.delenv(key_name, raising=False)
    with pytest.raises(ValueError, match=f"Set environment variable: {key_name}"):
        create_llm(model_name=model_name)


def test_openai_codex_force_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_FORCE_FALLBACK", "1")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-5-mini")
    llm = create_llm(model_name="gpt-5.3-codex")
    assert getattr(llm, "model_name", None) == "gpt-5-mini"


def test_openai_gpt5_uses_responses_and_skips_temperature(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = create_llm(model_name="gpt-5-mini", temperature=0.0)
    assert getattr(llm, "use_responses_api", None) is True
    assert getattr(llm, "temperature", None) is None


def test_openai_non_gpt5_keeps_temperature(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = create_llm(model_name="gpt-4o-mini", temperature=0.2)
    assert getattr(llm, "temperature", None) == 0.2
