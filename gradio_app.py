"""
SiliconCrew Architect - Gradio Frontend

A modern, streaming-friendly frontend for the RTL Design Agent.
Fixes issues with Streamlit:
- Proper streaming of interleaved text + tool calls
- Automatic file refresh without hardcoded patterns
- Better state management
"""

import os
import time
import json
import sqlite3
import shutil
import yaml
import base64
from datetime import datetime
from typing import Generator, List, Tuple, Dict, Any, Optional
from copy import deepcopy

import gradio as gr
from dotenv import load_dotenv

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from src.agents.architect import create_architect_agent, SYSTEM_PROMPT
from src.utils.session_manager import SessionManager
from src.utils.reporter import generate_markdown_report
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


def format_tool_call(tool_call: dict) -> str:
    """Format a tool call for display in chat."""
    name = tool_call.get("name", "unknown")
    args = tool_call.get("args", {})
    
    # Create summary based on common arg patterns
    summary = ""
    for key in ["filename", "target_file", "design_file", "verilog_files", "module_name"]:
        if key in args:
            summary = f": `{args[key]}`"
            break
    
    # Format args as compact JSON
    args_str = json.dumps(args, indent=2, ensure_ascii=True)
    if len(args_str) > 500:
        args_str = args_str[:500] + "..."
    
    return f"[TOOL] **{name}**{summary}\n```json\n{args_str}\n```"


def format_tool_result(content: str) -> str:
    """Format a tool result for display."""
    # Sanitize content for Windows encoding
    try:
        sanitized = content.encode('utf-8', errors='replace').decode('utf-8')
    except:
        sanitized = content
    
    # Determine icon based on content
    icon = "[OK]"
    if "Success" in sanitized or "PASSED" in sanitized or "Pass" in sanitized:
        icon = "[SUCCESS]"
    elif "Error" in sanitized or "FAILED" in sanitized or "Fail" in sanitized:
        icon = "[ERROR]"
    
    # Truncate if too long
    display_content = sanitized
    if len(sanitized) > 1000:
        display_content = sanitized[:1000] + "\n... (truncated)"
    
    return f"{icon} **Output**\n```\n{display_content}\n```"


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def get_session_list() -> List[str]:
    """Get list of all sessions."""
    return session_manager.get_all_sessions()


def create_new_session(name: str, model: str) -> Tuple[str, Any, List]:
    """Create a new session and return updated state."""
    if not name:
        return "❌ Please enter a session name", gr.update(), gr.update()
    
    try:
        session_id = session_manager.create_session(tag=name, model_name=model)
        sessions = get_session_list()
        return f"✅ Created session: {session_id}", gr.update(choices=sessions, value=session_id), []
    except (ValueError, FileExistsError) as e:
        return f"❌ {str(e)}", gr.update(), gr.update()


def delete_session(session_id: str) -> Tuple[str, Any]:
    """Delete a session."""
    if not session_id:
        return "❌ No session selected", gr.update()
    
    session_manager.delete_session(session_id)
    sessions = get_session_list()
    return f"✅ Deleted session: {session_id}", gr.update(choices=sessions, value=sessions[0] if sessions else None)


def load_session_history(session_id: str) -> List[Dict[str, str]]:
    """Load chat history for a session. Returns list of message dicts with 'role' and 'content'."""
    if not session_id:
        return []
    
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        memory = SqliteSaver(conn)
        
        meta = session_manager.get_session_metadata(session_id)
        model_name = meta.get("model_name", "gemini-2.5-flash") if meta else "gemini-2.5-flash"
        
        agent_graph = create_architect_agent(checkpointer=memory, model_name=model_name)
        config = {"configurable": {"thread_id": session_id}}
        
        current_state = agent_graph.get_state(config)
        conn.close()
        
        if not current_state.values or "messages" not in current_state.values:
            return []
        
        messages = current_state.values["messages"]
        history = []
        
        # Track pending tool calls to detect incomplete conversations
        pending_tool_calls = set()
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                continue
            elif isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": get_clean_content(msg)})
            elif isinstance(msg, AIMessage):
                content_parts = []
                
                # Add text content
                text = get_clean_content(msg)
                if text:
                    content_parts.append(text)
                
                # Track and add tool calls
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        pending_tool_calls.add(tc.get("id"))
                        content_parts.append(format_tool_call(tc))
                
                if content_parts:
                    history.append({"role": "assistant", "content": "\n\n".join(content_parts)})
                    
            elif hasattr(msg, "tool_call_id"):
                # Tool result - mark as completed
                pending_tool_calls.discard(msg.tool_call_id)
                result_text = format_tool_result(msg.content)
                if history and history[-1]["role"] == "assistant":
                    history[-1]["content"] += f"\n\n{result_text}"
                else:
                    history.append({"role": "assistant", "content": result_text})
        
        # If there are pending tool calls, add a warning message
        if pending_tool_calls:
            history.append({
                "role": "assistant", 
                "content": "[WARNING] Previous request was interrupted. Some tool calls did not complete. Please start a new message or create a new session if you encounter errors."
            })
        
        return history
        
    except Exception as e:
        print(f"Error loading history: {e}")
        return []


def get_session_info(session_id: str) -> str:
    """Get session metadata for display."""
    if not session_id:
        return "No session selected"
    
    meta = session_manager.get_session_metadata(session_id)
    if not meta:
        return f"Session: {session_id}"
    
    cost = meta.get("total_cost", 0)
    tokens = meta.get("total_tokens", 0)
    model = meta.get("model_name", "unknown")
    
    return f"🤖 {model} | 🎫 {tokens//1000}k tokens | 💰 ${cost:.4f}"


# =============================================================================
# CHAT FUNCTIONALITY
# =============================================================================

def chat_stream(
    message: str,
    history: List[Dict[str, str]],
    session_id: str
) -> Generator[Tuple[List[Dict[str, str]], str], None, None]:
    """
    Stream chat responses with proper handling of interleaved text and tool calls.
    
    This generator yields (history, status) tuples as the response streams in.
    History is a list of dicts with 'role' and 'content' keys.
    """
    if not session_id:
        history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": "❌ Please select or create a session first."}
        ]
        yield history, "No session"
        return
    
    if not message.strip():
        yield history, "Empty message"
        return
    
    # Add user message
    history = history + [{"role": "user", "content": message}]
    yield history, "Processing..."
    
    try:
        # SET THE WORKSPACE PATH - Critical for tools to write to correct directory
        workspace_path = session_manager.get_workspace_path(session_id)
        if not os.path.exists(workspace_path):
            os.makedirs(workspace_path)
        os.environ["RTL_WORKSPACE"] = workspace_path
        print(f"[WORKSPACE] Set RTL_WORKSPACE to: {workspace_path}")
        
        # Initialize agent
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        memory = SqliteSaver(conn)
        
        meta = session_manager.get_session_metadata(session_id)
        model_name = meta.get("model_name", "gemini-2.5-flash") if meta else "gemini-2.5-flash"
        
        agent_graph = create_architect_agent(checkpointer=memory, model_name=model_name)
        config = {"configurable": {"thread_id": session_id}, "recursion_limit": 50}
        
        # Check if we need system prompt and validate state
        snapshot = agent_graph.get_state(config)
        input_messages = []
        
        # Check for corrupted state (tool calls without responses)
        if snapshot.values and snapshot.values.get("messages"):
            messages = snapshot.values["messages"]
            pending_tool_ids = set()
            
            for msg in messages:
                if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        pending_tool_ids.add(tc.get("id"))
                elif hasattr(msg, "tool_call_id"):
                    pending_tool_ids.discard(msg.tool_call_id)
            
            # If there are pending tool calls, we have a corrupted state
            if pending_tool_ids:
                # Add fake tool responses to fix the state
                for tool_id in pending_tool_ids:
                    fake_response = ToolMessage(
                        content="[Tool execution was interrupted. Please retry the operation.]",
                        tool_call_id=tool_id
                    )
                    input_messages.append(fake_response)
        
        if not snapshot.values or not snapshot.values.get("messages"):
            input_messages.append(SystemMessage(content=SYSTEM_PROMPT))
        input_messages.append(("user", message))
        
        # Stream events
        print(f"[LLM CALL] Session: {session_id} | Model: {model_name} | Input: {message[:50]}{'...' if len(message) > 50 else ''}")
        events = agent_graph.stream({"messages": input_messages}, config)
        
        current_response = ""
        tool_outputs = []
        total_input_tokens = 0
        total_output_tokens = 0
        assistant_added = False
        call_count = 0
        
        for event in events:
            if "agent" in event:
                call_count += 1
                msg = event["agent"]["messages"][-1]
                
                # Extract text content
                text = get_clean_content(msg)
                if text:
                    current_response = text
                    preview = text[:80].replace('\n', ' ')
                    print(f"[LLM RESP #{call_count}] Text: {preview}{'...' if len(text) > 80 else ''}")
                
                # Track tokens
                if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    total_input_tokens += msg.usage_metadata.get("input_tokens", 0)
                    total_output_tokens += msg.usage_metadata.get("output_tokens", 0)
                    print(f"[TOKENS] In: {msg.usage_metadata.get('input_tokens', 0)} | Out: {msg.usage_metadata.get('output_tokens', 0)}")
                
                # Handle tool calls
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.get("name", "unknown")
                        print(f"[TOOL CALL] {tool_name}")
                        tool_str = format_tool_call(tc)
                        tool_outputs.append(tool_str)
                
                # Build current display
                display_parts = []
                if current_response:
                    display_parts.append(current_response)
                if tool_outputs:
                    display_parts.append("\n\n---\n**🔧 Tool Execution:**\n" + "\n\n".join(tool_outputs))
                
                if display_parts:
                    assistant_content = "\n".join(display_parts)
                    if assistant_added:
                        # Update the last assistant message (create new list to avoid mutation issues)
                        history = history[:-1] + [{"role": "assistant", "content": assistant_content}]
                    else:
                        # Add new assistant message
                        history = history + [{"role": "assistant", "content": assistant_content}]
                        assistant_added = True
                    
                    yield history, f"Thinking... ({len(tool_outputs)} tools)"
                    
            elif "tools" in event:
                msg = event["tools"]["messages"][-1]
                # Log tool result
                status = "OK" if ("Success" in msg.content or "PASSED" in msg.content) else "DONE"
                if "Error" in msg.content or "FAILED" in msg.content:
                    status = "ERROR"
                print(f"[TOOL RESULT] {status} | {len(msg.content)} chars")
                result_str = format_tool_result(msg.content)
                tool_outputs.append(result_str)
                
                # Update display
                display_parts = []
                if current_response:
                    display_parts.append(current_response)
                if tool_outputs:
                    display_parts.append("\n\n---\n**🔧 Tool Execution:**\n" + "\n\n".join(tool_outputs))
                
                assistant_content = "\n".join(display_parts)
                if assistant_added:
                    # Update the last assistant message (create new list to avoid mutation issues)
                    history = history[:-1] + [{"role": "assistant", "content": assistant_content}]
                else:
                    history = history + [{"role": "assistant", "content": assistant_content}]
                    assistant_added = True
                
                yield history, f"Executing tools... ({len(tool_outputs)} results)"
        
        # Update token usage in session
        if total_input_tokens > 0 or total_output_tokens > 0:
            current_meta = session_manager.get_session_metadata(session_id)
            if current_meta:
                new_input = current_meta.get("input_tokens", 0) + total_input_tokens
                new_output = current_meta.get("output_tokens", 0) + total_output_tokens
                cached = current_meta.get("cached_tokens", 0)
                new_cost = calculate_cost(new_input, new_output, model_name)
                session_manager.update_session_stats(session_id, new_input, new_output, cached, new_cost)
        
        conn.close()
        print(f"[COMPLETE] Session: {session_id} | Calls: {call_count} | Tokens: {total_input_tokens + total_output_tokens}")
        yield history, "✅ Complete"
        
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        error_msg = f"[ERROR] {str(e)}"
        history = history + [{"role": "assistant", "content": error_msg}]
        yield history, "Error"


# =============================================================================
# WORKSPACE FILE VIEWERS
# =============================================================================

def get_workspace_path(session_id: str) -> Optional[str]:
    """Get workspace path for a session."""
    if not session_id:
        return None
    return session_manager.get_workspace_path(session_id)


def load_spec_files(session_id: str) -> Tuple[str, str]:
    """Load spec files for display. Returns (content, filename)."""
    print(f"[DEBUG] load_spec_files called with session_id: {session_id}")
    workspace = get_workspace_path(session_id)
    print(f"[DEBUG] workspace path: {workspace}")
    if not workspace or not os.path.exists(workspace):
        print(f"[DEBUG] Workspace does not exist!")
        return "No workspace found. Start a design to see specs here.", ""
    
    all_files = os.listdir(workspace)
    print(f"[DEBUG] All files in workspace: {all_files}")
    spec_files = sorted(
        [f for f in all_files if f.endswith("_spec.yaml")],
        key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
        reverse=True
    )
    print(f"[DEBUG] Spec files found: {spec_files}")
    
    if not spec_files:
        return "No specification files yet. Ask the agent to design something!", ""
    
    spec_file = spec_files[0]
    spec_path = os.path.join(workspace, spec_file)
    
    try:
        with open(spec_path, "r") as f:
            content = f.read()
        
        # Parse YAML for nice display
        spec_data = yaml.safe_load(content)
        module_name = list(spec_data.keys())[0]
        spec_info = spec_data[module_name]
        
        # Format as markdown
        md = f"# 📋 {module_name}\n\n"
        md += f"**Description:** {spec_info.get('description', 'N/A')}\n\n"
        md += f"**Clock Period:** {spec_info.get('clock_period', 'N/A')} ns\n\n"
        md += f"**Tech Node:** {spec_info.get('tech_node', 'N/A')}\n\n"
        
        # Ports table
        if spec_info.get("ports"):
            md += "## Ports\n\n"
            md += "| Name | Direction | Width | Description |\n"
            md += "|------|-----------|-------|-------------|\n"
            for p in spec_info["ports"]:
                md += f"| `{p.get('name', '')}` | {p.get('direction', '')} | {p.get('width', 1)} | {p.get('description', '')} |\n"
        
        # Module signature
        if spec_info.get("module_signature"):
            md += f"\n## Module Signature\n\n```verilog\n{spec_info['module_signature']}\n```\n"
        
        # Parameters
        if spec_info.get("parameters"):
            md += f"\n## Parameters\n\n```json\n{json.dumps(spec_info['parameters'], indent=2)}\n```\n"
        
        # Raw YAML
        md += f"\n---\n\n<details>\n<summary>📄 Raw YAML</summary>\n\n```yaml\n{content}\n```\n</details>"
        
        return md, spec_file
        
    except Exception as e:
        return f"Error reading spec: {e}", spec_file


def load_code_files(session_id: str) -> List[Tuple[str, str]]:
    """Load Verilog files for display. Returns list of (filename, content) tuples."""
    print(f"[DEBUG] load_code_files called with session_id: {session_id}")
    workspace = get_workspace_path(session_id)
    print(f"[DEBUG] workspace path: {workspace}")
    if not workspace or not os.path.exists(workspace):
        print(f"[DEBUG] Workspace does not exist!")
        return [("No Files", "No workspace found.")]
    
    all_files = os.listdir(workspace)
    print(f"[DEBUG] All files in workspace: {all_files}")
    files = sorted([
        f for f in all_files
        if f.endswith(('.v', '.sv')) and os.path.isfile(os.path.join(workspace, f))
    ])
    print(f"[DEBUG] Verilog files found: {files}")
    
    if not files:
        return [("No Files", "No Verilog files yet. Ask the agent to implement a design!")]
    
    result = []
    for filename in files:
        try:
            with open(os.path.join(workspace, filename), "r", errors='ignore') as f:
                content = f.read()
            result.append((filename, content))
        except Exception as e:
            result.append((filename, f"Error reading file: {e}"))
    
    return result


def load_waveform_files(session_id: str) -> Tuple[Any, List[str]]:
    """Load VCD files for waveform display."""
    workspace = get_workspace_path(session_id)
    if not workspace or not os.path.exists(workspace):
        return None, []
    
    vcd_files = [f for f in os.listdir(workspace) if f.endswith(".vcd")]
    return None, vcd_files


def render_waveform(session_id: str, vcd_filename: str) -> Any:
    """Render a VCD file as a plot."""
    workspace = get_workspace_path(session_id)
    if not workspace or not vcd_filename:
        return None
    
    vcd_path = os.path.join(workspace, vcd_filename)
    if not os.path.exists(vcd_path):
        return None
    
    try:
        import matplotlib.pyplot as plt
        from vcdvcd import VCDVCD
        
        vcd = VCDVCD(vcd_path)
        signals = vcd.get_signals()
        
        if not signals:
            return None
        
        # Filter to relevant signals
        display_signals = [s for s in signals if "tb" in s or "clk" in s or "rst" in s][:12]
        if not display_signals:
            display_signals = signals[:12]
        
        fig, axes = plt.subplots(len(display_signals), 1, figsize=(12, len(display_signals) * 0.7), sharex=True)
        if len(display_signals) == 1:
            axes = [axes]
        
        endtime = vcd.endtime
        
        for i, sig_name in enumerate(display_signals):
            sig = vcd[sig_name]
            tv = sig.tv
            
            times = [t for t, v in tv]
            values = []
            
            for t, v in tv:
                try:
                    if isinstance(v, str):
                        v_clean = v.lower().replace('x', '0').replace('z', '0')
                        val = int(v_clean, 2) if v_clean else 0
                    else:
                        val = int(v)
                except ValueError:
                    val = 0
                values.append(val)
            
            times.append(endtime)
            values.append(values[-1] if values else 0)
            
            max_val = max(values) if values else 1
            is_bus = max_val > 1
            
            if is_bus:
                axes[i].set_ylim(0, 1)
                axes[i].set_yticks([])
                axes[i].hlines(0.8, times[0], times[-1], colors='tab:blue', linewidth=1)
                axes[i].hlines(0.2, times[0], times[-1], colors='tab:blue', linewidth=1)
                
                for j in range(len(times) - 1):
                    axes[i].vlines(times[j], 0.2, 0.8, colors='tab:blue', linewidth=1)
                    duration = times[j+1] - times[j]
                    if duration > (endtime * 0.02):
                        center = times[j] + (duration / 2)
                        axes[i].text(center, 0.5, str(values[j]), ha='center', va='center', fontsize=7)
            else:
                axes[i].step(times, values, where='post')
                axes[i].set_yticks([0, 1])
                axes[i].set_yticklabels(['0', '1'], fontsize=6)
            
            short_name = sig_name.split('.')[-1]
            axes[i].set_ylabel(short_name, rotation=0, ha='right', fontsize=8)
            axes[i].grid(True, alpha=0.3)
        
        axes[-1].set_xlabel("Time (ns)")
        plt.tight_layout()
        
        return fig
        
    except Exception as e:
        print(f"Waveform error: {e}")
        return None


def load_gds_files(session_id: str) -> Tuple[str, List[str]]:
    """Load GDS files for layout display."""
    workspace = get_workspace_path(session_id)
    if not workspace or not os.path.exists(workspace):
        return "No workspace found.", []
    
    gds_files = []
    for root, dirs, files in os.walk(workspace):
        for f in files:
            if f.endswith(".gds"):
                rel_path = os.path.relpath(os.path.join(root, f), workspace)
                gds_files.append(rel_path)
    
    if not gds_files:
        return "No GDS files found. Run synthesis to generate layout.", []
    
    return "", gds_files


def render_gds(session_id: str, gds_filename: str) -> Optional[str]:
    """Render GDS file to SVG and return as HTML."""
    workspace = get_workspace_path(session_id)
    if not workspace or not gds_filename:
        return None
    
    gds_path = os.path.join(workspace, gds_filename)
    if not os.path.exists(gds_path):
        return None
    
    try:
        import gdstk
        
        if os.path.getsize(gds_path) == 0:
            return "<p>GDS file is empty.</p>"
        
        lib = gdstk.read_gds(gds_path)
        top_cells = lib.top_level()
        if not top_cells:
            return "<p>No top level cell found in GDS.</p>"
        
        cell = top_cells[0]
        svg_path = gds_path + ".svg"
        cell.write_svg(svg_path)
        
        with open(svg_path, "r") as f:
            svg_content = f.read()
        
        # Return as HTML with white background
        b64 = base64.b64encode(svg_content.encode('utf-8')).decode("utf-8")
        return f'<div style="background-color: white; padding: 20px; border-radius: 10px;"><img src="data:image/svg+xml;base64,{b64}" style="width: 100%;" /></div>'
        
    except Exception as e:
        return f"<p>Error rendering GDS: {e}</p>"


def load_schematic_files(session_id: str) -> Tuple[str, List[str]]:
    """Load schematic SVG files."""
    workspace = get_workspace_path(session_id)
    if not workspace or not os.path.exists(workspace):
        return "No workspace found.", []
    
    svg_files = [f for f in os.listdir(workspace) if f.endswith(".svg") and not f.endswith(".gds.svg")]
    
    if not svg_files:
        return "No schematics found. Ask the agent to 'generate schematic' for your design.", []
    
    return "", svg_files


def render_schematic(session_id: str, svg_filename: str) -> Optional[str]:
    """Render schematic SVG as HTML."""
    workspace = get_workspace_path(session_id)
    if not workspace or not svg_filename:
        return None
    
    svg_path = os.path.join(workspace, svg_filename)
    if not os.path.exists(svg_path):
        return None
    
    try:
        with open(svg_path, "r") as f:
            svg_content = f.read()
        
        b64 = base64.b64encode(svg_content.encode('utf-8')).decode("utf-8")
        return f'<div style="background-color: white; padding: 20px; border-radius: 10px;"><img src="data:image/svg+xml;base64,{b64}" style="width: 100%;" /></div>'
        
    except Exception as e:
        return f"<p>Error rendering schematic: {e}</p>"


def load_report(session_id: str) -> str:
    """Load or generate design report."""
    workspace = get_workspace_path(session_id)
    if not workspace or not os.path.exists(workspace):
        return "No workspace found."
    
    report_files = sorted(
        [f for f in os.listdir(workspace) if f.endswith("_report.md")],
        key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
        reverse=True
    )
    
    if report_files:
        try:
            with open(os.path.join(workspace, report_files[0]), "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading report: {e}"
    
    return "No reports generated yet. Click 'Generate Report' or ask the agent to create one."


def generate_report_action(session_id: str) -> str:
    """Generate a new design report."""
    workspace = get_workspace_path(session_id)
    if not workspace or not os.path.exists(workspace):
        return "No workspace found."
    
    try:
        report_path = save_design_report(workspace)
        with open(report_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error generating report: {e}"


# =============================================================================
# UI COMPONENTS
# =============================================================================

def create_code_tabs(files: List[Tuple[str, str]]) -> str:
    """Create tabbed code display as HTML."""
    if not files or (len(files) == 1 and files[0][0] == "No Files"):
        return f"<p>{files[0][1] if files else 'No files'}</p>"
    
    html = '<div class="code-tabs">'
    
    # Tab headers
    html += '<div class="tab-headers">'
    for i, (filename, _) in enumerate(files):
        active = "active" if i == 0 else ""
        html += f'<button class="tab-btn {active}" onclick="showTab({i})">{filename}</button>'
    html += '</div>'
    
    # Tab content
    for i, (filename, content) in enumerate(files):
        display = "block" if i == 0 else "none"
        escaped_content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html += f'<div class="tab-content" id="tab-{i}" style="display: {display};"><pre><code>{escaped_content}</code></pre></div>'
    
    html += '''
    <script>
    function showTab(idx) {
        document.querySelectorAll('.tab-content').forEach((el, i) => {
            el.style.display = i === idx ? 'block' : 'none';
        });
        document.querySelectorAll('.tab-btn').forEach((el, i) => {
            el.classList.toggle('active', i === idx);
        });
    }
    </script>
    <style>
    .code-tabs { border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }
    .tab-headers { display: flex; background: #f5f5f5; border-bottom: 1px solid #ddd; }
    .tab-btn { padding: 8px 16px; border: none; background: transparent; cursor: pointer; }
    .tab-btn.active { background: white; border-bottom: 2px solid #2196F3; }
    .tab-content { padding: 16px; max-height: 500px; overflow: auto; }
    .tab-content pre { margin: 0; white-space: pre-wrap; }
    </style>
    </div>
    '''
    
    return html


# =============================================================================
# GRADIO APP
# =============================================================================

def build_app():
    """Build the Gradio application."""
    
    # Custom CSS
    custom_css = """
    .container { max-width: 1400px; margin: 0 auto; }
    .chat-area { height: 600px; }
    .workspace-area { height: 600px; overflow-y: auto; }
    .status-bar { padding: 8px; background: #f0f0f0; border-radius: 4px; }
    .session-info { font-size: 0.9em; color: #666; }
    """
    
    with gr.Blocks(title="SiliconCrew Architect") as app:
        
        # State
        current_session = gr.State(value=None)
        
        # Header
        with gr.Row():
            gr.Markdown("# 🤖 SiliconCrew Architect\n*Autonomous RTL Design Agent*")
        
        # Main Layout
        with gr.Row():
            # Left Column: Session Management + Chat
            with gr.Column(scale=1):
                
                # Session Management
                with gr.Accordion("📂 Session Management", open=True):
                    with gr.Row():
                        session_dropdown = gr.Dropdown(
                            choices=get_session_list(),
                            label="Select Session",
                            interactive=True,
                            scale=3
                        )
                        refresh_btn = gr.Button("🔄", scale=1, min_width=50)
                    
                    session_info = gr.Markdown("No session selected", elem_classes=["session-info"])
                    
                    with gr.Row():
                        new_session_name = gr.Textbox(
                            label="New Session Name",
                            placeholder="e.g., LFSR_Design",
                            scale=2
                        )
                        model_dropdown = gr.Dropdown(
                            choices=["gemini-2.5-flash", "gemini-3-pro-preview"],
                            value="gemini-2.5-flash",
                            label="Model",
                            scale=1
                        )
                    
                    with gr.Row():
                        create_btn = gr.Button("➕ Create Session", variant="primary", scale=2)
                        delete_btn = gr.Button("🗑️ Delete", variant="stop", scale=1)
                    
                    status_msg = gr.Markdown("")
                
                # Chat Interface
                gr.Markdown("### 💬 Chat")
                
                chatbot = gr.Chatbot(
                    label="Conversation",
                    height=450
                )
                
                with gr.Row():
                    chat_input = gr.Textbox(
                        placeholder="Ex: Design an 8-bit counter with async reset",
                        label="Message",
                        scale=4,
                        lines=2
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)
                
                chat_status = gr.Markdown("Ready", elem_classes=["status-bar"])
            
            # Right Column: Workspace
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Live Workspace")
                
                with gr.Tabs() as workspace_tabs:
                    
                    # Spec Tab
                    with gr.Tab("📋 Spec"):
                        spec_display = gr.Markdown("Select a session to view specs.")
                        spec_refresh_btn = gr.Button("🔄 Refresh Spec")
                    
                    # Code Tab
                    with gr.Tab("📝 Code"):
                        code_display = gr.HTML("Select a session to view code.")
                        code_refresh_btn = gr.Button("🔄 Refresh Code")
                    
                    # Waveform Tab
                    with gr.Tab("📈 Waveform"):
                        vcd_dropdown = gr.Dropdown(choices=[], label="Select VCD File")
                        waveform_plot = gr.Plot(label="Waveform")
                        wave_refresh_btn = gr.Button("🔄 Refresh Waveforms")
                    
                    # Layout Tab
                    with gr.Tab("🗺️ Layout"):
                        gds_dropdown = gr.Dropdown(choices=[], label="Select GDS File")
                        gds_display = gr.HTML("No GDS files found.")
                        gds_refresh_btn = gr.Button("🔄 Refresh Layout")
                    
                    # Schematic Tab
                    with gr.Tab("🔌 Schematic"):
                        svg_dropdown = gr.Dropdown(choices=[], label="Select Schematic")
                        schematic_display = gr.HTML("No schematics found.")
                        schem_refresh_btn = gr.Button("🔄 Refresh Schematics")
                    
                    # Report Tab
                    with gr.Tab("📊 Report"):
                        report_display = gr.Markdown("No reports yet.")
                        with gr.Row():
                            report_refresh_btn = gr.Button("🔄 Refresh")
                            report_generate_btn = gr.Button("📝 Generate Report", variant="primary")
        
        # =================================================================
        # EVENT HANDLERS
        # =================================================================
        
        # Session selection
        def on_session_select(session_id):
            if not session_id:
                return (
                    None,
                    "No session selected",
                    [],
                    "Select a session to view specs.",
                    "Select a session to view code.",
                    gr.update(choices=[]),
                    None,
                    gr.update(choices=[]),
                    "No GDS files found.",
                    gr.update(choices=[]),
                    "No schematics found.",
                    "No reports yet."
                )
            
            # Load all data
            history = load_session_history(session_id)
            info = get_session_info(session_id)
            spec_content, _ = load_spec_files(session_id)
            code_files = load_code_files(session_id)
            code_html = create_code_tabs(code_files)
            _, vcd_files = load_waveform_files(session_id)
            gds_msg, gds_files = load_gds_files(session_id)
            schem_msg, svg_files = load_schematic_files(session_id)
            report = load_report(session_id)
            
            return (
                session_id,
                info,
                history,
                spec_content,
                code_html,
                gr.update(choices=vcd_files, value=vcd_files[0] if vcd_files else None),
                None,
                gr.update(choices=gds_files, value=gds_files[0] if gds_files else None),
                gds_msg or "Select a GDS file to view.",
                gr.update(choices=svg_files, value=svg_files[0] if svg_files else None),
                schem_msg or "Select a schematic to view.",
                report
            )
        
        session_dropdown.change(
            on_session_select,
            inputs=[session_dropdown],
            outputs=[
                current_session, session_info, chatbot,
                spec_display, code_display,
                vcd_dropdown, waveform_plot,
                gds_dropdown, gds_display,
                svg_dropdown, schematic_display,
                report_display
            ]
        )
        
        # Refresh session list
        refresh_btn.click(
            lambda: gr.update(choices=get_session_list()),
            outputs=[session_dropdown]
        )
        
        # Create session
        create_btn.click(
            create_new_session,
            inputs=[new_session_name, model_dropdown],
            outputs=[status_msg, session_dropdown, chatbot]
        ).then(
            on_session_select,
            inputs=[session_dropdown],
            outputs=[
                current_session, session_info, chatbot,
                spec_display, code_display,
                vcd_dropdown, waveform_plot,
                gds_dropdown, gds_display,
                svg_dropdown, schematic_display,
                report_display
            ]
        )
        
        # Delete session
        delete_btn.click(
            delete_session,
            inputs=[session_dropdown],
            outputs=[status_msg, session_dropdown]
        )
        
        # Chat submit
        def submit_chat(message, history, session_id):
            """Handle chat submission."""
            for updated_history, status in chat_stream(message, history, session_id):
                yield updated_history, status, ""
        
        # Auto-refresh workspace after chat
        def post_chat_refresh_all(session_id):
            """Refresh all workspace tabs after chat completes."""
            if not session_id:
                return gr.update(), gr.update(), gr.update(), gr.update()
            
            spec_content, _ = load_spec_files(session_id)
            code_files = load_code_files(session_id)
            code_html = create_code_tabs(code_files)
            _, vcd_files = load_waveform_files(session_id)
            report = load_report(session_id)
            
            return spec_content, code_html, gr.update(choices=vcd_files), report
        
        send_btn.click(
            submit_chat,
            inputs=[chat_input, chatbot, current_session],
            outputs=[chatbot, chat_status, chat_input]
        ).then(
            post_chat_refresh_all,
            inputs=[current_session],
            outputs=[spec_display, code_display, vcd_dropdown, report_display]
        )
        
        chat_input.submit(
            submit_chat,
            inputs=[chat_input, chatbot, current_session],
            outputs=[chatbot, chat_status, chat_input]
        ).then(
            post_chat_refresh_all,
            inputs=[current_session],
            outputs=[spec_display, code_display, vcd_dropdown, report_display]
        )
        
        # Workspace refresh handlers
        def refresh_spec(session_id):
            content, _ = load_spec_files(session_id)
            return content
        
        def refresh_code(session_id):
            files = load_code_files(session_id)
            return create_code_tabs(files)
        
        def refresh_waveforms(session_id):
            _, vcd_files = load_waveform_files(session_id)
            return gr.update(choices=vcd_files, value=vcd_files[0] if vcd_files else None)
        
        def refresh_gds(session_id):
            msg, gds_files = load_gds_files(session_id)
            return gr.update(choices=gds_files, value=gds_files[0] if gds_files else None), msg or "Select a GDS file."
        
        def refresh_schematics(session_id):
            msg, svg_files = load_schematic_files(session_id)
            return gr.update(choices=svg_files, value=svg_files[0] if svg_files else None), msg or "Select a schematic."
        
        spec_refresh_btn.click(refresh_spec, inputs=[current_session], outputs=[spec_display])
        code_refresh_btn.click(refresh_code, inputs=[current_session], outputs=[code_display])
        wave_refresh_btn.click(refresh_waveforms, inputs=[current_session], outputs=[vcd_dropdown])
        gds_refresh_btn.click(refresh_gds, inputs=[current_session], outputs=[gds_dropdown, gds_display])
        schem_refresh_btn.click(refresh_schematics, inputs=[current_session], outputs=[svg_dropdown, schematic_display])
        report_refresh_btn.click(lambda sid: load_report(sid), inputs=[current_session], outputs=[report_display])
        report_generate_btn.click(generate_report_action, inputs=[current_session], outputs=[report_display])
        
        # Render specific files
        vcd_dropdown.change(
            lambda sid, vcd: render_waveform(sid, vcd),
            inputs=[current_session, vcd_dropdown],
            outputs=[waveform_plot]
        )
        
        gds_dropdown.change(
            lambda sid, gds: render_gds(sid, gds),
            inputs=[current_session, gds_dropdown],
            outputs=[gds_display]
        )
        
        svg_dropdown.change(
            lambda sid, svg: render_schematic(sid, svg),
            inputs=[current_session, svg_dropdown],
            outputs=[schematic_display]
        )
        
    return app


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    app = build_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft()
    )
