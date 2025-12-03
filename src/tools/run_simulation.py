import os
import sys
from .run_iverilog import run_iverilog

def run_simulation(verilog_files, top_module="tb", cwd=None, timeout=60):
    """
    Runs a Verilog simulation and parses the output for pass/fail status.
    
    Args:
        verilog_files (list): List of paths to .v files (RTL + Testbench).
        top_module (str): Name of the top-level module (used for naming the executable).
        cwd (str): Working directory.
        timeout (int): Timeout in seconds (default 60).
        
    Returns:
        dict: {
            "success": bool,        # True if simulation ran and tests passed
            "compilation_success": bool,
            "simulation_success": bool, # True if vvp ran without crashing
            "test_passed": bool,    # True if "PASS" or "TEST PASSED" found in output
            "stdout": str,
            "stderr": str
        }
    """
    if cwd is None:
        cwd = os.getcwd()
        
    output_exec = f"{top_module}.out"
    
    # Run Icarus Verilog (Compile + Run)
    result = run_iverilog(verilog_files, output_executable=output_exec, cwd=cwd, timeout=timeout)
    
    response = {
        "success": False,
        "compilation_success": False,
        "simulation_success": False,
        "test_passed": False,
        "stdout": result["stdout"],
        "stderr": result["stderr"]
    }
    
    # Analyze results
    if "Compilation Failed" in result["stderr"] or not result["success"]:
        # Compilation failed or vvp crashed
        # Note: run_iverilog returns success=False if returncode != 0
        if "Compilation Failed" in result["stderr"]:
             response["compilation_success"] = False
        else:
             response["compilation_success"] = True # Compilation likely worked, but run failed
             
        return response
    
    response["compilation_success"] = True
    response["simulation_success"] = True
    
    # Check for Pass/Fail markers in stdout
    # Common conventions: "PASS", "TEST PASSED", "FAIL", "TEST FAILED"
    stdout_lower = result["stdout"].lower()
    
    if "fail" in stdout_lower or "error" in stdout_lower:
        response["test_passed"] = False
    elif "pass" in stdout_lower:
        response["test_passed"] = True
    else:
        # Ambiguous result - maybe just waveforms?
        # For this tool, we assume we need explicit confirmation.
        response["test_passed"] = False
        
    response["success"] = response["test_passed"]
    
    return response
