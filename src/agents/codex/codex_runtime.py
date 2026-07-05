"""Codex runtime handler — the RuntimeHandler the registry dispatches to.

Orchestrates: resolve model/key/account → run the Codex engine → translate its
events into the shared presentation contract (ctx.emit) → persist the transcript
+ external_thread_id (Codex's checkpointer substitute). Shared services
(session_manager, llm-key provider, auth manager, system-prompt loader) are
INJECTED at registration so this module never imports api.py (no cycle) and the
dependency arrow stays codex → shared.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

from src.agents.codex.codex_engine import CodexEngine, CodexTurn, CodexTurnError, CodexUnavailable
from src.agents.runtime_registry import RuntimeEvent, RuntimeTurnContext


# Appended to the architect system prompt for Codex turns so the agent behaves
# like the native tool-calling agent: SiliconCrew MCP tools are its ONLY levers.
# Paired with deny_all approval (exec is blocked at the gate), but the prompt is
# what makes Codex reach for the right tool in the first place rather than shell.
_CODEX_TOOL_POLICY = """

# Tool policy — STRICT (SiliconCrew)
You are the SiliconCrew RTL agent. Use ONLY the SiliconCrew MCP tools (the
`siliconcrew` server: get_manifest, list_files_tool, read_file, write_file,
edit_file_tool, linter_tool, simulation_tool, run_isolated_simulation,
cocotb_tool, sby_tool, schematic_tool, waveform_tool, start_synthesis, etc.)
for EVERYTHING — inspecting, reading, editing, linting, simulation, formal,
and synthesis.

Do NOT use the shell/bash/exec (no cat, ls, sed, printf, rg, grep, python, git)
and do NOT use apply_patch. To read a file, call read_file. To change a file,
call the SiliconCrew write/edit tool. If no SiliconCrew tool fits a request,
say so plainly — never fall back to the shell.
"""


class CodexRuntimeHandler:
    """Runs one Codex turn end to end for the chat shell."""

    runtime_id = "codex"

    def __init__(
        self,
        *,
        codex_store,
        session_manager,
        llm_key_resolve: Callable[[Optional[str], str], Any],
        account_home_for: Callable[[Optional[str]], Optional[str]],
        system_prompt_loader: Callable[[], str],
        default_model: str,
        normalize_model: Callable[[str], str],
        enabled: bool,
        mcp_data_dir: Optional[str] = None,
        engine_factory: Optional[Callable[..., CodexEngine]] = None,
        persist_credential: Optional[Callable[[Optional[str]], None]] = None,
    ):
        self._store = codex_store
        self._sessions = session_manager
        self._resolve_key = llm_key_resolve
        self._account_home_for = account_home_for
        # Called after an account-auth turn to save the (refreshed) auth.json to
        # the durable credential store (hosted). No-op in self-host.
        self._persist_credential = persist_credential or (lambda _uid: None)
        self._load_system_prompt = system_prompt_loader
        self._default_model = default_model
        self._normalize_model = normalize_model
        self._enabled = enabled
        # The bound MCP subprocess must read the SAME state.db as the app (so it
        # finds the session it is bound to). Pass the app's data dir through as
        # the engine's mcp_data_dir → config.toml's RTL_DATA_DIR.
        self._engine_factory = engine_factory or (lambda: CodexEngine(
            enabled=enabled,
            state_dir=os.environ.get("SILICONCREW_CODEX_STATE_DIR", "/app/codex-state"),
            local_sqlite_dir=os.environ.get("SILICONCREW_CODEX_SQLITE_DIR", "/app/codex-sqlite"),
            mcp_data_dir=mcp_data_dir,
        ))

    def _model_for(self, thread_row: Optional[dict]) -> str:
        model = (thread_row or {}).get("model") or self._default_model
        return self._normalize_model(model)

    async def run_turn(self, ctx: RuntimeTurnContext) -> None:
        # Persist the user message first (mirrors the native path's ordering).
        self._store.append_message(ctx.thread_id, "user", ctx.message)

        model = self._model_for(ctx.thread_row)
        api_key: Optional[str] = None
        account_home = self._account_home_for(ctx.user_id)
        # BYOK unless account auth is present (a BYOK key + account auth silently
        # zeroes tokens — so account auth wins and forces api_key=None).
        if not account_home:
            try:
                key = self._resolve_key(ctx.user_id, model)
            except Exception as exc:  # noqa: BLE001 - structured, actionable error
                await ctx.emit(RuntimeEvent.error(
                    "Codex needs an OpenAI API key or a connected Codex account. "
                    f"({exc})", code="no_key"))
                return
            api_key = getattr(key, "api_key", None)
            if getattr(key, "model", None):
                model = self._normalize_model(key.model)
            if not api_key:
                await ctx.emit(RuntimeEvent.error(
                    "Codex needs an OpenAI API key or a connected Codex account.",
                    code="no_key"))
                return

        external_id = self._store.get_external_thread_id(ctx.thread_id)
        engine = self._engine_factory()

        await ctx.emit(RuntimeEvent.start())
        assistant_content = ""
        tool_calls: list = []
        tool_results: list = []
        in_tokens = 0
        out_tokens = 0
        completed = False
        new_external_id: Optional[str] = None

        try:
            async for ev in engine.stream_turn(CodexTurn(
                session_id=ctx.session_id, thread_id=ctx.thread_id, message=ctx.message,
                workspace=ctx.workspace, user_id=ctx.user_id, model_name=model,
                api_key=api_key, external_thread_id=external_id,
                system_prompt=self._load_system_prompt()
                    + (_CODEX_TOOL_POLICY if os.environ.get("CODEX_TOOL_POLICY", "1").lower() not in ("0", "false", "no") else ""),
                tier=ctx.tier,
                codex_account_home=None if api_key else account_home,
                # LangChain-parity default: read-only so Codex acts only through
                # the SiliconCrew MCP tools (override with CODEX_SANDBOX).
                sandbox=os.environ.get("CODEX_SANDBOX", "read-only"),
                mcp_token=ctx.auth_token,
            )):
                if ev.type == "start":
                    new_external_id = ev.external_thread_id or new_external_id
                elif ev.type == "text" and ev.content:
                    # Engine emits deltas as `text`; stream as text_delta with
                    # cumulative content, matching the shared renderer.
                    assistant_content += ev.content
                    await ctx.emit(RuntimeEvent.text_delta(assistant_content))
                elif ev.type == "reasoning" and ev.content:
                    await ctx.emit(RuntimeEvent.reasoning(ev.content))
                elif ev.type == "plan" and ev.content:
                    await ctx.emit(RuntimeEvent.plan(ev.content))
                elif ev.type == "tool_call" and ev.tool:
                    tool_calls.append(ev.tool)
                    await ctx.emit(RuntimeEvent.tool_call(ev.tool))
                elif ev.type == "tool_result" and ev.tool_call_id:
                    result = {"tool_call_id": ev.tool_call_id,
                              "status": ev.status or "success", "content": ev.content or ""}
                    tool_results.append(result)
                    await ctx.emit(RuntimeEvent.tool_result(**result))
                elif ev.type in {"usage", "done"}:
                    in_tokens = ev.usage.input_tokens or in_tokens
                    out_tokens = ev.usage.output_tokens or out_tokens
                    if ev.type == "done":
                        completed = True
        except CodexUnavailable as exc:
            # Availability — Codex not enabled/installed; UI prompts to enable/connect.
            await ctx.emit(RuntimeEvent.error(exc.message, code="codex_unavailable"))
            return
        except CodexTurnError as exc:
            # A real turn failure (SDK/model/quota) — distinct from availability.
            await ctx.emit(RuntimeEvent.error(exc.message, code="codex_turn_failed"))
            return
        except Exception as exc:  # noqa: BLE001  (CancelledError is BaseException; it propagates for stop/supersede)
            await ctx.emit(RuntimeEvent.error(f"Codex turn failed: {exc}", code="codex_turn_failed"))
            return

        # Account-auth turn may have refreshed/rotated the token (the engine
        # synced it back to the account home) — persist it to the durable store.
        if account_home and not api_key:
            self._persist_credential(ctx.user_id)

        # Close the authoritative text block, then persist once.
        if assistant_content:
            await ctx.emit(RuntimeEvent.text(assistant_content))
        if assistant_content or tool_calls or tool_results:
            self._store.append_message(
                ctx.thread_id, "assistant", assistant_content,
                tool_metadata={"tool_calls": tool_calls, "tool_results": tool_results})
        # Persist external_thread_id ONLY on a completed turn (a failed turn must
        # not corrupt resume state).
        if completed and new_external_id and new_external_id != external_id:
            self._store.set_external_thread_id(ctx.thread_id, new_external_id)

        await ctx.emit(RuntimeEvent.done({"input": in_tokens, "output": out_tokens}))
