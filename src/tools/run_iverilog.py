import subprocess
import os
import shutil

def run_iverilog(verilog_files, output_executable="simulation.out", cwd=None):
    """
    Compiles and runs Verilog files using Icarus Verilog.
    
    Args:
        verilog_files (list): List of paths to .v files.
        output_executable (str): Name of the compiled binary.
        cwd (str): Working directory for execution.
        
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
        
    # Check if iverilog is installed
    if not shutil.which("iverilog"):
        return {
            "success": False,
            "stdout": "",
            "stderr": "Error: 'iverilog' executable not found in PATH.",
            "command": "shutil.which('iverilog')"
        }

    # 1. Compile
    compile_cmd = ["iverilog", "-g2012", "-o", output_executable] + verilog_files
    try:
        compile_proc = subprocess.run(
            compile_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )
        if compile_proc.returncode != 0:
            return {
                "success": False,
                "stdout": compile_proc.stdout,
                "stderr": f"Compilation Failed:\n{compile_proc.stderr}",
                "command": " ".join(compile_cmd)
            }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution Error during compilation: {str(e)}",
            "command": " ".join(compile_cmd)
        }

    # 2. Run Simulation (vvp)
    run_cmd = ["vvp", output_executable]
    try:
        run_proc = subprocess.run(
            run_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )
        return {
            "success": run_proc.returncode == 0,
            "stdout": run_proc.stdout,
            "stderr": run_proc.stderr,
            "command": " ".join(run_cmd)
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution Error during simulation: {str(e)}",
            "command": " ".join(run_cmd)
        }
