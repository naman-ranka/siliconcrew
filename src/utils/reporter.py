import sqlite3
import datetime
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from src.agents.architect import create_architect_agent

# Reuse pricing logic logic if possible, or duplicate for independence
PRICING = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-3-pro-preview": {"input": 2.00, "output": 12.00}
}

def generate_markdown_report(session_id, db_path, model_name="gemini-2.5-flash"):
    """
    Generates a Markdown report for a given session.
    """
    
    # 1. Connect to DB to get history
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        memory = SqliteSaver(conn)
        config = {"configurable": {"thread_id": session_id}}
        
        # We need the agent graph to load the state
        # We just need the state, no need to actually run agent
        # Passing a dummy model_name since we won't invoke LLM
        agent_graph = create_architect_agent(checkpointer=memory, model_name=model_name)
        
        current_state = agent_graph.get_state(config)
        messages = current_state.values.get("messages", [])
        conn.close()
    except Exception as e:
        return f"# Error Generating Report\n\nCould not load session: {e}"

    if not messages:
        return f"# Session Report: {session_id}\n\n*No messages found.*"

    # 2. Analyze Token Usage
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    total_tokens = 0
    
    transcript = []
    
    for msg in messages:
        # Transcript Formatting
        role = "Unknown"
        
        # Helper to clean content
        def get_clean_content(c):
            if isinstance(c, list):
                text_parts = []
                for item in c:
                    if isinstance(item, dict) and "text" in item:
                        text_parts.append(item["text"])
                    elif isinstance(item, str):
                        text_parts.append(item)
                return "\n".join(text_parts)
            return str(c)
            
        content = get_clean_content(msg.content)
        
        if isinstance(msg, SystemMessage):
            # Skip system prompt in transcript usually, or make it collapsible
            continue 
        elif isinstance(msg, HumanMessage):
            role = "User"
            transcript.append(f"## 👤 User\n\n{content}\n")
        elif isinstance(msg, AIMessage):
            role = "Assistant"
            # Check for tool calls
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tools_used = [tc['name'] for tc in msg.tool_calls]
                transcript.append(f"## 🤖 Assistant (Tools: {', '.join(tools_used)})\n")
            else:
                transcript.append(f"## 🤖 Assistant\n\n{content}\n")
                
            # Usage Tracking (Only on AI Messages)
            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                meta = msg.usage_metadata
                in_t = meta.get("input_tokens", 0)
                out_t = meta.get("output_tokens", 0)
                tot_t = meta.get("total_tokens", 0)
                
                # Cache
                c_t = 0
                if "input_token_details" in meta:
                    det = meta["input_token_details"]
                    if isinstance(det, dict):
                        c_t = det.get("cache_read", 0) or det.get("cache_read_input_tokens", 0)
                
                input_tokens += in_t
                output_tokens += out_t
                total_tokens += tot_t
                cached_tokens += c_t

        elif hasattr(msg, "tool_call_id"): # ToolMessage
             transcript.append(f"## ⚙️ Tool Output\n\n```\n{content[:500]}...\n```\n")

    # 3. Calculate Cost
    rates = PRICING.get(model_name, PRICING["gemini-2.5-flash"])
    cost = (input_tokens / 1_000_000 * rates["input"]) + (output_tokens / 1_000_000 * rates["output"])
    
    # 4. Build Report
    report = f"""# 📄 Session Report: {session_id}
**Date Generated:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Model:** {model_name}

---

## 📊 Usage Analysis

| Metric | Count | Cost (Approx) |
| :--- | :--- | :--- |
| **Input Tokens** | {input_tokens:,} | ${ (input_tokens / 1_000_000 * rates['input']):.4f} |
| **Output Tokens** | {output_tokens:,} | ${ (output_tokens / 1_000_000 * rates['output']):.4f} |
| **Cached Tokens** | {cached_tokens:,} | - |
| **Total** | **{total_tokens:,}** | **${cost:.4f}** |

> **Note:** Costs are estimated based on standard pricing for `{model_name}`.

---

# 📝 Transcript

"""
    report += "\n".join(transcript)
    
    return report
