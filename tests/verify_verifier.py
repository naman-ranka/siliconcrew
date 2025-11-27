import os
import sys
from dotenv import load_dotenv

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.verifier import verifier_node
from src.state.state import DesignState

def main():
    load_dotenv()
    print("Verifying Verifier Agent (Gemini)...")
    
    # Mock State with a valid design
    # We provide a correct 4-bit counter so the verification SHOULD pass
    valid_rtl = """
module counter(
    input clk,
    input rst,
    output reg [3:0] out
);
    always @(posedge clk or posedge rst) begin
        if (rst)
            out <= 4'b0000;
        else
            out <= out + 1;
    end
endmodule
"""
    
    initial_state: DesignState = {
        "design_spec": "A 4-bit up-counter with asynchronous active-high reset.",
        "verilog_code": valid_rtl,
        "testbench_code": "",
        "iteration_count": 0,
        "max_iterations": 5,
        "error_logs": [],
        "syntax_valid": True,
        "functional_valid": False,
        "ppa_metrics": {},
        "current_agent": "verifier",
        "messages": []
    }
    
    try:
        new_state = verifier_node(initial_state)
        
        print("\n--- Testbench Code ---")
        print(new_state.get("testbench_code", ""))
        print("----------------------")
        
        if new_state["functional_valid"]:
            print("✅ Functional Verification PASSED.")
            print("\n🎉 Verifier Agent Verification PASSED!")
        else:
            print("❌ Functional Verification FAILED.")
            print(f"Errors: {new_state['error_logs']}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Agent Execution Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
