"""
SiliconCrew Architect - FastAPI Backend

Production-grade API server for the RTL Design Agent.
Provides REST endpoints and WebSocket streaming for the Next.js frontend.
"""

import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yaml

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
# The checkpointer (sqlite self-host / pooled Postgres hosted) is engine-selected
# in src/platform_engines/checkpointer.py; api.py imports open_checkpointer below.

from src.agents.architect import create_architect_agent, load_system_prompt
from src.agents import runtime_registry
from src.model_catalog import DEFAULT_MODEL, PRICING, normalize_model_name, model_catalog_entries
from src.utils.session_manager import SessionManager
from src.utils.session_context import SessionContext, set_current_session, session_scope
from src.utils.paths import is_within
from src.platform_engines.workspace_provider import get_workspace_provider
from src.platform_engines.identity import Action, AuthError, Identity
from src.platform_engines import auth as auth_engine
from src.platform_engines.llm_keys import (
    build_key_vault,
    build_llm_key_provider,
    HostedTierExhausted,
    VALID_PROVIDERS,
)
from src.platform_engines.settings import get_settings
from src.utils.attempt_logger import log_tool_call, log_tool_result
from src.tools.design_report import save_design_report
from src.tools.synthesis_manager import get_run_dir, list_synthesis_runs
from src.tools import manifest as manifest_mod
from src.api.actions import build_actions_router
from src.api import workspace_fs

# Load environment
load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = os.path.dirname(__file__)
WORKSPACE_DIR = os.environ.get("RTL_WORKSPACE") or os.path.join(BASE_DIR, "workspace")
_DATA_DIR = os.environ.get("RTL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".siliconcrew")
os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(_DATA_DIR, "state.db")

# Initialize Session Manager
session_manager = SessionManager(base_dir=WORKSPACE_DIR, db_path=DB_PATH)

# BYOK vault (envelope-encrypted user API keys). None when BYOK isn't configured
# (no KMS / master key) — the /api/keys endpoints then return 503.
_KEY_VAULT = build_key_vault(get_settings(), db_path=os.path.join(_DATA_DIR, "byok.db"))

# The single LLM-key resolution point: env keys (self-host) or BYOK + capped
# hosted Gemini (hosted). The chat path asks this for a request-scoped key per
# turn so the agent uses the RIGHT key (the user's, the container env, or the
# capped hosted tier) instead of always reading process env.
_LLM_KEY_PROVIDER = build_llm_key_provider(get_settings(), _KEY_VAULT)

# --- Codex runtime extension (optional, flag-gated, removable) --------------
# The ONE sanctioned point where shared code names the Codex package. Guarded by
# the CODEX_ENABLED flag AND a try/except import: with the flag off (or the
# src/agents/codex package deleted) the app is exactly the native-only workbench.
# Nothing else in the shared path imports codex.
_CODEX_AUTH_MANAGER = None
_CODEX_STORE = None
if get_settings().codex_enabled:
    try:
        from src.agents.codex.codex_auth import CodexAccountAuthManager, VaultCodexCredentialStore
        from src.agents.codex.register import register_codex_runtime

        # Durable per-user credential store (hosted): reuse the encrypted,
        # tenant-keyed BYOK vault so the ChatGPT login survives redeploy/scale.
        # None in self-host (no vault) → the local auth_home file is the durable
        # copy, i.e. today's behavior.
        _codex_creds = VaultCodexCredentialStore(_KEY_VAULT) if _KEY_VAULT is not None else None
        _CODEX_AUTH_MANAGER = CodexAccountAuthManager(_DATA_DIR, credential_store=_codex_creds)

        def _codex_account_home_for(uid):
            # Normalize to match the /api/codex/auth endpoints, which store the
            # login under (uid or "anonymous"). In self-host uid is None, so
            # without this the turn would look up None, miss the "anonymous"
            # login, and wrongly fall back to a BYOK key.
            uid = uid or "anonymous"
            # DEFAULT path: the per-user ChatGPT login the user completed via the
            # in-app device-auth flow (/api/codex/auth). This is the only account
            # source out of the box — no credential copying.
            if _CODEX_AUTH_MANAGER and _CODEX_AUTH_MANAGER.is_connected(uid):
                # Restore the durable credential to local disk (hosted) / use the
                # local file (self-host). ensure_local returns None if the
                # credential can't be staged — do NOT fall back to an empty home
                # (that would run an account turn with no auth.json); let it
                # resolve BYOK / fail cleanly instead.
                staged = _CODEX_AUTH_MANAGER.ensure_local(uid)
                if staged:
                    return staged
            # ADVANCED, OFF BY DEFAULT: point CODEX_ACCOUNT_HOME at a
            # pre-provisioned CODEX_HOME (e.g. a mounted service-account login for
            # headless/CI). Unset by default; never mounts a user's personal
            # ~/.codex — the device-auth flow above is the intended path.
            host = os.environ.get("CODEX_ACCOUNT_HOME")
            if host and os.path.exists(os.path.join(host, "auth.json")):
                return host
            return None

        _CODEX_STORE = register_codex_runtime(
            db_path=DB_PATH,
            session_manager=session_manager,
            llm_key_resolve=lambda uid, model: _LLM_KEY_PROVIDER.resolve(uid, model),
            account_home_for=_codex_account_home_for,
            system_prompt_loader=load_system_prompt,
            default_model=DEFAULT_MODEL,
            normalize_model=normalize_model_name,
            enabled=True,
            persist_credential=lambda uid: _CODEX_AUTH_MANAGER.persist(uid),
        )
        print("[API] Codex runtime extension: ENABLED")
    except Exception as exc:  # noqa: BLE001 - codex wiring must never break startup
        print(f"[API] Codex runtime extension disabled (wiring failed): {exc}")
        _CODEX_AUTH_MANAGER = None
        _CODEX_STORE = None


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ProjectCreate(BaseModel):
    name: str


class ProjectPatch(BaseModel):
    # Rename only. The project id/slug is immutable (sessions reference it).
    name: str


class ProjectResponse(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None


class SessionCreate(BaseModel):
    name: str
    model: str = DEFAULT_MODEL
    project_id: Optional[str] = None


class SessionPatch(BaseModel):
    # Both fields optional; a PATCH must provide at least one (else 400).
    # ``name`` is a DISPLAY-ONLY rename: the session id and its workspace
    # directory never change (files/runs/threads all stay keyed by session_id).
    name: Optional[str] = None
    # project_id: None = remove from project. Only applied when the field is
    # actually present in the payload (model_fields_set), so a pure rename
    # never clears the project assignment.
    project_id: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    name: Optional[str] = None
    model_name: Optional[str] = None
    project_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    total_tokens: int = 0
    total_cost: float = 0.0
    # Honest COUNT of chat_threads rows for this session. A fresh session shows
    # 0 until its default "Chat 1" row is created (first thread list / connect);
    # the UI treats 0 as "no chats yet". Never triggers workspace hydration.
    thread_count: int = 0


class MessageResponse(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None


class ThreadCreate(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None
    runtime: Optional[str] = None  # 'langchain' (default) | 'codex'


class ThreadPatch(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None


class MCPConnectComplete(BaseModel):
    external_auth_id: str


class ThreadResponse(BaseModel):
    id: str
    session_id: str
    title: Optional[str] = None
    model: Optional[str] = None
    runtime: Optional[str] = None
    created_at: Optional[str] = None
    last_active: Optional[str] = None


def _thread_to_response(t: dict) -> "ThreadResponse":
    return ThreadResponse(
        id=t["id"],
        session_id=t.get("session_id"),
        title=t.get("title"),
        model=t.get("model"),
        runtime=t.get("runtime"),
        created_at=str(t["created_at"]) if t.get("created_at") else None,
        last_active=str(t["last_active"]) if t.get("last_active") else None,
    )


class FileInfo(BaseModel):
    name: str
    path: str
    type: str
    size: int
    modified: str
    role: Optional[str] = None  # manifest role: rtl|tb|sdc|include|other


class SpecResponse(BaseModel):
    filename: str
    content: str
    parsed: Optional[Dict[str, Any]] = None


class CodeFile(BaseModel):
    filename: str
    content: str
    language: str = "verilog"


class SynthesisRunResponse(BaseModel):
    run_id: str
    status: str
    updated_at: Optional[str] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None
    top_module: Optional[str] = None
    platform: Optional[str] = None
    elapsed_sec: Optional[float] = None
    summary_metrics: Optional[Dict[str, Any]] = None
    auto_checks: Optional[Dict[str, Any]] = None
    report_available: bool = False
    report_filename: Optional[str] = None


class ReportResponse(BaseModel):
    filename: str
    content: str
    run_id: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_clean_content(msg) -> str:
    """Extract clean text content from a message."""
    content = msg.content
    if isinstance(content, list):
        text_blocks = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_blocks.append(block.get("text", ""))
            elif isinstance(block, str):
                text_blocks.append(block)
        return "\n".join(text_blocks)
    return str(content) if content else ""


def calculate_cost(input_tokens: int, output_tokens: int, model_name: str) -> float:
    """Calculate cost based on token usage."""
    canonical_model = normalize_model_name(model_name)
    rates = PRICING.get(canonical_model, PRICING[DEFAULT_MODEL])
    return (input_tokens / 1_000_000 * rates["input"]) + (output_tokens / 1_000_000 * rates["output"])


def format_tool_call_for_api(tool_call: dict) -> dict:
    """Format a tool call for API response."""
    return {
        "id": tool_call.get("id", ""),
        "name": tool_call.get("name", "unknown"),
        "args": tool_call.get("args", {})
    }


def format_tool_result_for_api(content: str) -> dict:
    """Format a tool result for API response."""
    status = "success"

    # Prefer structured tool statuses when the tool returned JSON.
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed_status = parsed.get("status")
            parsed_success = parsed.get("success")
            if isinstance(parsed_status, str) and parsed_status.strip():
                status = parsed_status.strip()
            elif isinstance(parsed_success, bool):
                status = "success" if parsed_success else "error"
    except Exception:
        if "Error" in content or "FAILED" in content or "Fail" in content:
            status = "error"
        elif "Success" in content or "PASSED" in content or "Pass" in content:
            status = "success"

    return {
        "status": status,
        "content": content[:5000] if len(content) > 5000 else content
    }


def resolve_report_path(workspace: str, run_id: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    if run_id:
        run_dir = get_run_dir(workspace, run_id)
        if run_dir:
            report_path = os.path.join(run_dir, "design_report.md")
            if os.path.exists(report_path):
                return report_path, run_id
            return None, run_id
        return None, None

    latest_run_dir = get_run_dir(workspace, None)
    if latest_run_dir:
        report_path = os.path.join(latest_run_dir, "design_report.md")
        if os.path.exists(report_path):
            return report_path, os.path.basename(latest_run_dir)

    report_files = sorted(
        [f for f in os.listdir(workspace) if f.endswith("_report.md")],
        key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
        reverse=True
    )
    if report_files:
        return os.path.join(workspace, report_files[0]), None

    return None, None


# Engine-selected checkpointer (Wave 10): SQLite per-call on self-host, a
# shared app-scoped pooled AsyncPostgresSaver on hosted so conversation content
# survives restart/redeploy/scale and is shared across instances. The seam is
# unchanged for callers — `create_architect_agent(checkpointer=…)` and the
# thread-history reads stay engine-agnostic.
from src.platform_engines.checkpointer import open_checkpointer  # noqa: E402,F401


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print(f"[API] Starting SiliconCrew API server")
    print(f"[API] Workspace: {WORKSPACE_DIR}")
    print(f"[API] Database: {DB_PATH}")

    if not os.path.exists(WORKSPACE_DIR):
        os.makedirs(WORKSPACE_DIR)

    # Single wiring point: select + bind cloud engines (quota store, per-user
    # job queue, ORFS runner, BYOK vault) from settings. No-op in self-host.
    from src.platform_engines.settings import apply_platform_wiring
    apply_platform_wiring()

    # Mount and run MCP server if in hosted mode
    from src.platform_engines.settings import get_settings
    settings = get_settings()

    # Durable checkpointer: build the shared Postgres pool + saver (hosted).
    # Fail-fast — a checkpointer that can't init must abort startup rather than
    # silently run on ephemeral SQLite in production (the data-loss bug). No-op
    # in self-host (stays SQLite per-call).
    from src.platform_engines.checkpointer import init_checkpointer, close_checkpointer
    await init_checkpointer(settings)
    if settings.hosted:
        print("[API] Hosted mode: initializing remote MCP server integration")
        from mcp_server import RTLDesignMCPServer
        mcp_server = RTLDesignMCPServer(codex_tools=True)
        mcp_app, mcp_transport = mcp_server.get_http_app()

        # Store them on app.state
        app.state.mcp_server = mcp_server
        app.state.mcp_transport = mcp_transport

        # Enter the connection context
        mcp_conn_context = mcp_transport.connect()
        streams = await mcp_conn_context.__aenter__()

        # Start the MCP server processing task
        mcp_task = asyncio.create_task(
            mcp_server.server.run(
                streams[0],
                streams[1],
                mcp_server.server.create_initialization_options()
            )
        )
        app.state.mcp_task = mcp_task
        app.state.mcp_conn_context = mcp_conn_context

    yield

    # Shutdown
    print("[API] Shutting down...")
    await close_checkpointer()
    if hasattr(app.state, "mcp_task"):
        print("[API] Stopping remote MCP server...")
        app.state.mcp_task.cancel()
        from contextlib import suppress
        with suppress(asyncio.CancelledError):
            await app.state.mcp_task
        await app.state.mcp_conn_context.__aexit__(None, None, None)


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="SiliconCrew Architect API",
    description="API for the RTL Design Agent",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for the Next.js frontend. The browser now talks to the backend directly
# (cross-origin), so the deployed frontend origin must be allowed. Local dev is
# always permitted; extra origins come from CORS_ALLOW_ORIGINS (comma-separated)
# and/or CORS_ALLOW_ORIGIN_REGEX. The regex lets Terraform allow the frontend
# Cloud Run service by name without referencing its URL (avoids a dependency
# cycle, since the URL isn't known until the service is created).
_cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
_cors_origins += [o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=os.environ.get("CORS_ALLOW_ORIGIN_REGEX") or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# MCP REMOTE SERVICE MOUNTING (HOSTED ONLY)
# =============================================================================

from src.platform_engines.settings import get_settings
if get_settings().hosted:
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from src.platform_engines.mcp_auth import HostedMCPAuthMiddleware, PROTECTED_RESOURCE_PATH
    from starlette.responses import JSONResponse
    from fastapi import Request

    async def handle_mcp_asgi(scope, receive, send):
        parent_app_state = scope["app"].state.parent_app_state
        transport = parent_app_state.mcp_transport
        await transport.handle_request(scope, receive, send)

    mcp_subapp = Starlette(
        debug=False,
        routes=[
            # Starlette strips "/mcp" prefix, so the sub-app sees it as "/"
            Mount("/", app=handle_mcp_asgi)
        ],
        middleware=[
            Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
            Middleware(HostedMCPAuthMiddleware)
        ]
    )
    # Share parent state
    mcp_subapp.state.parent_app_state = app.state

    def mcp_resource_url_from_request(request: Request) -> str:
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("host", request.url.netloc)
        return f"{scheme}://{host}/mcp"

    def mcp_resource_url_from_scope(scope) -> str:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        scheme = headers.get("x-forwarded-proto", scope.get("scheme", "http"))
        host = headers.get("host")
        if not host:
            server = scope.get("server") or ("localhost", 80)
            host = f"{server[0]}:{server[1]}"
        return f"{scheme}://{host}/mcp"

    def mcp_protected_resource_response(resource_url: str) -> JSONResponse:
        from src.platform_engines.mcp_auth import protected_resource_metadata
        return JSONResponse(protected_resource_metadata(resource_url=resource_url))

    class MCPNoSlashMiddleware:
        def __init__(self, app, mcp_app):
            self.app = app
            self.mcp_app = mcp_app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http" and scope.get("path") == f"/mcp{PROTECTED_RESOURCE_PATH}":
                response = mcp_protected_resource_response(mcp_resource_url_from_scope(scope))
                await response(scope, receive, send)
                return

            if scope["type"] == "http" and scope.get("path") == "/mcp":
                sub_scope = dict(scope)
                sub_scope["path"] = "/"
                root_path = scope.get("root_path", "").rstrip("/")
                sub_scope["root_path"] = f"{root_path}/mcp" if root_path else "/mcp"
                await self.mcp_app(sub_scope, receive, send)
                return

            await self.app(scope, receive, send)

    app.add_middleware(MCPNoSlashMiddleware, mcp_app=mcp_subapp)

    app.mount("/mcp", mcp_subapp)

    @app.get(PROTECTED_RESOURCE_PATH)
    async def get_mcp_protected_resource_metadata(request: Request):
        return mcp_protected_resource_response(mcp_resource_url_from_request(request))

    @app.get(f"{PROTECTED_RESOURCE_PATH}/mcp")
    async def get_mcp_scoped_protected_resource_metadata(request: Request):
        return mcp_protected_resource_response(mcp_resource_url_from_request(request))


# =============================================================================
# AUTH DEPENDENCIES
# =============================================================================

def get_identity(authorization: Optional[str] = Header(default=None)) -> Identity:
    """Resolve the caller's Identity from the Authorization header.

    Self-host: always the trusted local user. Hosted: verified OAuth user, or an
    anonymous trial when no token is present. A *present but invalid* token 401s.
    """
    try:
        return auth_engine.authenticate(auth_engine.parse_bearer(authorization))
    except AuthError as e:
        raise HTTPException(status_code=401, detail={"code": e.code, "message": e.message})


def require_signed_in(identity: Identity = Depends(get_identity)) -> Identity:
    """Dependency for save/synth/MCP endpoints — rejects the anonymous trial."""
    try:
        auth_engine.ensure_signed_in(identity)
    except AuthError as e:
        raise HTTPException(status_code=403, detail={"code": e.code, "message": e.message})
    return identity


def _auth_error_status(exc: AuthError) -> int:
    if exc.code in {"auth_unconfigured"}:
        return 503
    if exc.code in {"workos_complete_failed"}:
        return 502
    if exc.code in {"signin_required"}:
        return 403
    return 400


@app.post("/api/mcp/oauth/complete")
async def complete_mcp_oauth(
    payload: MCPConnectComplete,
    identity: Identity = Depends(require_signed_in),
):
    """Complete WorkOS Standalone Connect after SiliconCrew web sign-in.

    WorkOS redirects the browser to the SiliconCrew frontend Login URI with an
    ``external_auth_id``. The frontend signs the user in using the existing web
    AuthKit path, then calls this endpoint with its bearer token. We tell WorkOS
    which authenticated SiliconCrew user completed the login, and return the
    WorkOS redirect URI that continues the OAuth flow back to the AI client.
    """
    from src.platform_engines.mcp_auth import complete_workos_standalone_connect

    try:
        return await complete_workos_standalone_connect(
            payload.external_auth_id,
            identity,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=_auth_error_status(exc),
            detail={"code": exc.code, "message": exc.message},
        )


def _uid(identity: Identity) -> Optional[str]:
    """Tenant id to scope metadata by (None in self-host)."""
    return auth_engine.scoped_user_id(identity)


def _require_owned(session_id: str, identity: Identity) -> str:
    """404 unless the caller owns the session; returns the scoped user id."""
    uid = _uid(identity)
    if not session_manager.owns_session(session_id, uid):
        raise HTTPException(status_code=404, detail="Session not found")
    return uid


def verify_session_access(session_id: str, identity: Identity = Depends(get_identity)) -> Optional[str]:
    """Dependency for workspace/artifact reads: enforce tenant ownership (404).

    FastAPI binds ``session_id`` from the route's path param. Attach to any
    ``/api/workspace/{session_id}/...`` endpoint so a tenant can never read
    another tenant's files. Returns the scoped user id for optional use.
    """
    return _require_owned(session_id, identity)


def _resolve_workspace(session_id: str) -> str:
    """Resolve a session's workspace path through the active WorkspaceProvider.

    In hosted mode the provider materializes the session's object-storage tarball
    into local scratch and returns THAT path, so READS see files written on any
    instance — Cloud Run's local disk is ephemeral and per-instance, so a plain
    ``session_manager.get_workspace_path`` 404s on a cold/other instance even
    though the data is safe in object storage. Self-host returns the same
    ``workspace/<sid>`` dir, so behavior is unchanged. Mirrors the action router
    (``build_actions_router``) and the WebSocket agent path
    (``_ws_provider.workspace_for``). Resolved per-call so a
    ``set_workspace_provider()`` override (tests) is honored. Ownership is
    enforced separately by ``verify_session_access`` / ``_require_owned`` (the
    metadata store), so disk presence is no longer the access gate.
    """
    return get_workspace_provider().workspace_for(session_id)


# =============================================================================
# SESSION ENDPOINTS
# =============================================================================

@app.get("/api/sessions", response_model=List[SessionResponse])
async def list_sessions(identity: Identity = Depends(get_identity)):
    """List the caller's sessions (tenant-scoped in hosted mode)."""
    uid = _uid(identity)
    sessions = session_manager.get_all_sessions(user_id=uid)
    # ONE grouped COUNT over chat_threads for the whole list (not a per-session
    # query, and no workspace hydration). Honest row count: a fresh session's
    # default "Chat 1" row doesn't exist until the first thread list/connect,
    # so it reports 0 ("no chats yet").
    thread_counts = session_manager.count_threads_by_session(user_id=uid)
    result = []

    for session_id in sessions:
        meta = session_manager.get_session_metadata(session_id, user_id=uid)
        result.append(SessionResponse(
            id=session_id,
            name=meta.get("session_name") if meta else None,
            model_name=meta.get("model_name") if meta else None,
            project_id=meta.get("project_id") if meta else None,
            created_at=str(meta.get("created_at")) if meta else None,
            updated_at=str(meta.get("updated_at")) if meta and meta.get("updated_at") else None,
            total_tokens=meta.get("total_tokens", 0) if meta else 0,
            total_cost=meta.get("total_cost", 0.0) if meta else 0.0,
            thread_count=thread_counts.get(session_id, 0),
        ))

    return result


@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(data: SessionCreate, identity: Identity = Depends(require_signed_in)):
    """Create (save) a new session. Requires sign-in (anonymous → use /trial-session)."""
    uid = _uid(identity)
    try:
        model_name = normalize_model_name(data.model)
        session_id = session_manager.create_session(
            tag=data.name, model_name=model_name, project_id=data.project_id, user_id=uid
        )
        meta = session_manager.get_session_metadata(session_id, user_id=uid)

        return SessionResponse(
            id=session_id,
            name=meta.get("session_name") if meta else data.name,
            model_name=model_name,
            project_id=data.project_id,
            created_at=str(meta.get("created_at")) if meta else None,
            updated_at=str(meta.get("updated_at")) if meta and meta.get("updated_at") else None,
            total_tokens=0,
            total_cost=0.0,
            # Creation seeds "Chat 1" (Wave 8) — report the honest count so
            # the client isn't stale until the next list/GET.
            thread_count=1,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/trial-session", response_model=SessionResponse)
async def create_trial_session(data: SessionCreate, identity: Identity = Depends(get_identity)):
    """Anonymous-trial session creation path (lint/sim only).

    Available to anonymous users; the session is owned by the (anonymous)
    identity so tenancy still applies, and synth/save remain blocked downstream
    by quotas + capability gating.
    """
    uid = _uid(identity)
    try:
        model_name = normalize_model_name(data.model)
        session_id = session_manager.create_session(
            tag=data.name, model_name=model_name, project_id=data.project_id, user_id=uid
        )
        meta = session_manager.get_session_metadata(session_id, user_id=uid)
        return SessionResponse(
            id=session_id,
            name=meta.get("session_name") if meta else data.name,
            model_name=model_name,
            project_id=data.project_id,
            created_at=str(meta.get("created_at")) if meta else None,
            updated_at=str(meta.get("updated_at")) if meta and meta.get("updated_at") else None,
            total_tokens=0,
            total_cost=0.0,
            thread_count=1,  # seeded "Chat 1" (Wave 8)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


# NOTE: the catch-all ``GET /api/sessions/{session_id:path}`` is defined LOWER in
# this file (after the /threads sub-routes). ``session_id`` uses the greedy
# ``:path`` converter (session ids can contain a slash for project-scoped
# sessions), so if this GET were registered before ``GET …/threads`` it would
# shadow it — ``/api/sessions/<sid>/threads`` would bind session_id="<sid>/threads"
# and 404. Keep specific GET sub-routes ABOVE the catch-all. See get_session below.


# =============================================================================
# PROJECT ENDPOINTS
# =============================================================================

@app.get("/api/projects", response_model=List[ProjectResponse])
async def list_projects(identity: Identity = Depends(get_identity)):
    """List the caller's projects (tenant-scoped in hosted mode)."""
    projects = session_manager.get_all_projects(user_id=_uid(identity))
    return [ProjectResponse(id=p["id"], name=p["name"], created_at=str(p.get("created_at") or "")) for p in projects]


@app.post("/api/projects", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate, identity: Identity = Depends(require_signed_in)):
    """Create a new project (requires sign-in)."""
    try:
        project = session_manager.create_project(data.name, user_id=_uid(identity))
        return ProjectResponse(id=project["id"], name=project["name"], created_at=str(project["created_at"]))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.patch("/api/projects/{project_id}", response_model=ProjectResponse)
async def rename_project(project_id: str, data: ProjectPatch, identity: Identity = Depends(require_signed_in)):
    """Rename a project (owner only; requires sign-in like create/delete).

    The project id/slug is immutable — only the display name changes; sessions
    keep their project_id unchanged.
    """
    uid = _uid(identity)
    if not session_manager.get_project(project_id, user_id=uid):
        raise HTTPException(status_code=404, detail="Project not found")
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="'name' must be a non-empty string.")
    session_manager.rename_project(project_id, name, user_id=uid)
    p = session_manager.get_project(project_id, user_id=uid)
    return ProjectResponse(id=p["id"], name=p["name"], created_at=str(p.get("created_at") or ""))


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, identity: Identity = Depends(require_signed_in)):
    """Delete a project (owner only; sessions are kept, unassigned)."""
    uid = _uid(identity)
    if not session_manager.get_project(project_id, user_id=uid):
        raise HTTPException(status_code=404, detail="Project not found")
    session_manager.delete_project(project_id, user_id=uid)
    return {"status": "deleted", "project_id": project_id}


# =============================================================================
# BYOK KEY ENDPOINTS (envelope-encrypted; require sign-in)
# =============================================================================

class KeyUpsert(BaseModel):
    api_key: str


def _byok_user(identity: Identity) -> str:
    """Owner id for a BYOK key. Requires a real (hosted) user id."""
    uid = _uid(identity)
    if uid is None:
        # Self-host uses env keys; BYOK-per-user has no meaning without tenancy.
        raise HTTPException(status_code=400, detail="BYOK is only available in hosted mode.")
    return uid


def _require_vault():
    if _KEY_VAULT is None:
        raise HTTPException(status_code=503, detail="BYOK key storage is not configured on this server.")
    return _KEY_VAULT


@app.get("/api/keys")
async def list_keys(identity: Identity = Depends(require_signed_in)):
    """List which providers the caller has a stored key for (never the keys)."""
    vault = _require_vault()
    uid = _byok_user(identity)
    return {"providers": [p for p in VALID_PROVIDERS if vault.has_key(uid, p)]}


@app.put("/api/keys/{provider}")
async def put_key(provider: str, data: KeyUpsert, identity: Identity = Depends(require_signed_in)):
    """Store (envelope-encrypt) the caller's API key for a provider."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")
    if not data.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key must not be empty.")
    vault = _require_vault()
    vault.store_key(_byok_user(identity), provider, data.api_key.strip())
    return {"ok": True, "provider": provider, "stored": True}


@app.delete("/api/keys/{provider}")
async def delete_key(provider: str, identity: Identity = Depends(require_signed_in)):
    """Remove the caller's stored key for a provider."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'.")
    vault = _require_vault()
    uid = _byok_user(identity)
    vault.delete_key(uid, provider)
    return {"ok": True, "provider": provider, "deleted": True}


# =============================================================================
# CODEX ACCOUNT AUTH (device-auth). Always present; degrade cleanly when the
# Codex extension is off/absent (runtime_enabled=false, not connected).
# =============================================================================

def _codex_auth_payload(status: Dict[str, Any]) -> Dict[str, Any]:
    return {**status, "runtime_enabled": get_settings().codex_enabled}


def _codex_disabled_status() -> Dict[str, Any]:
    return {"connected": False, "in_progress": False, "login_url": None,
            "user_code": None, "message": "Codex runtime is not enabled."}


@app.get("/api/codex/auth")
async def codex_auth_status(identity: Identity = Depends(require_signed_in)):
    if _CODEX_AUTH_MANAGER is None:
        return _codex_auth_payload(_codex_disabled_status())
    return _codex_auth_payload(_CODEX_AUTH_MANAGER.status(_uid(identity) or "anonymous"))


@app.post("/api/codex/auth/device/start")
async def codex_auth_device_start(identity: Identity = Depends(require_signed_in)):
    """Start `codex login --device-auth` for the signed-in user."""
    if _CODEX_AUTH_MANAGER is None:
        raise HTTPException(status_code=409, detail="Codex runtime is not enabled.")
    try:
        return _codex_auth_payload(_CODEX_AUTH_MANAGER.start_device_auth(_uid(identity) or "anonymous"))
    except Exception as exc:  # noqa: BLE001 - structured error, never a 500 page
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/codex/auth/device/cancel")
async def codex_auth_device_cancel(identity: Identity = Depends(require_signed_in)):
    if _CODEX_AUTH_MANAGER is None:
        raise HTTPException(status_code=409, detail="Codex runtime is not enabled.")
    return _codex_auth_payload(_CODEX_AUTH_MANAGER.cancel(_uid(identity) or "anonymous"))


@app.delete("/api/codex/auth")
async def codex_auth_disconnect(identity: Identity = Depends(require_signed_in)):
    if _CODEX_AUTH_MANAGER is None:
        return _codex_auth_payload(_codex_disabled_status())
    return _codex_auth_payload(_CODEX_AUTH_MANAGER.disconnect(_uid(identity) or "anonymous"))


# =============================================================================
# MODELS ENDPOINT (availability from usable provider keys; tenant-scoped)
# =============================================================================

_PROVIDER_ENV = {"gemini": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def _usable_providers(identity: Identity) -> set:
    """Which LLM providers are usable for THIS request — so we never offer a
    model that would 500. Self-host: env keys. Hosted: the user's BYOK keys plus
    the capped hosted Gemini tier."""
    settings = get_settings()
    if not settings.hosted:
        return {p for p, env in _PROVIDER_ENV.items() if os.environ.get(env)}
    usable = set()
    uid = identity.user_id
    if _KEY_VAULT is not None and uid:
        for p in VALID_PROVIDERS:
            try:
                if _KEY_VAULT.has_key(uid, p):
                    usable.add(p)
            except Exception:
                pass
    # Also mark a provider as usable if a fallback container environment key is present
    for p, env in _PROVIDER_ENV.items():
        if os.environ.get(env):
            usable.add(p)
    if settings.hosted_gemini_key:
        usable.add("gemini")  # hosted free tier (capped)
    return usable


@app.get("/api/models")
async def list_models(identity: Identity = Depends(get_identity)):
    """Model registry for the picker, with per-request availability."""
    usable = _usable_providers(identity)
    models = [
        {**e, "available": e["provider"] in usable}
        for e in model_catalog_entries()
    ]
    return {"models": models, "default": DEFAULT_MODEL}


# =============================================================================
# CHAT ENDPOINTS
# =============================================================================

async def _read_thread_history(thread_id: str, model_name: str, uid: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read one LangGraph thread's messages as API history (keyed by thread_id).

    Shared by the legacy /api/chat/{session_id}/history (thread_id == session_id =
    Chat 1) and the per-thread history endpoint. Workspace is irrelevant here —
    this only reads conversation state (no LLM call is made).

    Building the agent constructs an LLM client, which needs a key — but a user
    may have none yet. Resolve best-effort and tolerate failure (api_key=None);
    if construction still fails for lack of a key the callers treat it as "no
    history" so viewing never 500s.
    """
    # Codex threads persist their own transcript (no checkpointer). Read it from
    # the codex store and return the same history shape the native path yields.
    if _CODEX_STORE is not None:
        _row = session_manager.get_thread(thread_id, user_id=uid)
        if _row and _row.get("runtime") == "codex":
            history: List[Dict[str, Any]] = []
            for m in _CODEX_STORE.list_messages(thread_id):
                if m["role"] == "user":
                    history.append({"role": "user", "content": m["content"]})
                elif m["role"] == "assistant":
                    meta = m.get("tool_metadata") or {}
                    history.append({
                        "role": "assistant", "content": m["content"],
                        "tool_calls": meta.get("tool_calls", []),
                        "tool_results": meta.get("tool_results", []),
                    })
            return history

    api_key: Optional[str] = None
    try:
        api_key = _LLM_KEY_PROVIDER.resolve(uid, model_name).api_key
    except Exception:
        api_key = None  # no key yet — read-only path tolerates it
    async with open_checkpointer(DB_PATH) as memory:
        agent_graph = create_architect_agent(checkpointer=memory, model_name=model_name, api_key=api_key)
        config = {"configurable": {"thread_id": thread_id}}
        current_state = await agent_graph.aget_state(config)

        if not current_state.values or "messages" not in current_state.values:
            return []

        messages = current_state.values["messages"]
        history: List[Dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                continue
            elif isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": get_clean_content(msg)})
            elif isinstance(msg, AIMessage):
                entry = {"role": "assistant", "content": get_clean_content(msg), "tool_calls": []}
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    entry["tool_calls"] = [format_tool_call_for_api(tc) for tc in msg.tool_calls]
                history.append(entry)
            elif hasattr(msg, "tool_call_id"):
                result = format_tool_result_for_api(msg.content)
                if history and history[-1]["role"] == "assistant":
                    history[-1].setdefault("tool_results", []).append(
                        {"tool_call_id": msg.tool_call_id, **result}
                    )
        return history


def _session_model(session_id: str, uid: Optional[str]) -> str:
    meta = session_manager.get_session_metadata(session_id, user_id=uid)
    return normalize_model_name(meta.get("model_name", DEFAULT_MODEL) if meta else DEFAULT_MODEL)


def _is_missing_llm_error(exc: Exception) -> bool:
    """True when reading history failed only because no LLM is configured.

    A brand-new session legitimately has no history, and reading conversation
    state should not need a live model — but the agent graph is built with one,
    so the absence of an API key / provider package surfaces here. Treat that as
    "no history" (empty), never as a server error. Any other failure is real and
    must still propagate.
    """
    msg = str(exc).lower()
    signatures = (
        "missing api key",
        "no module named 'langchain_google_genai'",
        "no module named 'langchain_anthropic'",
        "no module named 'langchain_openai'",
        "api key",
        "api_key",
    )
    return any(s in msg for s in signatures)


@app.get("/api/chat/{session_id:path}/history")
async def get_chat_history(session_id: str, identity: Identity = Depends(get_identity)) -> List[Dict[str, Any]]:
    """Get chat history for a session's default thread (Chat 1; owner only)."""
    uid = _require_owned(session_id, identity)
    # History is checkpoint-DB-backed, not in the workspace dir — ownership above
    # (metadata store) is the gate; do NOT 404 on ephemeral local-disk absence.
    try:
        # Back-compat: the default thread id == session_id.
        return await _read_thread_history(session_id, _session_model(session_id, uid), uid=uid)
    except Exception as e:
        # A fresh session with no LLM key has no history — return empty, not 500.
        if _is_missing_llm_error(e):
            print(f"[INFO] No history (no LLM configured) for {session_id}: {e}")
            return []
        print(f"[ERROR] Loading history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# CHAT THREAD ENDPOINTS (a chat = a thread_id; many per workspace, owner-scoped)
# =============================================================================

@app.get("/api/sessions/{session_id:path}/threads", response_model=List[ThreadResponse])
async def list_threads(session_id: str, identity: Identity = Depends(get_identity)):
    """List this session's chat threads (newest active first). READ-ONLY:
    browsing never materializes rows — "Chat 1" is seeded at creation."""
    uid = _require_owned(session_id, identity)
    return [_thread_to_response(t) for t in session_manager.list_threads(session_id, user_id=uid)]


@app.post("/api/sessions/{session_id:path}/threads", response_model=ThreadResponse, status_code=201)
async def create_thread(session_id: str, data: ThreadCreate, identity: Identity = Depends(get_identity)):
    """Start a fresh chat in this workspace (own conversation; shared files).

    ``runtime`` picks the agent: native by default, or a registered extension
    (e.g. 'codex'). An unknown/disabled runtime is rejected — you can't create a
    thread for a runtime the server doesn't have.
    """
    uid = _require_owned(session_id, identity)
    model = normalize_model_name(data.model) if data.model else None
    runtime = runtime_registry.NATIVE_RUNTIME
    if data.runtime and data.runtime != runtime_registry.NATIVE_RUNTIME:
        if not runtime_registry.is_registered(data.runtime):
            raise HTTPException(status_code=409, detail=f"Runtime '{data.runtime}' is not enabled on this server.")
        runtime = data.runtime
    t = session_manager.create_thread(session_id, user_id=uid, title=data.title, model=model, runtime=runtime)
    return _thread_to_response(t)


@app.get("/api/sessions/{session_id:path}/threads/{tid}/history")
async def get_thread_history(session_id: str, tid: str, identity: Identity = Depends(get_identity)) -> List[Dict[str, Any]]:
    """History for one thread (owner-checked; thread must belong to the session)."""
    uid = _require_owned(session_id, identity)
    if not session_manager.thread_belongs_to_session(tid, session_id, user_id=uid):
        raise HTTPException(status_code=404, detail="Thread not found")
    try:
        return await _read_thread_history(tid, _session_model(session_id, uid), uid=uid)
    except Exception as e:
        # A thread with no LLM key configured has no readable history — empty, not 500.
        if _is_missing_llm_error(e):
            print(f"[INFO] No thread history (no LLM configured) for {tid}: {e}")
            return []
        print(f"[ERROR] Loading thread history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Catch-all single-session GET. MUST stay below the specific /threads GET routes
# above: ``session_id`` is greedy (``:path``), so this would otherwise shadow
# ``GET …/threads`` and ``GET …/threads/{tid}/history`` (binding session_id to
# "<sid>/threads…" → 404). Route match order in FastAPI is definition order.
@app.get("/api/sessions/{session_id:path}", response_model=SessionResponse)
async def get_session(session_id: str, identity: Identity = Depends(get_identity)):
    """Get session details (only if the caller owns it)."""
    uid = _uid(identity)
    meta = session_manager.get_session_metadata(session_id, user_id=uid)
    if not meta:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        id=session_id,
        name=meta.get("session_name"),
        model_name=meta.get("model_name"),
        project_id=meta.get("project_id"),
        created_at=str(meta.get("created_at")),
        updated_at=str(meta.get("updated_at")) if meta.get("updated_at") else None,
        total_tokens=meta.get("total_tokens", 0),
        total_cost=meta.get("total_cost", 0.0),
        thread_count=session_manager.count_threads(session_id, user_id=uid),
    )


@app.patch("/api/sessions/{session_id:path}/threads/{tid}", response_model=ThreadResponse)
async def patch_thread(session_id: str, tid: str, data: ThreadPatch, identity: Identity = Depends(get_identity)):
    """Rename a thread and/or set its model (owner-checked)."""
    uid = _require_owned(session_id, identity)
    # A PATCH is a deliberate act on the chat (unlike browsing), so the
    # DEFAULT thread only (tid == session_id) may materialize here — legacy
    # sessions predate creation-time seeding and would otherwise have no
    # row to rename / set a model on until their first WS message.
    if tid == session_id:
        session_manager.ensure_default_thread(session_id, user_id=uid)
    if not session_manager.thread_belongs_to_session(tid, session_id, user_id=uid):
        raise HTTPException(status_code=404, detail="Thread not found")
    if data.title is not None:
        session_manager.rename_thread(tid, data.title, user_id=uid)
    if data.model is not None:
        session_manager.set_thread_model(tid, normalize_model_name(data.model), user_id=uid)
    return _thread_to_response(session_manager.get_thread(tid, user_id=uid))


@app.delete("/api/sessions/{session_id:path}/threads/{tid}")
async def delete_thread(session_id: str, tid: str, identity: Identity = Depends(get_identity)):
    """Delete a conversation only — never the workspace files/runs."""
    uid = _require_owned(session_id, identity)
    if not session_manager.thread_belongs_to_session(tid, session_id, user_id=uid):
        raise HTTPException(status_code=404, detail="Thread not found")
    session_manager.delete_thread(tid, user_id=uid)
    return {"status": "deleted", "thread_id": tid}


# NOTE: session-level DELETE/PATCH use the greedy `{session_id:path}` converter
# and MUST be registered AFTER every /threads sub-route above — otherwise
# `PATCH /api/sessions/<sid>/threads/<tid>` binds session_id="<sid>/threads/<tid>"
# and 404s (this shadowing silently broke thread rename/model-set over REST).
@app.delete("/api/sessions/{session_id:path}")
async def delete_session(session_id: str, identity: Identity = Depends(require_signed_in)):
    """Delete a session (owner only)."""
    uid = _require_owned(session_id, identity)
    session_manager.delete_session(session_id, user_id=uid)
    return {"status": "deleted", "session_id": session_id}


@app.patch("/api/sessions/{session_id:path}", response_model=SessionResponse)
async def patch_session(session_id: str, data: SessionPatch, identity: Identity = Depends(require_signed_in)):
    """Rename a session and/or move it to a different project (owner only).

    Rename is DISPLAY-ONLY: the session id and its workspace directory never
    change — files, runs, threads, and checkpoints all stay keyed by the
    original session_id. At least one of ``name``/``project_id`` is required.
    """
    uid = _require_owned(session_id, identity)
    # model_fields_set distinguishes "field absent" from "explicit null":
    # {"project_id": null} means remove-from-project; {} is an empty patch.
    provided = data.model_fields_set & {"name", "project_id"}
    if not provided:
        raise HTTPException(status_code=400,
                            detail="Provide at least one of 'name' or 'project_id'.")
    if "name" in provided:
        name = (data.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="'name' must be a non-empty string.")
        session_manager.rename_session(session_id, name, user_id=uid)
    if "project_id" in provided:
        try:
            session_manager.move_session_to_project(session_id, data.project_id, user_id=uid)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    meta = session_manager.get_session_metadata(session_id, user_id=uid)
    return SessionResponse(
        id=session_id,
        name=meta.get("session_name"),
        model_name=meta.get("model_name"),
        project_id=meta.get("project_id"),
        created_at=str(meta.get("created_at")),
        updated_at=str(meta.get("updated_at")) if meta.get("updated_at") else None,
        total_tokens=meta.get("total_tokens", 0),
        total_cost=meta.get("total_cost", 0.0),
        thread_count=session_manager.count_threads(session_id, user_id=uid),
    )



# Keepalive cadence for the chat stream. LangGraph emits nothing during a long
# tool call (e.g. a 60s+ ORFS synth wait); a `ping` well under the ~30s GCP load
# balancer / proxy idle timeout keeps the connection from being dropped mid-run.
_WS_HEARTBEAT_SEC = 20
# Coalesce token deltas: at most one text_delta frame per interval per turn, so
# a fast stream doesn't flood the socket / React state. The authoritative
# `text` frame carries anything the gate trimmed.
_WS_DELTA_INTERVAL_SEC = 0.05


class _ActiveTurn:
    """Handle to a thread's in-flight agent run.

    Process-local by design: Cloud Run session affinity pins a user's requests
    to one instance, so the runs for a thread land in the same process.
    """

    def __init__(self, task: asyncio.Task, queue: asyncio.Queue):
        self.task = task
        self.queue = queue

    def supersede(self) -> None:
        self.task.cancel()
        try:
            # Wake the run's consumer so it terminates its socket cleanly.
            self.queue.put_nowait(("superseded", None))
        except asyncio.QueueFull:
            pass


# One live run per chat thread. A run can outlive its socket (headless after a
# refresh/drop); without this registry a new message would start a SECOND run
# on the same thread — two writers interleaving on one checkpoint (SQLite lock
# stalls, no reply to the new message, terminal frames never sent).
_ACTIVE_TURNS: Dict[str, _ActiveTurn] = {}

# Fire-and-forget background tasks (post-turn bookkeeping) need a strong
# reference or the event loop may garbage-collect them mid-flight; this set
# holds them until they finish, then a done-callback removes themselves.
_BACKGROUND_TASKS: set = set()


def _run_in_background(coro) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def _pending_tool_call_ids(messages) -> list:
    """Tool-call ids with no matching ToolMessage yet (dangling after an
    interrupted/stopped run)."""
    pending: set = set()
    for msg in messages or []:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                pending.add(tc.get("id"))
        elif hasattr(msg, "tool_call_id"):
            pending.discard(msg.tool_call_id)
    pending.discard(None)
    return sorted(pending)


@app.websocket("/api/chat/{session_id:path}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming chat."""
    await websocket.accept()

    # Authenticate the connection. Browsers can't set headers on a WebSocket, so
    # the token rides a query param (?token=...). Self-host needs none (local
    # trusted user); hosted verifies the OAuth token or grants an anonymous trial.
    token = websocket.query_params.get("token")
    try:
        identity = auth_engine.authenticate(token, session_hint=session_id)
    except AuthError as e:
        await websocket.send_json({"type": "error", "error": e.message, "code": e.code})
        await websocket.close()
        return
    uid = _uid(identity)

    # Tenant check: the caller must own this session (404 otherwise). In self-host
    # uid is None and this is true for any existing session.
    if not session_manager.owns_session(session_id, uid):
        await websocket.send_json({"type": "error", "error": "Session not found"})
        await websocket.close()
        return

    # The chat thread (LangGraph thread_id) this connection talks to. May be
    # overridden per-message. Defaults to the session's "Chat 1" (id == session_id)
    # for back-compat. The WORKSPACE stays bound from session_id regardless of
    # which thread is active — threads share the live workspace.
    conn_thread_id = websocket.query_params.get("thread_id") or session_id

    # Materialize the workspace via the active WorkspaceProvider. Locally this is
    # the same workspace/<session_id> directory the session manager uses; in
    # hosted mode it stages the session's object-storage tarball into local
    # scratch and returns that POSIX path. The tools never know the difference.
    # F7: hydrate the workspace once on WS connect (session open) so the first
    # artifact read isn't a cold full download — and F6: off the event loop so a
    # cold hydration doesn't block the accept / other connections.
    _ws_provider = get_workspace_provider()
    workspace = await asyncio.to_thread(_ws_provider.workspace_for, session_id)

    # Bind this connection's task to its session/workspace/identity. Each
    # WebSocket runs in its own asyncio task, so this contextvar is task-local
    # and isolated across concurrent users — replacing the process-global
    # RTL_WORKSPACE mutation that raced. The user_id + tier flow to tenant-scoped
    # queries and to quota enforcement around synthesis. Propagation through
    # LangGraph tool execution is covered by tests/test_session_context_propagation.py.
    set_current_session(SessionContext(
        session_id=session_id, workspace=workspace, user_id=uid, tier=identity.tier,
    ))

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            # A late `stop` after the turn already ended is a no-op, not an error.
            if isinstance(data, dict) and data.get("type") == "stop":
                continue

            message = data.get("message", "")

            if not message.strip():
                await websocket.send_json({"type": "error", "error": "Empty message"})
                continue

            # Stable per-turn id (client-generated when provided): echoed on
            # every frame of this turn so the UI can correlate frames — and
            # drop stale ones after a stop or reconnect — by id instead of by
            # last-message heuristics.
            turn_id = str(data.get("turn_id") or "") or uuid.uuid4().hex

            # Resolve the chat thread for this turn (per-message override → the
            # connection default → Chat 1). The workspace stays bound to
            # session_id; only the conversation checkpoint key varies. The id
            # is VALIDATED, never trusted: only the default ("Chat 1") is
            # lazily materialized — a stale/crafted id must not create rows.
            requested_tid = data.get("thread_id") or conn_thread_id or session_id
            thread_id = session_manager.resolve_ws_thread(requested_tid, session_id, user_id=uid)
            if thread_id is None:
                await websocket.send_json({"type": "error", "error": "Unknown chat thread"})
                continue
            # Bump activity + auto-title an untitled thread from the first message.
            session_manager.touch_thread(thread_id, user_id=uid, auto_title_from=message)

            # --- Runtime dispatch seam (plans/codex-runtime-extension.md) ------
            # Extensions (e.g. Codex) register a handler + own a per-thread
            # `runtime` marker; the shell routes their turns here. The native
            # LangChain turn below is the DEFAULT and runs UNCHANGED whenever the
            # thread resolves to native — which is always, until an extension +
            # a `runtime` column land. Shipping with zero extensions registered
            # makes this a no-op today: removability is the default state.
            _turn_thread_row = session_manager.get_thread(thread_id, user_id=uid)
            _ext_runtime = runtime_registry.handler_for(
                runtime_registry.resolve_runtime(_turn_thread_row)
            )
            if _ext_runtime is not None:
                _ext_client_gone = False

                async def _ext_send(frame: dict) -> None:
                    nonlocal _ext_client_gone
                    if _ext_client_gone:
                        return
                    frame.setdefault("turn_id", turn_id)
                    try:
                        await websocket.send_json(frame)
                    except Exception:
                        _ext_client_gone = True  # keep the turn going headless

                # Run the extension turn as a task so we can (a) emit heartbeat
                # pings during long MCP tool calls — else the client's liveness
                # watchdog closes the socket ~45s in and drops the turn — and
                # (b) read a `stop` frame concurrently and cancel mid-run. Mirrors
                # the native path's ping/stop handling.
                _ext_turn = asyncio.create_task(_ext_runtime.run_turn(
                    runtime_registry.RuntimeTurnContext(
                        message=message, turn_id=turn_id, thread_id=thread_id,
                        session_id=session_id, workspace=workspace, user_id=uid,
                        thread_row=_turn_thread_row, send=_ext_send,
                        tier=identity.tier, auth_token=token,
                    )
                ))

                async def _ext_watch_stop():
                    # Return "stop" on a stop frame, "disconnect" if the socket
                    # drops. Non-stop frames are ignored (UI queues follow-ups).
                    while True:
                        try:
                            frame = await websocket.receive_json()
                        except Exception:
                            return "disconnect"
                        if isinstance(frame, dict) and frame.get("type") == "stop":
                            return "stop"

                _ext_stop = asyncio.create_task(_ext_watch_stop())
                _ext_stopped = False
                try:
                    while True:
                        done, _ = await asyncio.wait(
                            {_ext_turn, _ext_stop},
                            timeout=_WS_HEARTBEAT_SEC,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if not done:
                            await _ext_send({"type": "ping"})
                            continue
                        if _ext_turn in done:
                            break  # turn finished on its own (persisted in run_turn)
                        # The stop-watcher fired first.
                        if _ext_stop.result() == "stop":
                            # Explicit stop: cancel the turn (unless it just finished).
                            if not _ext_turn.done():
                                _ext_stopped = True
                                _ext_turn.cancel()
                            break
                        # Client disconnected: stop framing, but let the turn run to
                        # completion HEADLESS so it still persists and a reload
                        # refetches it — do NOT cancel it (native-parity, inv #9).
                        _ext_client_gone = True
                        try:
                            await _ext_turn
                        except Exception:
                            pass  # run_turn handles its own errors; nothing to send
                        break
                finally:
                    # Only ever cancel the stop-watcher here; the turn was finished,
                    # explicitly cancelled above, or completed headless — never
                    # cancelled on disconnect.
                    if not _ext_stop.done():
                        _ext_stop.cancel()
                    for _t in (_ext_turn, _ext_stop):
                        try:
                            await _t
                        except (asyncio.CancelledError, Exception):
                            pass

                if _ext_stopped:
                    await _ext_send({"type": "stopped", "tokens": {"input": 0, "output": 0}})
                continue
            # --- native LangChain turn (unchanged) ----------------------------

            # One live run per thread: a new message SUPERSEDES a run that is
            # still executing for this thread (left running headless after a
            # page refresh, or orphaned by a dropped socket). Two concurrent
            # runs would interleave writes on one checkpoint — the "sent a
            # message, got no reply, but the old run was still going" failure.
            # The superseded run's dangling tool calls are repaired by the
            # start-of-turn scan below.
            prior = _ACTIVE_TURNS.pop(thread_id, None)
            if prior is not None and not prior.task.done():
                prior.supersede()
                # Let its checkpoint writes settle before we read state.
                await asyncio.wait({prior.task}, timeout=10)

            print(f"[CHAT] Session: {session_id} | Thread: {thread_id} | Message: {message[:50]}...")

            # Initialize agent with the engine-selected checkpointer (async).
            # The model is read from the ACTIVE THREAD (falls back to the session's
            # model, then DEFAULT) so each chat can use a different model.
            async with open_checkpointer(DB_PATH) as memory:
                thread_row = session_manager.get_thread(thread_id, user_id=uid)
                thread_model = (thread_row or {}).get("model")
                meta = session_manager.get_session_metadata(session_id, user_id=uid)
                model_name = normalize_model_name(
                    thread_model or (meta.get("model_name") if meta else None) or DEFAULT_MODEL
                )

                # Resolve the request-scoped LLM key (BYOK → container env →
                # capped hosted Gemini). A "no usable key" / "tier exhausted"
                # outcome is a clean, actionable error the UI turns into an
                # "Add an API key" CTA — never a 500.
                try:
                    llm_key = _LLM_KEY_PROVIDER.resolve(uid, model_name)
                except HostedTierExhausted as e:
                    await websocket.send_json({"type": "error", "code": e.code, "error": e.message})
                    continue
                except ValueError as e:
                    await websocket.send_json({"type": "error", "code": "no_key", "error": str(e)})
                    continue

                # The hosted free tier may pin a specific model — honor it so the
                # key and the model agree, and downstream cost accounting matches.
                if llm_key.model:
                    model_name = normalize_model_name(llm_key.model)

                agent_graph = create_architect_agent(
                    checkpointer=memory, model_name=model_name, api_key=llm_key.api_key
                )
                config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

                # Start-of-turn repair: a previous run interrupted mid-tool
                # leaves dangling tool calls in the checkpoint; close them with
                # explicit interrupted results so the provider accepts the
                # history.
                snapshot = await agent_graph.aget_state(config)
                input_messages = []

                if snapshot.values and snapshot.values.get("messages"):
                    for tool_id in _pending_tool_call_ids(snapshot.values["messages"]):
                        input_messages.append(ToolMessage(
                            content="[Tool execution was interrupted. Please retry the operation.]",
                            tool_call_id=tool_id,
                        ))

                if not snapshot.values or not snapshot.values.get("messages"):
                    input_messages.append(SystemMessage(content=load_system_prompt()))
                input_messages.append(("user", message))

                # Stream the agent turn. A background task drains astream() into
                # a bounded queue; a second task reads the socket (so `stop`
                # works mid-run) and forwards control signals onto the SAME
                # queue. This coroutine is the single consumer and the ONLY
                # writer to the websocket — no concurrent-send races.
                #
                # The heartbeat MUST time out on the queue read, never on the
                # generator itself: asyncio.wait_for cancels its awaitable on
                # timeout, and cancelling astream.__anext__ threw CancelledError
                # into the running graph — aborting the very long tool call
                # (e.g. wait_for_synthesis) the ping was meant to protect
                # (plans/phase2/REVIEW_FINDINGS.md P0 #2).
                total_input_tokens = 0
                total_output_tokens = 0
                pending_tool_calls: Dict[str, Dict[str, Any]] = {}
                client_gone = False
                stop_requested = False

                async def _send(payload: dict) -> None:
                    # Single writer (this coroutine only). Every frame carries
                    # the turn id so the UI can drop stale frames by id. After
                    # a client drop, keep the agent running to completion (the
                    # checkpoint persists; the UI refetches history on
                    # reconnect) but stop attempting sends.
                    nonlocal client_gone
                    if client_gone:
                        return
                    payload.setdefault("turn_id", turn_id)
                    try:
                        await websocket.send_json(payload)
                    except Exception:
                        client_gone = True

                await _send({"type": "start"})

                # Bounded: a slow client backpressures the drain task instead
                # of building unbounded memory.
                event_queue: asyncio.Queue = asyncio.Queue(maxsize=512)

                async def _drain_stream() -> None:
                    try:
                        async for ev in agent_graph.astream(
                            {"messages": input_messages},
                            config,
                            stream_mode=["updates", "messages"],
                        ):
                            await event_queue.put(("event", ev))
                    except Exception as exc:
                        await event_queue.put(("error", exc))
                    else:
                        await event_queue.put(("end", None))

                drain_task = asyncio.create_task(_drain_stream())
                turn_handle = _ActiveTurn(drain_task, event_queue)
                _ACTIVE_TURNS[thread_id] = turn_handle

                async def _watch_client() -> None:
                    # Reads the socket for the duration of the run. A `stop`
                    # frame cancels the run; any other frame is rejected — the
                    # UI queues follow-up messages and sends them after the
                    # terminal frame. Signals go through the event queue so
                    # sending stays with the single writer.
                    while True:
                        try:
                            frame = await websocket.receive_json()
                        except Exception:
                            await event_queue.put(("disconnect", None))
                            return
                        if isinstance(frame, dict) and frame.get("type") == "stop":
                            await event_queue.put(("stop", None))
                            return
                        await event_queue.put(("busy", None))

                watch_task = asyncio.create_task(_watch_client())

                # `text_delta` frames carry the cumulative text of the CURRENT
                # LLM segment (the UI replaces the active text block), so a
                # replayed or duplicated frame is harmless. A new message id
                # starts a new segment; the authoritative `text` frame closes it.
                segment_text = ""
                segment_id = None

                def _handle_updates(update: dict) -> List[dict]:
                    nonlocal total_input_tokens, total_output_tokens, segment_text, segment_id
                    frames: List[dict] = []
                    if "agent" in update:
                        msg = update["agent"]["messages"][-1]
                        text = get_clean_content(msg)
                        if text:
                            frames.append({"type": "text", "content": text})
                            segment_text, segment_id = "", None
                        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                            total_input_tokens += msg.usage_metadata.get("input_tokens", 0)
                            total_output_tokens += msg.usage_metadata.get("output_tokens", 0)
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                tc_id = tc.get("id", "")
                                tc_name = tc.get("name", "unknown")
                                tc_args = tc.get("args", {}) if isinstance(tc.get("args"), dict) else {}
                                if tc_id:
                                    pending_tool_calls[tc_id] = {"name": tc_name, "args": tc_args}
                                log_tool_call(
                                    workspace=workspace,
                                    session_id=session_id,
                                    source="api_ws",
                                    tool=tc_name,
                                    arguments=tc_args,
                                    tool_call_id=tc_id or None,
                                )
                                frames.append({"type": "tool_call", "tool": format_tool_call_for_api(tc)})
                    elif "tools" in update:
                        msg = update["tools"]["messages"][-1]
                        result = format_tool_result_for_api(msg.content)
                        call_meta = pending_tool_calls.pop(msg.tool_call_id, {})
                        log_tool_result(
                            workspace=workspace,
                            session_id=session_id,
                            source="api_ws",
                            tool=call_meta.get("name", "unknown"),
                            result=msg.content,
                            status="success" if result.get("status") == "success" else "error",
                            tool_call_id=msg.tool_call_id,
                            arguments=call_meta.get("args", {}),
                        )
                        frames.append({"type": "tool_result", "tool_call_id": msg.tool_call_id, **result})
                    return frames

                agent_error: Optional[Exception] = None
                superseded = False
                delta_gate = 0.0
                try:
                    while True:
                        try:
                            kind, payload = await asyncio.wait_for(
                                event_queue.get(), timeout=_WS_HEARTBEAT_SEC
                            )
                        except asyncio.TimeoutError:
                            # Silent gap (tool still running). This cancels only
                            # the queue read — never the agent stream.
                            await _send({"type": "ping"})
                            continue

                        if kind == "end":
                            break
                        if kind == "error":
                            agent_error = payload
                            break
                        if kind == "stop":
                            stop_requested = True
                            drain_task.cancel()
                            break
                        if kind == "superseded":
                            # A newer message on this thread took over the run.
                            superseded = True
                            break
                        if kind == "disconnect":
                            # Client dropped mid-run. Finish the run headless so
                            # the result lands in the checkpoint; the UI
                            # reconciles via history refetch.
                            client_gone = True
                            continue
                        if kind == "busy":
                            await _send({
                                "type": "error", "code": "busy",
                                "error": "A response is already in progress.",
                            })
                            continue

                        mode, data = payload
                        if mode == "messages":
                            chunk, meta = data
                            if (meta or {}).get("langgraph_node") == "agent":
                                piece = get_clean_content(chunk)
                                if piece:
                                    chunk_id = getattr(chunk, "id", None)
                                    if chunk_id != segment_id:
                                        segment_id, segment_text = chunk_id, ""
                                        delta_gate = 0.0  # new segment: emit at once
                                    segment_text += piece
                                    now = asyncio.get_running_loop().time()
                                    if now - delta_gate >= _WS_DELTA_INTERVAL_SEC:
                                        delta_gate = now
                                        await _send({"type": "text_delta", "content": segment_text})
                        elif mode == "updates":
                            for frame in _handle_updates(data):
                                await _send(frame)
                finally:
                    watch_task.cancel()
                    if not drain_task.done():
                        drain_task.cancel()
                    try:
                        await drain_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    if _ACTIVE_TURNS.get(thread_id) is turn_handle:
                        _ACTIVE_TURNS.pop(thread_id, None)

                if stop_requested:
                    # Close the turn cleanly NOW: write explicit interrupted
                    # results for any dangling tool calls into the checkpoint,
                    # so the conversation history is immediately consistent
                    # instead of being lazily repaired on the next turn.
                    try:
                        snap = await agent_graph.aget_state(config)
                        repairs = [
                            ToolMessage(
                                content="[Stopped by user before this tool finished.]",
                                tool_call_id=tid,
                            )
                            for tid in _pending_tool_call_ids(
                                (snap.values or {}).get("messages") or []
                            )
                        ]
                        if repairs:
                            await agent_graph.aupdate_state(config, {"messages": repairs})
                    except Exception:
                        pass  # the next turn's start-of-turn repair still covers it

                # Fast, correctness-sensitive bookkeeping stays synchronous and
                # BEFORE the terminal frame: local SQLite writes (sub-ms), and
                # the hosted-tier limiter must reflect this turn's usage before
                # the client can possibly send the next message on this same
                # connection, or a rapid back-to-back turn could slip past a
                # cap it should have hit.
                try:
                    if total_input_tokens > 0 or total_output_tokens > 0:
                        current_meta = session_manager.get_session_metadata(session_id, user_id=uid)
                        if current_meta:
                            new_input = current_meta.get("input_tokens", 0) + total_input_tokens
                            new_output = current_meta.get("output_tokens", 0) + total_output_tokens
                            cached = current_meta.get("cached_tokens", 0)
                            new_cost = calculate_cost(new_input, new_output, model_name)
                            session_manager.update_session_stats(session_id, new_input, new_output, cached, new_cost, user_id=uid)

                    # Cap the shared hosted tier: charge THIS turn's tokens/cost to
                    # the limiter so the per-user daily + global ceilings actually
                    # bite (otherwise a free-tier user is effectively uncapped).
                    if llm_key.source == "hosted":
                        limiter = getattr(_LLM_KEY_PROVIDER, "limiter", None)
                        if limiter is not None:
                            turn_cost = calculate_cost(total_input_tokens, total_output_tokens, model_name)
                            limiter.record(uid or "anonymous", total_input_tokens + total_output_tokens, turn_cost)
                except Exception as exc:
                    print(f"[WARN] token/limiter bookkeeping failed: {exc}")

                # Terminal frame goes out NOW — the moment the assistant's turn
                # is logically complete — not after whatever comes next.
                tokens = {"input": total_input_tokens, "output": total_output_tokens}
                if agent_error is not None:
                    print(f"[ERROR] Agent error: {agent_error}")
                    await _send({"type": "error", "error": str(agent_error)})
                elif stop_requested:
                    # Explicit terminal marker for a user-initiated stop; the
                    # dangling tool calls were closed with interrupted results
                    # right above.
                    await _send({"type": "stopped", "tokens": tokens})
                elif superseded:
                    # Usually the socket is already gone (this run was
                    # orphaned); if a second tab is still attached, tell it
                    # honestly what happened.
                    await _send({
                        "type": "error", "code": "superseded",
                        "error": "A newer message took over this chat.",
                    })
                else:
                    await _send({"type": "done", "tokens": tokens})

                # Persist workspace changes to durable storage in hosted mode
                # (no-op locally) as a background task — this is the ONE slow,
                # non-critical step (a real network upload). Awaiting it before
                # the terminal frame made the UI sit on "Stop" for as long as
                # the upload took (observed up to ~1 minute) even though the
                # reply had fully rendered. It doesn't touch the checkpoint
                # connection (already closed by then), so it's safe to outlive
                # this turn.
                _sync = getattr(_ws_provider, "sync", None)
                if callable(_sync):
                    async def _background_sync() -> None:
                        try:
                            await asyncio.to_thread(_sync, session_id)
                        except Exception as exc:
                            print(f"[WARN] workspace sync failed: {exc}")

                    _run_in_background(_background_sync())

                if client_gone:
                    # The socket is dead; nothing more can be received on it.
                    return

    except WebSocketDisconnect:
        print(f"[CHAT] WebSocket disconnected: {session_id}")
    except Exception as e:
        print(f"[ERROR] WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except:
            pass


# =============================================================================
# WORKSPACE/ARTIFACTS ENDPOINTS
# =============================================================================

@app.get("/api/workspace/{session_id:path}/files")
async def list_workspace_files(session_id: str, _acl: Optional[str] = Depends(verify_session_access)) -> List[FileInfo]:
    """List all files in the workspace."""
    # F6: the whole body blocks (workspace hydration download+untar, os.listdir,
    # os.stat, manifest read) — run it off the event loop so a slow hydration on
    # one request can't stall every other in-flight request.
    def work() -> List[FileInfo]:
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        # Manifest roles annotate the design files (rtl/tb/sdc/include),
        # keyed by workspace-relative path (nested design files have roles too).
        ignore: List[str] = []
        try:
            with session_scope(SessionContext(session_id=session_id, workspace=workspace)):
                manifest = manifest_mod.read_manifest(workspace, session_id)
            roles = {f.path: f.role for f in manifest.files}
            ignore = manifest.ignore
        except Exception:
            roles = {}

        # Recursive listing under the manifest's exclusion policy (run dirs,
        # dot-dirs, user ignore globs, depth cap). ``path`` is the
        # workspace-relative POSIX path — the same key the manifest uses.
        files = []
        for rel in manifest_mod.iter_workspace_files(workspace, ignore):
            item_path = os.path.join(workspace, rel)
            try:
                stat = os.stat(item_path)
            except OSError:
                continue
            item = os.path.basename(rel)

            # Determine file type
            ext = os.path.splitext(item)[1].lower()
            file_type = "unknown"
            if ext in [".v", ".sv"]:
                file_type = "verilog"
            elif ext == ".yaml":
                file_type = "spec" if "_spec" in item else "yaml"
            elif ext == ".vcd":
                file_type = "waveform"
            elif ext == ".gds":
                file_type = "layout"
            elif ext == ".svg":
                file_type = "schematic"
            elif ext == ".md":
                file_type = "report"

            files.append(FileInfo(
                name=item,
                path=rel,
                type=file_type,
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                role=roles.get(rel),
            ))

        return sorted(files, key=lambda f: f.modified, reverse=True)

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/spec")
async def get_spec(session_id: str, _acl: Optional[str] = Depends(verify_session_access)) -> SpecResponse:
    """Get the latest spec file."""
    def work() -> SpecResponse:  # F6: hydration + listdir + file read off-thread
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        # Recursive under the manifest exclusion policy (nested specs count too).
        spec_files = sorted(
            [f for f in manifest_mod.iter_workspace_files(workspace) if f.endswith("_spec.yaml")],
            key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
            reverse=True
        )

        if not spec_files:
            raise HTTPException(status_code=404, detail="No spec files found")

        spec_file = spec_files[0]
        spec_path = os.path.join(workspace, spec_file)

        with open(spec_path, "r") as f:
            content = f.read()

        try:
            parsed = yaml.safe_load(content)
        except:
            parsed = None

        return SpecResponse(
            filename=spec_file,
            content=content,
            parsed=parsed
        )

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/code")
async def get_code_files(session_id: str, _acl: Optional[str] = Depends(verify_session_access)) -> List[CodeFile]:
    """Get all Verilog/SystemVerilog files."""
    def work() -> List[CodeFile]:  # F6: hydration + listdir + file reads off-thread
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        # Manifest-driven, recursive: code files = manifest files with code roles
        # (rtl/tb/include) + any .v/.sv the exclusion-aware scan found. ``filename``
        # is the workspace-relative POSIX path (the frontend keys code tabs by it).
        try:
            with session_scope(SessionContext(session_id=session_id, workspace=workspace)):
                manifest = manifest_mod.read_manifest(workspace, session_id)
            rels = {f.path for f in manifest.files if f.role in ("rtl", "tb", "include")}
            ignore = manifest.ignore
        except Exception:
            rels, ignore = set(), []
        rels.update(
            rel for rel in manifest_mod.iter_workspace_files(workspace, ignore)
            if rel.lower().endswith((".v", ".sv"))
        )

        result = []
        for filename in sorted(rels):
            full = os.path.join(workspace, filename)
            if not os.path.isfile(full):
                continue
            with open(full, "r", errors='ignore') as f:
                content = f.read()

            lang = "systemverilog" if filename.endswith((".sv", ".svh")) else "verilog"
            result.append(CodeFile(filename=filename, content=content, language=lang))

        return result

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/code/{filename:path}")
async def get_code_file(session_id: str, filename: str, _acl: Optional[str] = Depends(verify_session_access)) -> CodeFile:
    """Get a specific code file."""
    def work() -> CodeFile:  # F6: hydration + file read off-thread
        workspace = _resolve_workspace(session_id)
        file_path = os.path.join(workspace, filename)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        if not is_within(workspace, file_path):
            raise HTTPException(status_code=403, detail="Access denied")

        with open(file_path, "r", errors='ignore') as f:
            content = f.read()

        lang = "systemverilog" if filename.endswith((".sv", ".svh")) else "verilog"
        return CodeFile(filename=filename, content=content, language=lang)

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/waveforms")
async def list_waveform_files(session_id: str, _acl: Optional[str] = Depends(verify_session_access)) -> List[str]:
    """List VCD files in the workspace."""
    def work() -> List[str]:  # F6: hydration + listdir off-thread
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        return [f for f in os.listdir(workspace) if f.endswith(".vcd")]

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/waveform/{filename:path}")
async def get_waveform_data(session_id: str, filename: str, _acl: Optional[str] = Depends(verify_session_access)):
    """Get parsed VCD waveform data."""
    # F6: hydration + the VCD parse are both blocking — run them off the loop.
    workspace = await asyncio.to_thread(_resolve_workspace, session_id)
    vcd_path = os.path.join(workspace, filename)

    if not os.path.exists(vcd_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not is_within(workspace, vcd_path):
        raise HTTPException(status_code=403, detail="Access denied")

    parsed = await asyncio.to_thread(_parse_vcd_file, vcd_path, filename)
    # A terminal run's VCD never changes — let the browser cache the (expensive)
    # parsed payload forever; loose/root VCDs stay uncached.
    cache_control = await asyncio.to_thread(workspace_fs.artifact_cache_control, workspace, vcd_path)
    return JSONResponse(parsed, headers={"Cache-Control": cache_control})


def _parse_vcd_file(vcd_path: str, filename: str) -> dict:
    """Parse a VCD into the viewer payload (blocking; run via asyncio.to_thread)."""
    try:
        from vcdvcd import VCDVCD

        vcd = VCDVCD(vcd_path)
        signals = vcd.get_signals()
        endtime = vcd.endtime
        # Resolve the VCD time unit so the frontend can place a failure cursor
        # (which is given in ns) at the right x — VCDs dump in their own ticks
        # (ps when the TB declares `timescale 1ns/1ps`, otherwise raw).
        timescale = None
        unit_seconds = None
        _UNIT_S = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}
        try:
            ts = getattr(vcd, "timescale", None)
            if isinstance(ts, dict):
                unit = str(ts.get("unit") or "").lower()
                mag = float(ts.get("magnitude") or 1)
                if unit in _UNIT_S:
                    unit_seconds = mag * _UNIT_S[unit]
                    timescale = f"{int(mag) if mag == int(mag) else mag}{unit}"
            elif ts:
                timescale = str(ts)
        except Exception:
            timescale = None
            unit_seconds = None

        # Parse signals, PRESERVING hierarchy (scope path), width, and x/z state
        # so the viewer can build a scope tree and show unknowns — not the old
        # leaf-only/collapsed view that lost the dut.* vs tb.* distinction.
        signal_data = []
        seen = set()
        for sig_name in signals[:128]:
            if sig_name in seen:
                continue
            seen.add(sig_name)
            try:
                sig = vcd[sig_name]
                tv = sig.tv
                width = int(getattr(sig, "size", 1) or 1)

                # full_name like "counter_tb.dut.count[7:0]" → scope/leaf/bus-range
                base = sig_name.rsplit("[", 1)[0]
                parts = base.split(".")
                leaf = parts[-1]
                scope = ".".join(parts[:-1]) if len(parts) > 1 else ""

                times, values, values_str, x_flags = [], [], [], []
                for t, v in tv:
                    times.append(t)
                    s = str(v).lower()
                    has_x = ("x" in s) or ("z" in s)
                    x_flags.append(has_x)
                    values_str.append(str(v))
                    try:
                        cleaned = s.replace("x", "0").replace("z", "0")
                        values.append(int(cleaned, 2) if cleaned else 0)
                    except ValueError:
                        values.append(0)

                signal_data.append({
                    "name": leaf,
                    "full_name": sig_name,
                    "scope": scope,
                    "width": width,
                    "isBus": width > 1,
                    "times": times,
                    "values": values,
                    "valuesStr": values_str,
                    "xFlags": x_flags,
                })
            except Exception:
                continue

        # Stable, hierarchy-aware ordering: by scope depth then name.
        signal_data.sort(key=lambda s: (s["scope"].count("."), s["scope"], s["name"]))

        return {
            "filename": filename,
            "endtime": endtime,
            "timescale": timescale,
            "unitSeconds": unit_seconds,  # seconds per VCD tick (None/1.0 = unknown)
            "signalCount": len(signal_data),
            "signals": signal_data,
        }

    except ImportError:
        raise HTTPException(status_code=500, detail="vcdvcd library not installed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspace/{session_id:path}/synthesis-runs", response_model=List[SynthesisRunResponse])
async def get_synthesis_runs(session_id: str, _acl: Optional[str] = Depends(verify_session_access)):
    """List synthesis runs for a workspace."""
    def work():  # F6: hydration + index read off-thread
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        return [SynthesisRunResponse(**item) for item in list_synthesis_runs(workspace)]

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/report", response_model=ReportResponse)
async def get_report(session_id: str, run_id: Optional[str] = Query(default=None), _acl: Optional[str] = Depends(verify_session_access)) -> ReportResponse:
    """Get the latest available report or a report for a specific synthesis run."""
    def work() -> ReportResponse:  # F6: hydration + report read off-thread
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        report_path, resolved_run_id = resolve_report_path(workspace, run_id=run_id)
        if not report_path:
            raise HTTPException(status_code=404, detail="No report found")

        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()

        return ReportResponse(filename=os.path.basename(report_path), content=content, run_id=resolved_run_id)

    return await asyncio.to_thread(work)


@app.post("/api/workspace/{session_id:path}/report/generate", response_model=ReportResponse)
async def generate_report(session_id: str, run_id: Optional[str] = Query(default=None), _acl: Optional[str] = Depends(verify_session_access)) -> ReportResponse:
    """Generate a design report for the selected synthesis run or latest available run."""
    # F6: report generation (+ the hosted sync it triggers) is blocking — off the loop.
    def work() -> ReportResponse:
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        try:
            report_path = save_design_report(workspace, run_id=run_id)
            with open(report_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Persist the freshly-written report back to object storage so a later
            # read on a different/cold instance can see it (hosted only; self-host
            # writes are already in-place). Mirrors the action router's sync.
            if get_settings().hosted:
                get_workspace_provider().sync(session_id)

            resolved_run_id = None
            report_dir = os.path.dirname(report_path)
            if os.path.basename(report_path) == "design_report.md" and os.path.realpath(report_dir) != os.path.realpath(workspace):
                resolved_run_id = os.path.basename(report_dir)

            return ReportResponse(filename=os.path.basename(report_path), content=content, run_id=resolved_run_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/layouts")
async def list_layout_files(session_id: str, _acl: Optional[str] = Depends(verify_session_access)) -> List[str]:
    """List GDS files in the workspace."""
    def work() -> List[str]:  # F6: hydration + os.walk off-thread
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        gds_files = []
        for root, dirs, files in os.walk(workspace):
            for f in files:
                if f.endswith(".gds"):
                    rel_path = os.path.relpath(os.path.join(root, f), workspace)
                    gds_files.append(rel_path)

        return gds_files

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/layout/{filename:path}")
async def get_layout_svg(session_id: str, filename: str, _acl: Optional[str] = Depends(verify_session_access)):
    """Best-effort GDS→SVG for the layout viewer.

    Prefers a pre-rendered ``<file>.svg`` next to the GDS; otherwise renders the
    top cell with gdstk (bounded by a polygon cap). Full layout rendering of
    large designs is a Phase-2 concern, so this degrades to a structured error
    the viewer shows gracefully rather than failing the request.
    """
    # F6: hydration + the (potentially heavy) gdstk render run off the loop.
    # A terminal run's GDS never changes — cache the rendered SVG immutably.
    cache_holder = {"cc": workspace_fs.CACHE_NO_STORE}

    def work():
        workspace = _resolve_workspace(session_id)
        gds_path = os.path.join(workspace, filename)
        if not is_within(workspace, gds_path):
            raise HTTPException(status_code=403, detail="Access denied")
        if not os.path.exists(gds_path):
            raise HTTPException(status_code=404, detail="Layout not found")
        cache_holder["cc"] = workspace_fs.artifact_cache_control(workspace, gds_path)

        # 1) pre-rendered SVG sidecar
        sidecar = gds_path + ".svg"
        if os.path.exists(sidecar):
            with open(sidecar, "r", encoding="utf-8", errors="ignore") as f:
                return {"svg": f.read(), "cell_name": os.path.basename(filename), "cached": True}

        # 2) render with gdstk if available
        try:
            import gdstk  # type: ignore
        except Exception:
            return {"error": "unsupported", "message": "Layout rendering needs gdstk (Phase 2). No pre-rendered SVG found.", "cell_name": ""}

        import tempfile

        try:
            lib = gdstk.read_gds(gds_path)
            top = lib.top_level()
            if not top:
                return {"error": "render_failed", "message": "No top cell in GDS.", "cell_name": ""}
            # Render the largest top cell (the real design, not an empty wrapper).
            cell = max(top, key=lambda c: len(c.get_polygons()))
            polygon_count = len(cell.get_polygons())
            if polygon_count > 2_000_000:
                return {"error": "too_large", "message": "Layout too large to render inline.", "cell_name": cell.name}
            # gdstk's Cell only exposes write_svg(outfile, ...) (no in-memory svg()).
            # Render to a temp file, read it back, and return the markup inline.
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "layout.svg")
                cell.write_svg(out, scaling=10.0, background="#0b0e14")
                with open(out, "r", encoding="utf-8", errors="ignore") as f:
                    svg = f.read()
            return {"svg": svg, "cell_name": cell.name, "polygon_count": polygon_count}
        except Exception as e:
            return {"error": "render_failed", "message": str(e), "cell_name": ""}

    payload = await asyncio.to_thread(work)
    return JSONResponse(payload, headers={"Cache-Control": cache_holder["cc"]})


@app.get("/api/workspace/{session_id:path}/schematics")
async def list_schematic_files(session_id: str, _acl: Optional[str] = Depends(verify_session_access)) -> List[str]:
    """List SVG schematic files in the workspace."""
    def work() -> List[str]:  # F6: hydration + listdir off-thread
        workspace = _resolve_workspace(session_id)
        if not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")

        return [f for f in os.listdir(workspace) if f.endswith(".svg") and not f.endswith(".gds.svg")]

    return await asyncio.to_thread(work)


@app.get("/api/workspace/{session_id:path}/file/{filename:path}")
async def get_file_content(
    session_id: str,
    filename: str,
    raw: bool = Query(default=False),
    _acl: Optional[str] = Depends(verify_session_access),
):
    """File content with honest binary/size handling.

    Default: JSON ``{filename, content, size, binary, tooLarge}`` — content is
    null (never lossy garbage) for binary or oversized files. ``?raw=1``
    streams the raw bytes as a download (the VCD/GDS/netlist escape hatch).
    Terminal-run artifacts get immutable cache headers (their bytes can never
    change); everything else is no-store.
    """
    def resolve():  # F6: hydration + stat off-thread
        workspace = _resolve_workspace(session_id)
        file_path = os.path.join(workspace, filename)

        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        # Security check - ensure file is within workspace
        if not is_within(workspace, file_path):
            raise HTTPException(status_code=403, detail="Access denied")

        return workspace, file_path, workspace_fs.artifact_cache_control(workspace, file_path)

    workspace, file_path, cache_control = await asyncio.to_thread(resolve)

    if raw:
        return FileResponse(
            file_path,
            filename=os.path.basename(filename),
            headers={"Cache-Control": cache_control},
        )

    payload = await asyncio.to_thread(workspace_fs.read_smart_file, workspace, file_path, filename)
    return JSONResponse(payload, headers={"Cache-Control": cache_control})


# =============================================================================
# ACTION LAYER  (manifest + IDE-first buttons + unified runs)
#   Implemented as a standalone router so it has no dependency on the agent
#   stack — see src/api/actions.py. Both the human (these endpoints) and the
#   agent (the @tool wrappers) drive the identical tool functions underneath.
# =============================================================================

# Resolve workspaces through the active WorkspaceProvider — NOT
# session_manager.get_workspace_path. In hosted mode the provider materializes
# the session's object-storage tarball into local scratch and returns THAT path,
# which is exactly the directory `sync_workspace` persists back; using the local
# base_dir here instead would write to one directory and upload another, silently
# dropping every save/upload/sim/synth output. Locally the provider returns the
# same workspace/<sid> directory, so self-host behaviour is unchanged. This
# mirrors the WebSocket agent path (see `_ws_provider.workspace_for` above).
app.include_router(build_actions_router(
    lambda sid: get_workspace_provider().workspace_for(sid),
    get_identity=get_identity,
    require_signed_in=require_signed_in,
    require_owned=_require_owned,
    sync_workspace=(lambda sid: get_workspace_provider().sync(sid)) if get_settings().hosted else None,
))


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "workspace": WORKSPACE_DIR,
        "sessions": len(session_manager.get_all_sessions())
    }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
