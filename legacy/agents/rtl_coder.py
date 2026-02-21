import os
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from src.state.state import DesignState
from src.config import DEFAULT_MODEL

# Initialize LLM
if "GOOGLE_API_KEY" not in os.environ:
    # Try to load from .env if not in env (useful for local runs not using load_dotenv before import)
    from dotenv import load_dotenv
    load_dotenv()

llm = ChatGoogleGenerativeAI(model=DEFAULT_MODEL, google_api_key=os.environ.get("GOOGLE_API_KEY"))

SYSTEM_PROMPT = """You are an expert Verilog/SystemVerilog RTL Engineer. 
Your goal is to write syntactically correct and functionally accurate Verilog modules based on specifications.

Rules:
1. Return ONLY the Verilog code. Do not include markdown formatting (like ```verilog).
2. If fixing errors, analyze the error log carefully and correct the specific lines.
3. Use standard Verilog-2001 or SystemVerilog syntax.
4. Ensure module names match the requested top-level name.
"""

def rtl_coder_node(state: DesignState) -> DesignState:
    """
    Agent node that generates or fixes Verilog code.
    """
    print("[RTL] RTL Coder: Generating code...")
    
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    
    # Context Construction
    if state.get("verilog_code"):
        # We are in a fix loop
        user_content = f"""
        Current Code:
        {state['verilog_code']}
        
        Error Logs:
        {state['error_logs'][-1] if state['error_logs'] else "Unknown Error"}
        
        Please fix the errors and return the corrected Verilog code.
        """
    else:
        # Fresh generation
        user_content = f"""
        Design Specification:
        {state['design_spec']}
        
        Please generate the Verilog code for this specification.
        """
        
    messages.append(HumanMessage(content=user_content))
    
    # Call LLM
    response = llm.invoke(messages)
    code = response.content.strip()
    
    # Clean up markdown if present (just in case)
    if code.startswith("```verilog"):
        code = code.replace("```verilog", "").replace("```", "")
    elif code.startswith("```"):
        code = code.replace("```", "")
        
    return {"verilog_code": code.strip()}
