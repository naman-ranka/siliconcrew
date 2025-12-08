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
    
    import contextlib
    import io
    
    # Capture stdout/stderr to find compilation errors
    out_capture = io.StringIO()
    err_capture = io.StringIO()
    
    # Helper to sanitize output for Windows consoles
    def safe_output(s):
        try:
            # Try to encode/decode with current stdout encoding to filter bad chars
            encoding = sys.stdout.encoding or 'utf-8'
            return s.encode(encoding, errors='replace').decode(encoding)
        except:
            return s.encode('ascii', errors='replace').decode('ascii')
            
    try:
        # We need to ensure python_module is in python path
        # If python_module is "test_cocotb_design" and it is in "workspace",
        # we need to add "workspace" to PYTHONPATH.
        env = os.environ.copy()
        env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8" # Force UTF-8 for subprocess
        
        print(f"Running cocotb-test for {toplevel}...")
        
        with contextlib.redirect_stdout(out_capture), contextlib.redirect_stderr(err_capture):
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
            
        full_stdout = out_capture.getvalue() or "Cocotb test passed successfully."
        full_stderr = err_capture.getvalue()
        
        return {
            "success": True,
            "stdout": safe_output(full_stdout),
            "stderr": safe_output(full_stderr),
            "command": "cocotb_test.simulator.run(...)"
        }
        
    except BaseException as e: # Catch SystemExit (raised by pytest) and others
        return {
            "success": False,
            "stdout": safe_output(out_capture.getvalue()),
            "stderr": f"Cocotb test failed: {str(e)}\nCaptured Stderr: {safe_output(err_capture.getvalue())}\nCaptured Stdout: {safe_output(out_capture.getvalue())}",
            "command": "cocotb_test.simulator.run(...)"
        }
