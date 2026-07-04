import os
import warnings
from typing import Literal

from src.model_catalog import normalize_model_name


Provider = Literal["gemini", "openai", "anthropic"]


def infer_provider_from_model(model_name: str) -> Provider:
    """
    Infer provider from model naming conventions.
    """
    name = (model_name or "").strip().lower()
    if name.startswith("gemini-"):
        return "gemini"
    if name.startswith("claude-"):
        return "anthropic"
    if (
        name.startswith("gpt-")
        or name.startswith("chatgpt-")
        or name.startswith("o1")
        or name.startswith("o3")
        or name.startswith("o4")
    ):
        return "openai"
    raise ValueError(
        f"Unsupported model '{model_name}'. Expected prefixes: "
        "gemini-*, claude-*, gpt-*/chatgpt-*/o1|o3|o4*."
    )


def _require_env(var_name: str, provider: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        raise ValueError(
            f"Missing API key for provider '{provider}'. "
            f"Set environment variable: {var_name}."
        )
    return value


def _prefer_openai_responses_api(model_name: str) -> bool:
    name = (model_name or "").strip().lower()
    return (
        name.startswith("gpt-5")
        or "codex" in name
        or name.startswith("o1")
        or name.startswith("o3")
        or name.startswith("o4")
    )


def _openai_temperature_supported(model_name: str) -> bool:
    """
    GPT-5/Codex/o-series are typically constrained and may reject explicit
    temperature overrides. Keep requests compatible by omitting temperature.
    """
    return not _prefer_openai_responses_api(model_name)


def _anthropic_temperature_supported(model_name: str) -> bool:
    """
    Claude Opus 4.7+, Sonnet 5, and the Fable/Mythos family removed sampling
    parameters — sending `temperature` returns a 400 ("deprecated for this
    model"). Older families (Haiku 4.5, Sonnet 4.6, Opus 4.6) still accept it.
    """
    name = (model_name or "").strip().lower()
    return not name.startswith((
        "claude-opus-4-7",
        "claude-opus-4-8",
        "claude-sonnet-5",
        "claude-opus-5",
        "claude-haiku-5",
        "claude-fable",
        "claude-mythos",
    ))


def create_llm(model_name: str, temperature: float = 0.0, api_key: str | None = None):
    """
    Create a LangChain chat model for the inferred provider.
    Uses lazy imports so optional provider deps do not affect others.

    Args:
        api_key: Optional explicit, request-scoped API key (BYOK / hosted tier
            resolved via LlmKeyProvider). When None, the provider key is read
            from the environment — today's self-host behavior. Passing it here
            keeps the key out of the process environment entirely.
    """
    model_name = normalize_model_name(model_name)
    provider = infer_provider_from_model(model_name)

    def _key(env_var: str) -> str:
        return api_key or _require_env(env_var, provider)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm_kwargs = {
            "model": model_name,
            "google_api_key": _key("GOOGLE_API_KEY"),
            "temperature": temperature,
        }

        if "gemini-3" in model_name.lower():
            # Gemini 3+ models emit thought parts; surface them so downstream
            # content handling (which filters to text blocks) stays correct.
            llm_kwargs["include_thoughts"] = True

        return ChatGoogleGenerativeAI(**llm_kwargs)

    if provider == "openai":
        openai_api_key = _key("OPENAI_API_KEY")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ImportError(
                "Missing dependency 'langchain-openai'. Install it with: pip install langchain-openai"
            ) from exc

        openai_model = model_name
        if model_name == "gpt-5.3-codex":
            fallback = os.environ.get("OPENAI_FALLBACK_MODEL", "gpt-5-mini")
            if os.environ.get("OPENAI_FORCE_FALLBACK", "0").strip() in {"1", "true", "yes"}:
                warnings.warn(
                    f"OPENAI_FORCE_FALLBACK is enabled. Using '{fallback}' instead of '{model_name}'.",
                    UserWarning,
                )
                openai_model = fallback

        openai_kwargs = {
            "model": openai_model,
            "api_key": openai_api_key,
        }

        if _prefer_openai_responses_api(openai_model):
            openai_kwargs["use_responses_api"] = True

        if _openai_temperature_supported(openai_model):
            openai_kwargs["temperature"] = temperature
        elif temperature is not None and temperature != 1:
            warnings.warn(
                f"Skipping explicit temperature={temperature} for model '{openai_model}' "
                "to avoid unsupported parameter errors.",
                UserWarning,
            )

        return ChatOpenAI(**openai_kwargs)

    # provider == "anthropic"
    anthropic_api_key = _key("ANTHROPIC_API_KEY")
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise ImportError(
            "Missing dependency 'langchain-anthropic'. Install it with: pip install langchain-anthropic"
        ) from exc

    anthropic_kwargs = {
        "model": model_name,
        "anthropic_api_key": anthropic_api_key,
    }
    if _anthropic_temperature_supported(model_name):
        anthropic_kwargs["temperature"] = temperature
    elif temperature is not None and temperature != 1:
        warnings.warn(
            f"Skipping explicit temperature={temperature} for model '{model_name}' "
            "— sampling parameters are rejected on this model family.",
            UserWarning,
        )

    return ChatAnthropic(**anthropic_kwargs)
