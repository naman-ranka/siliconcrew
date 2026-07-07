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
from src.tools.wrappers import (
    write_spec,
    read_spec,
    load_yaml_spec_file,
    write_file,
    read_file,
    apply_patch_tool,
    edit_file_tool,
    list_files_tool,
    linter_tool,
    simulation_tool,
    waveform_tool,
    cocotb_tool,
    sby_tool,
    start_synthesis,
    retry_pd,
    get_synthesis_status,
    wait_for_synthesis,
    get_synthesis_metrics,
    read_stage_report,
    get_route_drc_summary,
    get_cts_summary,
    get_congestion_summary,
    compare_pd_runs,
    search_logs_tool,
    schematic_tool,
    save_metrics_tool,
    generate_report_tool,
    run_dslx_interpreter,
    compile_dslx_to_ir,
    experimental_compile_cpp_to_ir,
    optimize_xls_ir,
    codegen_xls,
    benchmark_xls,
    run_xls_flow,
    get_workspace_path,
    mcp_tools,
)
from src.utils.session_manager import SessionManager
from src.utils.attempt_logger import log_tool_call, log_tool_result
from src.platform_engines.request_scope import run_in_session
from src.platform_engines import auth as auth_engine
from src.platform_engines.identity import Action, AuthError, authorize

load_dotenv()

# Single source of truth for tool dispatch: derive the name→tool map from the
# same ``mcp_tools`` list that ``list_tools`` advertises from. Building it by
# hand drifted (tools got listed but not dispatchable → "Unknown tool", e.g.
# run_isolated_simulation / get_manifest / update_manifest); deriving it keeps
# "advertised" and "callable" in lockstep. See test_mcp_tool_registry.
TOOL_REGISTRY = {t.name: t for t in mcp_tools}

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts" / "architect"
DEFAULT_ARCHITECT_PROMPT_VERSION = (os.environ.get("ARCHITECT_PROMPT_VERSION", "v2") or "v2").strip().lower()
if not DEFAULT_ARCHITECT_PROMPT_VERSION:
    DEFAULT_ARCHITECT_PROMPT_VERSION = "v2"


def _load_architect_prompt() -> tuple[str, str, str]:
    """
    Load a versioned architect prompt from prompts/architect.
    Falls back to SYSTEM_PROMPT if the file is unavailable.
    Returns: (prompt_text, source_label, resolved_version)
    """
    resolved = DEFAULT_ARCHITECT_PROMPT_VERSION
    prompt_file = PROMPTS_DIR / f"architect_prompt_{resolved}.md"
    if prompt_file.exists():
        try:
            return prompt_file.read_text(encoding="utf-8"), str(prompt_file), resolved
        except Exception:
            # Fall through to SYSTEM_PROMPT fallback.
            pass

    # Lazy: the LangGraph agent stack behind SYSTEM_PROMPT is only needed on
    # this fallback (prompt file missing/unreadable) — importing it at module
    # load taxed every Codex MCP subprocess spawn for a constant that is
    # almost never used (4C, hosted-latency plan).
    from src.agents.architect import SYSTEM_PROMPT

    return SYSTEM_PROMPT, "src.agents.architect.SYSTEM_PROMPT", "legacy"

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
)

# Flatten for easy lookup
ALL_CATEGORIZED_TOOLS = set()
for tools in TOOL_CATEGORIES.values():
    ALL_CATEGORIZED_TOOLS.update(tools)


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
        self.server = Server("rtl-design-agent")
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
        self.tool_filter_mode = "all"  # Options: "all", "essential", "custom"
        self.custom_tool_filter = None  # List of tool names or categories
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
        # set — _scoped_user_id resolves identity through it.)
        if self.bound_session:
            if not self.session_manager.owns_session(self.bound_session, self._scoped_user_id()):
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

    def _scoped_user_id(self):
        return auth_engine.scoped_user_id(self._current_identity())

    def _resource_sessions(self) -> list[str]:
        """Sessions this MCP identity may see through the RESOURCE surface —
        mirrors the tool path's scoping so resources can't leak past the same
        boundary tool calls respect: the bound session only (Codex bound mode),
        the owner's sessions (hosted), or all (self-host / single-tenant)."""
        if self.bound_session:
            return [self.bound_session]
        if self._hosted:
            return self.session_manager.get_all_sessions(user_id=self._scoped_user_id())
        return self.session_manager.get_all_sessions()

    def _assert_session_readable(self, session_id: str) -> None:
        """Deny reading a session's resources outside this identity's scope
        (bound session in Codex mode; owner in hosted). Defense-in-depth for the
        resource path, parity with call_tool's bound-session/ownership guards."""
        if self.bound_session:
            if session_id != self.bound_session:
                raise ValueError(f"Access denied; this server is bound to session '{self.bound_session}'.")
            return
        if self._hosted and not self.session_manager.owns_session(session_id, self._scoped_user_id()):
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
            workspace = self.session_manager.get_workspace_path(session_id)
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
                workspace = self.session_manager.get_workspace_path(session_id)
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
                workspace = self.session_manager.get_workspace_path(session_id)
                
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
            
            # If no session provided, generate a new one
            if not session_id:
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                session_id = f"mcp_session_{timestamp}"
            session_id = self.session_manager.ensure_session(
                tag=session_id, model_name="claude-via-mcp", user_id=self._scoped_user_id()
            )
            
            workspace = self.session_manager.get_workspace_path(session_id)
            
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
    
    def _should_include_tool(self, tool_name: str) -> bool:
        """Determine if a tool should be included based on current filter mode."""
        if self.tool_filter_mode == "all":
            return True
        
        if self.tool_filter_mode == "essential":
            return tool_name in TOOL_CATEGORIES["essential"]
        
        if self.tool_filter_mode == "custom" and self.custom_tool_filter:
            # Check if tool name is directly in filter
            if tool_name in self.custom_tool_filter:
                return True
            # Check if any category in filter contains this tool
            for item in self.custom_tool_filter:
                if item in TOOL_CATEGORIES and tool_name in TOOL_CATEGORIES[item]:
                    return True
            return False
        
        return True
    
    async def list_tools(self) -> list[Tool]:
        """
        Expose RTL design tools using AUTO-DISCOVERY with optional filtering.
        Automatically converts LangChain tools to MCP format.
        
        Filtering controlled by:
        - self.tool_filter_mode: "all" | "essential" | "custom"
        - self.custom_tool_filter: List of tool names or categories
        """
        tools_out = []
        
        # Session management tools (always included)
        tools_out.extend([
            Tool(
                name="create_session_tool",
                description="Create a new isolated session workspace for a design project.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_name": {"type": "string", "description": "Session name (e.g., 'counter_design')"},
                        "model_name": {"type": "string", "description": "Model name for tracking", "default": "claude-via-mcp"},
                        "project_id": {"type": "string", "description": "Optional project ID to group this session under. Project must already exist."}
                    },
                    "required": ["session_name"]
                }
            ),
            Tool(
                name="list_sessions_tool",
                description="List all available sessions with metadata.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="set_active_session",
                description="Switch to a different session. All tools will use that session's workspace.",
                inputSchema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="get_current_session",
                description="Get the currently active session ID and workspace path.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="delete_session_tool",
                description="Delete a session and all its workspace files.",
                inputSchema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"]
                }
            ),
        ])
        
        # Add tool filtering control tool
        tools_out.append(
            Tool(
                name="configure_tool_filter",
                description="Control which tools are visible to reduce cognitive load. Use 'essential' for basic workflow, 'all' for everything, or specify custom categories.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["all", "essential", "custom"],
                            "description": "Filter mode: 'all', 'essential' (7 core tools), or 'custom' (specify categories/tools)"
                        },
                        "custom_filter": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tool names or categories (essential, verification, synthesis, editing, reporting, hls)"
                        }
                    },
                    "required": ["mode"]
                }
            )
        )

        # Codex-only helper tools (disabled by default for other MCP clients)
        if self.codex_tools:
            tools_out.append(
                Tool(
                    name="inject_architect_prompt",
                    description="Return the configured Architect prompt for Codex clients. Optional session_id also sets active session/workspace.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Optional existing session to activate before returning the prompt"
                            }
                        }
                    }
                )
            )
        
        # AUTO-DISCOVER all LangChain tools from mcp_tools (with filtering)
        for langchain_tool in mcp_tools:
            try:
                # Apply filter
                if not self._should_include_tool(langchain_tool.name):
                    continue
                
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
        # one. Defense-in-depth — config.toml also lists these in disabled_tools.
        if self.bound_session:
            if name in {"create_session_tool", "list_sessions_tool", "delete_session_tool", "set_active_session"}:
                return [TextContent(type="text",
                    text=f"Session management is disabled; this server is bound to '{self.bound_session}'.")]
            req_sid = arguments.get("session_id")
            if req_sid and req_sid != self.bound_session:
                return [TextContent(type="text",
                    text=f"Access denied; this server is bound to session '{self.bound_session}'.")]
            self.current_session = self.bound_session

        # Handle session management tools
        if name == "create_session_tool":
            session_name = arguments["session_name"]
            model_name = arguments.get("model_name", "claude-via-mcp")
            project_id = arguments.get("project_id") or None
            try:
                session_id = self.session_manager.create_session(
                    tag=session_name, model_name=model_name, project_id=project_id,
                    user_id=self._scoped_user_id(),
                )
                self.current_session = session_id
                workspace = self.session_manager.get_workspace_path(session_id)
                project_line = f"\nProject: {project_id}" if project_id else ""
                return [TextContent(
                    type="text",
                    text=f"✅ Created session '{session_id}'\nWorkspace: {workspace}{project_line}\nThis session is now active."
                )]
            except FileExistsError:
                return [TextContent(type="text", text=f"❌ Session '{session_name}' already exists. Use set_active_session to switch to it.")]
            except Exception as e:
                return [TextContent(type="text", text=f"❌ Error creating session: {str(e)}")]
        
        elif name == "list_sessions_tool":
            # Tenant scope (F1): pass the caller's scoped uid so hosted users see
            # ONLY their own sessions. Self-host uid is None → full list (parity
            # with the resource path and set_active_session's ownership check).
            uid = self._scoped_user_id()
            sessions = self.session_manager.get_all_sessions(user_id=uid)
            if not sessions:
                return [TextContent(type="text", text="No sessions found. Create one with create_session_tool.")]

            import json
            session_list = []
            for session_id in sessions:
                meta = self.session_manager.get_session_metadata(session_id, user_id=uid)
                is_current = "← ACTIVE" if session_id == self.current_session else ""
                session_list.append({
                    "id": session_id,
                    "model": meta.get("model_name") if meta else "unknown",
                    "created": str(meta.get("created_at")) if meta else "unknown",
                    "tokens": meta.get("total_tokens", 0) if meta else 0,
                    "active": is_current
                })
            
            return [TextContent(type="text", text=json.dumps(session_list, indent=2))]
        
        elif name == "set_active_session":
            session_id = arguments["session_id"]
            # Tenant check: only switch to a session the caller owns (self-host
            # uid is None → any existing session).
            if not self.session_manager.owns_session(session_id, self._scoped_user_id()):
                return [TextContent(type="text", text=f"❌ Session '{session_id}' not found.")]
            workspace = self.session_manager.get_workspace_path(session_id)

            self.current_session = session_id
            return [TextContent(
                type="text",
                text=f"✅ Switched to session '{session_id}'\nWorkspace: {workspace}\nAll tools will now use this workspace."
            )]
        
        elif name == "get_current_session":
            if not self.current_session:
                return [TextContent(type="text", text="No active session. Load a prompt or call create_session_tool.")]
            
            workspace = self.session_manager.get_workspace_path(self.current_session)
            meta = self.session_manager.get_session_metadata(self.current_session)
            
            import json
            info = {
                "session_id": self.current_session,
                "workspace": workspace,
                "metadata": meta
            }
            return [TextContent(type="text", text=json.dumps(info, indent=2, default=str))]
        
        elif name == "delete_session_tool":
            session_id = arguments["session_id"]
            if session_id == self.current_session:
                return [TextContent(type="text", text=f"❌ Cannot delete active session. Switch to another session first.")]
            
            try:
                # Tenant scope (F1): pass the caller's scoped uid so the
                # ownership guard in delete_session fires. Without it a hosted
                # user could rmtree ANY tenant's workspace/chats/checkpoints by id.
                self.session_manager.delete_session(session_id, user_id=self._scoped_user_id())
                return [TextContent(type="text", text=f"✅ Deleted session '{session_id}' and all its files.")]
            except PermissionError:
                # Do not leak the existence of another tenant's session.
                return [TextContent(type="text", text=f"❌ Session '{session_id}' not found.")]
            except Exception as e:
                return [TextContent(type="text", text=f"❌ Error deleting session: {str(e)}")]
        
        elif name == "configure_tool_filter":
            mode = arguments["mode"]
            custom_filter = arguments.get("custom_filter")
            
            self.tool_filter_mode = mode
            self.custom_tool_filter = custom_filter
            
            # Count how many tools will be visible
            visible_count = 0
            for tool in mcp_tools:
                if self._should_include_tool(tool.name):
                    visible_count += 1
            
            visible_count += 6  # Session tools + configure_tool_filter
            
            import json
            response = f"✅ Tool filter updated to '{mode}'\n"
            response += f"📊 Visible tools: {visible_count}\n"
            
            if mode == "essential":
                response += f"\nEssential tools: {', '.join(TOOL_CATEGORIES['essential'])}"
            elif mode == "custom" and custom_filter:
                response += f"\nCustom filter: {json.dumps(custom_filter)}"
            
            response += "\n\n⚠️  Note: Client may need to refresh tool list to see changes."
            
            return [TextContent(type="text", text=response)]

        elif name == "inject_architect_prompt":
            session_id = arguments.get("session_id")
            workspace = None

            if session_id:
                if not self.session_manager.owns_session(session_id, self._scoped_user_id()):
                    return [TextContent(type="text", text=f"❌ Session '{session_id}' not found.")]
                workspace = self.session_manager.get_workspace_path(session_id)
                self.current_session = session_id
            elif self.current_session:
                workspace = self.session_manager.get_workspace_path(self.current_session)

            prompt_text, prompt_source, resolved_version = _load_architect_prompt()
            payload = f"{prompt_text}"
            if self.current_session and workspace:
                payload += (
                    "\n\n---\n"
                    f"CURRENT_SESSION: {self.current_session}\n"
                    f"WORKSPACE: {workspace}\n"
                    f"PROMPT_VERSION: {resolved_version}\n"
                    f"PROMPT_SOURCE: {prompt_source}\n"
                    "All tool calls should operate inside this workspace."
                )
            else:
                payload += (
                    "\n\n---\n"
                    f"PROMPT_VERSION: {resolved_version}\n"
                    f"PROMPT_SOURCE: {prompt_source}\n"
                )

            return [TextContent(type="text", text=payload)]
        
        # A session must be active for regular tools (workspace is resolved
        # per-call via session_request_scope — no process-global env mutation).
        if not self.current_session:
            return [TextContent(type="text", text="❌ No active session. Create or select one first.")]

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
            and not self.session_manager.owns_session(self.current_session, self._scoped_user_id())
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
        active_workspace = self.session_manager.get_workspace_path(active_session)
        identity = self._current_identity()
        uid = auth_engine.scoped_user_id(identity)

        try:
            log_tool_call(
                workspace=active_workspace,
                session_id=active_session,
                source="mcp",
                tool=name,
                arguments=arguments,
            )
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
                tool_func.invoke,
                arguments,
                user_id=uid,
                tier=identity.tier,
                sync=mutates and not self.defer_workspace_sync,
            )
            log_tool_result(
                workspace=active_workspace,
                session_id=active_session,
                source="mcp",
                tool=name,
                result=str(result),
                status="success",
                arguments=arguments,
            )
            
            return [TextContent(type="text", text=str(result))]
            
        except Exception as e:
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
