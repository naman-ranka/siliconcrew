"""Resolving the architect prompt — the ONE place that knows how.

Two callers need this and they have opposite constraints. ``src.agents.architect``
imports LangGraph, which is expensive; ``mcp_server`` is spawned as a subprocess
per Codex client and pays that import on every spawn. That is why a second copy
of this logic grew inside the MCP server, and with it a second answer to "which
prompt is running" and a second fallback policy.

This module has no heavy imports, so both can use it and there is one answer.

There is deliberately NO fallback to an embedded prompt. Serving a stale prompt
when the file is missing turns a bad deploy or a typo'd ARCHITECT_PROMPT_VERSION
into an agent that looks healthy while running the wrong instructions, and
provenance records a version that was never loaded.

The skill index is appended HERE, in the one place every runtime already asks
for a prompt — the native agent, the Codex runtime, the MCP prompt envelope and
the Codex-client prompt tool all go through this function, so all four receive
the same bytes and none of them can forget. A second composition would be a
second list, and the skill that would go missing from it is the always-loaded
one, whose absence produces no error anywhere (finding A3-H2).
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = _REPO_ROOT / "prompts" / "architect"


def resolved_version() -> str:
    """The prompt version this process is configured to run."""
    version = (os.environ.get("ARCHITECT_PROMPT_VERSION", "v3") or "v3").strip().lower()
    return version or "v3"


def prompt_path(version: str | None = None) -> Path:
    return PROMPTS_DIR / f"architect_prompt_{version or resolved_version()}.md"


class PromptUnavailable(RuntimeError):
    """The runtime prompt file is missing, unreadable, or empty."""


def load_system_prompt(path: Path | None = None, with_skills: bool = True,
                      skills=None) -> str:
    """Return the prompt text plus the skill block, or raise
    :class:`PromptUnavailable`.

    An agent running the wrong prompt is worse than one that refuses to start,
    because the failure is invisible.

    ``with_skills=False`` returns the prompt FILE alone. It exists for the
    identity/provenance readers, which hash the file; everything that actually
    drives a model leaves it on.

    ``skills`` is an already-resolved set. Pass it when the caller ALSO stamps
    those skills into a provenance record: resolving here would be a second
    read of the store, and a skill edited between the two reads would reach the
    model while the run recorded the digest of what it replaced. Left None,
    this resolves the caller's own layer as before.
    """
    path = path or prompt_path()
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise PromptUnavailable(
            f"Architect prompt not found at {path}. Check ARCHITECT_PROMPT_VERSION "
            f"(currently {resolved_version()!r}) and that prompts/architect/ shipped "
            f"with this build."
        ) from exc
    except OSError as exc:
        raise PromptUnavailable(f"Architect prompt at {path} could not be read: {exc}") from exc
    if not text:
        raise PromptUnavailable(f"Architect prompt at {path} is empty.")
    if not with_skills:
        return text
    from src.utils.skills import compose_skills_block

    # No try/except: a malformed shipped skill is a bad build, and an agent
    # quietly missing the knowledge it was supposed to have is the failure this
    # whole layer exists to prevent. An absent store composes to "" already.
    return text + compose_skills_block(skills)


def load_with_provenance() -> tuple[str, str, str]:
    """``(prompt_text, source_label, resolved_version)`` for callers that report
    which prompt they served."""
    version = resolved_version()
    path = prompt_path(version)
    return load_system_prompt(path), str(path), version
