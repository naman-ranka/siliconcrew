import sys
import os

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tools.run_simulation import run_simulation

def verify():
    # Create infinite loop file
    test_file = os.path.abspath("workspace/test3/test_timeout.v")
    with open(test_file, "w") as f:
        f.write("module test_timeout; initial begin while(1); end endmodule")

    print(f"Running simulation on {test_file} with timeout=5s...")
    result = run_simulation([test_file], top_module="test_timeout", timeout=5)
    
    print("Result:", result)

    if "Simulation timed out" in result["stderr"]:
        print("SUCCESS: Timeout caught!")
    else:
        print("FAILURE: Did not timeout as expected.")

if __name__ == "__main__":
    verify()
