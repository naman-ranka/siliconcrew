import os
import sys

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.run_simulation import run_simulation

def create_file(filename, content):
    with open(filename, "w") as f:
        f.write(content)

def main():
    print("Verifying Simulation Tool...")
    
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../workspace'))
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir)
        
    # 1. Create RTL
    rtl_file = os.path.join(workspace_dir, "adder.v")
    create_file(rtl_file, """
module adder(input [3:0] a, b, output [3:0] sum);
    assign sum = a + b;
endmodule
""")

    # 2. Create Testbench (PASS case)
    tb_pass_file = os.path.join(workspace_dir, "adder_tb_pass.v")
    create_file(tb_pass_file, """
module adder_tb;
    reg [3:0] a, b;
    wire [3:0] sum;
    
    adder uut(a, b, sum);
    
    initial begin
        a = 2; b = 3;
        #10;
        if (sum == 5) $display("TEST PASSED");
        else $display("TEST FAILED");
        $finish;
    end
endmodule
""")

    # 3. Create Testbench (FAIL case)
    tb_fail_file = os.path.join(workspace_dir, "adder_tb_fail.v")
    create_file(tb_fail_file, """
module adder_tb;
    reg [3:0] a, b;
    wire [3:0] sum;
    
    adder uut(a, b, sum);
    
    initial begin
        a = 2; b = 2;
        #10;
        if (sum == 5) $display("TEST PASSED"); # Expecting 4, checking for 5 -> FAIL
        else $display("TEST FAILED: Expected 5, got %d", sum);
        $finish;
    end
endmodule
""")

    # Test 1: Expect PASS
    print("\nTest 1: Running Passing Testbench...")
    result_pass = run_simulation([rtl_file, tb_pass_file], top_module="adder_tb_pass", cwd=workspace_dir)
    
    if result_pass['success'] and result_pass['test_passed']:
        print("✅ Test 1 Passed as expected.")
    else:
        print("❌ Test 1 FAILED (Should have passed).")
        print(f"Stdout: {result_pass['stdout']}")
        sys.exit(1)

    # Test 2: Expect FAIL
    print("\nTest 2: Running Failing Testbench...")
    result_fail = run_simulation([rtl_file, tb_fail_file], top_module="adder_tb_fail", cwd=workspace_dir)
    
    if not result_fail['success'] and not result_fail['test_passed']:
        print("✅ Test 2 Failed as expected.")
        if "TEST FAILED" in result_fail['stdout']:
            print("✅ Captured 'TEST FAILED' in output.")
            print("\n🎉 Simulation Tool Verification PASSED!")
        else:
            print("⚠️  Failed but didn't find 'TEST FAILED' string.")
    else:
        print("❌ Test 2 PASSED (Should have failed).")
        print(f"Stdout: {result_fail['stdout']}")
        sys.exit(1)

    # Cleanup
    for f in [rtl_file, tb_pass_file, tb_fail_file]:
        if os.path.exists(f): os.remove(f)
    for f in ["adder_tb_pass.out", "adder_tb_fail.out"]:
        p = os.path.join(workspace_dir, f)
        if os.path.exists(p): os.remove(p)

if __name__ == "__main__":
    main()
