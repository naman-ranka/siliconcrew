import os


MODEL_ALIASES = {
    # Google's docs currently expose Gemini 3 Flash as the general text/code
    # Flash model. Accept this compatibility alias and resolve it server-side.
    "gemini-3.1-flash": "gemini-3-flash-preview",
}


PRICING = {
    "gemini-3-flash-preview": {"input": 0.50, "output": 3.00},
    "gemini-3.1-flash-lite-preview": {"input": 0.25, "output": 1.50},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    "gpt-5-mini": {"input": 0.30, "output": 2.50},
    "gpt-5.3-codex": {"input": 2.00, "output": 12.00},
    "gpt-5.4": {"input": 2.00, "output": 12.00},
    "gpt-5.4-mini": {"input": 0.30, "output": 2.50},
    "claude-sonnet-4-6": {"input": 0.30, "output": 2.50},
    "claude-opus-4-6": {"input": 2.00, "output": 12.00},
}


DEFAULT_MODEL = "gemini-3-flash-preview"


def normalize_model_name(model_name: str | None) -> str:
    name = (model_name or "").strip()
    if not name:
        return DEFAULT_MODEL
    return MODEL_ALIASES.get(name, name)


def get_default_model_name() -> str:
    return normalize_model_name(os.environ.get("DEFAULT_MODEL", DEFAULT_MODEL))
