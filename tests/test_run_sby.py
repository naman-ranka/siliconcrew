import os
import sys
import shutil

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tools.run_sby import run_sby

def test_run_sby_pass():
    # 1. Create a dummy design
    design_v = os.path.abspath("workspace/test_sby_pass.v")
    with open(design_v, "w") as f:
        f.write("""
module test_sby_pass (input clk, input a, output b);
    assign b = a;
    
    always @(posedge clk) begin
        assert(b == a);
    end
endmodule
""")

    # 2. Create .sby file
    sby_file = os.path.abspath("workspace/test_sby_pass.sby")
    with open(sby_file, "w") as f:
        f.write("""
[options]
mode prove

[engines]
abc pdr

[script]
read -formal test_sby_pass.v
prep -top test_sby_pass

[files]
test_sby_pass.v
""")

    # 3. Run the tool
    # We need to ensure run_docker_command mounts the workspace correctly.
    # The tool assumes the file is in the workspace.
    
    result = run_sby(
        sby_file=sby_file,
        cwd=os.path.dirname(sby_file),
        timeout=60
    )
    
    with open("test_sby_output.txt", "w") as f:
        f.write(str(result))
        
    print("Status:", result["status"])
    print("Stdout:", result["stdout"])
    
    assert result["status"] == "PASS", "SBY run failed or did not pass"

if __name__ == "__main__":
    test_run_sby_pass()
