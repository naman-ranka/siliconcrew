import streamlit as st
import time
import os
import sqlite3
import shutil
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from src.agents.architect import create_architect_agent, SYSTEM_PROMPT

from src.utils.session_manager import SessionManager

# Load environment
load_dotenv()

st.set_page_config(page_title="SiliconCrew Architect", layout="wide", initial_sidebar_state="collapsed")

# Initialize Token Usage State
if "token_usage" not in st.session_state:
    st.session_state.token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "total_cost": 0.0
    }

if "processed_msg_ids" not in st.session_state:
    st.session_state.processed_msg_ids = set()

if "selected_model" not in st.session_state:
    st.session_state.selected_model = "gemini-2.5-flash"

# Pricing Constants (Per 1M Tokens)
PRICING = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-3-pro-preview": {"input": 2.00, "output": 12.00}
}

def update_token_usage(usage_metadata, model_name, msg_id=None):
    if not usage_metadata: return
    
    # Prevent double counting
    if msg_id and msg_id in st.session_state.processed_msg_ids:
        return
        
    if msg_id:
        st.session_state.processed_msg_ids.add(msg_id)
    
    in_t = usage_metadata.get("input_tokens", 0)
    out_t = usage_metadata.get("output_tokens", 0)
    total_t = usage_metadata.get("total_tokens", 0)
    
    # Attempt to extract cache info (provider dependent)
    cached_t = 0
    # Check for cache_read (Google style via LangChain)
    if "input_token_details" in usage_metadata:
        details = usage_metadata["input_token_details"]
        if isinstance(details, dict):
            # Try both keys just in case
            cached_t = details.get("cache_read", 0) or details.get("cache_read_input_tokens", 0)
    
    st.session_state.token_usage["input_tokens"] += in_t
    st.session_state.token_usage["output_tokens"] += out_t
    st.session_state.token_usage["total_tokens"] += total_t
    st.session_state.token_usage["cached_tokens"] += cached_t
    
    # Calculate Cost based on Model
    rates = PRICING.get(model_name, PRICING["gemini-2.5-flash"]) # Default to 2.5 rates if unknown
    
    cost_input = (in_t / 1_000_000) * rates["input"]
    cost_output = (out_t / 1_000_000) * rates["output"]
    
    st.session_state.token_usage["total_cost"] += (cost_input + cost_output)
    
    # Persist to DB
    if st.session_state.current_session:
        session_manager.update_session_stats(
            st.session_state.current_session,
            st.session_state.token_usage["input_tokens"],
            st.session_state.token_usage["output_tokens"],
            st.session_state.token_usage["cached_tokens"],
            st.session_state.token_usage["total_cost"]
        )

# Initialize Manager
session_manager = SessionManager(base_dir=os.path.join(os.path.dirname(__file__), 'workspace'), 
                               db_path=os.path.join(os.path.dirname(__file__), 'state.db'))

# --- Session Logic ---
if "current_session" not in st.session_state:
    # Default to Home (None) instead of auto-loading
    st.session_state.current_session = None

# Set Workspace Env Var (if session active)
if st.session_state.current_session:
    CURRENT_WORKSPACE = session_manager.get_workspace_path(st.session_state.current_session)
    os.environ["RTL_WORKSPACE"] = CURRENT_WORKSPACE
else:
    CURRENT_WORKSPACE = None

DB_PATH = session_manager.db_path

# Custom CSS
st.markdown("""
<style>
    .stChatMessage { padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; }
    .tool-call-header { font-size: 0.85em; color: #666; display: flex; align-items: center; gap: 0.5rem; }
    .tool-icon { font-size: 1em; }
</style>
""", unsafe_allow_html=True)

# Helper to parse message content
def get_clean_content(msg):
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
    return str(content)

# --- UI Functions ---

def render_home():
    st.title("SiliconCrew 🤖")
    st.markdown("### Autonomous RTL Design Agent")
    st.divider()

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.subheader("🚀 Start New Session")
        with st.form("new_session_home"):
            tag = st.text_input("Session Name (Required)", placeholder="e.g., LFSR_Design")
            
            # Model Selection at Creation
            model = st.selectbox(
                "Select Model", 
                ["gemini-2.5-flash", "gemini-3-pro-preview"],
                index=0,
                help="Choose the model for this entire session."
            )
            
            if st.form_submit_button("Create & Start", type="primary", use_container_width=True):
                if tag:
                    try:
                        new_session = session_manager.create_session(tag=tag, model_name=model)
                        st.session_state.current_session = new_session
                        # Reset token session state for new session
                        st.session_state.token_usage = {
                             "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0, "total_cost": 0.0
                        }
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                    except FileExistsError as e:
                        st.error(str(e))
                else:
                    st.error("Please enter a session name.")

    with col2:
        st.subheader("📂 Load Previous Session")
        sessions = session_manager.get_all_sessions()
        if sessions:
            for sess in sessions:
                c1, c2 = st.columns([0.8, 0.2])
                if c1.button(f"📄 {sess}", key=f"load_{sess}", use_container_width=True):
                    st.session_state.current_session = sess
                    st.rerun()
                if c2.button("🗑️", key=f"del_{sess}"):
                    # Delete logic would go here (need to add delete_session to manager)
                    # For now, just clear all is available
                    pass
        else:
            st.info("No previous sessions found.")
            
    st.divider()
    if st.button("🗑️ Clear All History", type="secondary"):
        session_manager.clear_all_sessions()
        st.rerun()

# Helper to build a tree structure from file paths
def build_file_tree(root_path):
    tree = {"files": [], "dirs": {}}
    relevant_extensions = ('.v', '.sv', '.rpt', '.txt', '.log', '.gds', '.sdc', '.lef', '.def', '.lib')
    
    if os.path.exists(root_path):
        for item in sorted(os.listdir(root_path)):
            item_path = os.path.join(root_path, item)
            if os.path.isdir(item_path):
                # Recursively build tree for subdirs
                sub_tree = build_file_tree(item_path)
                if sub_tree["files"] or sub_tree["dirs"]: # Only add if not empty
                    tree["dirs"][item] = sub_tree
            elif item.endswith(relevant_extensions):
                tree["files"].append(item)
    return tree

def render_tree_view(tree, current_path=""):
    # Render Files first (optional preference, or dirs first)
    for f in tree["files"]:
        full_path = os.path.join(current_path, f)
        # Use a unique key for each button
        if st.sidebar.button(f"📄 {f}", key=f"file_{full_path}", use_container_width=True):
            st.session_state.selected_file = full_path
            st.rerun()
            
    # Render Directories
    for d, sub_tree in tree["dirs"].items():
        # Create a unique key for the expander
        with st.sidebar.expander(f"📁 {d}", expanded=False):
            render_tree_view(sub_tree, os.path.join(current_path, d))
            
    # --- Export Section (Bottom of Sidebar if possible, or just append) ---
        with st.sidebar.expander(f"📁 {d}", expanded=False):
            render_tree_view(sub_tree, os.path.join(current_path, d))

from src.utils.visualizers import render_waveform, render_gds
from src.utils.reporter import generate_markdown_report

def render_workspace():
    # --- Main Layout ---
    # Top Bar for Navigation
    top_col1, top_col2 = st.columns([0.1, 0.9])
    with top_col1:
        if st.button("🏠", help="Back to Home"):
            st.session_state.current_session = None
            st.rerun()
    with top_col2:
        # Metrics Display
        metrics = st.session_state.token_usage
        cost_str = f"${metrics['total_cost']:.4f}"
        
        # Determine Color for Cost (Visual Indicator)
        cost_color = "green"
        if metrics['total_cost'] > 0.1: cost_color = "orange"
        if metrics['total_cost'] > 1.0: cost_color = "red"
        
        # Tooltip for details
        tooltip = f"""
        Model: {st.session_state.selected_model}
        Input: {metrics['input_tokens']:,}
        Output: {metrics['output_tokens']:,}
        Cached: {metrics.get('cached_tokens', 0):,}
        """
        
        c1, c2, c3, c4, c5 = st.columns([0.35, 0.2, 0.15, 0.15, 0.15])
        c1.caption(f"Session: `{st.session_state.current_session}`")
        
        # Load Model from Metadata (Locked)
        locked_model = "gemini-2.5-flash" # Default
        meta = session_manager.get_session_metadata(st.session_state.current_session)
        if meta and meta.get("model_name"):
            locked_model = meta["model_name"]
            st.session_state.selected_model = locked_model # Sync state
            
            # Sync starting tokens if local is empty but DB has data (Resume scenario)
            if st.session_state.token_usage["total_tokens"] == 0 and meta["total_tokens"] > 0:
                 st.session_state.token_usage["input_tokens"] = meta["input_tokens"]
                 st.session_state.token_usage["output_tokens"] = meta["output_tokens"]
                 st.session_state.token_usage["cached_tokens"] = meta["cached_tokens"]
                 st.session_state.token_usage["total_tokens"] = meta["total_tokens"]
                 st.session_state.token_usage["total_cost"] = meta["total_cost"]
        
        # Display Locked Model
        with c2:
            st.markdown(f"**🤖 {locked_model}**", help="Model is locked for this session.")
            
        # Display Totals
        c3.markdown(f"**🎫 {metrics['total_tokens'] // 1000}k**", help=tooltip)
        c4.markdown(f":{cost_color}[**{cost_str}**]")
        
        # Expert Button
        with c5:
             if st.session_state.current_session and DB_PATH:
                 # Generate on fly (lightweight)
                 report = generate_markdown_report(st.session_state.current_session, DB_PATH, locked_model)
                 st.download_button(
                     label="📥",
                     data=report,
                     file_name=f"{st.session_state.current_session}.md",
                     mime="text/markdown",
                     help="Download Session Report",
                     key="top_dl_btn"
                 )

    col1, col2 = st.columns([1.2, 0.8])

    # Column 2: Live Workspace (Code & Metrics)
    with col2:
        # Header with "Close File" if viewing a specific file
        if st.session_state.get("selected_file"):
            c_head_1, c_head_2 = st.columns([0.8, 0.2])
            c_head_1.subheader(f"📄 {os.path.basename(st.session_state.selected_file)}")
            if c_head_2.button("❌ Close", use_container_width=True):
                st.session_state.selected_file = None
                st.rerun()
                
            # Render Selected File
            file_path = os.path.join(CURRENT_WORKSPACE, st.session_state.selected_file)
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", errors='ignore') as f:
                        content = f.read()
                    st.code(content, language="verilog" if file_path.endswith(".v") else "text")
                except Exception as e:
                    st.error(f"Error reading file: {e}")
            else:
                st.error("File not found.")
                
        else:
            # Default View: Live Tabs (Generated Files)
            st.subheader("Live Workspace")
            
            # Tabs for different views
            tab_code, tab_wave, tab_layout, tab_schematic = st.tabs(["📝 Code", "📈 Waveform", "🗺️ Layout", "🔌 Schematic"])
            
            with tab_code:
                file_viewer_placeholder = st.empty()
                def render_files():
                    with file_viewer_placeholder.container():
                        # Right Side: Only show root level source files (generated by write_file)
                        if os.path.exists(CURRENT_WORKSPACE):
                            all_files = sorted(os.listdir(CURRENT_WORKSPACE))
                            files = [f for f in all_files if f.endswith(('.v', '.sv', '.rpt', '.txt', '.log')) and os.path.isfile(os.path.join(CURRENT_WORKSPACE, f))]
                        else:
                            files = []

                        if files:
                            sub_tabs = st.tabs(files)
                            for i, file_name in enumerate(files):
                                with sub_tabs[i]:
                                    file_path = os.path.join(CURRENT_WORKSPACE, file_name)
                                    try:
                                        with open(file_path, "r", errors='ignore') as f:
                                            content = f.read()
                                        st.code(content, language="verilog" if file_name.endswith(".v") else "text")
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                        else:
                            st.info("Waiting for generated files...")
                render_files()

            with tab_wave:
                if os.path.exists(CURRENT_WORKSPACE):
                    vcd_files = [f for f in os.listdir(CURRENT_WORKSPACE) if f.endswith(".vcd")]
                    if vcd_files:
                        selected_vcd = st.selectbox("Select VCD", vcd_files)
                        if selected_vcd:
                            render_waveform(os.path.join(CURRENT_WORKSPACE, selected_vcd))
                    else:
                        st.info("No VCD files found. Run simulation to generate waveforms.")
                else:
                    st.info("Workspace not ready.")

            with tab_layout:
                # Recursive search for GDS
                gds_files = []
                if os.path.exists(CURRENT_WORKSPACE):
                    for root, dirs, files in os.walk(CURRENT_WORKSPACE):
                        for file in files:
                            if file.endswith(".gds"):
                                rel_path = os.path.relpath(os.path.join(root, file), CURRENT_WORKSPACE)
                                gds_files.append(rel_path)
                
                if gds_files:
                    selected_gds = st.selectbox("Select Layout (GDS)", gds_files)
                    if selected_gds:
                        render_gds(os.path.join(CURRENT_WORKSPACE, selected_gds))
                else:
                    st.info("No GDS files found. Run synthesis to generate layout.")

            with tab_schematic:
                # Search for SVGs
                svg_files = []
                if os.path.exists(CURRENT_WORKSPACE):
                    svg_files = [f for f in os.listdir(CURRENT_WORKSPACE) if f.endswith(".svg")]
                
                if svg_files:
                    selected_svg = st.selectbox("Select Schematic", svg_files)
                    if selected_svg:
                        # Render with white background for visibility in dark mode
                        svg_path = os.path.join(CURRENT_WORKSPACE, selected_svg)
                        with open(svg_path, "r") as f:
                            svg_content = f.read()
                        
                        # Encode SVG for embedding
                        import base64
                        b64 = base64.b64encode(svg_content.encode('utf-8')).decode("utf-8")
                        html = f'<div style="background-color: white; padding: 20px; border-radius: 10px; overflow: auto;"><img src="data:image/svg+xml;base64,{b64}" style="width: 100%;" /></div>'
                        st.markdown(html, unsafe_allow_html=True)
                else:
                    st.info("No Schematic found. Ask the agent to 'generate schematic' for your design.")

    # Column 1: Chat Interface
    with col1:
        st.subheader("Chat")
        
        # Initialize Agent
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        memory = SqliteSaver(conn)
        # Pass Dynamic Model
        model_to_use = st.session_state.get("selected_model", "gemini-2.5-flash")
        agent_graph = create_architect_agent(checkpointer=memory, model_name=model_to_use)
        config = {"configurable": {"thread_id": st.session_state.current_session}}
        
        current_state = agent_graph.get_state(config)
        
        # Render History with Grouping
        if current_state.values and "messages" in current_state.values:
            messages = current_state.values["messages"]
            
            # Grouping Logic
            grouped_messages = []
            current_group = []
            
            for msg in messages:
                if isinstance(msg, SystemMessage): continue
                
                is_tool_related = False
                if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                    is_tool_related = True
                elif hasattr(msg, "tool_call_id"): # ToolMessage
                    is_tool_related = True
                    
                if is_tool_related:
                    current_group.append(msg)
                else:
                    # Flush current group if exists
                    if current_group:
                        grouped_messages.append({"type": "group", "msgs": current_group})
                        current_group = []
                    # Add normal text message
                    grouped_messages.append({"type": "single", "msg": msg})
            
            # Flush remaining group
            if current_group:
                grouped_messages.append({"type": "group", "msgs": current_group})
                
            # Render Groups
            for item in grouped_messages:
                if item["type"] == "single":
                    msg = item["msg"]
                    role = "user"
                    if isinstance(msg, AIMessage): role = "assistant"
                    with st.chat_message(role):
                        st.markdown(get_clean_content(msg))
                        
                elif item["type"] == "group":
                    # Render text of FIRST message if it exists
                    first_msg = item["msgs"][0]
                    if isinstance(first_msg, AIMessage):
                        clean_text = get_clean_content(first_msg)
                        if clean_text:
                            with st.chat_message("assistant"):
                                st.markdown(clean_text)
                    
                    # Render Steps in Expander
                    with st.chat_message("assistant"):
                        with st.status("🛠️ Execution Log", expanded=False, state="complete"):
                            for m in item["msgs"]:
                                if isinstance(m, AIMessage) and m.tool_calls:
                                    for tc in m.tool_calls:
                                        t_name = tc['name']
                                        t_args = tc['args']
                                        # Smart Summary
                                        summary = ""
                                        if "filename" in t_args: summary = t_args["filename"]
                                        elif "target_file" in t_args: summary = t_args["target_file"]
                                        elif "design_file" in t_args: summary = t_args["design_file"]
                                        
                                        with st.expander(f"⚙️ **{t_name}** {summary}", expanded=False):
                                            st.json(t_args)
                                            
                                elif hasattr(m, "tool_call_id"):
                                    # Output
                                    icon = "📄"
                                    if "Success" in m.content or "PASSED" in m.content: icon = "✅"
                                    elif "Error" in m.content or "FAILED" in m.content: icon = "❌"
                                    
                                    with st.expander(f"{icon} Output", expanded=False):
                                        st.code(m.content[:500] + ("..." if len(m.content)>500 else ""))

        else:
            st.info("👋 Hi! I'm the Architect. What hardware shall we build today?")

        # Input
        if prompt := st.chat_input("Ex: Design an 8-bit counter"):
            with st.chat_message("user"):
                st.markdown(prompt)
                
            with st.chat_message("assistant"):
                # 1. Text Placeholder First
                response_placeholder = st.empty()
                
                # 2. Status Container (Thinking) Second
                status_container = st.status("Thinking...", expanded=True)
                
                full_response = ""
                total_time = 0
                tool_start_times = {} # Map tool_call_id (or name) to start time
                
                try:
                    input_messages = []
                    snapshot = agent_graph.get_state(config)
                    if not snapshot.values or not snapshot.values.get("messages"):
                        input_messages.append(SystemMessage(content=SYSTEM_PROMPT))
                    
                    input_messages.append(("user", prompt))
                    config["recursion_limit"] = 50
                    
                    events = agent_graph.stream({"messages": input_messages}, config)
                    
                    for event in events:
                        if "agent" in event:
                            msg = event["agent"]["messages"][-1]
                            
                            clean_text = get_clean_content(msg)
                            if clean_text:
                                full_response = clean_text
                                response_placeholder.markdown(full_response)
                            
                            # Track Tokens (Agent)
                            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                                update_token_usage(msg.usage_metadata, st.session_state.selected_model, msg.id)

                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tool_call in msg.tool_calls:
                                    # Extract key info for the header
                                    t_name = tool_call['name']
                                    t_args = tool_call['args']
                                    t_id = tool_call['id']
                                    
                                    # Track start time
                                    tool_start_times[t_id] = time.time()
                                    
                                    # Smart Summary
                                    summary = ""
                                    if "filename" in t_args: summary = t_args["filename"]
                                    elif "target_file" in t_args: summary = t_args["target_file"]
                                    elif "design_file" in t_args: summary = t_args["design_file"]
                                    elif "verilog_files" in t_args: summary = str(t_args["verilog_files"])
                                    
                                    # Render as Expander inside Status
                                    with status_container:
                                        with st.expander(f"🛠️ **{t_name}** {summary}", expanded=False):
                                            st.json(t_args)
                            
                        elif "tools" in event:
                            msg = event["tools"]["messages"][-1]
                            content = msg.content
                            t_id = msg.tool_call_id
                            
                            # Calculate Duration
                            duration_str = ""
                            if t_id in tool_start_times:
                                duration = time.time() - tool_start_times[t_id]
                                total_time += duration
                                duration_str = f"({duration:.1f}s)"
                            
                            # Render Output inside Status
                            with status_container:
                                # Determine if success or fail for icon
                                icon = "📄"
                                if "Success" in content or "PASSED" in content: icon = "✅"
                                elif "Error" in content or "FAILED" in content: icon = "❌"
                                
                                with st.expander(f"{icon} Output {duration_str}", expanded=False):
                                    st.code(content)
                                    
                            # Side Effects (Refresh UI)
                            if "Successfully wrote" in content:
                                render_files() # Update tabs
                                
                    status_container.update(label=f"Finished! (Total: {total_time:.1f}s)", state="complete", expanded=False)
                                
                except Exception as e:
                    status_container.update(label="Error", state="error")
                    st.error(f"❌ Error: {e}")
                    
        conn.close()

# --- Main Routing ---
if "current_session" not in st.session_state or st.session_state.current_session is None:
    render_home()
else:
    # Ensure workspace env var is set
    CURRENT_WORKSPACE = session_manager.get_workspace_path(st.session_state.current_session)
    os.environ["RTL_WORKSPACE"] = CURRENT_WORKSPACE
    render_workspace()
