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
from typing import Any, Sequence

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
    ReadResourceResult,
)

from dotenv import load_dotenv
from src.tools.wrappers import (
    write_spec,
    read_spec,
    load_yaml_spec_file,
    write_file,
    read_file,
    edit_file_tool,
    list_files_tool,
    linter_tool,
    simulation_tool,
    waveform_tool,
    cocotb_tool,
    sby_tool,
    start_synthesis,
    get_synthesis_job,
    search_logs_tool,
    schematic_tool,
    save_metrics_tool,
    generate_report_tool,
    get_workspace_path,
    mcp_tools,
)
from src.agents.architect import SYSTEM_PROMPT
from src.utils.session_manager import SessionManager

load_dotenv()

# =============================================================================
# TOOL AUTO-DISCOVERY HELPERS
# =============================================================================

# Tool categorization for filtering
TOOL_CATEGORIES = {
    "essential": [
        "write_spec", "read_spec", "write_file", "read_file", 
        "linter_tool", "simulation_tool", "list_files_tool"
    ],
    "verification": [
        "waveform_tool", "cocotb_tool", "sby_tool"
    ],
    "synthesis": [
        "start_synthesis", "get_synthesis_job", "search_logs_tool", "schematic_tool"
    ],
    "editing": [
        "edit_file_tool", "load_yaml_spec_file"
    ],
    "reporting": [
        "save_metrics_tool", "generate_report_tool"
    ]
}

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
    def __init__(self):
        self.server = Server("rtl-design-agent")
        # Use absolute paths relative to this script
        base_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_dir = os.path.join(base_dir, "workspace")
        _data_dir = os.path.join(os.path.expanduser("~"), ".siliconcrew")
        os.makedirs(_data_dir, exist_ok=True)
        db_path = os.path.join(_data_dir, "state.db")
        
        self.session_manager = SessionManager(base_dir=workspace_dir, db_path=db_path)
        self.current_session = None  # Track active session
        self.tool_filter_mode = "all"  # Options: "all", "essential", "custom"
        self.custom_tool_filter = None  # List of tool names or categories
        
        # Register handlers using decorators
        self._setup_handlers()
    
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
        
        # Add resources for each session
        sessions = self.session_manager.get_all_sessions()
        for session_id in sessions:
            workspace = self.session_manager.get_workspace_path(session_id)
            
            # Session info resource
            resources.append(Resource(
                uri=f"rtl://session/{session_id}",
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
                            uri=f"rtl://session/{session_id}/file/{filename}",
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
            # List all sessions with metadata
            sessions = self.session_manager.get_all_sessions()
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
                    TextContent(
                        type="text",
                        text=json.dumps(session_data, indent=2),
                        uri=uri,
                        mimeType="application/json"
                    )
                ]
            )
        
        elif uri.startswith("rtl://session/"):
            parts = uri.replace("rtl://session/", "").split("/")
            session_id = parts[0]
            
            if len(parts) == 1:
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
                        TextContent(
                            type="text",
                            text=json.dumps(session_info, indent=2),
                            uri=uri,
                            mimeType="application/json"
                        )
                    ]
                )
            
            elif len(parts) == 3 and parts[1] == "file":
                # Read specific file
                filename = parts[2]
                workspace = self.session_manager.get_workspace_path(session_id)
                filepath = os.path.join(workspace, filename)
                
                if not os.path.exists(filepath):
                    raise ValueError(f"File not found: {filename}")
                
                with open(filepath, "r", errors="ignore") as f:
                    content = f.read()
                
                return ReadResourceResult(
                    contents=[
                        TextContent(
                            type="text",
                            text=content,
                            uri=uri,
                            mimeType=self._get_mime_type(filename)
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
                try:
                    session_id = self.session_manager.create_session(tag=session_id, model_name="claude-via-mcp")
                except FileExistsError:
                    # Session already exists, use it
                    pass
            
            # Ensure session exists
            workspace = self.session_manager.get_workspace_path(session_id)
            if not os.path.exists(workspace):
                os.makedirs(workspace)
            
            # Set as current session
            self.current_session = session_id
            
            # Set workspace for tools
            os.environ["RTL_WORKSPACE"] = workspace
            
            return GetPromptResult(
                description="RTL Design Expert System Prompt",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""You are now equipped with RTL design tools. Please follow this expert workflow:

{SYSTEM_PROMPT}

---

**CURRENT SESSION**: {session_id}
**WORKSPACE**: {workspace}

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
                        "model_name": {"type": "string", "description": "Model name for tracking", "default": "claude-via-mcp"}
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
                            "description": "Filter mode: 'all' (23 tools), 'essential' (7 core tools), 'custom' (specify categories/tools)"
                        },
                        "custom_filter": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tool names or categories (essential, verification, synthesis, editing, reporting)"
                        }
                    },
                    "required": ["mode"]
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
        
        # Handle session management tools
        if name == "create_session_tool":
            session_name = arguments["session_name"]
            model_name = arguments.get("model_name", "claude-via-mcp")
            try:
                session_id = self.session_manager.create_session(tag=session_name, model_name=model_name)
                self.current_session = session_id
                workspace = self.session_manager.get_workspace_path(session_id)
                os.environ["RTL_WORKSPACE"] = workspace
                return [TextContent(
                    type="text",
                    text=f"✅ Created session '{session_id}'\nWorkspace: {workspace}\nThis session is now active."
                )]
            except FileExistsError:
                return [TextContent(type="text", text=f"❌ Session '{session_name}' already exists. Use set_active_session to switch to it.")]
            except Exception as e:
                return [TextContent(type="text", text=f"❌ Error creating session: {str(e)}")]
        
        elif name == "list_sessions_tool":
            sessions = self.session_manager.get_all_sessions()
            if not sessions:
                return [TextContent(type="text", text="No sessions found. Create one with create_session_tool.")]
            
            import json
            session_list = []
            for session_id in sessions:
                meta = self.session_manager.get_session_metadata(session_id)
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
            workspace = self.session_manager.get_workspace_path(session_id)
            if not os.path.exists(workspace):
                return [TextContent(type="text", text=f"❌ Session '{session_id}' not found.")]
            
            self.current_session = session_id
            os.environ["RTL_WORKSPACE"] = workspace
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
            return [TextContent(type="text", text=json.dumps(info, indent=2))]
        
        elif name == "delete_session_tool":
            session_id = arguments["session_id"]
            if session_id == self.current_session:
                return [TextContent(type="text", text=f"❌ Cannot delete active session. Switch to another session first.")]
            
            try:
                self.session_manager.delete_session(session_id)
                return [TextContent(type="text", text=f"✅ Deleted session '{session_id}' and all its files.")]
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
        
        # Ensure workspace is set for regular tools
        if self.current_session:
            workspace = self.session_manager.get_workspace_path(self.current_session)
            os.environ["RTL_WORKSPACE"] = workspace
        
        # Map tool names to implementations
        tool_map = {
            "write_spec": write_spec,
            "read_spec": read_spec,
            "load_yaml_spec_file": load_yaml_spec_file,
            "write_file": write_file,
            "read_file": read_file,
            "edit_file_tool": edit_file_tool,
            "list_files_tool": list_files_tool,
            "linter_tool": linter_tool,
            "simulation_tool": simulation_tool,
            "waveform_tool": waveform_tool,
            "cocotb_tool": cocotb_tool,
            "sby_tool": sby_tool,
            "start_synthesis": start_synthesis,
            "get_synthesis_job": get_synthesis_job,
            "search_logs_tool": search_logs_tool,
            "schematic_tool": schematic_tool,
            "save_metrics_tool": save_metrics_tool,
            "generate_report_tool": generate_report_tool,
        }
        
        if name not in tool_map:
            raise ValueError(f"Unknown tool: {name}")
        
        # Execute the tool
        tool_func = tool_map[name]
        
        try:
            # LangChain tools are sync, so we run in executor for async
            result = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: tool_func.invoke(arguments)
            )
            
            return [TextContent(type="text", text=str(result))]
            
        except Exception as e:
            return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]
    
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
                ],
                middleware=[
                    Middleware(
                        CORSMiddleware,
                        allow_origins=["*"],
                        allow_methods=["*"],
                        allow_headers=["*"],
                    )
                ],
            )

            print(f"🚀 MCP SSE server running on http://{host}:{port}")
            print(f"   SSE endpoint:     http://{host}:{port}/sse")
            print(f"   Messages endpoint: http://{host}:{port}/messages/")
            print(f"   No authentication required")

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

            # Create a session-less transport (no auth, stateless)
            session_transport = StreamableHTTPServerTransport(
                mcp_session_id=None,  # Stateless mode
            )

            async def handle_mcp(request):
                async with session_transport.connect(
                    request.scope, request.receive, request._send
                ) as streams:
                    await self.server.run(
                        streams[0],
                        streams[1],
                        self.server.create_initialization_options()
                    )

            from starlette.routing import Route

            app = Starlette(
                debug=True,
                routes=[
                    Route("/mcp", endpoint=handle_mcp, methods=["GET", "POST", "DELETE"]),
                ],
                middleware=[
                    Middleware(
                        CORSMiddleware,
                        allow_origins=["*"],
                        allow_methods=["*"],
                        allow_headers=["*"],
                    )
                ],
            )

            print(f"🚀 MCP Streamable HTTP server running on http://{host}:{port}")
            print(f"   MCP endpoint: http://{host}:{port}/mcp")
            print(f"   No authentication required")

            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()

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
    args = parser.parse_args()

    server = RTLDesignMCPServer()
    await server.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    asyncio.run(main())
