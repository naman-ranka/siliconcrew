"""
SiliconCrew Architect - FastAPI Backend

Production-grade API server for the RTL Design Agent.
Provides REST endpoints and WebSocket streaming for the Next.js frontend.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yaml

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agents.architect import create_architect_agent, SYSTEM_PROMPT
from src.utils.session_manager import SessionManager
from src.tools.design_report import save_design_report

# Load environment
load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = os.path.dirname(__file__)
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
DB_PATH = os.path.join(BASE_DIR, "state.db")

# Pricing Constants (Per 1M Tokens)
PRICING = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-3-pro-preview": {"input": 2.00, "output": 12.00}
}

# Initialize Session Manager
session_manager = SessionManager(base_dir=WORKSPACE_DIR, db_path=DB_PATH)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class SessionCreate(BaseModel):
    name: str
    model: str = "gemini-2.5-flash"


class SessionResponse(BaseModel):
    id: str
    model_name: Optional[str] = None
    created_at: Optional[str] = None
    total_tokens: int = 0
    total_cost: float = 0.0


class MessageResponse(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None


class FileInfo(BaseModel):
    name: str
    path: str
    type: str
    size: int
    modified: str


class SpecResponse(BaseModel):
    filename: str
    content: str
    parsed: Optional[Dict[str, Any]] = None


class CodeFile(BaseModel):
    filename: str
    content: str
    language: str = "verilog"


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
    rates = PRICING.get(model_name, PRICING["gemini-2.5-flash"])
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
    if "Error" in content or "FAILED" in content or "Fail" in content:
        status = "error"
    elif "Success" in content or "PASSED" in content or "Pass" in content:
        status = "success"

    return {
        "status": status,
        "content": content[:5000] if len(content) > 5000 else content
    }


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

    yield

    # Shutdown
    print("[API] Shutting down...")


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="SiliconCrew Architect API",
    description="API for the RTL Design Agent",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# SESSION ENDPOINTS
# =============================================================================

@app.get("/api/sessions", response_model=List[SessionResponse])
async def list_sessions():
    """List all sessions."""
    sessions = session_manager.get_all_sessions()
    result = []

    for session_id in sessions:
        meta = session_manager.get_session_metadata(session_id)
        result.append(SessionResponse(
            id=session_id,
            model_name=meta.get("model_name") if meta else None,
            created_at=str(meta.get("created_at")) if meta else None,
            total_tokens=meta.get("total_tokens", 0) if meta else 0,
            total_cost=meta.get("total_cost", 0.0) if meta else 0.0
        ))

    return result


@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(data: SessionCreate):
    """Create a new session."""
    try:
        session_id = session_manager.create_session(tag=data.name, model_name=data.model)
        meta = session_manager.get_session_metadata(session_id)

        return SessionResponse(
            id=session_id,
            model_name=data.model,
            created_at=str(meta.get("created_at")) if meta else None,
            total_tokens=0,
            total_cost=0.0
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session details."""
    meta = session_manager.get_session_metadata(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        id=session_id,
        model_name=meta.get("model_name"),
        created_at=str(meta.get("created_at")),
        total_tokens=meta.get("total_tokens", 0),
        total_cost=meta.get("total_cost", 0.0)
    )


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    session_manager.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


# =============================================================================
# CHAT ENDPOINTS
# =============================================================================

@app.get("/api/chat/{session_id}/history")
async def get_chat_history(session_id: str) -> List[Dict[str, Any]]:
    """Get chat history for a session."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        async with AsyncSqliteSaver.from_conn_string(DB_PATH) as memory:
            meta = session_manager.get_session_metadata(session_id)
            model_name = meta.get("model_name", "gemini-2.5-flash") if meta else "gemini-2.5-flash"

            agent_graph = create_architect_agent(checkpointer=memory, model_name=model_name)
            config = {"configurable": {"thread_id": session_id}}

            current_state = await agent_graph.aget_state(config)

            if not current_state.values or "messages" not in current_state.values:
                return []

            messages = current_state.values["messages"]
            history = []

            for msg in messages:
                if isinstance(msg, SystemMessage):
                    continue
                elif isinstance(msg, HumanMessage):
                    history.append({
                        "role": "user",
                        "content": get_clean_content(msg)
                    })
                elif isinstance(msg, AIMessage):
                    entry = {
                        "role": "assistant",
                        "content": get_clean_content(msg),
                        "tool_calls": []
                    }

                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        entry["tool_calls"] = [
                            format_tool_call_for_api(tc) for tc in msg.tool_calls
                        ]

                    history.append(entry)

                elif hasattr(msg, "tool_call_id"):
                    # Tool result - attach to previous assistant message
                    result = format_tool_result_for_api(msg.content)
                    if history and history[-1]["role"] == "assistant":
                        if "tool_results" not in history[-1]:
                            history[-1]["tool_results"] = []
                        history[-1]["tool_results"].append({
                            "tool_call_id": msg.tool_call_id,
                            **result
                        })

            return history

    except Exception as e:
        print(f"[ERROR] Loading history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/api/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming chat."""
    await websocket.accept()

    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        await websocket.send_json({"type": "error", "error": "Session not found"})
        await websocket.close()
        return

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("message", "")

            if not message.strip():
                await websocket.send_json({"type": "error", "error": "Empty message"})
                continue

            # Set workspace path for tools
            os.environ["RTL_WORKSPACE"] = workspace
            print(f"[CHAT] Session: {session_id} | Message: {message[:50]}...")

            # Initialize agent with AsyncSqliteSaver (supports async streaming/state)
            async with AsyncSqliteSaver.from_conn_string(DB_PATH) as memory:
                meta = session_manager.get_session_metadata(session_id)
                model_name = meta.get("model_name", "gemini-2.5-flash") if meta else "gemini-2.5-flash"

                agent_graph = create_architect_agent(checkpointer=memory, model_name=model_name)
                config = {"configurable": {"thread_id": session_id}, "recursion_limit": 50}

                # Check for corrupted state
                snapshot = await agent_graph.aget_state(config)
                input_messages = []

                if snapshot.values and snapshot.values.get("messages"):
                    messages = snapshot.values["messages"]
                    pending_tool_ids = set()

                    for msg in messages:
                        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                pending_tool_ids.add(tc.get("id"))
                        elif hasattr(msg, "tool_call_id"):
                            pending_tool_ids.discard(msg.tool_call_id)

                    # Fix corrupted state with fake responses
                    if pending_tool_ids:
                        for tool_id in pending_tool_ids:
                            fake_response = ToolMessage(
                                content="[Tool execution was interrupted. Please retry the operation.]",
                                tool_call_id=tool_id
                            )
                            input_messages.append(fake_response)

                if not snapshot.values or not snapshot.values.get("messages"):
                    input_messages.append(SystemMessage(content=SYSTEM_PROMPT))
                input_messages.append(("user", message))

                # Stream using LangGraph's astream()
                await websocket.send_json({"type": "start"})

                total_input_tokens = 0
                total_output_tokens = 0

                try:
                    async for event in agent_graph.astream(
                        {"messages": input_messages},
                        config,
                        stream_mode="updates"
                    ):
                        if "agent" in event:
                            msg = event["agent"]["messages"][-1]

                            # Send text content
                            text = get_clean_content(msg)
                            if text:
                                await websocket.send_json({
                                    "type": "text",
                                    "content": text
                                })

                            # Track tokens
                            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                                total_input_tokens += msg.usage_metadata.get("input_tokens", 0)
                                total_output_tokens += msg.usage_metadata.get("output_tokens", 0)

                            # Send tool calls
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    await websocket.send_json({
                                        "type": "tool_call",
                                        "tool": format_tool_call_for_api(tc)
                                    })

                        elif "tools" in event:
                            msg = event["tools"]["messages"][-1]
                            result = format_tool_result_for_api(msg.content)
                            await websocket.send_json({
                                "type": "tool_result",
                                "tool_call_id": msg.tool_call_id,
                                **result
                            })

                    # Update token usage
                    if total_input_tokens > 0 or total_output_tokens > 0:
                        current_meta = session_manager.get_session_metadata(session_id)
                        if current_meta:
                            new_input = current_meta.get("input_tokens", 0) + total_input_tokens
                            new_output = current_meta.get("output_tokens", 0) + total_output_tokens
                            cached = current_meta.get("cached_tokens", 0)
                            new_cost = calculate_cost(new_input, new_output, model_name)
                            session_manager.update_session_stats(session_id, new_input, new_output, cached, new_cost)

                    await websocket.send_json({
                        "type": "done",
                        "tokens": {
                            "input": total_input_tokens,
                            "output": total_output_tokens
                        }
                    })

                except Exception as e:
                    print(f"[ERROR] Agent error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e)
                    })

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

@app.get("/api/workspace/{session_id}/files")
async def list_workspace_files(session_id: str) -> List[FileInfo]:
    """List all files in the workspace."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    files = []
    for item in os.listdir(workspace):
        item_path = os.path.join(workspace, item)
        if os.path.isfile(item_path):
            stat = os.stat(item_path)

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
                path=item_path,
                type=file_type,
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime).isoformat()
            ))

    return sorted(files, key=lambda f: f.modified, reverse=True)


@app.get("/api/workspace/{session_id}/spec")
async def get_spec(session_id: str) -> SpecResponse:
    """Get the latest spec file."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    spec_files = sorted(
        [f for f in os.listdir(workspace) if f.endswith("_spec.yaml")],
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


@app.get("/api/workspace/{session_id}/code")
async def get_code_files(session_id: str) -> List[CodeFile]:
    """Get all Verilog/SystemVerilog files."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    files = sorted([
        f for f in os.listdir(workspace)
        if f.endswith(('.v', '.sv')) and os.path.isfile(os.path.join(workspace, f))
    ])

    result = []
    for filename in files:
        with open(os.path.join(workspace, filename), "r", errors='ignore') as f:
            content = f.read()

        lang = "systemverilog" if filename.endswith(".sv") else "verilog"
        result.append(CodeFile(filename=filename, content=content, language=lang))

    return result


@app.get("/api/workspace/{session_id}/code/{filename}")
async def get_code_file(session_id: str, filename: str) -> CodeFile:
    """Get a specific code file."""
    workspace = session_manager.get_workspace_path(session_id)
    file_path = os.path.join(workspace, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    with open(file_path, "r", errors='ignore') as f:
        content = f.read()

    lang = "systemverilog" if filename.endswith(".sv") else "verilog"
    return CodeFile(filename=filename, content=content, language=lang)


@app.get("/api/workspace/{session_id}/waveforms")
async def list_waveform_files(session_id: str) -> List[str]:
    """List VCD files in the workspace."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    return [f for f in os.listdir(workspace) if f.endswith(".vcd")]


@app.get("/api/workspace/{session_id}/waveform/{filename}")
async def get_waveform_data(session_id: str, filename: str):
    """Get parsed VCD waveform data."""
    workspace = session_manager.get_workspace_path(session_id)
    vcd_path = os.path.join(workspace, filename)

    if not os.path.exists(vcd_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        from vcdvcd import VCDVCD

        vcd = VCDVCD(vcd_path)
        signals = vcd.get_signals()
        endtime = vcd.endtime

        # Parse signals
        signal_data = []
        for sig_name in signals[:20]:  # Limit to 20 signals
            try:
                sig = vcd[sig_name]
                tv = sig.tv

                times = []
                values = []
                for t, v in tv:
                    times.append(t)
                    try:
                        if isinstance(v, str):
                            v_clean = v.lower().replace('x', '0').replace('z', '0')
                            val = int(v_clean, 2) if v_clean else 0
                        else:
                            val = int(v)
                    except ValueError:
                        val = 0
                    values.append(val)

                signal_data.append({
                    "name": sig_name.split('.')[-1],
                    "full_name": sig_name,
                    "times": times,
                    "values": values
                })
            except:
                continue

        return {
            "filename": filename,
            "endtime": endtime,
            "signals": signal_data
        }

    except ImportError:
        raise HTTPException(status_code=500, detail="vcdvcd library not installed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspace/{session_id}/report")
async def get_report(session_id: str) -> Dict[str, str]:
    """Get the design report."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    report_files = sorted(
        [f for f in os.listdir(workspace) if f.endswith("_report.md")],
        key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
        reverse=True
    )

    if not report_files:
        raise HTTPException(status_code=404, detail="No report found")

    with open(os.path.join(workspace, report_files[0]), "r", encoding="utf-8") as f:
        content = f.read()

    return {"filename": report_files[0], "content": content}


@app.post("/api/workspace/{session_id}/report/generate")
async def generate_report(session_id: str) -> Dict[str, str]:
    """Generate a new design report."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        report_path = save_design_report(workspace)
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {"filename": os.path.basename(report_path), "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspace/{session_id}/layouts")
async def list_layout_files(session_id: str) -> List[str]:
    """List GDS files in the workspace."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    gds_files = []
    for root, dirs, files in os.walk(workspace):
        for f in files:
            if f.endswith(".gds"):
                rel_path = os.path.relpath(os.path.join(root, f), workspace)
                gds_files.append(rel_path)

    return gds_files


@app.get("/api/workspace/{session_id}/schematics")
async def list_schematic_files(session_id: str) -> List[str]:
    """List SVG schematic files in the workspace."""
    workspace = session_manager.get_workspace_path(session_id)
    if not os.path.exists(workspace):
        raise HTTPException(status_code=404, detail="Session not found")

    return [f for f in os.listdir(workspace) if f.endswith(".svg") and not f.endswith(".gds.svg")]


@app.get("/api/workspace/{session_id}/file/{filename:path}")
async def get_file_content(session_id: str, filename: str):
    """Get raw file content."""
    workspace = session_manager.get_workspace_path(session_id)
    file_path = os.path.join(workspace, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Security check - ensure file is within workspace
    real_workspace = os.path.realpath(workspace)
    real_file = os.path.realpath(file_path)
    if not real_file.startswith(real_workspace):
        raise HTTPException(status_code=403, detail="Access denied")

    with open(file_path, "r", errors='ignore') as f:
        content = f.read()

    return {"filename": filename, "content": content}


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
