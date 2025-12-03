import sys
import os

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tools.run_sby import run_sby

def main():
    sby_file = os.path.abspath("workspace/test3/async_fifo.sby")
    print(f"Running SBY for {sby_file}...")
    
    result = run_sby(
        sby_file=sby_file,
        cwd=os.path.dirname(sby_file),
        timeout=300
    )
    
    print("SBY Result:", result)
    
    if result["status"] == "PASS":
        print("SUCCESS: Design Verified!")
    else:
        print(f"FAILURE: Status {result['status']}")
        print("Stdout:", result["stdout"])

if __name__ == "__main__":
    main()
