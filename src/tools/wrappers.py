import os
import json
import time
from typing import Any
from langchain_core.tools import tool
from src.tools.run_linter import run_linter
from src.tools.run_simulation import run_simulation
from src.tools.read_waveform import read_waveform
from src.tools.run_cocotb import run_cocotb
from src.tools.run_sby import run_sby
from src.tools.synthesis_manager import (
    start_synthesis_job,
    get_synthesis_job_status,
    get_synthesis_metrics as collect_synthesis_metrics,
)
from src.tools.file_patch import apply_unified_patch

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


def _normalize_verilog_files_arg(verilog_files: list[str] | str) -> list[str]:
    """
    Normalize verilog_files argument from tool-calling models.
    Accepts list[str], single filename str, or JSON-stringified list.
    """
    if isinstance(verilog_files, list):
        return [str(x) for x in verilog_files]

    if not isinstance(verilog_files, str):
        return [str(verilog_files)]

    raw = verilog_files.strip()
    if not raw:
        return []

    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass

    return [raw]

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
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
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
        
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

@tool
def linter_tool(verilog_files: list[str] | str) -> str:
    """
    Checks syntax using iverilog. Supports single-file or multi-file linting.
    Args:
        verilog_files: Filename string or list of filenames (e.g., 'design.v' or ['design.v','tb.v']).
        When linting a testbench, include all dependent RTL files in the same call
        (for example ['seq_detector.v', 'seq_detector_tb.v']) so module references resolve.
    """
    workspace = get_workspace_path()
    verilog_files = _normalize_verilog_files_arg(verilog_files)

    filepaths = []
    for item in verilog_files:
        fp = item if os.path.isabs(item) else os.path.join(workspace, item)
        if not os.path.exists(fp):
            return f"Error: File {item} does not exist."
        filepaths.append(fp)

    result = run_linter(filepaths, cwd=workspace)
    
    if result["success"]:
        return "Syntax OK."
    else:
        return f"Syntax Error:\n{result['stderr']}"

@tool
def simulation_tool(
    verilog_files: list[str],
    top_module: str,
    mode: str = "rtl",
    run_id: str = None,
    netlist_file: str = None,
    platform: str = None,
    sim_profile: str = "auto",
    pass_marker: str = "TEST PASSED",
) -> str:
    """
    Runs RTL or post-synthesis simulation with strict status contracts.
    Args:
        verilog_files: List of filenames to compile (usually includes testbench).
        top_module: Name of the top-level module in the testbench.
        mode: 'rtl' or 'post_synth'.
        run_id: Optional synthesis run ID for post-synth mode.
        netlist_file: Optional explicit netlist path.
        platform: Optional platform override for post-synth mode.
        sim_profile: 'auto' (default), 'pinned', or 'compat'. Auto selects 'compat' for ASAP7 post-synth.
        pass_marker: Explicit pass marker required for test_passed status.
    """
    workspace = get_workspace_path()
    verilog_files = _normalize_verilog_files_arg(verilog_files)
    abs_files = []
    for f in verilog_files or []:
        abs_files.append(f if os.path.isabs(f) else os.path.join(workspace, f))

    for f in abs_files:
        if not os.path.exists(f):
            return f"Error: File {f} does not exist."

    abs_netlist = None
    if netlist_file:
        abs_netlist = netlist_file if os.path.isabs(netlist_file) else os.path.join(workspace, netlist_file)

    result = run_simulation(
        verilog_files=abs_files,
        top_module=top_module,
        cwd=workspace,
        mode=mode,
        run_id=run_id,
        netlist_file=abs_netlist,
        platform=platform,
        sim_profile=sim_profile,
        pass_marker=pass_marker,
    )
    return json.dumps(result, indent=2)

from src.tools.search_logs import search_logs

@tool
def start_synthesis(
    verilog_files: list[str],
    top_module: str,
    platform: str = "sky130hd",
    clock_period_ns: float = 10.0,
    utilization: int = 5,
    aspect_ratio: float = 1.0,
    core_margin: float = 2.0,
    run_equiv: bool = False,
    constraints_mode: str = "auto",
) -> str:
    """
    Starts synthesis asynchronously and returns quickly with job_id and run_id.
    """
    workspace = get_workspace_path()
    verilog_files = _normalize_verilog_files_arg(verilog_files)

    abs_files = []
    for f in verilog_files:
        abs_f = f if os.path.isabs(f) else os.path.join(workspace, f)
        if not os.path.exists(abs_f):
            return f"Error: File {f} does not exist."
        abs_files.append(abs_f)

    result = start_synthesis_job(
        workspace=workspace,
        verilog_files=abs_files,
        top_module=top_module,
        platform=platform,
        clock_period_ns=clock_period_ns,
        utilization=utilization,
        aspect_ratio=aspect_ratio,
        core_margin=core_margin,
        run_equiv=run_equiv,
        constraints_mode=constraints_mode,
    )
    return json.dumps(result, indent=2)

@tool
def get_synthesis_job(job_id: str) -> str:
    """
    Gets synthesis job status including stage, auto-check summaries, and best-effort metrics.
    """
    workspace = get_workspace_path()
    result = get_synthesis_job_status(job_id, workspace=workspace)
    return json.dumps(result, indent=2)


def _wait_for_synthesis_job(
    workspace: str,
    job_id: str,
    max_wait_sec: int,
    poll_interval_sec: int,
) -> dict[str, Any]:
    start = time.time()
    max_wait = max(1, int(max_wait_sec))
    poll_interval = max(1, int(poll_interval_sec))
    last = None

    while (time.time() - start) < max_wait:
        status = get_synthesis_job_status(job_id, workspace=workspace)
        last = status
        if status.get("status") in {"completed", "failed"}:
            status["waited_sec"] = round(time.time() - start, 2)
            status["timed_out"] = False
            return status

        suggested = status.get("retry_after_sec")
        if suggested is None:
            suggested = status.get("poll_after_sec", poll_interval)
        sleep_s = max(1, int(round(float(suggested))))
        remaining = max_wait - (time.time() - start)
        if remaining <= 0:
            break
        time.sleep(min(sleep_s, max(1, int(remaining))))

    # timeout path returns latest known status with explicit timeout flag
    if last is None:
        last = {"job_id": job_id, "status": "running"}
    last["waited_sec"] = round(time.time() - start, 2)
    last["timed_out"] = True
    last["next_action"] = "Call wait_for_synthesis again or poll with get_synthesis_job."
    return last


@tool
def wait_for_synthesis(job_id: str, max_wait_sec: int = 30, poll_interval_sec: int = 2) -> str:
    """
    MCP-safe bounded wait for synthesis completion.
    Internally polls synthesis for up to max_wait_sec, then returns either terminal or running status.
    Args:
        job_id: Synthesis job id from start_synthesis.
        max_wait_sec: Max seconds to block in this call (default 30).
        poll_interval_sec: Fallback poll interval when guidance is absent.
    """
    workspace = get_workspace_path()
    result = _wait_for_synthesis_job(workspace, job_id, max_wait_sec, poll_interval_sec)
    return json.dumps(result, indent=2)


@tool
def run_synthesis_and_wait(
    verilog_files: list[str],
    top_module: str,
    platform: str = "sky130hd",
    clock_period_ns: float = 10.0,
    utilization: int = 5,
    aspect_ratio: float = 1.0,
    core_margin: float = 2.0,
    run_equiv: bool = False,
    constraints_mode: str = "auto",
    max_wait_sec: int = 300,
    poll_interval_sec: int = 2,
) -> str:
    """
    Starts synthesis and waits (bounded) for completion.
    Intended for non-MCP agent flows to reduce poll/sleep turn overhead.
    """
    started_json = start_synthesis.invoke(
        {
            "verilog_files": verilog_files,
            "top_module": top_module,
            "platform": platform,
            "clock_period_ns": clock_period_ns,
            "utilization": utilization,
            "aspect_ratio": aspect_ratio,
            "core_margin": core_margin,
            "run_equiv": run_equiv,
            "constraints_mode": constraints_mode,
        }
    )

    try:
        started = json.loads(started_json)
    except Exception:
        return started_json
    if "job_id" not in started:
        return started_json

    workspace = get_workspace_path()
    waited = _wait_for_synthesis_job(workspace, started["job_id"], max_wait_sec, poll_interval_sec)
    return json.dumps({"start": started, "result": waited}, indent=2)

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
def search_logs_tool(query: str, run_id: str = None) -> str:
    """
    Searches for a keyword in OpenROAD logs and reports.
    Useful for finding specific errors, warnings, or metrics (e.g. "slack", "error", "area").
    Args:
        query: The string to search for.
        run_id: Optional run ID for deterministic lookup.
    """
    workspace = get_workspace_path()
    return search_logs(query, workspace, run_id=run_id)


@tool
def get_synthesis_metrics(run_id: str = None) -> str:
    """
    Returns structured synthesis metrics for a run.
    Parses standard ORFS outputs (6_finish.rpt + synth_stat.txt) and returns JSON.
    """
    workspace = get_workspace_path()
    result = collect_synthesis_metrics(workspace=workspace, run_id=run_id)
    return json.dumps(result, indent=2)


from src.tools.edit_file import replace_in_file

@tool
def apply_patch_tool(unified_diff: str) -> str:
    """
    Applies a unified-diff patch inside the active workspace.
    Prefer this for robust code edits over exact-text replacement.
    """
    workspace = get_workspace_path()
    result = apply_unified_patch(workspace=workspace, unified_diff=unified_diff)
    return json.dumps(result, indent=2)


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
from src.tools.design_report import generate_design_report, save_design_report, save_metrics
from src.tools.spec_manager import (
    DesignSpec, PortSpec, parse_yaml_spec, validate_spec, 
    spec_to_prompt, save_yaml_file, load_yaml_file, create_spec_from_dict
)

@tool
def write_spec(
    module_name: str,
    description: str,
    ports: list[dict],
    clock_period_ns: float = 10.0,
    tech_node: str = "SkyWater 130HD",
    parameters: dict = None,
    module_signature: str = "",
    behavioral_description: str = ""
) -> str:
    """
    Creates a YAML design specification file. Call this FIRST before writing any RTL.
    The spec defines the module interface and requirements that the RTL must follow.
    
    Args:
        module_name: Name of the Verilog module (e.g., 'counter_8bit')
        description: What the module does (e.g., '8-bit synchronous counter with enable')
        ports: List of port definitions, each with keys: name, direction ('input'/'output'), 
               optional: type ('logic'), width (int), description (str)
               Example: [{"name": "clk", "direction": "input"}, 
                        {"name": "count", "direction": "output", "width": 8}]
        clock_period_ns: Target clock period in nanoseconds (default: 10.0)
        tech_node: Target technology node (default: 'SkyWater 130HD')
        parameters: Optional dict of Verilog parameters (e.g., {"WIDTH": 8, "DEPTH": 16})
        module_signature: Optional exact Verilog module signature to enforce
        behavioral_description: Optional detailed behavioral requirements
        
    Returns:
        Confirmation message with the spec filename
    """
    workspace = get_workspace_path()
    if not os.path.exists(workspace):
        os.makedirs(workspace)
    
    # Create DesignSpec from arguments
    spec = create_spec_from_dict({
        "module_name": module_name,
        "description": description,
        "ports": ports,
        "clock_period_ns": clock_period_ns,
        "tech_node": tech_node,
        "parameters": parameters or {},
        "module_signature": module_signature,
        "behavioral_description": behavioral_description
    })
    
    # Validate
    validation = validate_spec(spec)
    if not validation["valid"]:
        return f"Spec validation failed:\n" + "\n".join(validation["errors"])
    
    # Generate module signature if not provided
    if not spec.module_signature:
        spec.module_signature = spec.generate_module_signature()
    
    # Save to file
    spec_filename = f"{module_name}_spec.yaml"
    spec_filepath = os.path.join(workspace, spec_filename)
    save_yaml_file(spec, spec_filepath)
    
    # Also generate SDC
    sdc_content = spec.generate_sdc()
    sdc_filepath = os.path.join(workspace, "constraints.sdc")
    with open(sdc_filepath, "w") as f:
        f.write(sdc_content)
    
    warnings_str = ""
    if validation["warnings"]:
        warnings_str = "\nWarnings:\n" + "\n".join(f"  - {w}" for w in validation["warnings"])
    
    return f"""Spec created successfully! ✅

**File**: {spec_filename}
**Module**: {module_name}
**Clock Period**: {clock_period_ns}ns
**Ports**: {len(ports)}
**SDC Generated**: constraints.sdc
{warnings_str}

The user can now review the spec in the **Spec tab**. 
Once confirmed, proceed to write the RTL following this specification exactly."""


@tool
def read_spec(spec_filename: str = None) -> str:
    """
    Reads a design specification from a YAML file.
    Use this to understand requirements before writing RTL.
    
    Args:
        spec_filename: Name of the spec file (e.g., 'counter_spec.yaml'). 
                      If not provided, reads the most recent *_spec.yaml file.
    
    Returns:
        The spec contents formatted for RTL implementation
    """
    workspace = get_workspace_path()
    
    if spec_filename:
        spec_path = os.path.join(workspace, spec_filename)
    else:
        # Find most recent spec file
        spec_files = [f for f in os.listdir(workspace) if f.endswith("_spec.yaml")]
        if not spec_files:
            return "Error: No spec files found in workspace. Create one first with write_spec."
        spec_files.sort(key=lambda x: os.path.getmtime(os.path.join(workspace, x)), reverse=True)
        spec_path = os.path.join(workspace, spec_files[0])
        spec_filename = spec_files[0]
    
    if not os.path.exists(spec_path):
        return f"Error: Spec file {spec_filename} not found."
    
    try:
        spec = load_yaml_file(spec_path)
        prompt = spec_to_prompt(spec)
        
        return f"""**Design Specification: {spec.module_name}**

{prompt}

---
Use this specification to write the RTL. The module signature MUST match exactly."""
    except Exception as e:
        return f"Error parsing spec file: {str(e)}"


@tool
def load_yaml_spec_file(yaml_path: str) -> str:
    """
    Loads an external YAML specification file (e.g., from hackathon problems).
    Copies it to workspace and returns the parsed spec.
    
    Args:
        yaml_path: Path to the YAML file (relative to workspace or absolute)
    
    Returns:
        Parsed specification ready for implementation
    """
    workspace = get_workspace_path()
    
    # Handle relative paths
    if not os.path.isabs(yaml_path):
        # Try workspace first
        check_path = os.path.join(workspace, yaml_path)
        if not os.path.exists(check_path):
            # Try project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            check_path = os.path.join(project_root, yaml_path)
        yaml_path = check_path
    
    if not os.path.exists(yaml_path):
        return f"Error: YAML file not found at {yaml_path}"
    
    try:
        spec = load_yaml_file(yaml_path)
        
        # Copy to workspace as the active spec
        spec_filename = f"{spec.module_name}_spec.yaml"
        spec_filepath = os.path.join(workspace, spec_filename)
        save_yaml_file(spec, spec_filepath)
        
        # Generate SDC
        sdc_content = spec.generate_sdc()
        sdc_filepath = os.path.join(workspace, "constraints.sdc")
        with open(sdc_filepath, "w") as f:
            f.write(sdc_content)
        
        prompt = spec_to_prompt(spec)
        
        return f"""**Loaded External Spec: {spec.module_name}**

{prompt}

---
Spec saved to: {spec_filename}
SDC generated: constraints.sdc

Proceed to implement the RTL following this specification."""
    except Exception as e:
        return f"Error loading YAML spec: {str(e)}"


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

@tool
def save_metrics_tool(
    area_um2: float = None,
    cell_count: int = None,
    wns_ns: float = None,
    tns_ns: float = None,
    power_uw: float = None
) -> str:
    """
    Saves PPA metrics that you found (e.g., via search_logs_tool) for the design report.
    Use this when ppa_tool fails but you found metrics manually through log searching.
    
    Args:
        area_um2: Chip area in square micrometers (e.g., 142.5)
        cell_count: Number of standard cells (e.g., 48)
        wns_ns: Worst Negative Slack in nanoseconds (e.g., 0.85 or -0.12)
        tns_ns: Total Negative Slack in nanoseconds (e.g., 0.0 or -1.5)
        power_uw: Total power in microwatts (e.g., 12.34)
        
    Returns:
        Confirmation of saved metrics
    """
    workspace = get_workspace_path()
    
    metrics = {}
    if area_um2 is not None:
        metrics["area_um2"] = area_um2
    if cell_count is not None:
        metrics["cell_count"] = cell_count
    if wns_ns is not None:
        metrics["wns_ns"] = wns_ns
    if tns_ns is not None:
        metrics["tns_ns"] = tns_ns
    if power_uw is not None:
        metrics["power_uw"] = power_uw
    
    if not metrics:
        return "Error: No metrics provided. Please specify at least one metric."
    
    try:
        save_metrics(workspace, metrics)
        
        saved_str = ", ".join([f"{k}={v}" for k, v in metrics.items()])
        return f"""Metrics saved successfully! 📊

**Saved**: {saved_str}

These will be included in the design report when you call `generate_report_tool`."""
    except Exception as e:
        return f"Error saving metrics: {str(e)}"


@tool
def generate_report_tool() -> str:
    """
    Generates a comprehensive design report comparing the specification vs actual results.
    Call this at the end of a design session to summarize verification and synthesis outcomes.
    
    Note: If ppa_tool failed but you found metrics via search_logs_tool, use save_metrics_tool 
    first to persist those values, then call this.
    
    Returns:
        The generated report content and the path where it was saved
    """
    workspace = get_workspace_path()
    
    if not os.path.exists(workspace):
        return "Error: Workspace does not exist."
    
    try:
        report_path = save_design_report(workspace)
        report_content = generate_design_report(workspace)
        
        return f"""Design Report Generated! 📊

**Saved to**: {os.path.basename(report_path)}

{report_content}"""
    except Exception as e:
        return f"Error generating report: {str(e)}"


@tool
def cocotb_tool(verilog_files: list[str], top_module: str, python_module: str) -> str:
    """
    Runs a constrained random verification test using Cocotb (Python).
    Use this ONLY when the user explicitly asks for "Cocotb", "Python testbench", or "Randomized testing".
    Args:
        verilog_files: List of Verilog source files.
        top_module: Name of the top-level Verilog module.
        python_module: Name of the Python test file (without .py extension).
    """
    workspace = get_workspace_path()
    
    # Ensure all files exist
    abs_files = [os.path.join(workspace, f) for f in verilog_files]
    for f in abs_files:
        if not os.path.exists(f):
             return f"Error: File {f} does not exist."
             
    result = run_cocotb(abs_files, top_module, python_module, cwd=workspace)
    
    if result["success"]:
        return "Cocotb Test PASSED. ✅"
    else:
        return f"Cocotb Test FAILED. ❌\nError: {result['stderr']}"

@tool
def sby_tool(sby_file: str) -> str:
    """
    Runs Formal Verification using SymbiYosys (SBY).
    Use this ONLY when the user explicitly asks for "Formal Verification", "SBY", or "Proofs".
    Args:
        sby_file: Name of the .sby configuration file (e.g., 'fifo.sby').
    """
    workspace = get_workspace_path()
    abs_file = os.path.join(workspace, sby_file)
    
    if not os.path.exists(abs_file):
        return f"Error: File {sby_file} does not exist."
        
    result = run_sby(abs_file, cwd=workspace)
    
    status_icon = "❓"
    if result["status"] == "PASS": status_icon = "✅"
    elif result["status"] == "FAIL": status_icon = "❌"
    elif result["status"] == "ERROR": status_icon = "⚠️"
    
    return f"SBY Run Finished. Status: {result['status']} {status_icon}\nOutput:\n{result['stdout'][-500:]}"

@tool
def list_files_tool() -> str:
    """
    Lists all files in the current workspace.
    Use this to explore the project structure or verify generated files.
    """
    workspace = get_workspace_path()
    if not os.path.exists(workspace):
        return "Workspace directory does not exist."
        
    files = []
    for root, dirs, filenames in os.walk(workspace):
        for f in filenames:
            rel_path = os.path.relpath(os.path.join(root, f), workspace)
            files.append(rel_path)
            
    if not files:
        return "Workspace is empty."
        
    return "Files in workspace:\n" + "\n".join(sorted(files))

@tool
def sleep_tool(seconds: int) -> str:
    """
    Blocks briefly before the next action.
    Use this to honor synthesis polling guidance from get_synthesis_job.
    Args:
        seconds: Requested sleep time (clamped to 1..30 seconds).
    """
    wait_s = max(1, min(int(seconds), 30))
    time.sleep(wait_s)
    return f"Slept for {wait_s} second(s)."

# Tools exposed over MCP (no blocking wait tool).
mcp_tools = [
    # Specification tools (use FIRST)
    write_spec,
    read_spec,
    load_yaml_spec_file,
    # File management
    write_file,
    read_file,
    apply_patch_tool,
    edit_file_tool,
    list_files_tool,
    # Verification tools
    linter_tool,
    simulation_tool,
    waveform_tool,
    cocotb_tool,
    sby_tool,
    # Synthesis & Analysis
    start_synthesis,
    get_synthesis_job,
    wait_for_synthesis,
    get_synthesis_metrics,
    search_logs_tool,
    schematic_tool,
    # Reporting & Metrics
    save_metrics_tool,
    generate_report_tool,
]

# Tools bound to the in-process architect agent.
architect_tools = [*mcp_tools, run_synthesis_and_wait, sleep_tool]
