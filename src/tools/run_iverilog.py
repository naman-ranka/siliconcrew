import subprocess
import os
import shutil

def run_iverilog(verilog_files, output_executable="simulation.out", cwd=None, timeout=60):
    """
    Compiles and runs Verilog files using Icarus Verilog.
    
    Args:
        verilog_files (list): List of paths to .v files.
        output_executable (str): Name of the compiled binary.
        cwd (str): Working directory for execution.
        timeout (int): Timeout in seconds for each step (compile and run).
        
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
    proc = None
    try:
        proc = subprocess.Popen(
            compile_cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        
        if proc.returncode != 0:
            return {
                "success": False,
                "stdout": stdout,
                "stderr": f"Compilation Failed:\n{stderr}",
                "command": " ".join(compile_cmd)
            }
    except subprocess.TimeoutExpired:
        if proc: proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": "Error: Compilation timed out.",
            "command": " ".join(compile_cmd)
        }
    except Exception as e:
        if proc: proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution Error during compilation: {str(e)}",
            "command": " ".join(compile_cmd)
        }
    finally:
        if proc and proc.poll() is None:
            proc.kill()

    # 2. Run Simulation (vvp)
    run_cmd = ["vvp", output_executable]
    proc = None
    try:
        proc = subprocess.Popen(
            run_cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        
        return {
            "success": proc.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "command": " ".join(run_cmd)
        }
    except subprocess.TimeoutExpired:
        if proc: proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": "Error: Simulation timed out (possible infinite loop).",
            "command": " ".join(run_cmd)
        }
    except Exception as e:
        if proc: proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution Error during simulation: {str(e)}",
            "command": " ".join(run_cmd)
        }
    finally:
        if proc and proc.poll() is None:
            proc.kill()
