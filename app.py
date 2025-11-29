import streamlit as st
import os
import sqlite3
import shutil
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from src.agents.architect import create_architect_agent, SYSTEM_PROMPT

# Load environment
load_dotenv()

st.set_page_config(page_title="SiliconCrew Architect", layout="wide")

# --- Dynamic Workspace Logic ---
if "run_id" not in st.session_state:
    st.session_state.run_id = "default_run"

# Define workspace based on run_id
BASE_WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'workspace'))
CURRENT_WORKSPACE = os.path.join(BASE_WORKSPACE, st.session_state.run_id)

if not os.path.exists(CURRENT_WORKSPACE):
    os.makedirs(CURRENT_WORKSPACE)

# Set Env Var for Tools
os.environ["RTL_WORKSPACE"] = CURRENT_WORKSPACE

DB_PATH = os.path.join(os.path.dirname(__file__), 'state.db')

# Custom CSS
st.markdown("""
<style>
    .stChatMessage { padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; }
    .tool-call { background-color: transparent; padding: 0.5rem; border-radius: 0.3rem; border-left: 3px solid #2196f3; font-family: monospace; margin-bottom: 0.5rem; }
    .tool-output { background-color: #f0f2f6; padding: 0.5rem; border-radius: 0.3rem; font-family: monospace; font-size: 0.9em; border-left: 3px solid #ff4b4b; }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("SiliconCrew 🤖")
    st.caption("Autonomous RTL Design Agent")
    st.divider()
    
    # Session & Run Management
    session_id = st.text_input("Session ID", value="default_session")
    
    # Run Selector
    runs = [d for d in os.listdir(BASE_WORKSPACE) if os.path.isdir(os.path.join(BASE_WORKSPACE, d))]
    selected_run = st.selectbox("Select Run/Workspace", ["New Run"] + sorted(runs, reverse=True))
    
    if selected_run == "New Run":
        new_run_name = st.text_input("New Run Name", value=f"run_{len(runs)+1}")
        if st.button("Create Run"):
            st.session_state.run_id = new_run_name
            st.rerun()
    else:
        if st.session_state.run_id != selected_run:
            st.session_state.run_id = selected_run
            st.rerun()
            
    st.info(f"📂 Workspace: {st.session_state.run_id}")
    st.divider()
    
# Main Layout
col1, col2 = st.columns([1.2, 0.8])

# Column 2: Live Workspace
with col2:
    st.subheader(f"Live Workspace: {st.session_state.run_id}")
    
    # Placeholder for dynamic updates
    file_viewer_placeholder = st.empty()

    def render_files():
        with file_viewer_placeholder.container():
            # Get list of files
            if os.path.exists(CURRENT_WORKSPACE):
                all_files = sorted(os.listdir(CURRENT_WORKSPACE))
                # Filter for relevant files
                files = [f for f in all_files if f.endswith(('.v', '.sv', '.rpt', '.txt', '.log', '.gds'))]
            else:
                files = []

            if files:
                tabs = st.tabs(files)
                for i, file_name in enumerate(files):
                    with tabs[i]:
                        file_path = os.path.join(CURRENT_WORKSPACE, file_name)
                        try:
                            with open(file_path, "r", errors='ignore') as f:
                                content = f.read()
                            st.code(content, language="verilog" if file_name.endswith(".v") else "text")
                        except Exception as e:
                            st.error(f"Error reading file: {e}")
            else:
                st.info("No files in workspace.")

    # Initial render
    render_files()

    # Alias for compatibility
    def update_file_viewer(target_file=None):
        render_files()

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

# Column 1: Chat Interface
with col1:
    st.subheader("Chat")
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    memory = SqliteSaver(conn)
    agent_graph = create_architect_agent(checkpointer=memory)
    config = {"configurable": {"thread_id": session_id}}
    
    current_state = agent_graph.get_state(config)
    
    if current_state.values and "messages" in current_state.values:
        for msg in current_state.values["messages"]:
            if isinstance(msg, SystemMessage): continue
            
            role = "user"
            if isinstance(msg, AIMessage):
                role = "assistant"
                with st.chat_message(role):
                    # Show Tool Calls if present
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            args_str = str(tool_call['args'])
                            # Truncate for display
                            short_args = (args_str[:100] + '...') if len(args_str) > 100 else args_str
                            
                            st.markdown(f"<div class='tool-call'>🛠️ Calling <b>{tool_call['name']}</b></div>", unsafe_allow_html=True)
                            with st.expander(f"Arguments: {short_args}", expanded=False):
                                st.code(args_str)
                    
                    # Clean content display
                    clean_text = get_clean_content(msg)
                    if clean_text:
                        st.markdown(clean_text)
                        
            elif hasattr(msg, "tool_call_id"): # ToolMessage
                role = "tool"
                with st.chat_message(role):
                    with st.expander("🛠️ Tool Output", expanded=False):
                        st.markdown(f"```\n{msg.content}\n```")
    else:
        st.info("👋 Hi! I'm the Architect. What hardware shall we build today?")

    if prompt := st.chat_input("Ex: Design an 8-bit counter"):
        with st.chat_message("user"):
            st.markdown(prompt)
            
        with st.chat_message("assistant"):
            status_container = st.status("Thinking...", expanded=True)
            response_placeholder = st.empty()
            full_response = ""
            
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
                        
                        # Show Tool Calls in Status
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tool_call in msg.tool_calls:
                                status_container.markdown(f"**🛠️ Calling {tool_call['name']}:**")
                                status_container.json(tool_call['args'])
                        
                        # Clean content display
                        clean_text = get_clean_content(msg)
                        if clean_text:
                            full_response = clean_text
                            response_placeholder.markdown(full_response)
                            
                    elif "tools" in event:
                        msg = event["tools"]["messages"][-1]
                        content = msg.content
                        status_container.markdown(f"**📄 Output:**\n```\n{content[:500]}...\n```")
                        
                        if "Successfully wrote to" in content:
                            # Extract filename: "Successfully wrote to design.v..."
                            import re
                            match = re.search(r"Successfully wrote to ([^\s]+)", content)
                            if match:
                                written_file = match.group(1)
                                update_file_viewer(written_file)
                                status_container.success(f"Updated {written_file}")
                            else:
                                update_file_viewer()
                                status_container.success(f"Updated file.")
                                
                        elif "FAILED" in content:
                            status_container.error("Tool Failed. Retrying...")
                        elif "PASSED" in content:
                            status_container.success("Verification Passed!")
                            
                status_container.update(label="Finished!", state="complete", expanded=False)
                            
            except Exception as e:
                status_container.update(label="Error", state="error")
                st.error(f"❌ Error: {e}")
                
    conn.close()
