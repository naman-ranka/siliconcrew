import os
from langchain_core.tools import tool
from src.tools.run_linter import run_linter
from src.tools.run_simulation import run_simulation
from src.tools.run_synthesis import run_synthesis
from src.tools.get_ppa import get_ppa_metrics
from src.tools.read_waveform import read_waveform

# Helper to get workspace path
def get_workspace_path():
    """
    Returns the active workspace directory.
    Defaults to 'workspace/' relative to project root, 
    but can be overridden by RTL_WORKSPACE env var for isolated runs.
    """
    env_path = os.environ.get("RTL_WORKSPACE")
    if env_path:
        return os.path.abspath(env_path)
        
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

from src.tools.search_logs import search_logs

@tool
def synthesis_tool(design_file: str, top_module: str, clock_period_ns: float = 10.0,
                   utilization: int = 5, aspect_ratio: float = 1.0, core_margin: float = 2.0) -> str:
    """
    Runs logic synthesis using OpenROAD Flow Scripts (ORFS).
    Returns a rich summary including generated files and key metrics.
    Args:
        design_file: Name of the Verilog design file (e.g., 'design.v').
        top_module: Name of the top module to synthesize.
        clock_period_ns: Target clock period in nanoseconds (default: 10.0).
        utilization: Core utilization percentage (1-100). Higher = smaller area. Default: 5 (very safe).
        aspect_ratio: Core aspect ratio (Height/Width). 1.0 = Square. Default: 1.0.
        core_margin: Margin around core in microns. Default: 2.0.
    """
    workspace = get_workspace_path()
    abs_file = os.path.join(workspace, design_file)
    
    if not os.path.exists(abs_file):
        return f"Error: File {design_file} does not exist."
        
    result = run_synthesis([abs_file], top_module=top_module, clock_period_ns=clock_period_ns, 
                           utilization=utilization, aspect_ratio=aspect_ratio, core_margin=core_margin,
                           cwd=workspace)
    
    if result["success"]:
        # 1. Auto-Grep for Metrics
        area_info = search_logs("Chip area", workspace)
        wns_info = search_logs("WNS", workspace)
        if "No matches" in wns_info: wns_info = search_logs("slack", workspace)
        
        # 2. List Generated Files (GDS, Reports)
        results_dir = os.path.join(workspace, "orfs_results", "sky130hd", top_module, "base")
        files_summary = ""
        if os.path.exists(results_dir):
            files = [f for f in os.listdir(results_dir) if f.endswith(('.gds', '.v', '.rpt'))]
            files_summary = ", ".join(files[:5]) # List first 5 relevant files
            
        return f"""Synthesis Command Successful! ✅
        
🔍 Quick PPA Scan:
{area_info.splitlines()[0] if "File:" in area_info else "Area: Not found"}
{wns_info.splitlines()[0] if "File:" in wns_info else "Timing: Not found"}

📂 Output Files (in orfs_results):
{files_summary} ...

(Use 'ppa_tool' for full detailed metrics)"""
    else:
        return f"Synthesis Command Finished. Output:\n{result['stderr'][-1000:]}"

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

@tool
def search_logs_tool(query: str) -> str:
    """
    Searches for a keyword in all OpenROAD logs and reports.
    Useful for finding specific errors, warnings, or metrics (e.g. "slack", "error", "area").
    Args:
        query: The string to search for.
    """
    workspace = get_workspace_path()
    return search_logs(query, workspace)

from src.tools.edit_file import replace_in_file

@tool
def edit_file_tool(filename: str, target_text: str, replacement_text: str) -> str:
    """
    Surgically replaces a block of text in a file.
    Use this for small fixes (e.g. changing a parameter, fixing a typo) to avoid rewriting the whole file.
    Args:
        filename: Name of the file (e.g., 'design.v').
        target_text: The EXACT text block to find and replace (must match whitespace).
        replacement_text: The new text to insert.
    """
    workspace = get_workspace_path()
    abs_file = os.path.join(workspace, filename)
    
    result = replace_in_file(abs_file, target_text, replacement_text)
    
    if result["success"]:
        return f"Success: {result['message']}\nDiff:\n{result.get('diff', '')}"
    else:
        return f"Error: {result['message']}"

from src.tools.generate_schematic import generate_schematic

@tool
def schematic_tool(verilog_file: str, top_module: str) -> str:
    """
    Generates a visual schematic (SVG) from a Verilog file.
    Args:
        verilog_file: Name of the Verilog file (e.g., 'design.v').
        top_module: Name of the top-level module.
    """
    workspace = get_workspace_path()
    abs_file = os.path.join(workspace, verilog_file)
    
    if not os.path.exists(abs_file):
        return f"Error: File {verilog_file} does not exist."
        
    result = generate_schematic(abs_file, top_module, cwd=workspace)
    
    if result["success"]:
        return f"Schematic generated successfully! 🎨\nSVG Path: {result['svg_path']}\n(The user can see this in the 'Schematic' tab)"
    else:
        return f"Failed to generate schematic: {result['error']}"

# List of tools to bind to the agent
architect_tools = [
    write_file,
    read_file,
    edit_file_tool,
    linter_tool,
    simulation_tool,
    synthesis_tool,
    ppa_tool,
    waveform_tool,
    schematic_tool,
    search_logs_tool
]
