import os
import sys

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.run_linter import run_linter

def create_verilog_file(filename, content):
    with open(filename, "w") as f:
        f.write(content)

def main():
    print("Verifying Linter Tool (Icarus Verilog)...")
    
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../workspace'))
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir)
        
    # 1. Test Valid File
    valid_file = os.path.join(workspace_dir, "valid_design.v")
    create_verilog_file(valid_file, """
module counter(input clk, output reg [7:0] count);
    always @(posedge clk) count <= count + 1;
endmodule
""")
    
    print(f"\nTesting Valid File: {valid_file}")
    result_valid = run_linter([valid_file], cwd=workspace_dir)
    
    if result_valid['success']:
        print("✅ Valid file passed linting.")
    else:
        print("❌ Valid file FAILED linting.")
        print(f"Stderr: {result_valid['stderr']}")
        sys.exit(1)

    # 2. Test Invalid File (Syntax Error)
    invalid_file = os.path.join(workspace_dir, "invalid_design.v")
    create_verilog_file(invalid_file, """
module broken(input clk);
    always @(posedge clk) begin
        count <= count + 1  // Missing semicolon
    end
endmodule
""")
    
    print(f"\nTesting Invalid File: {invalid_file}")
    result_invalid = run_linter([invalid_file], cwd=workspace_dir)
    
    if not result_invalid['success']:
        print("✅ Invalid file correctly failed linting.")
        if "syntax error" in result_invalid['stderr'].lower():
             print("✅ Error message contains 'syntax error'.")
             print("\n🎉 Linter Tool Verification PASSED!")
        else:
             print(f"⚠️  Failed but unexpected error message: {result_invalid['stderr']}")
             # We still consider this a pass for the tool wrapper, as it reported failure.
             print("\n🎉 Linter Tool Verification PASSED!")
    else:
        print("❌ Invalid file PASSED linting (It should have failed).")
        sys.exit(1)
        
    # Cleanup
    if os.path.exists(valid_file): os.remove(valid_file)
    if os.path.exists(invalid_file): os.remove(invalid_file)

if __name__ == "__main__":
    main()
