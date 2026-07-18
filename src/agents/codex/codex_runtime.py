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
import sys
import time
from typing import Any, Callable, Dict, Optional, Tuple

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
        warm_pool: Optional[Any] = None,
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
        # TTFT warm-keep (plans/codex-ttft-remediation.md): one per-process pool
        # of session/thread/user-bound workers. Default ON for hosted (where the
        # ~8.5s per-turn rebuild was measured), opt-in for self-host via
        # CODEX_WARM_KEEP=1, and CODEX_WARM_KEEP=0 disables everywhere.
        # Injectable so tests share one pool between the handler and the
        # engines their explicit engine_factory builds.
        self._pool = warm_pool if warm_pool is not None else (
            self._build_pool() if enabled else None)
        # The bound MCP subprocess must read the SAME state.db as the app (so it
        # finds the session it is bound to). Pass the app's data dir through as
        # the engine's mcp_data_dir → config.toml's RTL_DATA_DIR.
        self._engine_factory = engine_factory or (lambda: CodexEngine(
            enabled=enabled,
            state_dir=os.environ.get("SILICONCREW_CODEX_STATE_DIR", "/app/codex-state"),
            local_sqlite_dir=os.environ.get("SILICONCREW_CODEX_SQLITE_DIR", "/app/codex-sqlite"),
            mcp_data_dir=mcp_data_dir,
            warm_pool=self._pool,
        ))

    @staticmethod
    def _build_pool():
        raw = (os.environ.get("CODEX_WARM_KEEP") or "").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return None
        if raw in ("1", "true", "yes", "on"):
            enabled = True
        else:  # unset → hosted default-on, self-host default-off (untouched)
            from src.platform_engines.settings import get_settings

            enabled = get_settings().hosted
        if not enabled:
            return None
        from src.agents.codex.codex_warm import CodexWorkerPool

        return CodexWorkerPool()

    def _system_prompt(self) -> str:
        # ONE composition used by run_turn AND prewarm — the worker fingerprint
        # includes the prompt, so the two must build it identically or the
        # first real turn would discard its own pre-warmed worker.
        policy_on = os.environ.get("CODEX_TOOL_POLICY", "1").lower() not in ("0", "false", "no")
        return self._load_system_prompt() + (_CODEX_TOOL_POLICY if policy_on else "")

    def on_thread_deleted(self, thread_id: str) -> None:
        """Drop any warm worker for a deleted thread (registry cleanup hook)."""
        if self._pool is not None:
            self._pool.close_thread_sync(thread_id)

    def worker_state(self, *, session_id: str, thread_id: str, user_id) -> str:
        """Honest readiness for the UI: ready | starting | cold | unavailable."""
        from src.agents.codex.codex_warm import STATE_UNAVAILABLE

        if not self._enabled or self._pool is None:
            return STATE_UNAVAILABLE
        return self._pool.state_for((session_id, thread_id, user_id or ""))

    async def prewarm(self, *, session_id: str, thread_id: str, user_id,
                      workspace: str, tier=None, auth_token=None,
                      thread_row=None) -> str:
        """Start (or confirm) this thread's worker WITHOUT waiting for it (3B).

        Returns the resulting state. Anything that would make a real turn fail
        with an actionable error (no key, Codex disabled) reports "unavailable"
        here — the turn path owns the user-facing error, prewarm never spawns
        speculatively without resolvable auth.
        """
        from src.agents.codex.codex_warm import STATE_UNAVAILABLE

        if not self._enabled or self._pool is None:
            return STATE_UNAVAILABLE
        model = self._model_for(thread_row)
        api_key = None
        account_home = self._account_home_for(user_id)
        if not account_home:
            try:
                key = self._resolve_key(user_id, model)
            except Exception:
                return STATE_UNAVAILABLE
            api_key = getattr(key, "api_key", None)
            if getattr(key, "model", None):
                model = self._normalize_model(key.model)
            if not api_key:
                return STATE_UNAVAILABLE

        engine = self._engine_factory()
        if getattr(engine, "warm_pool", None) is None:
            return STATE_UNAVAILABLE
        try:
            engine.check_available()
        except CodexUnavailable:
            return STATE_UNAVAILABLE
        turn = CodexTurn(
            session_id=session_id, thread_id=thread_id, message="",
            workspace=workspace, user_id=user_id, model_name=model,
            api_key=api_key,
            external_thread_id=self._store.get_external_thread_id(thread_id),
            system_prompt=self._system_prompt(), tier=tier,
            codex_account_home=None if api_key else account_home,
            sandbox=os.environ.get("CODEX_SANDBOX", "read-only"),
            reasoning_effort=(thread_row or {}).get("reasoning_effort"),
            mcp_token=auth_token,
            history=self._store.list_messages(thread_id),
        )
        key_tuple = engine._worker_key(turn)
        state = self._pool.ensure(
            key_tuple, engine._worker_fingerprint(turn),
            lambda: engine.spawn_worker(turn),
        )
        print(
            f"[CODEX-TIMING] thread={thread_id} event=prewarm state={state}",
            file=sys.stderr,
        )
        return state

    def _model_for(self, thread_row: Optional[dict]) -> str:
        model = (thread_row or {}).get("model") or self._default_model
        return self._normalize_model(model)

    async def run_turn(self, ctx: RuntimeTurnContext) -> None:
        # --- server-side timing instrumentation (additive; logging only) ---
        # Cloud Run shows nothing today about where a Codex turn spends its
        # time (see plans note); these lines are the only place that sees
        # every tool call uniformly, regardless of which tool it is. Grep for
        # "[CODEX-TIMING]" in logs. time.monotonic() for durations,
        # wall-clock only for the human-readable start line.
        turn_start = time.monotonic()
        # call_id -> (monotonic start, tool name), so a tool_result (which
        # only carries the call_id) can be matched back to its tool_call.
        _tool_call_starts: Dict[str, Tuple[float, str]] = {}
        print(
            f"[CODEX-TIMING] thread={ctx.thread_id} turn={ctx.turn_id} event=turn_start",
            file=sys.stderr,
        )

        def _log_turn_end(status: str) -> None:
            elapsed = time.monotonic() - turn_start
            print(
                f"[CODEX-TIMING] thread={ctx.thread_id} turn={ctx.turn_id} "
                f"event=turn_end status={status} elapsed={elapsed:.2f}s",
                file=sys.stderr,
            )

        # Snapshot prior transcript BEFORE persisting this turn's own user
        # message, so it never leaks into itself: if thread_resume later fails
        # (its rollout lost on a dead Cloud Run instance), the engine seeds the
        # fresh thread with exactly what happened before this turn (see
        # CodexTurn.history / codex_engine.stream_turn's fallback branch).
        prior_messages = self._store.list_messages(ctx.thread_id)
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
                _log_turn_end("no_key")
                return
            api_key = getattr(key, "api_key", None)
            if getattr(key, "model", None):
                model = self._normalize_model(key.model)
            if not api_key:
                await ctx.emit(RuntimeEvent.error(
                    "Codex needs an OpenAI API key or a connected Codex account.",
                    code="no_key"))
                _log_turn_end("no_key")
                return

        external_id = self._store.get_external_thread_id(ctx.thread_id)
        engine = self._engine_factory()

        await ctx.emit(RuntimeEvent.start())
        assistant_content = ""   # full turn text (for persistence)
        current_segment = ""     # text of the CURRENT block; resets when a tool/
                                 # reasoning/plan block interrupts, so a follow-up
                                 # text segment renders fresh instead of repeating
                                 # the earlier segment (the shared renderer starts a
                                 # new text block after any non-text block).
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
                system_prompt=self._system_prompt(),
                tier=ctx.tier,
                codex_account_home=None if api_key else account_home,
                # LangChain-parity default: read-only so Codex acts only through
                # the SiliconCrew MCP tools (override with CODEX_SANDBOX).
                sandbox=os.environ.get("CODEX_SANDBOX", "read-only"),
                reasoning_effort=(ctx.thread_row or {}).get("reasoning_effort"),
                images=ctx.images,
                mcp_token=ctx.auth_token,
                history=prior_messages,
            )):
                if ev.type == "start":
                    new_external_id = ev.external_thread_id or new_external_id
                elif ev.type == "text" and ev.content:
                    # Engine emits deltas as `text`; stream the CURRENT segment
                    # (cumulative within the block, not the whole turn) so a text
                    # segment after a tool/reasoning block doesn't repeat earlier
                    # text. assistant_content keeps the full turn for persistence.
                    current_segment += ev.content
                    assistant_content += ev.content
                    await ctx.emit(RuntimeEvent.text_delta(current_segment))
                elif ev.type == "reasoning" and ev.content:
                    current_segment = ""  # a new (non-text) block ends the segment
                    await ctx.emit(RuntimeEvent.reasoning(ev.content))
                elif ev.type == "plan" and ev.content:
                    current_segment = ""
                    await ctx.emit(RuntimeEvent.plan(ev.content))
                elif ev.type == "diff" and ev.content:
                    current_segment = ""
                    await ctx.emit(RuntimeEvent("diff", {"content": ev.content}))
                elif ev.type == "compaction":
                    current_segment = ""
                    await ctx.emit(RuntimeEvent("compaction", {"content": ev.content or "Conversation context compacted"}))
                elif ev.type == "model_rerouted":
                    await ctx.emit(RuntimeEvent("model_rerouted", ev.metadata))
                elif ev.type == "tool_call" and ev.tool:
                    current_segment = ""
                    tool_calls.append(ev.tool)
                    tool_name = ev.tool.get("name", "unknown") if isinstance(ev.tool, dict) else "unknown"
                    call_id = ev.tool_call_id or (ev.tool.get("id") if isinstance(ev.tool, dict) else None)
                    if call_id:
                        _tool_call_starts[call_id] = (time.monotonic(), tool_name)
                    print(
                        f"[CODEX-TIMING] thread={ctx.thread_id} turn={ctx.turn_id} "
                        f"tool={tool_name} call_id={call_id} event=tool_call_start",
                        file=sys.stderr,
                    )
                    await ctx.emit(RuntimeEvent.tool_call(ev.tool))
                elif ev.type == "tool_result" and ev.tool_call_id:
                    result = {"tool_call_id": ev.tool_call_id,
                              "status": ev.status or "success", "content": ev.content or ""}
                    tool_results.append(result)
                    started = _tool_call_starts.pop(ev.tool_call_id, None)
                    if started is not None:
                        start_ts, tool_name = started
                        elapsed = time.monotonic() - start_ts
                        print(
                            f"[CODEX-TIMING] thread={ctx.thread_id} turn={ctx.turn_id} "
                            f"tool={tool_name} call_id={ev.tool_call_id} status={result['status']} "
                            f"elapsed={elapsed:.2f}s",
                            file=sys.stderr,
                        )
                    else:
                        # No matching tool_call seen (shouldn't happen; logged
                        # anyway so the log stream is never silently missing).
                        print(
                            f"[CODEX-TIMING] thread={ctx.thread_id} turn={ctx.turn_id} "
                            f"tool=unknown call_id={ev.tool_call_id} status={result['status']} "
                            f"elapsed=unknown (no matching tool_call_start)",
                            file=sys.stderr,
                        )
                    await ctx.emit(RuntimeEvent.tool_result(**result))
                elif ev.type in {"usage", "done"}:
                    in_tokens = ev.usage.input_tokens or in_tokens
                    out_tokens = ev.usage.output_tokens or out_tokens
                    if ev.type == "done":
                        completed = True
        except CodexUnavailable as exc:
            # Availability — Codex not enabled/installed; UI prompts to enable/connect.
            await ctx.emit(RuntimeEvent.error(exc.message, code="codex_unavailable"))
            _log_turn_end("codex_unavailable")
            return
        except CodexTurnError as exc:
            # A real turn failure (SDK/model/quota) — distinct from availability.
            await ctx.emit(RuntimeEvent.error(exc.message, code="codex_turn_failed"))
            _log_turn_end("codex_turn_failed")
            return
        except Exception as exc:  # noqa: BLE001  (CancelledError is BaseException; it propagates for stop/supersede)
            await ctx.emit(RuntimeEvent.error(f"Codex turn failed: {exc}", code="codex_turn_failed"))
            _log_turn_end("error")
            return

        # Account-auth turn may have refreshed/rotated the token (the engine
        # synced it back to the account home) — persist it to the durable store.
        if account_home and not api_key:
            self._persist_credential(ctx.user_id)

        # Close the authoritative text block (the LAST segment only — earlier
        # segments were already finalized before their interrupting block).
        if current_segment:
            await ctx.emit(RuntimeEvent.text(current_segment))
        if assistant_content or tool_calls or tool_results:
            self._store.append_message(
                ctx.thread_id, "assistant", assistant_content,
                tool_metadata={"tool_calls": tool_calls, "tool_results": tool_results})
        # Persist external_thread_id ONLY on a completed turn (a failed turn must
        # not corrupt resume state).
        if completed and new_external_id and new_external_id != external_id:
            self._store.set_external_thread_id(ctx.thread_id, new_external_id)

        _log_turn_end("completed" if completed else "incomplete")
        await ctx.emit(RuntimeEvent.done({"input": in_tokens, "output": out_tokens}))
