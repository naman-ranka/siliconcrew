import streamlit as st
import os
import sqlite3
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from src.agents.architect import create_architect_agent, SYSTEM_PROMPT

# Load environment
load_dotenv()

st.set_page_config(page_title="SiliconCrew Architect", layout="wide")

# Paths
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'workspace'))
if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR)

DB_PATH = os.path.join(os.path.dirname(__file__), 'state.db')

# Custom CSS for better styling
st.markdown("""
<style>
    .stChatMessage {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .tool-output {
        background-color: #f0f2f6;
        padding: 0.5rem;
        border-radius: 0.3rem;
        font-family: monospace;
        font-size: 0.9em;
        border-left: 3px solid #ff4b4b;
    }
    .agent-thought {
        font-style: italic;
        color: #555;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("SiliconCrew 🤖")
    st.caption("Autonomous RTL Design Agent")
    
    st.divider()
    
    # Session Management
    session_id = st.text_input("Session ID", value="default_session")
    if st.button("Clear History"):
        st.warning("Switch Session ID to start fresh.")
        
    st.divider()
    
    st.markdown("### 📂 Workspace")
    if os.path.exists(WORKSPACE_DIR):
        files = sorted(os.listdir(WORKSPACE_DIR))
    else:
        files = []
    selected_file = st.selectbox("View File", options=files, index=0 if files else None)
    
    if st.button("Refresh Files"):
        st.rerun()

# Main Layout
col1, col2 = st.columns([1.2, 0.8])

# Column 2: Live Workspace (Right Side)
with col2:
    st.subheader("Live Workspace")
    tab1, tab2, tab3 = st.tabs(["📄 Code", "📊 Metrics", "🌊 Waveforms"])
    
    code_placeholder = tab1.empty()
    metrics_placeholder = tab2.empty()
    waveform_placeholder = tab3.empty()

    def update_file_viewer():
        if selected_file:
            file_path = os.path.join(WORKSPACE_DIR, selected_file)
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    content = f.read()
                code_placeholder.code(content, language="verilog" if selected_file.endswith(".v") else "text")
            else:
                code_placeholder.warning("File not found.")
        else:
            code_placeholder.info("No files in workspace.")
            
    update_file_viewer()
    metrics_placeholder.info("PPA Metrics will appear here after synthesis.")
    waveform_placeholder.info("Waveform visualization coming soon.")

# Column 1: Chat Interface (Left Side)
with col1:
    st.subheader("Chat")
    
    # Load History from DB
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    memory = SqliteSaver(conn)
    agent_graph = create_architect_agent(checkpointer=memory)
    
    config = {"configurable": {"thread_id": session_id}}
    
    # Get current state
    current_state = agent_graph.get_state(config)
    
    # Display History
    if current_state.values and "messages" in current_state.values:
        for msg in current_state.values["messages"]:
            if isinstance(msg, SystemMessage):
                continue
                
            role = "user"
            if isinstance(msg, AIMessage):
                role = "assistant"
            elif hasattr(msg, "tool_call_id"): # ToolMessage
                role = "tool"
                
            with st.chat_message(role):
                if role == "tool":
                    with st.expander("🛠️ Tool Output", expanded=False):
                        st.markdown(f"```\n{msg.content}\n```")
                else:
                    st.markdown(msg.content)
    else:
        st.info("👋 Hi! I'm the Architect. What hardware shall we build today?")

    # User Input
    if prompt := st.chat_input("Ex: Design an 8-bit counter"):
        # Add user message
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # Run Agent Synchronously
        with st.chat_message("assistant"):
            # We use a container for the "Thinking" process
            status_container = st.status("Thinking...", expanded=True)
            response_placeholder = st.empty()
            full_response = ""
            
            try:
                # Prepare input messages
                input_messages = []
                snapshot = agent_graph.get_state(config)
                if not snapshot.values or not snapshot.values.get("messages"):
                    input_messages.append(SystemMessage(content=SYSTEM_PROMPT))
                
                input_messages.append(("user", prompt))
                
                # Update config with recursion limit
                config["recursion_limit"] = 50
                
                # Stream events
                events = agent_graph.stream(
                    {"messages": input_messages},
                    config
                )
                
                for event in events:
                    if "agent" in event:
                        msg = event["agent"]["messages"][-1]
                        content = msg.content
                        
                        # If content is empty (tool call), show status
                        if not content:
                            status_container.write("🤖 Deciding next step...")
                        else:
                            # Final answer or thought
                            full_response = content
                            response_placeholder.markdown(full_response)
                            
                    elif "tools" in event:
                        msg = event["tools"]["messages"][-1]
                        content = msg.content
                        
                        # Show tool output inside the status container
                        status_container.markdown(f"**🛠️ Tool Output:**\n```\n{content[:500]}...\n```")
                        
                        if "Successfully wrote to" in content:
                            update_file_viewer()
                            status_container.write(f"✅ Updated file.")
                        elif "FAILED" in content:
                            status_container.error("❌ Tool Failed. Retrying...")
                        elif "PASSED" in content:
                            status_container.success("✅ Verification Passed!")
                            
                status_container.update(label="Finished!", state="complete", expanded=False)
                            
            except Exception as e:
                status_container.update(label="Error", state="error")
                st.error(f"❌ Error: {e}")
                
    conn.close()
