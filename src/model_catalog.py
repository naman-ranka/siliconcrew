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


# UI-facing model registry. Order within a provider = display order. `tier` is a
# coarse speed/capability bucket the picker groups by hint; `hint` is the
# one-line capability/speed note shown under each row.
CATALOG = [
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash", "provider": "gemini",
     "tier": "fast", "hint": "Fast, low-cost default — great for most RTL work."},
    {"id": "gemini-3.1-flash-lite-preview", "label": "Gemini 3.1 Flash Lite", "provider": "gemini",
     "tier": "fast", "hint": "Cheapest + quickest; light edits and quick questions."},
    {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro", "provider": "gemini",
     "tier": "capable", "hint": "Deeper reasoning for tricky debugging / architecture."},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 mini", "provider": "openai",
     "tier": "fast", "hint": "Fast and inexpensive OpenAI option."},
    {"id": "gpt-5-mini", "label": "GPT-5 mini", "provider": "openai",
     "tier": "fast", "hint": "Compact OpenAI model for routine tasks."},
    {"id": "gpt-5.4", "label": "GPT-5.4", "provider": "openai",
     "tier": "capable", "hint": "Strong general reasoning."},
    {"id": "gpt-5.3-codex", "label": "GPT-5.3 Codex", "provider": "openai",
     "tier": "capable", "hint": "Code-tuned; thorough on larger designs."},
    {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6", "provider": "anthropic",
     "tier": "balanced", "hint": "Balanced quality/speed; reliable tool use."},
    {"id": "claude-opus-4-6", "label": "Claude Opus 4.6", "provider": "anthropic",
     "tier": "capable", "hint": "Most capable; best for hard, multi-step work."},
]

PROVIDER_LABELS = {"anthropic": "Anthropic", "openai": "OpenAI", "gemini": "Google"}


def model_catalog_entries() -> list[dict]:
    """Catalog rows with pricing merged in (for the picker)."""
    out = []
    for e in CATALOG:
        entry = dict(e)
        price = PRICING.get(e["id"])
        if price:
            entry["pricing"] = price
        out.append(entry)
    return out


def normalize_model_name(model_name: str | None) -> str:
    name = (model_name or "").strip()
    if not name:
        return DEFAULT_MODEL
    return MODEL_ALIASES.get(name, name)


def get_default_model_name() -> str:
    return normalize_model_name(os.environ.get("DEFAULT_MODEL", DEFAULT_MODEL))
