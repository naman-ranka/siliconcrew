import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from src.tools.wrappers import write_file, read_file, linter_tool
from src.state.state import DesignState
from src.config import DEFAULT_MODEL

# Initialize LLM
llm = ChatGoogleGenerativeAI(model=DEFAULT_MODEL, google_api_key=os.environ.get("GOOGLE_API_KEY"))

# Restrict tools for the Multi-Agent Architect
# It can only Write and Lint. It CANNOT simulate or synthesize.
architect_tools = [write_file, read_file, linter_tool]

SYSTEM_PROMPT = """You are "The Architect", the RTL Coding Specialist.
Your goal is to write SystemVerilog/Verilog code that meets the user's specification.

**Your Role in the Team:**
1.  **Write Code:** You generate `design.v`.
2.  **Lint Code:** You use `linter_tool` to ensure syntax is perfect.
3.  **Fix Bugs:** If the "Verifier" sends you an error log, you analyze it and fix the code.

**What you CANNOT do:**
- Do NOT write testbenches (The Verifier does that).
- Do NOT run simulations (The Verifier does that).
- Do NOT run synthesis (The Analyst does that).

**Instructions:**
- If this is the first iteration, write the code based on the spec.
- If you have `error_logs` in the state, analyze them carefully. They come from failed simulations.
- Always run `linter_tool` before finishing. If it fails, fix the syntax immediately.
- Once you are confident the code is syntax-free and addresses the requirements/errors, STOP.
"""

def architect_node(state: DesignState) -> DesignState:
    """
    The Architect Node.
    - Input: Design Spec + (Optional) Error Logs.
    - Output: design.v (written to disk) + Updated State.
    """
    print("🏗️ Architect: Working on RTL...")

    # 1. Increment Iteration Count
    current_iter = state.get("iteration_count", 0) + 1

    # 2. Construct Prompt
    # We explicitly feed the state into the agent's context
    prompt_content = f"Design Spec: {state['design_spec']}\n"

    if state.get("error_logs") and len(state["error_logs"]) > 0:
        # Load current code to help the agent fix it
        # Try to read design.v from workspace, or fallback to state
        current_code = state.get("verilog_code", "")
        workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../workspace'))
        design_path = os.path.join(workspace_dir, "design.v")
        if os.path.exists(design_path):
             with open(design_path, "r") as f:
                 current_code = f.read()

        prompt_content += f"\n⚠️ PREVIOUS SIMULATION FAILED:\n{state['error_logs'][-1]}\n"
        prompt_content += f"\nCURRENT CODE:\n{current_code}\n"
        prompt_content += "Please fix the code based on this error."
    else:
        prompt_content += "\nPlease generate the initial RTL design (design.v)."

    # 3. Create/Invoke the ReAct Agent (Local Loop)
    # We use a localized agent just for this step to handle tool calls (Linting)
    agent = create_react_agent(llm, architect_tools)

    result = agent.invoke({
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt_content)
        ]
    })

    # 4. Extract Final Response
    last_message = result["messages"][-1]

    # 5. Read the generated file to put into state (for the Verifier to see)
    # We assume the agent used write_file tool.
    # To be safe, we read 'design.v' from the workspace.
    # Note: Ideally, the agent should return the code, but file I/O is robust.
    # Using read_file tool logic manually here would be cleaner, but we can trust the agent wrote it.
    
    return {
        "iteration_count": current_iter,
        "messages": [last_message] # Append to history
    }
