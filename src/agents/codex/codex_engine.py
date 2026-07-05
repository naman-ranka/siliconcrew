"""Codex SDK adapter — subprocess app-server behind an injectable seam.

Ported faithfully from the proven reference engine (see
plans/codex-engine-reference.md §1-3), adapted to this codex-owned module with
its own internal event/turn dataclasses. The SDK object/event surface (§3) is
the beta ``openai_codex`` contract and the only part not verifiable without live
creds; ``sdk_factory`` is injectable so the whole translation is unit-testable
against a fake stream.

The engine yields internal :class:`CodexEvent`s; the runtime handler
(codex_runtime.py) maps those to the shared presentation contract.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Optional

CodexEventType = str  # start | text | tool_call | tool_result | usage | done


class CodexUnavailable(RuntimeError):
    """Codex is valid but not configured/available (rendered as a clean error)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class CodexUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class CodexEvent:
    type: CodexEventType
    content: Optional[str] = None
    tool: Optional[Dict[str, Any]] = None
    tool_call_id: Optional[str] = None
    status: Optional[str] = None
    usage: CodexUsage = field(default_factory=CodexUsage)
    external_thread_id: Optional[str] = None


@dataclass(frozen=True)
class CodexTurn:
    session_id: str
    thread_id: str
    message: str
    workspace: str
    user_id: Optional[str]
    model_name: str
    api_key: Optional[str] = None
    external_thread_id: Optional[str] = None
    system_prompt: Optional[str] = None
    tier: Optional[str] = None
    codex_account_home: Optional[str] = None
    sandbox: Optional[str] = None
    mcp_token: Optional[str] = None


# --- small helpers (SDK object duck-typing) --------------------------------

def _safe_component(value: Optional[str], fallback: str = "default") -> str:
    raw = (value or fallback).strip() or fallback
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return (safe or fallback)[:96]


def _toml_string(value: Any) -> str:
    return json.dumps(str(value))


def _toml_array(values: list[Any]) -> str:
    return "[" + ", ".join(_toml_string(v) for v in values) + "]"


def _workspace_base(workspace: str, session_id: str) -> str:
    path = Path(workspace).resolve()
    session_parts = tuple(p for p in session_id.replace("\\", "/").split("/") if p)
    if session_parts and tuple(path.parts[-len(session_parts):]) == session_parts:
        for _ in session_parts:
            path = path.parent
        return str(path)
    return str(path.parent)


def _mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with suppress(OSError, NotImplementedError):
        path.chmod(0o700)


def _stringify_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(getattr(item, "text", None) or item))
        return "\n".join(p for p in parts if p)
    return str(value)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _root(value: Any) -> Any:
    return getattr(value, "root", value)


def _event_payload(event: Any) -> Any:
    return getattr(event, "payload", None) or getattr(event, "params", None)


def _item_from_payload(payload: Any) -> Any:
    return _root(getattr(payload, "item", None))


def _tool_from_item(item: Any) -> Optional[dict[str, Any]]:
    item_type = _enum_value(getattr(item, "type", "")).lower()
    if item_type not in {"mcptoolcall", "dynamictoolcall", "commandexecution"}:
        return None
    call_id = str(getattr(item, "id", "") or "")
    if item_type == "commandexecution":
        name = "command"
        args: dict[str, Any] = {"command": getattr(item, "command", "")}
    else:
        name = str(getattr(item, "tool", "") or "unknown")
        args_value = getattr(item, "arguments", {}) or {}
        args = args_value if isinstance(args_value, dict) else {"arguments": args_value}
    return {"id": call_id, "name": name, "args": args}


def _tool_result_from_item(item: Any) -> Optional[dict[str, str]]:
    item_type = _enum_value(getattr(item, "type", "")).lower()
    if item_type not in {"mcptoolcall", "dynamictoolcall", "commandexecution"}:
        return None
    call_id = str(getattr(item, "id", "") or "")
    status = _enum_value(getattr(item, "status", "")).lower()
    if item_type == "commandexecution":
        exit_code = getattr(item, "exit_code", None)
        status = "success" if exit_code in (0, None) else "error"
        content = _stringify_content(getattr(item, "aggregated_output", None))
    else:
        error = getattr(item, "error", None)
        result = getattr(item, "result", None)
        content = _stringify_content(getattr(result, "content", None))
        if error is not None:
            status = "error"
            content = _stringify_content(getattr(error, "message", None)) or content
        elif status in {"completed", "success"}:
            status = "success"
        elif status == "failed":
            status = "error"
    return {"tool_call_id": call_id, "status": status or "success", "content": content}


def _usage_from_payload(payload: Any) -> CodexUsage:
    token_usage = getattr(payload, "token_usage", None) or getattr(payload, "tokenUsage", None)
    last = getattr(token_usage, "last", None) or token_usage
    return CodexUsage(
        input_tokens=int(getattr(last, "input_tokens", 0) or getattr(last, "inputTokens", 0) or 0),
        output_tokens=int(getattr(last, "output_tokens", 0) or getattr(last, "outputTokens", 0) or 0),
    )


class CodexEngine:
    """Runs one Codex turn via the SDK subprocess app-server."""

    def __init__(
        self,
        enabled: bool = False,
        *,
        state_dir: Optional[str] = None,
        local_sqlite_dir: Optional[str] = None,
        mcp_data_dir: Optional[str] = None,
        repo_root: Optional[str] = None,
        sdk_factory: Optional[Callable[..., Any]] = None,
    ):
        self.enabled = enabled
        self.state_dir = os.path.abspath(
            state_dir or os.environ.get("SILICONCREW_CODEX_STATE_DIR")
            or os.path.join(os.path.expanduser("~"), ".siliconcrew", "codex-runtime")
        )
        self.local_sqlite_dir = os.path.abspath(
            local_sqlite_dir or os.environ.get("SILICONCREW_CODEX_SQLITE_DIR") or "/app/codex-sqlite"
        )
        self.mcp_data_dir = os.path.abspath(
            mcp_data_dir or os.environ.get("RTL_DATA_DIR") or self.state_dir
        )
        self.repo_root = os.path.abspath(
            repo_root or os.environ.get("SILICONCREW_REPO_ROOT")
            or os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        )
        self.sdk_factory = sdk_factory

    def check_available(self) -> Any:
        if not self.enabled:
            raise CodexUnavailable(
                "Codex runtime is not enabled on this server. Set CODEX_ENABLED=1 "
                "after configuring Codex credentials."
            )
        if self.sdk_factory is not None:
            return None  # injected fake SDK; no import needed
        try:
            import openai_codex
        except ImportError as exc:
            raise CodexUnavailable(
                "Codex runtime requires the optional 'openai-codex' package."
            ) from exc
        return openai_codex

    async def stream_turn(self, turn: CodexTurn) -> AsyncIterator[CodexEvent]:
        if False:  # pragma: no cover - keeps this an async generator
            yield CodexEvent(type="done")
        openai_codex = self.check_available()
        self._prepare_paths(turn)
        config = self._sdk_config(openai_codex, turn)
        sdk_factory = self.sdk_factory or getattr(openai_codex, "AsyncCodex")

        try:
            async with sdk_factory(config=config) as codex:
                if turn.api_key:
                    await codex.login_api_key(turn.api_key)
                # Account auth: omit model (an unknown name silently returns 0 tokens).
                effective_model = turn.model_name if turn.api_key else None
                sandbox = self._sdk_sandbox(openai_codex, turn.sandbox)
                thread_kwargs = {k: v for k, v in {
                    "model": effective_model, "cwd": turn.workspace, "sandbox": sandbox,
                    "approval_mode": self._sdk_approval_mode(openai_codex), "service_tier": turn.tier,
                }.items() if v is not None}

                if turn.external_thread_id:
                    try:
                        thread = await codex.thread_resume(turn.external_thread_id, **thread_kwargs)
                    except Exception as e:
                        print(f"[CODEX] resume {turn.external_thread_id} failed ({e}); starting fresh", file=sys.stderr)
                        thread = await codex.thread_start(
                            base_instructions=turn.system_prompt, config=self._thread_config(), **thread_kwargs)
                else:
                    thread = await codex.thread_start(
                        base_instructions=turn.system_prompt, config=self._thread_config(), **thread_kwargs)

                external_thread_id = str(getattr(thread, "id", "") or turn.external_thread_id or "")
                yield CodexEvent(type="start", external_thread_id=external_thread_id)

                turn_kwargs = {k: v for k, v in {
                    "cwd": turn.workspace, "model": effective_model, "sandbox": sandbox,
                    "approval_mode": self._sdk_approval_mode(openai_codex), "service_tier": turn.tier,
                }.items() if v is not None}
                turn_handle = await thread.turn(turn.message, **turn_kwargs)
                async for event in self._stream_sdk_events(turn_handle):
                    yield event
        except CodexUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - structured error for the WS layer
            raise CodexUnavailable(f"Codex runtime failed: {exc}") from exc

    # -- path + config setup --
    def _prepare_paths(self, turn: CodexTurn) -> None:
        user = _safe_component(turn.user_id, "anonymous")
        session = _safe_component(turn.session_id, "session")
        thread = _safe_component(turn.thread_id, "thread")
        self._codex_home = Path(self.state_dir) / "users" / user / "sessions" / session / "threads" / thread
        _mkdir_private(self._codex_home)
        self._codex_sqlite_home = Path(self.local_sqlite_dir) / "users" / user / "sessions" / session / "threads" / thread
        _mkdir_private(self._codex_sqlite_home)
        self._workspace_base = _workspace_base(turn.workspace, turn.session_id)
        self._write_config(self._codex_home / "config.toml", turn, self._workspace_base)
        if turn.codex_account_home:
            self._sync_auth_file(Path(turn.codex_account_home), self._codex_home)

    def _write_config(self, config_path: Path, turn: CodexTurn, workspace_base: str) -> None:
        _mkdir_private(config_path.parent)
        python_exe = os.environ.get("CODEX_MCP_PYTHON", sys.executable)
        mcp_server = os.environ.get("CODEX_MCP_SERVER", os.path.join(self.repo_root, "mcp_server.py"))
        args = [mcp_server, "--transport", "stdio", "--codex-tools", "--bound-session", turn.session_id]
        env = {"RTL_WORKSPACE": workspace_base, "RTL_DATA_DIR": self.mcp_data_dir, "PYTHONUNBUFFERED": "1"}
        token = turn.mcp_token or os.environ.get("CODEX_MCP_BEARER_TOKEN") or os.environ.get("SILICONCREW_MCP_TOKEN")
        if token:
            env["SILICONCREW_MCP_TOKEN"] = token
        lines = [
            "# Generated by SiliconCrew for one Codex chat thread.",
            'cli_auth_credentials_store = "file"',
            # LangChain-parity: the SiliconCrew MCP tools are the agent's ONLY
            # levers. read-only sandbox neuters Codex's native apply_patch (our
            # MCP server runs out-of-sandbox, so its write tools still work); the
            # native shell + web + image tools are turned off; approval_policy
            # 'never' auto-runs MCP calls (no human approver in the chat loop).
            'sandbox_mode = "read-only"',
            # approval_policy=never + approval_mode=deny_all: Codex may not
            # escalate a command outside the sandbox. In THIS container
            # unprivileged user namespaces are disabled, so bwrap (Codex's
            # sandbox) can't start either — verified: every exec_command fails
            # with "bwrap: No permissions to create a new namespace" and cannot
            # escalate. Net: native exec is dead; MCP tools (pre-approved) are the
            # only path. NOTE the block is contingent on the container denying
            # unprivileged userns — keep it disabled; do NOT run Codex privileged.
            'approval_policy = "never"',
            # Steer Codex toward the SiliconCrew MCP tools by removing its native
            # edit tool (apply_patch_tool=false — openai/codex#8161) and shell.
            # NOTE: these are SOFT. Empirically Codex still has other exec paths
            # (unified_exec/exec_command), and its sandbox confines WRITES+NETWORK
            # only — NOT reads. So Codex can still read anything in the container
            # (other sessions, state.db, byok.db). Hard tenant isolation requires
            # an EXTERNAL OS jail exposing only the session workspace (see
            # plans/codex-runtime-extension.md). Do not rely on this for hosted.
            "apply_patch_tool = false",
            "shell_tool = false",
            "",
            "[features]",
            "enable_mcp_apps = true",
            "",
            "[tools]",
            "web_search = false",
            "view_image = false",
            "",
            "[mcp_servers.siliconcrew]",
            f"command = {_toml_string(python_exe)}",
            f"args = {_toml_array(args)}",
            f"cwd = {_toml_string(self.repo_root)}",
            "enabled = true", "required = true",
            "startup_timeout_sec = 20", "tool_timeout_sec = 300",
            'disabled_tools = ["create_session_tool", "list_sessions_tool", "set_active_session", "delete_session_tool"]',
            'default_tools_approval_mode = "approve"', "",
            "[mcp_servers.siliconcrew.env]",
        ]
        lines.extend(f"{k} = {_toml_string(v)}" for k, v in sorted(env.items()))
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with suppress(OSError, NotImplementedError):
            config_path.chmod(0o600)

    def _sync_auth_file(self, source_home: Path, dest_home: Path) -> None:
        source = source_home / "auth.json"
        if not source.exists() or source.stat().st_size <= 0:
            return
        _mkdir_private(dest_home)
        dest = dest_home / "auth.json"
        shutil.copyfile(source, dest)
        with suppress(OSError, NotImplementedError):
            dest.chmod(0o600)

    def _sdk_config(self, openai_codex: Any, turn: CodexTurn) -> Any:
        # env-key scrubbing: the external agent must never see the server's other keys.
        env = {
            "CODEX_HOME": str(self._codex_home), "CODEX_SQLITE_HOME": str(self._codex_sqlite_home),
            "RTL_WORKSPACE": self._workspace_base, "RTL_DATA_DIR": self.mcp_data_dir,
            "ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "OPENAI_API_KEY": "",
        }
        if turn.api_key:
            env["OPENAI_API_KEY"] = turn.api_key
        if os.environ.get("CODEX_ACCESS_TOKEN"):
            env["CODEX_ACCESS_TOKEN"] = os.environ["CODEX_ACCESS_TOKEN"]
        if openai_codex is None:  # injected fake SDK
            return {"cwd": turn.workspace, "env": env}
        return getattr(openai_codex, "CodexConfig")(
            cwd=turn.workspace, env=env,
            client_name="siliconcrew_workbench", client_title="SiliconCrew Workbench",
        )

    def _thread_config(self) -> Optional[dict[str, Any]]:
        effort = os.environ.get("CODEX_MODEL_REASONING_EFFORT")
        return {"model_reasoning_effort": effort} if effort else None

    def _sdk_sandbox(self, openai_codex: Any, sandbox: Optional[str]) -> Any:
        if openai_codex is None:
            return None
        sandbox_cls = getattr(openai_codex, "Sandbox", None)
        if sandbox_cls is None:
            return None
        name = (sandbox or os.environ.get("CODEX_SANDBOX") or "workspace_write").replace("-", "_")
        return getattr(sandbox_cls, name, None)

    def _sdk_approval_mode(self, openai_codex: Any) -> Any:
        # deny_all: deny any command that requests approval/escalation. Combined
        # with approval_policy=never and the container disallowing unprivileged
        # user namespaces (bwrap can't start), Codex's exec is left with no way
        # to run — verified: shell commands fail with a bwrap namespace error and
        # cannot escalate. MCP tools are pre-approved (default_tools_approval_mode
        # ="approve") and unaffected.
        if openai_codex is None:
            return None
        approval_cls = getattr(openai_codex, "ApprovalMode", None)
        if approval_cls is None:
            return None
        return getattr(approval_cls, "deny_all", None) or getattr(approval_cls, "auto_review", None)

    async def _stream_sdk_events(self, turn_handle: Any) -> AsyncIterator[CodexEvent]:
        completed_texts: list[str] = []
        emitted_text_delta = False
        latest_usage = CodexUsage()

        async for event in turn_handle.stream():
            method = str(getattr(event, "method", "") or "")
            payload = _event_payload(event)

            if "error" in method:
                error_msg = ""
                if hasattr(payload, "error") and hasattr(payload.error, "message"):
                    error_msg = payload.error.message
                elif hasattr(payload, "message"):
                    error_msg = payload.message
                if error_msg:
                    raise CodexUnavailable(f"Codex turn failed: {error_msg}")

            if method == "item/agentMessage/delta":
                delta = _stringify_content(getattr(payload, "delta", ""))
                if delta:
                    emitted_text_delta = True
                    yield CodexEvent(type="text", content=delta)
                continue

            if method == "thread/tokenUsage/updated":
                latest_usage = _usage_from_payload(payload)
                yield CodexEvent(type="usage", usage=latest_usage)
                continue

            if method == "item/started":
                item = _item_from_payload(payload)
                tool = _tool_from_item(item)
                if tool and tool.get("id"):
                    yield CodexEvent(type="tool_call", tool=tool, tool_call_id=tool["id"])
                continue

            if method == "item/completed":
                item = _item_from_payload(payload)
                if _enum_value(getattr(item, "type", "")) == "agentMessage":
                    text = _stringify_content(getattr(item, "text", ""))
                    if text:
                        completed_texts.append(text)
                    continue
                result = _tool_result_from_item(item)
                if result and result.get("tool_call_id"):
                    yield CodexEvent(
                        type="tool_result", tool_call_id=result["tool_call_id"],
                        status=result["status"], content=result["content"])
                continue

            if method == "turn/completed":
                if not emitted_text_delta and completed_texts:
                    yield CodexEvent(type="text", content=completed_texts[-1])
                yield CodexEvent(type="done", usage=latest_usage)
                continue
