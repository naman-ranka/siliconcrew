"""Codex extension registration — the single wiring seam.

The api layer calls :func:`register_codex_runtime` at startup, guarded by the
CODEX_ENABLED flag and a try/except import, so deleting this package or leaving
the flag off leaves the app exactly native-only. Shared services flow IN as
arguments (dependency injection); nothing here reaches back into api.py.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

from src.agents.codex.codex_runtime import CodexRuntimeHandler
from src.agents.codex.codex_store import build_codex_store
from src.agents.runtime_registry import RuntimeDescriptor, register_runtime


def register_codex_runtime(
    *,
    db_path: str,
    session_manager,
    llm_key_resolve: Callable[[Optional[str], str], Any],
    account_home_for: Callable[[Optional[str]], Optional[str]],
    system_prompt_loader: Callable[[], str],
    default_model: str,
    normalize_model: Callable[[str], str],
    enabled: bool,
    engine_factory: Optional[Callable[..., Any]] = None,
    persist_credential: Optional[Callable[[Optional[str]], None]] = None,
) -> None:
    """Build the Codex store + handler and register them as the 'codex' runtime.

    Idempotent-ish: raises if already registered (a double-wire bug). Safe to
    skip entirely when ``enabled`` is False — the caller gates on the flag.
    """
    store = build_codex_store(db_path)
    store.init_schema()

    handler = CodexRuntimeHandler(
        codex_store=store,
        session_manager=session_manager,
        llm_key_resolve=llm_key_resolve,
        account_home_for=account_home_for,
        system_prompt_loader=system_prompt_loader,
        default_model=default_model,
        normalize_model=normalize_model,
        enabled=enabled,
        # The bound MCP subprocess must open the same DB as the app.
        mcp_data_dir=os.path.dirname(db_path),
        engine_factory=engine_factory,
        persist_credential=persist_credential,
    )

    def _on_thread_deleted(thread_id, user_id):
        # Codex owns its transcript; the shared delete path calls this via the
        # registry so it never references Codex directly. Also drops any warm
        # worker bound to the deleted thread (TTFT warm-keep lifecycle).
        store.delete_for_thread(thread_id)
        handler.on_thread_deleted(thread_id)

    register_runtime(
        RuntimeDescriptor(id="codex", display_name="Codex"),
        handler,
        on_thread_deleted=_on_thread_deleted,
    )
    return store
