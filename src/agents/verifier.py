import os
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from src.state.state import DesignState
from src.tools.run_simulation import run_simulation
from src.config import DEFAULT_MODEL

# Initialize LLM
if "GOOGLE_API_KEY" not in os.environ:
    from dotenv import load_dotenv
    load_dotenv()

llm = ChatGoogleGenerativeAI(model=DEFAULT_MODEL, google_api_key=os.environ.get("GOOGLE_API_KEY"))

SYSTEM_PROMPT = """You are an expert Verification Engineer.
Your goal is to write a robust SystemVerilog/Verilog testbench to verify a given RTL design.

Rules:
1. Return ONLY the Testbench code. Do not include markdown formatting.
2. The testbench must instantiate the DUT (Device Under Test).
3. It must include self-checking logic (if/else statements checking outputs).
4. It must print "TEST PASSED" if all checks pass, and "TEST FAILED" otherwise.
5. Use $finish to end the simulation.
6. Ensure the module name matches the requested testbench name (usually <module>_tb).
7. CRITICAL: When checking sequential logic outputs after a clock edge, ALWAYS wait for a small delay (e.g., #1;) before checking the value to avoid race conditions.
"""

def verifier_node(state: DesignState) -> DesignState:
    """
    Agent node that generates testbenches and runs simulations.
    """
    print("🕵️ Verifier: Generating testbench and running simulation...")
    
    # 0. Read Code from Workspace
    # The Architect wrote 'design.v' to disk. We should read it to ensure we have the latest.
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../workspace'))
    rtl_file = os.path.join(workspace_dir, "design.v")

    if os.path.exists(rtl_file):
        with open(rtl_file, "r") as f:
            rtl_code = f.read()
    else:
        # Fallback or error if file missing
        rtl_code = state.get("verilog_code", "")

    spec = state['design_spec']
    
    # 1. Generate Testbench
    user_content = f"""
    Design Specification:
    {spec}
    
    RTL Code:
    {rtl_code}
    
    Please generate a self-checking testbench for this design. 
    The testbench module name should be 'tb'.
    """
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content)
    ]
    
    response = llm.invoke(messages)
    tb_code = response.content.strip()
    
    # Clean up markdown
    if tb_code.startswith("```verilog"):
        tb_code = tb_code.replace("```verilog", "").replace("```", "")
    elif tb_code.startswith("```systemverilog"):
        tb_code = tb_code.replace("```systemverilog", "").replace("```", "")
    elif tb_code.startswith("```"):
        tb_code = tb_code.replace("```", "")
        
    tb_code = tb_code.strip()
    
    # 2. Write TB File
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir)
        
    tb_file = os.path.join(workspace_dir, "tb.v")
    with open(tb_file, "w") as f:
        f.write(tb_code)
        
    # 3. Run Simulation
    # We assume the testbench top module is 'tb' based on our prompt
    result = run_simulation([rtl_file, tb_file], top_module="tb", cwd=workspace_dir)
    
    # 4. Update State
    new_state = {
        "verilog_code": rtl_code, # Sync back just in case
        "testbench_code": tb_code,
        "functional_valid": result["success"], # result['success'] checks for 'TEST PASSED'
        "error_logs": []
    }
    
    if not result["success"]:
        # Simulation failed or Test failed
        error_msg = f"Simulation Failed.\nStdout: {result['stdout']}\nStderr: {result['stderr']}"
        new_state["error_logs"] = [error_msg]
        print(f"❌ Verification Failed. Error: {error_msg[:100]}...")
    else:
        print("✅ Verification Passed.")
        
    return new_state
