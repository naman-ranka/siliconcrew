import subprocess
import os
import shutil

def run_linter(verilog_files, cwd=None):
    """
    Runs a syntax check on Verilog files using Icarus Verilog (-t null).
    
    Args:
        verilog_files (list): List of paths to .v files.
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

    # Construct command: iverilog -t null -g2012 <files>
    # -t null: Specify the null target (no code generation, just check)
    # -g2012: Enable SystemVerilog 2012 support (common for modern designs)
    lint_cmd = ["iverilog", "-t", "null", "-g2012"] + verilog_files
    
    try:
        proc = subprocess.run(
            lint_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )
        
        # iverilog returns 0 on success (no syntax errors)
        # Errors usually go to stderr
        
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": " ".join(lint_cmd)
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution Error during linting: {str(e)}",
            "command": " ".join(lint_cmd)
        }
