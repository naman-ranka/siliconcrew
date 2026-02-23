import os
import sys

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.wrappers import start_synthesis

def main():
    print("Testing Synthesis Tool Wrapper (Rich Output)...")
    
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../workspace'))
    design_file = "synth_counter.v"
    
    # Ensure the file exists (created by previous tests)
    if not os.path.exists(os.path.join(workspace_dir, design_file)):
        print(f"Creating dummy {design_file}...")
        with open(os.path.join(workspace_dir, design_file), "w") as f:
            f.write("module synth_counter(input clk, output reg [3:0] q); always @(posedge clk) q <= q + 1; endmodule")

    print(f"Calling start_synthesis('{design_file}', 'synth_counter')...")
    
    # This script is informational; start_synthesis is async and returns job metadata.
    output = start_synthesis.invoke({"verilog_files": [design_file], "top_module": "synth_counter"})
    
    print("\n--- Tool Output ---")
    print(output)
    print("-------------------")
    
    if "job_id" in output and "run_id" in output:
        print("✅ Async synthesis start verified!")
    else:
        print("❌ Rich Output Missing or Synthesis Failed")

if __name__ == "__main__":
    main()
