import os
import sys
from dotenv import load_dotenv

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.rtl_coder import rtl_coder_node
from src.state.state import DesignState

def main():
    # Load env vars (API KEY)
    load_dotenv()
    
    if "GOOGLE_API_KEY" not in os.environ:
        print("❌ GOOGLE_API_KEY not found in environment variables.")
        print("Please set it in .env or export it.")
        sys.exit(1)

    print("Verifying RTL Coder Agent (Gemini)...")
    
    # Mock State
    initial_state: DesignState = {
        "design_spec": "Create a 4-bit up-counter with active-high reset and enable.",
        "verilog_code": "",
        "testbench_code": "",
        "iteration_count": 0,
        "max_iterations": 5,
        "error_logs": [],
        "syntax_valid": False,
        "functional_valid": False,
        "ppa_metrics": {},
        "current_agent": "rtl_coder",
        "messages": []
    }
    
    try:
        new_state = rtl_coder_node(initial_state)
        code = new_state.get("verilog_code", "")
        
        print("\n--- Generated Code ---")
        print(code)
        print("----------------------")
        
        if "module" in code and "endmodule" in code:
            print("✅ Valid Verilog Structure detected.")
            print("\n🎉 RTL Coder Verification PASSED!")
        else:
            print("❌ Generated code does not look like Verilog.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Agent Execution Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
