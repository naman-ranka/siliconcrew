import os
import sys

# Add src to python path to import the tool
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.run_iverilog import run_iverilog

def create_hello_world_verilog(filename):
    content = """
module hello;
  initial begin
    $display("Hello, SiliconCrew!");
    $finish;
  end
endmodule
"""
    with open(filename, "w") as f:
        f.write(content)

def main():
    print("Verifying Icarus Verilog Tool...")
    
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../workspace'))
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir)
        
    test_file = os.path.join(workspace_dir, "test_hello.v")
    create_hello_world_verilog(test_file)
    
    print(f"Created test file: {test_file}")
    
    # Run the tool
    result = run_iverilog([test_file], output_executable="test_hello.out", cwd=workspace_dir)
    
    print(f"Command executed: {result['command']}")
    
    if result['success']:
        print("✅ Compilation and Execution Successful")
        if "Hello, SiliconCrew!" in result['stdout']:
            print("✅ Output Verified: 'Hello, SiliconCrew!' found.")
            print("\n🎉 Icarus Verilog Tool Verification PASSED!")
            
            # Cleanup
            if os.path.exists(test_file):
                os.remove(test_file)
            out_file = os.path.join(workspace_dir, "test_hello.out")
            if os.path.exists(out_file):
                os.remove(out_file)
                
            sys.exit(0)
        else:
            print(f"❌ Output Mismatch. Got:\n{result['stdout']}")
            sys.exit(1)
    else:
        print("❌ Execution Failed")
        print(f"Stderr: {result['stderr']}")
        sys.exit(1)

if __name__ == "__main__":
    main()
