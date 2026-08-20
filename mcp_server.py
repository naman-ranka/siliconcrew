"""
RTL Design Agent - MCP Server

Exposes RTL design tools via Model Context Protocol (MCP).
Provides individual tools + expert workflow prompts.

Supports three transport modes:
  - stdio (default): Local process communication (Claude Desktop, VS Code)
  - sse:  Server-Sent Events over HTTP for remote access
  - http: Streamable HTTP transport (newer MCP spec) for remote access

Usage:
  python mcp_server.py                     # stdio (default)
  python mcp_server.py --transport sse     # SSE on http://0.0.0.0:8080
  python mcp_server.py --transport http    # Streamable HTTP on http://0.0.0.0:8080
  python mcp_server.py --transport sse --host 0.0.0.0 --port 9090
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote, unquote

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    Prompt,
    PromptMessage,
    GetPromptResult,
    Resource,
    ResourceContents,
    TextResourceContents,
    ReadResourceResult,
)

from dotenv import load_dotenv
# Only the registry seam is imported here: the server advertises and dispatches
# ``mcp_tools`` (plus the Codex surface), so naming individual tools would be a
# second, hand-kept list of what exists — the exact drift ``tools_on_surface``
# removes.
from src.tools.wrappers import (
    get_workspace_path,
    mcp_tools,
    session_host,
    tools_on_surface,
)
from src.utils.session_manager import SessionManager
from src.utils.attempt_logger import log_tool_call, log_tool_result
from src.platform_engines.request_scope import resolve_workspace_path, run_in_session
from src.platform_engines.workspace_flusher import get_workspace_flusher
from src.platform_engines import auth as auth_engine
from src.platform_engines.identity import Action, AuthError, authorize

load_dotenv()

# Single source of truth for tool dispatch: derive the name→tool map from the
# same ``mcp_tools`` list that ``list_tools`` advertises from. Building it by
# hand drifted (tools got listed but not dispatchable → "Unknown tool", e.g.
# run_isolated_simulation / get_manifest / update_manifest); deriving it keeps
# "advertised" and "callable" in lockstep. See test_mcp_tool_registry.
# The Codex-surface tool is dispatchable on every server (it always was — only
# its ADVERTISEMENT was ever gated on --codex-tools).
TOOL_REGISTRY = {t.name: t for t in (*mcp_tools, *tools_on_surface("codex"))}

# Prompt resolution lives in src.utils.architect_prompt — ONE answer to "which
# prompt is running", shared with the agent. This file used to carry its own
# copy plus a fallback to an embedded constant, which meant a missing prompt
# file quietly served a stale prompt and reported it as version "legacy".
# The shared module has no heavy imports, so the reason the copy existed — not
# paying LangGraph's import cost on every Codex subprocess spawn — still holds.
from src.utils.architect_prompt import (  # noqa: E402
    PROMPTS_DIR,
    PromptUnavailable,
    load_with_provenance as _load_architect_prompt,
    resolved_version,
)

DEFAULT_ARCHITECT_PROMPT_VERSION = resolved_version()


# =============================================================================
# SERVER INSTRUCTIONS
# =============================================================================

# Delivered ONCE, in the MCP `initialize` result (InitializeResult.instructions),
# to every client on every transport — Server(instructions=...) is carried into
# create_initialization_options() by the SDK. This is where a fact that is true
# of the whole server belongs: the alternative is copying the same sentence into
# 40+ tool descriptions, which is a second list to keep in step and drifts the
# first time one copy is edited.
#
# It answers what a stranger client (Claude Code, Codex, Cursor) cannot learn
# from tools/list: that a session gates every other tool, that "session" here
# means a design workspace rather than the MCP connection, that tools run
# server-side rather than in the caller's sandbox, and that paths are
# workspace-relative. Per-tool behaviour stays in the per-tool description.
SERVER_INSTRUCTIONS = """SiliconCrew is a chip-design platform: you take a
Verilog/RTL design from spec through lint, simulation and synthesis by calling
these tools.

Start by selecting a session — nothing else works without one. A SiliconCrew
session is not this MCP connection; it is a workspace on the server holding ONE
design block (its RTL, testbenches, spec, reports, waveforms and synthesis
runs). Call `create_session_tool` to start a new design, or `list_sessions_tool`
then `set_active_session` to continue an existing one; `get_current_session`
reports which session is active. Every other tool acts on that session's
workspace, and refuses to run until one is active.

These tools execute SERVER-SIDE, not in your sandbox. They read and write the
session workspace on the SiliconCrew server — not your machine, your container,
or your working directory. Your own sandbox permissions say nothing about it: a
read-only sandbox of your own does NOT make the workspace read-only, so never
refuse an edit on that basis. Equally, your shell and file tools cannot see or
change these files; the SiliconCrew tools are the only way in.

Paths are workspace-relative. Pass `counter.v` or `tb/tb_counter.v`, never an
absolute path or a path from your own filesystem — a path that leaves the
workspace is rejected. `list_files_tool` shows what the workspace holds."""


# =============================================================================
# TOOL AUTO-DISCOVERY HELPERS
# =============================================================================

# Tool categorization for filtering — single source of truth shared with the
# web UI's tool catalog (src/api/tool_catalog.py), so the Command Surface, the
# agent, and MCP clients all see one taxonomy and one protection policy.
from src.api.tool_catalog import (
    TOOL_CATEGORIES,
    PROTECTED_TOOLS as _SHARED_PROTECTED_TOOLS,
    MUTATING_TOOLS as _SHARED_MUTATING_TOOLS,
    DISABLED_WHEN_BOUND as _SHARED_DISABLED_WHEN_BOUND,
    requires_session,
)


def langchain_to_mcp_schema(langchain_tool) -> Tool:
    """
    Automatically convert a LangChain tool to MCP Tool format.
    Extracts schema from the LangChain @tool decorator.
    """
    # Get the tool's input schema (from Pydantic model or args_schema)
    input_schema = {}
    
    if hasattr(langchain_tool, 'args_schema') and langchain_tool.args_schema:
        # Pydantic model - convert to JSON Schema
        input_schema = langchain_tool.args_schema.model_json_schema()
    elif hasattr(langchain_tool, 'args'):
        # Fallback to basic schema from function signature
        input_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    return Tool(
        name=langchain_tool.name,
        description=langchain_tool.description or f"Execute {langchain_tool.name}",
        inputSchema=input_schema
    )


# =============================================================================
# MCP SERVER
# =============================================================================

class RTLDesignMCPServer:
    def __init__(self, codex_tools: bool = False, bound_session: str | None = None):
        self.server = Server("rtl-design-agent", instructions=SERVER_INSTRUCTIONS)
        # Bound-session mode (Codex): this server instance is locked to exactly
        # one session. Session-management + cross-session tool access are refused
        # so an embedded Codex agent can only ever touch its own workspace.
        self.bound_session = (bound_session or "").strip() or None
        # Respect mounted workspace path when running in Docker.
        # Falls back to repo-local workspace for non-container/local usage.
        base_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_dir = os.environ.get("RTL_WORKSPACE") or os.path.join(base_dir, "workspace")
        workspace_dir = os.path.abspath(workspace_dir)
        _data_dir = os.environ.get("RTL_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".siliconcrew")
        os.makedirs(_data_dir, exist_ok=True)
        db_path = os.path.join(_data_dir, "state.db")
        
        self.session_manager = SessionManager(base_dir=workspace_dir, db_path=db_path)
        self.current_session = None  # Track active session
        self.codex_tools = codex_tools  # Expose Codex-only MCP helpers when enabled
        # 4B (hosted-latency plan): when the parent process owns the once-per-
        # turn workspace sync (the Codex engine sets this env key for the bound
        # subprocess it spawns), skip the per-tool blocking upload here — a
        # mutating tool result must not wait on a full-workspace GCS PUT. The
        # parent's turn-end background sync tars the SAME scratch dir this
        # subprocess writes into (shared WORKSPACE_SCRATCH_DIR), so nothing is
        # lost — same crash exposure as the native agent's proven cadence.
        self.defer_workspace_sync = (
            os.environ.get("SILICONCREW_MCP_DEFER_WORKSPACE_SYNC", "").strip().lower()
            in ("1", "true", "yes")
        )

        # Identity for capability gating. MCP itself is a signed-in feature;
        # stdio/self-host is the trusted local user (full access). Hosted/remote
        # deployments construct the server with a verified identity (token).
        self.identity = self._resolve_identity()

        # Hosted flag, resolved once. In hosted mode the HTTP/SSE transports
        # carry a *per-request* verified identity (see _current_identity); local
        # / stdio keeps the single trusted process identity above, unchanged.
        from src.platform_engines.settings import get_settings
        self._hosted = get_settings().hosted

        # In bound mode, verify ownership and lock the active session up front so
        # every subsequent tool call operates only within it. (After _hosted is
        # set — scoped_user_id resolves identity through it.)
        if self.bound_session:
            if not self.session_manager.owns_session(self.bound_session, self.scoped_user_id()):
                raise RuntimeError(f"Bound session '{self.bound_session}' not found for this MCP identity.")
            self.current_session = self.bound_session

        # Wire cloud engines once (no-op in self-host).
        from src.platform_engines.settings import apply_platform_wiring
        apply_platform_wiring()

        # Register handlers using decorators
        self._setup_handlers()

    def _resolve_identity(self):
        """Resolve the MCP session identity (token in hosted, else local)."""
        token = os.environ.get("SILICONCREW_MCP_TOKEN")
        try:
            return auth_engine.authenticate(token, session_hint="mcp")
        except AuthError:
            # An invalid token degrades to anonymous (synth/save then blocked).
            from src.platform_engines.identity import new_anonymous
            return new_anonymous("mcp")

    # Tools that mutate/persist or are compute-heavy require a signed-in user.
    # Shared with the web UI's /invoke gate (src/api/tool_catalog.py) — one
    # policy, enforced identically for MCP clients and the Command Surface.
    # (Now also covers cocotb/SBY/HLS: containerized compute is sign-in-gated.)
    _PROTECTED_TOOLS = _SHARED_PROTECTED_TOOLS

    def _current_identity(self):
        """The identity to act as for the in-flight call.

        Hosted HTTP/SSE: the per-request identity verified by the auth
        middleware and stashed on the request scope (``scope["state"]``), which
        the transport surfaces via ``server.request_context.request.state``. This
        replaces the process-wide ``self.identity`` so every tool runs as the
        calling user. Local / stdio: there is no request — return the trusted
        process identity (``LOCAL_IDENTITY``) verbatim, exactly as before.
        """
        if self._hosted:
            ident = self._request_identity()
            if ident is not None:
                return ident
        return self.identity

    def _request_identity(self):
        from src.platform_engines.mcp_auth import MCP_IDENTITY_STATE_KEY

        try:
            request = self.server.request_context.request
        except (LookupError, AttributeError):
            return None
        state = getattr(request, "state", None) if request is not None else None
        return getattr(state, MCP_IDENTITY_STATE_KEY, None) if state is not None else None

    # --- The session tools' host (see src/tools/wrappers.py's session tools) ---
    # ``session_manager``, ``current_session`` and ``bound_session`` are the
    # attributes above; these three are the rest of that contract. Public
    # because the registry's session tools read them through session_host().

    def scoped_user_id(self):
        return auth_engine.scoped_user_id(self._current_identity())

    def architect_prompt(self) -> tuple[str, str, str]:
        """(prompt_text, source_label, version) — what inject_architect_prompt
        returns, and what the rtl_design_workflow prompt embeds."""
        return _load_architect_prompt()

    def workspace_path(self, session_id: str) -> str:
        """The workspace tools for ``session_id`` actually act on (dev#43).

        ``session_manager.get_workspace_path`` is the LOGICAL layout; on hosted,
        ``run_in_session`` binds the provider's scratch materialization instead,
        so every reply that names a workspace — and, critically, the path the
        activity log is written to — must come from the same provider. Pure: it
        never materializes, so it is safe on read/reply paths. Providers without
        the accessor (older test fakes) keep today's logical answer. A provider
        that fails to construct at all (settings error) also degrades to the
        logical path — a reply/log site must never be the thing that turns a
        misconfiguration into an unhandled tool failure."""
        try:
            return resolve_workspace_path(
                session_id, fallback=self.session_manager.get_workspace_path
            )
        except Exception:
            return self.session_manager.get_workspace_path(session_id)

    def _resource_sessions(self) -> list[str]:
        """Sessions this MCP identity may see through the RESOURCE surface —
        mirrors the tool path's scoping so resources can't leak past the same
        boundary tool calls respect: the bound session only (Codex bound mode),
        the owner's sessions (hosted), or all (self-host / single-tenant)."""
        if self.bound_session:
            return [self.bound_session]
        if self._hosted:
            return self.session_manager.get_all_sessions(user_id=self.scoped_user_id())
        return self.session_manager.get_all_sessions()

    def _assert_session_readable(self, session_id: str) -> None:
        """Deny reading a session's resources outside this identity's scope
        (bound session in Codex mode; owner in hosted). Defense-in-depth for the
        resource path, parity with call_tool's bound-session/ownership guards."""
        if self.bound_session:
            if session_id != self.bound_session:
                raise ValueError(f"Access denied; this server is bound to session '{self.bound_session}'.")
            return
        if self._hosted and not self.session_manager.owns_session(session_id, self.scoped_user_id()):
            raise ValueError("Access denied")

    def _setup_handlers(self):
        """Setup MCP protocol handlers"""
        @self.server.list_tools()
        async def handle_list_tools():
            return await self.list_tools()
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict):
            return await self.call_tool(name, arguments)
        
        @self.server.list_prompts()
        async def handle_list_prompts():
            return await self.list_prompts()
        
        @self.server.get_prompt()
        async def handle_get_prompt(name: str, arguments: dict | None):
            return await self.get_prompt(name, arguments)
        
        @self.server.list_resources()
        async def handle_list_resources():
            return await self.list_resources()
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str):
            return await self.read_resource(uri)
        
    async def list_resources(self) -> list[Resource]:
        """
        Expose sessions and workspace artifacts as browsable resources.
        """
        resources = [
            Resource(
                uri="rtl://sessions",
                name="Available Sessions",
                description="List of all RTL design sessions",
                mimeType="application/json"
            )
        ]
        
        # Add resources for each session THIS identity may see (bound session /
        # owner-scoped / all) — not every tenant's sessions.
        sessions = self._resource_sessions()
        for session_id in sessions:
            workspace = self.workspace_path(session_id)
            encoded_session_id = quote(session_id, safe="")
            
            # Session info resource
            resources.append(Resource(
                uri=f"rtl://session/{encoded_session_id}",
                name=f"Session: {session_id}",
                description=f"Workspace and metadata for session {session_id}",
                mimeType="application/json"
            ))
            
            # List files in session
            if os.path.exists(workspace):
                for filename in os.listdir(workspace):
                    filepath = os.path.join(workspace, filename)
                    if os.path.isfile(filepath):
                        resources.append(Resource(
                            uri=f"rtl://session/{encoded_session_id}/file/{quote(filename, safe='')}",
                            name=f"{session_id}/{filename}",
                            description=f"File from session {session_id}",
                            mimeType=self._get_mime_type(filename)
                        ))
        
        return resources
    
    async def read_resource(self, uri: str) -> ReadResourceResult:
        """
        Read the content of a resource (session info, files, etc.)
        """
        import json
        
        if uri == "rtl://sessions":
            # List only the sessions in this identity's scope (see _resource_sessions).
            sessions = self._resource_sessions()
            session_data = []
            for session_id in sessions:
                meta = self.session_manager.get_session_metadata(session_id)
                session_data.append({
                    "id": session_id,
                    "name": meta.get("session_name") if meta else session_id,
                    "model_name": meta.get("model_name") if meta else None,
                    "created_at": str(meta.get("created_at")) if meta else None,
                    "updated_at": str(meta.get("updated_at")) if meta and meta.get("updated_at") else None,
                    "total_tokens": meta.get("total_tokens", 0) if meta else 0,
                    "total_cost": meta.get("total_cost", 0.0) if meta else 0.0
                })
            
            return ReadResourceResult(
                contents=[
                    TextResourceContents(
                        uri=uri,
                        mimeType="application/json",
                        text=json.dumps(session_data, indent=2),
                    )
                ]
            )
        
        elif uri.startswith("rtl://session/"):
            remainder = uri.replace("rtl://session/", "", 1)

            if "/file/" in remainder:
                encoded_session_id, encoded_filename = remainder.split("/file/", 1)
                session_id = unquote(encoded_session_id)
                filename = unquote(encoded_filename)
                self._assert_session_readable(session_id)  # scope BEFORE touching the workspace
                workspace = self.workspace_path(session_id)
                filepath = os.path.join(workspace, filename)

                if not os.path.exists(filepath):
                    raise ValueError(f"File not found: {filename}")

                real_workspace = os.path.realpath(workspace)
                real_file = os.path.realpath(filepath)
                # Exact-or-under (with os.sep) so a sibling like `<ws>_other`
                # can't slip past a bare prefix match.
                if not (real_file == real_workspace or real_file.startswith(real_workspace + os.sep)):
                    raise ValueError("Access denied")

                with open(filepath, "r", errors="ignore") as f:
                    content = f.read()

                return ReadResourceResult(
                    contents=[
                        TextResourceContents(
                            uri=uri,
                            mimeType=self._get_mime_type(filename),
                            text=content,
                        )
                    ]
                )

            session_id = unquote(remainder)

            if session_id:
                self._assert_session_readable(session_id)  # scope BEFORE reading metadata/files
                # Session metadata
                meta = self.session_manager.get_session_metadata(session_id)
                workspace = self.workspace_path(session_id)
                
                files = []
                if os.path.exists(workspace):
                    files = os.listdir(workspace)
                
                session_info = {
                    "session_id": session_id,
                    "workspace": workspace,
                    "metadata": meta,
                    "files": files
                }
                
                return ReadResourceResult(
                    contents=[
                        TextResourceContents(
                            uri=uri,
                            mimeType="application/json",
                            text=json.dumps(session_info, indent=2, default=str),
                        )
                    ]
                )
        
        raise ValueError(f"Unknown resource URI: {uri}")
    
    def _get_mime_type(self, filename: str) -> str:
        """Determine MIME type from file extension."""
        ext = os.path.splitext(filename)[1].lower()
        mime_types = {
            ".v": "text/x-verilog",
            ".sv": "text/x-systemverilog",
            ".yaml": "application/yaml",
            ".yml": "application/yaml",
            ".md": "text/markdown",
            ".vcd": "application/octet-stream",
            ".gds": "application/octet-stream",
            ".svg": "image/svg+xml",
            ".sdc": "text/plain",
        }
        return mime_types.get(ext, "text/plain")
    
    async def list_prompts(self) -> list[Prompt]:
        """
        Provide predefined prompts that MCP clients can load.
        This allows Claude Desktop to use the SYSTEM_PROMPT!
        """
        return [
            Prompt(
                name="rtl_design_workflow",
                description="Expert RTL design workflow with Verilog best practices, verification methodology, and synthesis guidelines",
                arguments=[
                    {
                        "name": "session_id",
                        "description": "Session ID for workspace isolation (optional, creates new session if not provided)",
                        "required": False
                    }
                ]
            )
        ]
    
    async def get_prompt(self, name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        """
        Return the actual prompt content when requested by MCP client.
        """
        if name == "rtl_design_workflow":
            session_id = arguments.get("session_id") if arguments else None

            # Bound-session isolation (naman-ranka/siliconcrew#77): mirror the
            # call_tool guard. A bound server must never mint (or ensure) a
            # session from a prompts/get — an explicit different session_id is
            # refused exactly like call_tool refuses it, and no session_id
            # defaults to the bound session, which the constructor already
            # verified exists and is owned. Unbound behavior is unchanged.
            if self.bound_session:
                if session_id and session_id != self.bound_session:
                    raise ValueError(
                        f"Access denied; this server is bound to session '{self.bound_session}'."
                    )
                session_id = self.bound_session
            else:
                # If no session provided, generate a new one
                if not session_id:
                    import datetime
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    session_id = f"mcp_session_{timestamp}"
                session_id = self.session_manager.ensure_session(
                    tag=session_id, model_name="claude-via-mcp", user_id=self.scoped_user_id()
                )
            
            workspace = self.workspace_path(session_id)
            
            # Set as current session. Workspace resolution is now per-call via
            # session_request_scope (no process-global env mutation).
            self.current_session = session_id

            prompt_text, prompt_source, resolved_version = _load_architect_prompt()
            
            return GetPromptResult(
                description="RTL Design Expert System Prompt",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""You are now equipped with RTL design tools. Please follow this expert workflow:

{prompt_text}

---

**CURRENT SESSION**: {session_id}
**WORKSPACE**: {workspace}
**PROMPT_VERSION**: {resolved_version}
**PROMPT_SOURCE**: {prompt_source}

All tools will operate in this workspace. Files you create will be stored here.

**SESSION MANAGEMENT**:
- Use `set_active_session` to switch between sessions
- Use `list_sessions_tool` to see all available sessions
- Use `create_session_tool` to start a new isolated workspace
- Current session persists across tool calls

**IMPORTANT REMINDERS**:
1. ALWAYS start with `write_spec` before writing any RTL
2. ALWAYS use `linter_tool` after writing Verilog files
3. ALWAYS use `waveform_tool` to debug simulation failures (never guess!)
4. Follow the standard workflow: Spec → RTL → Testbench → Lint → Simulate → Debug → Synthesize

Ready to design! What would you like to create?"""
                        )
                    )
                ]
            )
        
        raise ValueError(f"Unknown prompt: {name}")
    
    async def list_tools(self) -> list[Tool]:
        """
        Expose RTL design tools using AUTO-DISCOVERY.
        Automatically converts LangChain tools to MCP format.

        The list is derived purely from the registry and is IDENTICAL for every
        connection: the MCP spec requires a server not to vary tools/list per
        connection except by auth scope, and per-process filter state leaked
        across tenants on the multiplexed streamable-HTTP transport.
        """
        tools_out = []

        # AUTO-DISCOVER every tool from the registry — including the session
        # tools, which used to be six hand-written Tool(name=..., inputSchema=)
        # objects right here. A hand-maintained schema is exactly the drift the
        # one-registry rule exists to prevent, and it kept them out of
        # build_catalog(), out of @policy and out of the schema tests.
        # A Codex-launched server serves one extra tool on top of the MCP set;
        # which tool that is comes from the tools' own surfaces, not from here.
        advertised = list(mcp_tools)
        if self.codex_tools:
            advertised += tools_on_surface("codex")
        for langchain_tool in advertised:
            try:
                mcp_tool = langchain_to_mcp_schema(langchain_tool)
                tools_out.append(mcp_tool)
            except Exception as e:
                print(f"Warning: Could not convert tool {langchain_tool.name}: {e}")
        
        return tools_out
    
    async def call_tool(self, name: str, arguments: dict[str, Any] | None) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """
        Execute a tool and return results.
        """
        if arguments is None:
            arguments = {}

        # Bound-session isolation (Codex): refuse session management and any tool
        # aimed at a different session, and pin the active session to the bound
        # one. Which tools those are is the tools' own declaration
        # (``disabled_when_bound``), read here and by the Codex engine that
        # writes the same set into config.toml's disabled_tools — one truth,
        # two readers, instead of the same four names typed in both places.
        if self.bound_session:
            if name in _SHARED_DISABLED_WHEN_BOUND:
                return [TextContent(type="text",
                    text=f"Session management is disabled; this server is bound to '{self.bound_session}'.")]
            req_sid = arguments.get("session_id")
            if req_sid and req_sid != self.bound_session:
                return [TextContent(type="text",
                    text=f"Access denied; this server is bound to session '{self.bound_session}'.")]
            self.current_session = self.bound_session

        # The session tools run BEFORE any session exists — that is what they
        # are for — so they dispatch here, outside the per-call session scope
        # and its workspace. Which tools those are is not a list kept here: it
        # is every tool whose policy says it needs no session. They need the
        # object that owns the active-session pointer, so this server binds
        # itself as their host for the duration of the call.
        if name in TOOL_REGISTRY and not requires_session(name):
            with session_host(self):
                return [TextContent(type="text", text=str(TOOL_REGISTRY[name].invoke(arguments)))]

        # A session must be active for regular tools (workspace is resolved
        # per-call via session_request_scope — no process-global env mutation).
        # This is the first thing a brand-new client hits, so the message has to
        # be recoverable on its own: name the tools that fix it, not just the
        # condition. (The same fact is stated once at connect time in
        # SERVER_INSTRUCTIONS; a client that ignored or never read those still
        # gets a way forward here.)
        if not self.current_session:
            return [TextContent(type="text", text=(
                f"❌ No active session, so '{name}' has no workspace to act on. "
                "A session is a workspace holding one design. Call "
                "create_session_tool to start a new design, or list_sessions_tool "
                "then set_active_session to continue an existing one — then retry "
                f"'{name}'."
            ))]

        # Defense in depth (F1 root cause 3): current_session is a process-global
        # field on the single hosted server that multiplexes all users, so a
        # concurrent request from another tenant can flip it underneath this
        # caller between their set_active_session and this dispatch. Re-verify
        # ownership before touching any workspace. Bound (Codex) mode is already
        # constrained to one owner-validated session, so it is exempt. The
        # durable fix is to request-scope current_session (REVIEW_FINDINGS P0 #1).
        if (
            self._hosted
            and not self.bound_session
            and not self.session_manager.owns_session(self.current_session, self.scoped_user_id())
        ):
            return [TextContent(type="text", text="❌ No active session for this user. Select one with set_active_session.")]

        # Capability gating: protected (synth/save) tools require a signed-in
        # identity. Self-host's local identity is non-anonymous → always allowed.
        if name in self._PROTECTED_TOOLS:
            try:
                authorize(self._current_identity(), Action.SYNTHESIZE if name in TOOL_CATEGORIES["synthesis"] else Action.SAVE)
            except AuthError as e:
                return [TextContent(type="text", text=f"❌ {e.message}")]

        # Dispatch from the single source of truth (TOOL_REGISTRY, derived from
        # mcp_tools) so every advertised tool is callable — no hand-maintained
        # map to drift out of sync.
        tool_map = TOOL_REGISTRY

        if name not in tool_map:
            raise ValueError(f"Unknown tool: {name}")
        
        # Execute the tool
        tool_func = tool_map[name]
        active_session = self.current_session
        # Pre-resolved path for the ONE place events may still be written
        # outside the bound scope: the scope-entry failure fallback in the
        # except handler below. Both normal-path events (call AND result) are
        # logged inside the bound scope via _invoke_with_call_log — attempt_
        # logger drops an event when the dir is absent and otherwise writes
        # attempt_events.jsonl there, so logging outside the scope either
        # vanished on a cold instance or landed on never-synced instance disk
        # (invariants 3 + 9). Cost stated plainly: on a cold hosted session
        # the "started" card appears after hydration, not before.
        active_workspace = self.workspace_path(active_session)
        identity = self._current_identity()
        uid = auth_engine.scoped_user_id(identity)

        # Both events are logged INSIDE the bound scope, before the scope's
        # exit sync — so a mutating call's synchronous sync covers its own
        # result event (previously the result was appended AFTER the sync and
        # sat on instance disk unscheduled: every successful mutating call's
        # "finished" card was lost to an instance recycle). It also pins both
        # events to the SAME workspace resolution (the bound scope's), so a
        # fallback provider can no longer split one call's events across two
        # files. This mirrors /invoke, which logs call+result inside
        # run_scoped. ``logged_result`` tells the outer handler whether the
        # error path still needs a best-effort event (scope-entry failures —
        # e.g. hydration — never reach the inner logging).
        logged_result = {"done": False}

        def _invoke_with_call_log(args):
            log_tool_call(
                workspace=get_workspace_path(),
                session_id=active_session,
                source="mcp",
                tool=name,
                arguments=args,
            )
            try:
                result = tool_func.invoke(args)
            except Exception as exc:
                log_tool_result(
                    workspace=get_workspace_path(),
                    session_id=active_session,
                    source="mcp",
                    tool=name,
                    result=None,
                    status="error",
                    error=str(exc),
                    arguments=args,
                )
                logged_result["done"] = True
                raise
            log_tool_result(
                workspace=get_workspace_path(),
                session_id=active_session,
                source="mcp",
                tool=name,
                result=str(result),
                status="success",
                arguments=args,
            )
            logged_result["done"] = True
            return result

        try:
            # Run the sync LangChain tool inside a per-call session scope bound in
            # the worker thread, so the workspace resolves task-locally and
            # concurrent MCP clients are isolated (replaces the RTL_WORKSPACE
            # env mutation). user_id/tier flow to tenancy + quota enforcement.
            #
            # F2 latency: only a MUTATING tool re-tars+uploads the workspace to
            # object storage on exit. A read-only tool (read_file/get_manifest/
            # get_synthesis_status/…) does NOT — a design loop is mostly reads,
            # and each was paying a full-workspace GCS PUT for nothing. Mirrors
            # the REST action router (actions.py run_scoped(mutates=…)). Two
            # caveats we accept by design: (1) the synth run-state that a status
            # read reconciles is persisted through its OWN durable push
            # (_persist_run_meta_durable → the run store), independent of this
            # workspace sync, so gating it off loses no run-state; (2) the
            # activity log a read appends (attempt_events.jsonl) rides the next
            # mutating call's sync (flush-on-next-mutation) — the only exposure
            # is a tail of pure-read calls before an instance recycle with no
            # following write, which is bounded and honest, not silent.
            # 4B: when the parent process syncs once per turn (Codex bound
            # mode, defer_workspace_sync), even a mutating call skips the
            # blocking per-tool upload — the write is persisted by the parent's
            # turn-end background sync instead.
            mutates = name in _SHARED_MUTATING_TOOLS
            result = await run_in_session(
                active_session,
                _invoke_with_call_log,
                arguments,
                user_id=uid,
                tier=identity.tier,
                sync=mutates and not self.defer_workspace_sync,
            )
            # Read-only calls append activity events with NO sync of their own
            # (the F2 gate above). Mark the flusher so those appends ride the
            # background incremental flush instead of waiting for the next
            # mutating call — otherwise an instance recycle, or another
            # writer's manifest bump forcing a hydration swap, deletes them.
            # Mutating calls synced synchronously inside the scope, AFTER both
            # events were logged (see _invoke_with_call_log) — so only the
            # non-synced paths need marking, and that claim is now true by
            # ordering, not by hope. Self-host: the flusher no-ops
            # (LocalWorkspaceProvider has no sync), so this is free.
            if not (mutates and not self.defer_workspace_sync):
                get_workspace_flusher().mark_dirty(active_session)

            return [TextContent(type="text", text=str(result))]

        except Exception as e:
            if not logged_result["done"]:
                # The scope itself failed (hydration, provider error) before
                # the inner logging could run: best-effort error event at the
                # pre-resolved path so the failure is not invisible.
                log_tool_result(
                    workspace=active_workspace,
                    session_id=active_session,
                    source="mcp",
                    tool=name,
                    result=None,
                    status="error",
                    error=str(e),
                    arguments=arguments,
                )
            else:
                # The tool succeeded (its success event is logged in-scope)
                # but the scope-EXIT sync raised afterwards. Two different
                # facts — the tool ran, the persist failed — and the client
                # is being told "Error", so the log must say why or the
                # activity trail and the reply disagree about the same call.
                log_tool_result(
                    workspace=active_workspace,
                    session_id=active_session,
                    source="mcp",
                    tool=name,
                    result=None,
                    status="error",
                    error=f"workspace sync failed after the call succeeded: {e}",
                    arguments=arguments,
                )
            get_workspace_flusher().mark_dirty(active_session)
            return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]

    def _hosted_auth_middleware(self):
        """Starlette middleware enforcing WorkOS bearer auth — hosted only.

        Returns an empty list in local/self-host so the remote transports are
        byte-for-byte today's "no auth" apps. In hosted mode it prepends the
        per-request auth middleware (which runs *inside* CORS so 401s still get
        CORS headers).
        """
        if not self._hosted:
            return []
        from starlette.middleware import Middleware
        from src.platform_engines.mcp_auth import HostedMCPAuthMiddleware

        return [Middleware(HostedMCPAuthMiddleware)]

    def _well_known_routes(self):
        """RFC 9728 protected-resource metadata route — hosted only (Slice 2)."""
        if not self._hosted:
            return []
        from starlette.routing import Route
        from starlette.responses import JSONResponse
        from src.platform_engines.mcp_auth import (
            PROTECTED_RESOURCE_PATH,
            _resource_metadata_url,
            protected_resource_metadata,
        )

        async def protected_resource(request):
            # Name this exact deployment as the resource; the issuer/auth-server
            # come from config so the AI client knows where to sign in.
            resource = str(request.base_url).rstrip("/") + "/mcp"
            return JSONResponse(protected_resource_metadata(resource_url=resource))

        return [Route(PROTECTED_RESOURCE_PATH, endpoint=protected_resource, methods=["GET"])]

    def _auth_banner(self) -> str:
        return (
            "   Auth: WorkOS bearer required (hosted); "
            f"metadata at /.well-known/oauth-protected-resource"
            if self._hosted
            else "   No authentication required"
        )

    def get_http_app(self):
        """Construct the Starlette app for Streamable HTTP transport (without starting uvicorn).

        Returns a tuple: (app, session_transport)
        """
        from mcp.server.streamable_http import StreamableHTTPServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount
        from starlette.middleware import Middleware
        from starlette.middleware.cors import CORSMiddleware

        # Create a session-less transport (no auth, stateless)
        session_transport = StreamableHTTPServerTransport(
            mcp_session_id=None,  # Stateless mode
        )

        async def handle_mcp(scope, receive, send):
            await session_transport.handle_request(scope, receive, send)

        app = Starlette(
            debug=False,
            routes=[
                Mount("/mcp", app=handle_mcp),
                *self._well_known_routes(),
            ],
            middleware=[
                Middleware(
                    CORSMiddleware,
                    allow_origins=["*"],
                    allow_methods=["*"],
                    allow_headers=["*"],
                ),
                # Hosted-only: per-request WorkOS auth, inside CORS. Empty in
                # self-host → identical to today's no-auth Streamable HTTP app.
                *self._hosted_auth_middleware(),
            ],
        )
        return app, session_transport

    async def run(self, transport: str = "stdio", host: str = "0.0.0.0", port: int = 8080):
        """Run the MCP server with the specified transport."""
        if transport == "stdio":
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )
        
        elif transport == "sse":
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Route, Mount
            from starlette.middleware import Middleware
            from starlette.middleware.cors import CORSMiddleware
            import uvicorn

            sse = SseServerTransport("/messages/")

            async def handle_sse(request):
                async with sse.connect_sse(
                    request.scope, request.receive, request._send
                ) as streams:
                    await self.server.run(
                        streams[0],
                        streams[1],
                        self.server.create_initialization_options()
                    )

            app = Starlette(
                debug=True,
                routes=[
                    Route("/sse", endpoint=handle_sse),
                    Mount("/messages/", app=sse.handle_post_message),
                    *self._well_known_routes(),
                ],
                middleware=[
                    Middleware(
                        CORSMiddleware,
                        allow_origins=["*"],
                        allow_methods=["*"],
                        allow_headers=["*"],
                    ),
                    # Hosted-only: per-request WorkOS auth, inside CORS. Empty in
                    # self-host → identical to today's no-auth SSE app.
                    *self._hosted_auth_middleware(),
                ],
            )

            print(f"🚀 MCP SSE server running on http://{host}:{port}")
            print(f"   SSE endpoint:     http://{host}:{port}/sse")
            print(f"   Messages endpoint: http://{host}:{port}/messages/")
            print(self._auth_banner())

            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()

        elif transport == "http":
            from mcp.server.streamable_http import StreamableHTTPServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Mount
            from starlette.middleware import Middleware
            from starlette.middleware.cors import CORSMiddleware
            import uvicorn
            from contextlib import suppress

            # Create a session-less transport (no auth, stateless)
            session_transport = StreamableHTTPServerTransport(
                mcp_session_id=None,  # Stateless mode
            )

            async def handle_mcp(scope, receive, send):
                await session_transport.handle_request(scope, receive, send)

            app = Starlette(
                debug=True,
                routes=[
                    Mount("/mcp", app=handle_mcp),
                    *self._well_known_routes(),
                ],
                middleware=[
                    Middleware(
                        CORSMiddleware,
                        allow_origins=["*"],
                        allow_methods=["*"],
                        allow_headers=["*"],
                    ),
                    # Hosted-only: per-request WorkOS auth, inside CORS. Empty in
                    # self-host → identical to today's no-auth Streamable HTTP app.
                    *self._hosted_auth_middleware(),
                ],
            )

            print(f"🚀 MCP Streamable HTTP server running on http://{host}:{port}")
            print(f"   MCP endpoint: http://{host}:{port}/mcp")
            print(self._auth_banner())

            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            web_server = uvicorn.Server(config)

            # Streamable HTTP transport needs an active connect() context before
            # handling requests.
            #
            # stateless=True MUST match the session-less transport above
            # (mcp_session_id=None). The default (stateless=False) leaves the
            # single long-lived ServerSession in NotInitialized until an
            # `initialize` handshake, so any request arriving before that — e.g.
            # a client reconnecting after a server restart WITHOUT re-handshaking
            # — makes ServerSession._received_request raise "Received request
            # before initialization was complete", which the SDK receive loop
            # blanket-maps to JSON-RPC -32602 "Invalid request parameters" (a
            # bad-argument lie). Pairing stateless transport with a stateless
            # session (as the SDK's own StreamableHTTPSessionManager does) treats
            # every request as post-init, so a reconnect just works. (F9c)
            async with session_transport.connect() as streams:
                mcp_task = asyncio.create_task(
                    self.server.run(
                        streams[0],
                        streams[1],
                        self.server.create_initialization_options(),
                        stateless=True,
                    )
                )
                try:
                    await web_server.serve()
                finally:
                    mcp_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await mcp_task

        else:
            raise ValueError(f"Unknown transport: {transport}. Use 'stdio', 'sse', or 'http'.")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="RTL Design Agent MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="Transport mode: stdio (local, default), sse (remote SSE), http (remote Streamable HTTP)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to for remote transports (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on for remote transports (default: 8080)"
    )
    parser.add_argument(
        "--codex-tools",
        action="store_true",
        help="Expose Codex-only helper tools (e.g., inject_architect_prompt)."
    )
    parser.add_argument(
        "--bound-session",
        default=None,
        help="Lock this server to one session id (Codex): blocks session management + cross-session access."
    )
    args = parser.parse_args()

    server = RTLDesignMCPServer(codex_tools=args.codex_tools, bound_session=args.bound_session)
    await server.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    asyncio.run(main())
