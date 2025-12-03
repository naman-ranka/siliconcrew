import sys
import os

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tools.run_synthesis import run_synthesis

def main():
    design_file = os.path.abspath("workspace/test3/design.v")
    print(f"Running synthesis for {design_file}...")
    
    # Using parameters from user request/context
    result = run_synthesis(
        verilog_files=[design_file],
        top_module="async_fifo",
        clock_period_ns=2, # Target 500MHz
        utilization=30,
        cwd=os.path.abspath("workspace/test3")
    )
    
    print("Synthesis Result:", result)
    
    if result["success"]:
        print("Synthesis SUCCESS!")
    else:
        print("Synthesis FAILED.")
        print("Stderr:", result["stderr"])

if __name__ == "__main__":
    main()
