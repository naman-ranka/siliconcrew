import os
import sys
import shutil
import pytest

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tools.run_cocotb import run_cocotb

def test_run_cocotb_simple():
    # 1. Create a dummy design
    design_v = os.path.abspath("workspace/test_cocotb_design.v")
    with open(design_v, "w") as f:
        f.write("""
module my_inverter (input a, output b);
    assign b = ~a;
endmodule
""")

    # 2. Create a dummy cocotb test
    test_py = os.path.abspath("workspace/test_cocotb_design.py")
    with open(test_py, "w") as f:
        f.write("""
import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def my_test(dut):
    dut.a.value = 0
    await Timer(1, units="ns")
    assert dut.b.value == 1, f"Expected 1, got {dut.b.value}"
    
    dut.a.value = 1
    await Timer(1, units="ns")
    assert dut.b.value == 0, f"Expected 0, got {dut.b.value}"
""")

    # 3. Run the tool
    # Note: python_module should be just the filename without .py
    result = run_cocotb(
        verilog_files=[design_v],
        toplevel="my_inverter",
        python_module="test_cocotb_design",
        cwd=os.path.abspath("workspace"),
        timeout=10
    )
    
    print("Stdout:", result["stdout"])
    print("Stderr:", result["stderr"])
    
    assert result["success"], "Cocotb run failed"
    assert "TEST PASSED" in result["stdout"] or "passed" in result["stdout"].lower()

if __name__ == "__main__":
    test_run_cocotb_simple()
