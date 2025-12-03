import os
import sys
from .run_docker import run_docker_command

def run_synthesis(verilog_files, top_module, platform="sky130hd", clock_period_ns=None, 
                  utilization=5, aspect_ratio=1, core_margin=2, cwd=None, timeout=600):
    """
    Runs Yosys synthesis using the OpenROAD Flow Scripts (ORFS) via Docker.
    
    Args:
        verilog_files (list): List of absolute paths to .v files.
        top_module (str): Name of the top-level module.
        platform (str): Target platform (default: sky130hd).
        clock_period_ns (float): Target clock period in nanoseconds (optional).
        utilization (int): Core utilization percentage (1-100, default: 5).
        aspect_ratio (float): Core aspect ratio H/W (default: 1).
        core_margin (float): Margin around core in microns (default: 2).
        cwd (str): Workspace directory (optional).
        timeout (int): Timeout in seconds (default 600).
        
    Returns:
        dict: {
            "success": bool,
            "stdout": str,
            "stderr": str,
            "metrics": dict (placeholder for now)
        }
    """
    if cwd is None:
        # Default to workspace dir relative to this file
        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../workspace'))
        
    if not os.path.exists(cwd):
        os.makedirs(cwd)

    # 1. Prepare Directories for ORFS outputs
    # We want to persist results, logs, and reports
    results_dir = os.path.join(cwd, "orfs_results")
    logs_dir = os.path.join(cwd, "orfs_logs")
    reports_dir = os.path.join(cwd, "orfs_reports")
    
    for d in [results_dir, logs_dir, reports_dir]:
        if not os.path.exists(d):
            os.makedirs(d)
            
    # 2. Generate config.mk
    # We need to map the local file paths to /workspace paths for the config
    # Assuming verilog_files are inside the workspace or accessible via /workspace mount
    
    # Convert local paths to container paths
    # If file is C:/Users/.../workspace/design.v, container path is /workspace/design.v
    container_verilog_files = []
    for f in verilog_files:
        # Simple heuristic: replace local workspace path with /workspace
        # This assumes files are IN the workspace.
        if cwd in os.path.abspath(f):
            rel_path = os.path.relpath(f, cwd).replace("\\", "/")
            container_verilog_files.append(f"/workspace/{rel_path}")
        else:
            # If file is outside workspace, we might have an issue unless we mount it.
            # For now, assume strict workspace usage.
            print(f"Warning: File {f} is not in workspace {cwd}. It may not be visible to Docker.")
            container_verilog_files.append(f"/workspace/{os.path.basename(f)}")

    # Generate or Update SDC file
    sdc_file = os.path.join(cwd, "constraints.sdc")
    
    # If clock_period is provided, we overwrite/create the SDC
    if clock_period_ns is not None:
        with open(sdc_file, "w") as f:
            f.write(f"create_clock -period {clock_period_ns} [get_ports clk]")
    # If not provided and file doesn't exist, create default
    elif not os.path.exists(sdc_file):
        with open(sdc_file, "w") as f:
            f.write(f"create_clock -period 10 [get_ports clk]")
            
    config_content = f"""
export DESIGN_NAME = {top_module}
export PLATFORM = {platform}
export VERILOG_FILES = {" ".join(container_verilog_files)}
export SDC_FILE = /workspace/constraints.sdc
export CORE_UTILIZATION = {utilization}
export CORE_ASPECT_RATIO = {aspect_ratio}
export CORE_MARGIN = {core_margin}
"""
    
    config_file = os.path.join(cwd, "config.mk")
    with open(config_file, "w") as f:
        f.write(config_content)
        
    # 3. Construct Docker Command
    # We mount the local output dirs to the ORFS flow directories
    volumes = [
        f"{results_dir}:/OpenROAD-flow-scripts/flow/results",
        f"{logs_dir}:/OpenROAD-flow-scripts/flow/logs",
        f"{reports_dir}:/OpenROAD-flow-scripts/flow/reports"
    ]
    
    # Command: make DESIGN_CONFIG=/workspace/config.mk
    # We add 'touch' to ensure make realizes the config has changed
    # But for SDC changes to propagate, we often need to force a clean or at least touch the target
    # The most robust way for ORFS when config changes is to force a run.
    # We can use the -B flag (Always make) or just rely on the fact that we just wrote config.mk
    # However, make might not track config.mk as a dependency of the flow targets in ORFS.
    
    # BEST FIX: Run 'make clean_issue' (ORFS specific) or just nuke the results for this design if we suspect a change.
    # Simpler approach: Use -B to force execution.
    make_cmd = "make -B DESIGN_CONFIG=/workspace/config.mk"
    
    print(f"🚀 Starting Synthesis for {top_module}...")
    result = run_docker_command(
        command=make_cmd,
        workspace_path=cwd,
        volumes=volumes,
        timeout=timeout
    )
    
    return result
