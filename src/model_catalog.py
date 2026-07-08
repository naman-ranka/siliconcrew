import os


MODEL_ALIASES = {
    # Compat + retired-id aliases, resolved server-side so threads created
    # against an older catalog keep working after a model refresh:
    # - "gemini-3.1-flash" was a docs-compat alias for the Gemini 3 Flash line.
    # - "gemini-3-flash-preview" was our previous default; superseded by the
    #   GA Gemini 3.5 Flash.
    # - "gemini-3.1-flash-lite-preview" was deprecated by Google (2026-05-25)
    #   in favor of the GA id.
    "gemini-3.1-flash": "gemini-3.5-flash",
    "gemini-3-flash-preview": "gemini-3.5-flash",
    "gemini-3.1-flash-lite-preview": "gemini-3.1-flash-lite",
}


# USD per 1M tokens. Superseded-but-still-selectable ids stay listed so cost
# accounting keeps working for existing threads pinned to them.
PRICING = {
    # Google
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    # OpenAI
    "gpt-5.5": {"input": 5.00, "output": 30.00},
    "gpt-5.4-mini": {"input": 0.30, "output": 2.50},
    "gpt-5.3-codex": {"input": 2.00, "output": 12.00},
    # Anthropic
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    # Previous generation (kept for threads that still pin them)
    "gpt-5-mini": {"input": 0.30, "output": 2.50},
    "gpt-5.4": {"input": 2.00, "output": 12.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
}


DEFAULT_MODEL = "gemini-3.5-flash"


# UI-facing model registry — the top current model of each provider plus a
# light/fast and a deep/capable option (verified against provider docs
# 2026-07). Order within a provider = display order. `tier` is a coarse
# speed/capability bucket the picker groups by hint; `hint` is the one-line
# capability/speed note shown under each row.
CATALOG = [
    # Google
    {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash", "provider": "gemini",
     "tier": "balanced", "hint": "Frontier speed/quality default — great for most RTL work."},
    {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash-Lite", "provider": "gemini",
     "tier": "fast", "hint": "Cheapest + quickest; light edits and quick questions."},
    {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro", "provider": "gemini",
     "tier": "capable", "hint": "Deeper reasoning for tricky debugging / architecture."},
    # OpenAI
    {"id": "gpt-5.5", "label": "GPT-5.5", "provider": "openai",
     "tier": "capable", "hint": "OpenAI flagship; strong reasoning and coding."},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 mini", "provider": "openai",
     "tier": "fast", "hint": "Fast and inexpensive OpenAI option."},
    {"id": "gpt-5.3-codex", "label": "GPT-5.3 Codex", "provider": "openai",
     "tier": "capable", "hint": "Code-tuned; thorough on larger designs."},
    # Anthropic
    {"id": "claude-opus-4-8", "label": "Claude Opus 4.8", "provider": "anthropic",
     "tier": "capable", "hint": "Most capable; best for hard, multi-step work."},
    {"id": "claude-sonnet-5", "label": "Claude Sonnet 5", "provider": "anthropic",
     "tier": "balanced", "hint": "Near-Opus quality at Sonnet speed; reliable tool use."},
    {"id": "claude-haiku-4-5", "label": "Claude Haiku 4.5", "provider": "anthropic",
     "tier": "fast", "hint": "Fastest Anthropic model for routine tasks."},
]

PROVIDER_LABELS = {"anthropic": "Anthropic", "openai": "OpenAI", "gemini": "Google"}


# Codex runtime model registry — maintained SEPARATELY from CATALOG (the
# native/LangChain picker). The Codex agent runs on OpenAI models only, and
# not every OpenAI API model is a sensible Codex model, so its picker gets its
# own curated list rather than a provider filter over CATALOG. Ids stay in
# PRICING so cost accounting works for threads pinned to them.
CODEX_DEFAULT_MODEL = "gpt-5.3-codex"

CODEX_CATALOG = [
    {"id": "gpt-5.3-codex", "label": "GPT-5.3 Codex", "provider": "openai",
     "tier": "capable", "hint": "Code-tuned Codex default — best for RTL work."},
    {"id": "gpt-5.5", "label": "GPT-5.5", "provider": "openai",
     "tier": "capable", "hint": "OpenAI flagship; strongest general reasoning."},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 mini", "provider": "openai",
     "tier": "fast", "hint": "Fast and inexpensive for light edits."},
]


def _entries_with_pricing(catalog: list[dict]) -> list[dict]:
    out = []
    for e in catalog:
        entry = dict(e)
        price = PRICING.get(e["id"])
        if price:
            entry["pricing"] = price
        out.append(entry)
    return out


def model_catalog_entries() -> list[dict]:
    """Catalog rows with pricing merged in (for the picker)."""
    return _entries_with_pricing(CATALOG)


def codex_catalog_entries() -> list[dict]:
    """Codex catalog rows with pricing merged in (for the Codex picker)."""
    return _entries_with_pricing(CODEX_CATALOG)


def normalize_model_name(model_name: str | None) -> str:
    name = (model_name or "").strip()
    if not name:
        return DEFAULT_MODEL
    return MODEL_ALIASES.get(name, name)


def get_default_model_name() -> str:
    return normalize_model_name(os.environ.get("DEFAULT_MODEL", DEFAULT_MODEL))
