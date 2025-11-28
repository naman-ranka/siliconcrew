import os
from langchain_core.tools import tool
from src.tools.run_linter import run_linter
from src.tools.run_simulation import run_simulation
from src.tools.run_synthesis import run_synthesis
from src.tools.get_ppa import get_ppa_metrics
from src.tools.read_waveform import read_waveform

# Helper to get workspace path
def get_workspace_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../../workspace'))

@tool
def write_file(filename: str, content: str) -> str:
    """
    Writes content to a file in the workspace.
    Args:
        filename: Name of the file (e.g., 'design.v', 'tb.v').
        content: The text content to write.
    """
    workspace = get_workspace_path()
    if not os.path.exists(workspace):
        os.makedirs(workspace)
    
    filepath = os.path.join(workspace, filename)
    with open(filepath, "w") as f:
        f.write(content)
    return f"Successfully wrote to {filename}"

@tool
def read_file(filename: str) -> str:
    """
    Reads content from a file in the workspace.
    Args:
        filename: Name of the file to read.
    """
    workspace = get_workspace_path()
    filepath = os.path.join(workspace, filename)
    
    if not os.path.exists(filepath):
        return f"Error: File {filename} does not exist."
        
    with open(filepath, "r") as f:
        return f.read()

@tool
def linter_tool(verilog_file: str) -> str:
    """
    Checks the syntax of a Verilog file using iverilog.
    Args:
        verilog_file: Name of the file to lint (e.g., 'design.v').
    """
    workspace = get_workspace_path()
    filepath = os.path.join(workspace, verilog_file)
    
    if not os.path.exists(filepath):
        return f"Error: File {verilog_file} does not exist."
        
    result = run_linter([filepath], cwd=workspace)
    
    if result["success"]:
        return "Syntax OK."
    else:
        return f"Syntax Error:\n{result['stderr']}"

@tool
def simulation_tool(verilog_files: list[str], top_module: str) -> str:
    """
    Runs a Verilog simulation.
    Args:
        verilog_files: List of filenames to compile (e.g., ['design.v', 'tb.v']).
        top_module: Name of the top-level module in the testbench (e.g., 'tb').
    """
    workspace = get_workspace_path()
    abs_files = [os.path.join(workspace, f) for f in verilog_files]
    
    # Check existence
    for f in abs_files:
        if not os.path.exists(f):
            return f"Error: File {f} does not exist."
            
    result = run_simulation(abs_files, top_module=top_module, cwd=workspace)
    
    if result["success"]:
        return "Simulation PASSED."
    else:
        return f"Simulation FAILED.\nStdout: {result['stdout']}\nStderr: {result['stderr']}"

@tool
def synthesis_tool(design_file: str, top_module: str) -> str:
    """
    Runs logic synthesis using OpenROAD Flow Scripts (ORFS).
    Args:
        design_file: Name of the Verilog design file (e.g., 'design.v').
        top_module: Name of the top module to synthesize.
    """
    workspace = get_workspace_path()
    abs_file = os.path.join(workspace, design_file)
    
    if not os.path.exists(abs_file):
        return f"Error: File {design_file} does not exist."
        
    result = run_synthesis([abs_file], top_module=top_module, cwd=workspace)
    
    if result["success"]:
        return "Synthesis Command Successful (Check PPA metrics for details)."
    else:
        # Check for partial success (netlist existence) as ORFS often fails later
        # We rely on the agent to check PPA next.
        return f"Synthesis Command Finished. Output:\n{result['stderr'][-500:]}" # Return last 500 chars of stderr

@tool
def ppa_tool() -> str:
    """
    Extracts PPA (Power, Performance, Area) metrics from the latest synthesis run.
    Returns a dictionary string of metrics.
    """
    workspace = get_workspace_path()
    logs_dir = os.path.join(workspace, "orfs_logs")
    
    metrics = get_ppa_metrics(logs_dir)
    return str(metrics)

@tool
def waveform_tool(vcd_file: str, signals: list[str], start_time: int = 0, end_time: int = 1000) -> str:
    """
    Reads a VCD waveform file to inspect signal values.
    Use this when simulation fails to understand WHY.
    Args:
        vcd_file: Name of the .vcd file (e.g., 'dump.vcd').
        signals: List of signal names to inspect (e.g., ['clk', 'rst', 'count']).
        start_time: Start time to view.
        end_time: End time to view.
    """
    workspace = get_workspace_path()
    abs_file = os.path.join(workspace, vcd_file)
    return read_waveform(abs_file, signals, start_time, end_time)

# List of tools to bind to the agent
architect_tools = [
    write_file,
    read_file,
    linter_tool,
    simulation_tool,
    synthesis_tool,
    ppa_tool,
    waveform_tool
]
