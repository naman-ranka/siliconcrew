import os
import sys
from .run_docker import run_docker_command

def run_sby(sby_file, cwd=None, timeout=300):
    """
    Runs SymbiYosys (SBY) formal verification using Docker.
    
    Args:
        sby_file (str): Path to the .sby file.
        cwd (str): Working directory (should contain the .sby file and sources).
        timeout (int): Timeout in seconds.
        
    Returns:
        dict: {
            "success": bool,
            "stdout": str,
            "stderr": str,
            "status": "PASS" | "FAIL" | "ERROR" | "UNKNOWN",
            "counter_example": str (path to trace if FAIL)
        }
    """
    # Resolve workspace path (Standard pattern from run_synthesis.py)
    # We assume the file is inside the 'workspace' directory.
    # run_docker_command defaults to mounting ../../workspace to /workspace
    
    # Find the 'workspace' directory
    # Heuristic: Look for 'workspace' in the path of the sby_file
    abs_sby_path = os.path.abspath(sby_file)
    if "workspace" in abs_sby_path.split(os.sep):
        # Split path at 'workspace'
        # e.g. C:\Users\...\workspace\test3\async_fifo.sby
        # workspace_root = C:\Users\...\workspace
        # rel_path = test3\async_fifo.sby
        
        parts = abs_sby_path.split(os.sep)
        idx = parts.index("workspace")
        workspace_root = os.sep.join(parts[:idx+1])
        rel_path = os.sep.join(parts[idx+1:])
    else:
        # Fallback: Assume standard project structure
        workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../workspace"))
        try:
            rel_path = os.path.relpath(abs_sby_path, workspace_root)
        except ValueError:
             return {
                "success": False,
                "stdout": "",
                "stderr": f"Error: SBY file {sby_file} must be inside the workspace directory {workspace_root}",
                "status": "ERROR",
                "counter_example": None
            }

    sby_dir = os.path.dirname(rel_path).replace("\\", "/")
    sby_filename = os.path.basename(rel_path)
    
    # Construct command
    # cd /workspace/<rel_dir> && sby -f <file>
    if sby_dir:
        cmd = f"cd /workspace/{sby_dir} && sby -f {sby_filename}"
    else:
        cmd = f"cd /workspace && sby -f {sby_filename}"
    
    print(f"Running SBY: {cmd}")
    
    # Run via Docker
    result = run_docker_command(
        command=cmd,
        workspace_path=workspace_root, # Explicitly pass the workspace root we found
        cwd="/workspace", 
        timeout=timeout
    )
    
    # Parse output
    response = {
        "success": result["success"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "status": "UNKNOWN",
        "counter_example": None
    }
    
    if result["success"]:
        if "DONE (PASS" in result["stdout"]:
            response["status"] = "PASS"
        elif "DONE (FAIL" in result["stdout"]:
            response["status"] = "FAIL"
            # Try to find counter example trace
            # Usually in <sby_name>/engine_*/trace.vcd
            pass
        else:
            response["status"] = "UNKNOWN"
    else:
        if "DONE (FAIL" in result["stdout"]:
            response["status"] = "FAIL"
        else:
            response["status"] = "ERROR"
            
    return response
