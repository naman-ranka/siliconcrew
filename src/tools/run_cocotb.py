import os
import sys
import shutil
from cocotb_test.simulator import run

def run_cocotb(verilog_files, toplevel, python_module, cwd=None, timeout=60):
    """
    Runs a Cocotb testbench using cocotb-test wrapper.
    
    Args:
        verilog_files (list): List of paths to .v files.
        toplevel (str): Name of the top-level Verilog module.
        python_module (str): Name of the Python test module (without .py).
        cwd (str): Working directory.
        timeout (int): Timeout in seconds.
        
    Returns:
        dict: {
            "success": bool,
            "stdout": str,
            "stderr": str,
            "command": str
        }
    """
    if cwd is None:
        cwd = os.getcwd()
        
    # Check for iverilog
    if not shutil.which("iverilog"):
        return {
            "success": False,
            "stdout": "",
            "stderr": "Error: 'iverilog' executable not found in PATH.",
            "command": "shutil.which('iverilog')"
        }

    # cocotb-test runs pytest by default, or just runs the simulator.
    # 'run' function runs the simulator and asserts success.
    # It prints to stdout. We want to capture it.
    # cocotb-test doesn't easily return stdout. It raises exception on failure.
    
    # We can wrap it in a try-except block.
    # And maybe capture stdout/stderr using contextlib.redirect_stdout?
    
    # Also, cocotb-test compiles in a 'sim_build' directory by default.
    
    try:
        # We need to ensure python_module is in python path
        # If python_module is "test_cocotb_design" and it is in "workspace",
        # we need to add "workspace" to PYTHONPATH.
        # The 'cwd' arg in run_cocotb usually implies where the test is.
        
        # Let's add cwd to PYTHONPATH
        env = os.environ.copy()
        env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")
        
        # Run cocotb-test
        # Note: run() might not support 'timeout' directly in all versions, 
        # but it supports 'kwargs' passed to simulator.
        
        print(f"Running cocotb-test for {toplevel}...")
        
        run(
            verilog_sources=verilog_files,
            toplevel=toplevel,
            module=python_module,
            simulator="icarus",
            python_search=[cwd], # Add cwd to python search path
            toplevel_lang="verilog",
            work_dir=os.path.join(cwd, "sim_build"),
            timescale="1ns/1ps",
            extra_env=env
        )
        
        return {
            "success": True,
            "stdout": "Cocotb test passed successfully.",
            "stderr": "",
            "command": "cocotb_test.simulator.run(...)"
        }
        
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Cocotb test failed: {str(e)}",
            "command": "cocotb_test.simulator.run(...)"
        }
