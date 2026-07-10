import os
import json
import time
from typing import Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from src.tools.run_linter import run_linter
from src.tools.run_simulation import run_simulation
from src.tools.read_waveform import read_waveform
from src.tools.run_cocotb import run_cocotb
from src.tools.run_sby import run_sby
from src.tools.synthesis_manager import (
    start_synthesis_job,
    retry_pd_job,
    get_synthesis_status as collect_synthesis_status,
    get_synthesis_metrics as collect_synthesis_metrics,
    read_stage_report as collect_stage_report,
    get_route_drc_summary as collect_route_drc_summary,
    get_cts_summary as collect_cts_summary,
    get_congestion_summary as collect_congestion_summary,
    compare_pd_runs as collect_pd_run_comparison,
)
from src.tools.file_patch import apply_unified_patch

# Workspace resolution lives in a dependency-light module (src.utils.workspace)
# so the tenancy seam and its concurrency gate test do not require this heavy
# tool/agent module. Re-exported here for backward compatibility — ~30 call
# sites in this file resolve the workspace via get_workspace_path().
from src.utils.workspace import get_workspace_path, resolve_in_workspace


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


class WriteFileArgs(BaseModel):
    filename: str = Field(
        description="Relative filename inside the active workspace, such as 'design.v' or 'dot_product_tb.v'."
    )
    content: str | None = Field(
        default=None,
        description=(
            "Complete file contents to write. Always include the full text of the file body, "
            "not just a summary or filename."
        ),
        json_schema_extra={
            "input_examples": [
                {
                    "filename": "hello.txt",
                    "content": "line 1\nline 2\n",
                }
            ]
        },
    )


@tool(args_schema=WriteFileArgs)
def write_file(filename: str, content: str | None = None) -> str:
    """
    Writes content to a file in the workspace.
    Args:
        filename: Name of the file (e.g., 'design.v', 'tb.v').
        content: The text content to write.
    """
    if content is None:
        return (
            "Error: Missing required argument 'content' for write_file. "
            "Retry the tool call with both 'filename' and the complete file text in 'content'."
        )

    # Route through the single shared write path so the agent and the human
    # editor's Save are one tracked mutation (and the manifest stays in sync).
    from src.tools.file_ops import write_file as _write_file
    workspace = get_workspace_path()
    try:
        resolve_in_workspace(filename, workspace=workspace)  # confine to workspace
        _write_file(workspace, filename, content)
    except ValueError as exc:
        return f"Error: {exc}"
    return f"Successfully wrote to {filename}"

@tool
def read_file(filename: str) -> str:
    """
    Reads content from a file in the workspace.
    Args:
        filename: Name of the file to read.
    """
    workspace = get_workspace_path()
    try:
        filepath = resolve_in_workspace(filename, workspace=workspace)
    except ValueError as exc:
        return f"Error: {exc}"

    if not os.path.exists(filepath):
        return f"Error: File {filename} does not exist."

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

@tool
def linter_tool(verilog_files: list[str] | str, engine: str = "auto") -> str:
    """
    Lints Verilog files. Supports single-file or multi-file linting.
    Args:
        verilog_files: Filename string or list of filenames (e.g., 'design.v' or ['design.v','tb.v']).
        When linting a testbench, include all dependent RTL files in the same call
        (for example ['seq_detector.v', 'seq_detector_tb.v']) so module references resolve.
        engine: 'auto' (verilator if installed, else iverilog), 'iverilog'
        (syntax/elaboration only), or 'verilator' (real lint: latches, width
        mismatches, unsynthesizable constructs — lint RTL only, not testbenches).
    """
    workspace = get_workspace_path()
    verilog_files = _normalize_verilog_files_arg(verilog_files)

    filepaths = []
    for item in verilog_files:
        fp = item if os.path.isabs(item) else os.path.join(workspace, item)
        if not os.path.exists(fp):
            return f"Error: File {item} does not exist."
        filepaths.append(fp)

    result = run_linter(filepaths, cwd=workspace, engine=engine)

    diags = result.get("diagnostics") or []
    warnings = [d for d in diags if d["severity"] == "warning"]
    errors = [d for d in diags if d["severity"] == "error"]

    def _fmt(d):
        loc = f"{d['file']}:{d['line']}" if d.get("file") else "(general)"
        code = f" [{d['code']}]" if d.get("code") else ""
        return f"{loc}: {d['severity']}{code}: {d['message']}"

    if result["success"] and not warnings:
        return f"Syntax OK. (engine: {result.get('engine')})"
    if result["success"]:
        lines = "\n".join(_fmt(d) for d in warnings)
        return f"Lint passed with {len(warnings)} warning(s) (engine: {result.get('engine')}):\n{lines}"
    lines = "\n".join(_fmt(d) for d in (errors + warnings)) or result["stderr"]
    return f"Lint FAILED — {len(errors)} error(s), {len(warnings)} warning(s) (engine: {result.get('engine')}):\n{lines}"

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
from src.tools import manifest as manifest_mod
from src.tools.sim_manager import run_sim_isolated


@tool
def get_manifest() -> str:
    """
    Returns the design manifest (files + roles + synthTop/simTop + clock + platform).
    The manifest is the single source of truth shared with the UI; auto-derived if absent.
    """
    workspace = get_workspace_path()
    m = manifest_mod.read_manifest(workspace)
    return json.dumps(m.model_dump(), indent=2)


@tool
def update_manifest(updates_json: str) -> str:
    """
    Upserts manifest fields. Pass a JSON object with any of:
    synthTop, simTop, clockPeriodNs, platform, or files: [{name, role}] to override roles.
    Roles: rtl | tb | sdc | include | other.
    """
    workspace = get_workspace_path()
    try:
        updates = json.loads(updates_json) if updates_json else {}
        if not isinstance(updates, dict):
            return "Error: updates_json must be a JSON object."
    except Exception as exc:
        return f"Error: invalid updates_json ({exc})."
    m = manifest_mod.write_manifest(workspace, updates)
    return json.dumps(m.model_dump(), indent=2)


@tool
def run_isolated_simulation(
    sim_top: str = "",
    mode: str = "rtl",
    run_id: str = None,
    sim_profile: str = "auto",
    pass_marker: str = "TEST PASSED",
) -> str:
    """
    Runs a manifest-driven simulation in an isolated sim_runs/sim_NNNN/ directory
    (its own VCD, persisted run record + provenance). Prefer this over simulation_tool
    so runs stay comparable and waveforms never collide.
    Args:
        sim_top: testbench top module; defaults to the manifest's simTop.
        mode: 'rtl' or 'post_synth'.
        run_id: optional synthesis run id for post_synth mode (resolves the netlist).
        sim_profile: 'auto' (default), 'pinned', or 'compat'.
        pass_marker: explicit pass marker required for a passing status.
    """
    workspace = get_workspace_path()
    m = manifest_mod.read_manifest(workspace)
    top = sim_top or m.simTop
    if not top:
        return "Error: no simTop in manifest and none provided. Set it with update_manifest."
    files = manifest_mod.files_for_stage(m, "simulate")
    if not files:
        return "Error: manifest has no rtl/tb files to simulate."
    result = run_sim_isolated(
        workspace=workspace,
        verilog_files=files,
        top_module=top,
        mode=mode,
        run_id=run_id,
        platform=m.platform,
        sim_profile=sim_profile,
        pass_marker=pass_marker,
    )
    return json.dumps(result, indent=2)


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
    max_stage: str = "finish",
) -> str:
    """
    Starts synthesis asynchronously and returns quickly with the run_id —
    the ONE durable handle for this run (poll it with get_synthesis_status).
    By default (max_stage="finish") this runs the FULL RTL->GDS ORFS flow.
    Set max_stage="synth" for a fast synthesis-only PPA estimate (area/cell
    count without place-and-route timing/power), or stop after any stage:
    constraints|synth|floorplan|place|cts|grt|route|finish. Stages after
    max_stage are recorded as "skipped". Continue a partial run toward GDS
    later with retry_pd starting from the next stage.
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
        max_stage=max_stage,
    )
    return json.dumps(result, indent=2)


@tool
def retry_pd(
    run_id: str,
    start_stage: str,
    max_stage: str = "finish",
    orfs_overrides_json: str = "",
    timeout_sec: int = 1200,
) -> str:
    """
    Creates a child PD retry run from an existing synthesis run.
    Validates the required checkpoint for start_stage, copies prerequisites into a new run,
    and reruns only the requested downstream ORFS do-* stages.
    """
    workspace = get_workspace_path()
    result = retry_pd_job(
        workspace=workspace,
        source_run_id=run_id,
        start_stage=start_stage,
        max_stage=max_stage,
        orfs_overrides_json=orfs_overrides_json,
        timeout=timeout_sec,
    )
    return json.dumps(result, indent=2)

@tool
def get_synthesis_status(run_id: str) -> str:
    """
    Full status for a synthesis run by its run_id: status, current stage,
    per-stage table + history, last log lines, artifacts found, best-effort
    metrics, and poll_after_sec guidance. Self-healing: a run whose worker
    died is reconciled from on-disk evidence (completed from artifacts, or
    failed once past its timeout ceiling) instead of reading "running" forever.
    """
    workspace = get_workspace_path()
    result = collect_synthesis_status(run_id, workspace=workspace)
    return json.dumps(result, indent=2)


# Bounded means bounded even for a creative caller (plan round-2 #6).
WAIT_MAX_WAIT_SEC = 120


def _wait_for_synthesis_job(
    workspace: str,
    run_id: str,
    max_wait_sec: int,
    poll_interval_sec: int,
) -> dict[str, Any]:
    start = time.time()
    max_wait = max(1, min(int(max_wait_sec), WAIT_MAX_WAIT_SEC))
    poll_interval = max(1, int(poll_interval_sec))

    while (time.time() - start) < max_wait:
        status = collect_synthesis_status(run_id, workspace=workspace)
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

    # One final sample after the wait loop: the run may have gone terminal
    # during the last sleep — report that, not a stale pre-sleep snapshot.
    last = collect_synthesis_status(run_id, workspace=workspace)
    last["waited_sec"] = round(time.time() - start, 2)
    if last.get("status") in {"completed", "failed"}:
        last["timed_out"] = False
        return last

    # timeout path returns latest known status with explicit timeout flag
    last["timed_out"] = True
    last["next_action"] = "Call wait_for_synthesis again or poll with get_synthesis_status."
    return last


@tool
def wait_for_synthesis(run_id: str, max_wait_sec: int = 30, poll_interval_sec: int = 2) -> str:
    """
    MCP-safe bounded wait for synthesis completion — the ONE blocking
    convenience, defined as a bounded poll loop over get_synthesis_status.
    Args:
        run_id: Synthesis run id from start_synthesis / retry_pd.
        max_wait_sec: Max seconds to block in this call (default 30, capped 120).
        poll_interval_sec: Fallback poll interval when guidance is absent.
    """
    workspace = get_workspace_path()
    result = _wait_for_synthesis_job(workspace, run_id, max_wait_sec, poll_interval_sec)
    return json.dumps(result, indent=2)



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


@tool
def read_stage_report(stage: str, run_id: str = None) -> str:
    """
    Reads the main ORFS artifact for a physical-design stage.
    Supported stages currently include floorplan, place, cts, grt, route, and finish.
    """
    workspace = get_workspace_path()
    result = collect_stage_report(workspace=workspace, stage=stage, run_id=run_id)
    return json.dumps(result, indent=2)


@tool
def get_route_drc_summary(run_id: str = None) -> str:
    """
    Summarizes the final route DRC report from ORFS.
    Treats an empty 5_route_drc.rpt as a clean final route result.
    """
    workspace = get_workspace_path()
    result = collect_route_drc_summary(workspace=workspace, run_id=run_id)
    return json.dumps(result, indent=2)


@tool
def get_cts_summary(run_id: str = None) -> str:
    """
    Summarizes the ORFS CTS final report.
    Extracts timing, skew, violation counts, and critical-path summary fields.
    """
    workspace = get_workspace_path()
    result = collect_cts_summary(workspace=workspace, run_id=run_id)
    return json.dumps(result, indent=2)


@tool
def get_congestion_summary(run_id: str = None) -> str:
    """
    Summarizes ORFS global-routing congestion from congestion.rpt or 5_1_grt.log.
    Extracts per-layer resource, demand, usage, and overflow totals.
    """
    workspace = get_workspace_path()
    result = collect_congestion_summary(workspace=workspace, run_id=run_id)
    return json.dumps(result, indent=2)


@tool
def compare_pd_runs(child_run_id: str, parent_run_id: str = None) -> str:
    """
    Compares a PD retry child run against its parent.
    If parent_run_id is omitted, uses the child run lineage metadata when available.
    """
    workspace = get_workspace_path()
    result = collect_pd_run_comparison(
        workspace=workspace,
        child_run_id=child_run_id,
        parent_run_id=parent_run_id,
    )
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
    try:
        abs_file = resolve_in_workspace(filename, workspace=workspace)
    except ValueError as exc:
        return f"Error: {exc}"

    result = replace_in_file(abs_file, target_text, replacement_text)
    
    if result["success"]:
        return f"Success: {result['message']}\nDiff:\n{result.get('diff', '')}"
    else:
        return f"Error: {result['message']}"

from src.tools.build_interactive_sim import build_websim_netlist
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
    # Hosted has no local Docker, so the Yosys-schematic path can't run — return
    # an honest answer instead of leaking a raw docker-socket error to the
    # external app (X2M-5). Mirrors the run_python_analysis hosted gate.
    from src.platform_engines.settings import get_settings

    if get_settings().hosted:
        return (
            "Schematic generation isn't available on the hosted platform yet — "
            "it needs a local Yosys/Docker toolchain. Run SiliconCrew self-host "
            "for schematics."
        )

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
def build_interactive_sim(verilog_files: list[str] | str, top_module: str) -> str:
    """
    Compiles RTL into the netlist artifact behind an interactive browser
    dashboard (`<top>.websim.json`) — the design then runs as a real gate-level
    simulation in the user's browser. Follow up by writing
    `<top>.dashboard.html` with write_file: a self-contained HTML/CSS/JS page
    (no external scripts/styles — everything inline) that

      * declares its netlist via
        `<meta name="siliconcrew-sim" content="<top>.websim.json">`, and
      * drives the design ONLY through the injected `window.simBridge` API:
          simBridge.ready(cb)            — cb(ports) once the sim is loaded;
                                           ports = [{name, direction, bits}]
          simBridge.setInput(name, val)  — set an input port (integer value)
          simBridge.onUpdate(cb)         — cb({outputs, cycle}) after each
                                           clock tick; outputs = {name: int}
                                           (an output is null while any of
                                           its bits is undefined/x)
          simBridge.setClockHz(hz)       — full clock cycles per second
                                           (default 25; 'clk' is auto-driven)

    NEVER re-implement or approximate the design's behavior in dashboard JS —
    every displayed state must come from onUpdate. If this tool fails, say so;
    do not ship a mock. Only offer dashboards for designs with human-shaped
    I/O (buttons, LEDs, displays, games, controllers); for datapath/protocol
    blocks (FIFOs, bus bridges, ALU pipelines) recommend simulation_tool +
    waveform_tool instead of building a junk switch panel.

    Args:
        verilog_files: RTL file name(s), e.g. 'counter.v' or ['simon.v', 'simon_game.v'].
        top_module: Name of the top-level module.

    Returns the design's port list so you can wire dashboard widgets to real pins.
    """
    workspace = get_workspace_path()
    files = _normalize_verilog_files_arg(verilog_files)
    result = build_websim_netlist(files, top_module, cwd=workspace)

    if not result["success"]:
        return f"Failed to build interactive sim netlist: {result['error']}"

    port_lines = "\n".join(
        f"  - {p['name']}: {p['direction']}, {p['bits']} bit(s)" for p in result["ports"]
    )
    return (
        f"Interactive sim netlist built: {result['artifact']} (engine: {result['engine']})\n"
        f"Ports of {top_module}:\n{port_lines}\n\n"
        f"Next: write `{top_module}.dashboard.html` (self-contained, inline CSS/JS) "
        f"with the meta tag `<meta name=\"siliconcrew-sim\" content=\"{result['artifact']}\">` "
        "and drive it exclusively via window.simBridge. The user opens it from the "
        "workbench's Interactive tab."
    )


@tool
def save_metrics_tool(
    area_um2: float = None,
    cell_count: int = None,
    wns_ns: float = None,
    tns_ns: float = None,
    power_uw: float = None,
    run_id: str = None
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
        save_metrics(workspace, metrics, run_id=run_id)
        
        saved_str = ", ".join([f"{k}={v}" for k, v in metrics.items()])
        return f"""Metrics saved successfully! 📊

**Saved**: {saved_str}

These will be included in the design report when you call `generate_report_tool`."""
    except Exception as e:
        return f"Error saving metrics: {str(e)}"


@tool
def generate_report_tool(run_id: str = None) -> str:
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
        report_path = save_design_report(workspace, run_id=run_id)
        report_content = generate_design_report(workspace, run_id=run_id)
        
        return f"""Design Report Generated! 📊

**Saved to**: {os.path.basename(report_path)}

{report_content}"""
    except Exception as e:
        return f"Error generating report: {str(e)}"


class RunPythonAnalysisArgs(BaseModel):
    script_file: str = Field(
        ...,
        description="Workspace-relative path to a .py script to run. Write the script with write_file FIRST — this tool runs a FILE, not inline code.",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Optional command-line arguments passed to the script (sys.argv[1:]).",
    )


@tool(args_schema=RunPythonAnalysisArgs)
def run_python_analysis(script_file: str, args: list[str] = None) -> str:
    """
    Run a workspace Python script for small engineering-support analysis —
    generating golden/expected vectors, .mem/.hex/.csv files, fixed-point/CRC/DSP
    checks, or plotting simulation outputs. Write the script with write_file
    first (it is recorded as exactly what ran); this tool executes a FILE, not
    inline code. Isolated subprocess: 30s timeout, workspace-only cwd, scrubbed
    env (no backend secrets), pinned libs (stdlib + numpy + matplotlib + pyyaml +
    vcdvcd) — no pip, no network in docker mode. NOT a cocotb replacement, REPL,
    or general shell. Returns JSON with exit_code, output tails, and the files
    the run produced (open them as artifacts).
    """
    # Load-bearing hosted gate (PA3/PA4): the tool runs local toolchains and is
    # OFF on the hosted platform. Placed at the wrapper entry so EVERY path
    # (agent / MCP / REST /invoke) is covered by construction — authorize() alone
    # can't express "hosted-unavailable" (it only distinguishes anonymous).
    from src.platform_engines.settings import get_settings

    if get_settings().hosted:
        return (
            "Python analysis runs locally and isn't available on the hosted "
            "platform yet — use it in self-host / local mode."
        )

    workspace = get_workspace_path()
    from src.tools.run_python import run_python_analysis as _run_python, PythonAnalysisError

    try:
        result = _run_python(workspace, script_file, args or [])
    except PythonAnalysisError as exc:
        return f"Error: {exc}"
    return json.dumps(result, indent=2)


@tool
def cocotb_tool(verilog_files: list[str], top_module: str, python_module: str) -> str:
    """
    Run a cocotb (Python) testbench against your RTL in a pinned simulator container.

    Compiles the listed sources and runs the named cocotb test module against the top-level design.
    A run that does not terminate is reported as a TIMEOUT — treat it as a FAILURE (combinational
    loop, missing clock, or unbounded test), not an inconclusive result. Returns a structured
    pass/fail with an output tail.

    Args:
        verilog_files: DUT + dependency Verilog/SV sources (workspace-relative).
        top_module: Top-level HDL module name.
        python_module: cocotb test module importable from the workspace (e.g. "verif.test_dut").
    """
    workspace = get_workspace_path()

    abs_files = [os.path.join(workspace, f) for f in verilog_files]
    missing = [f for f in abs_files if not os.path.exists(f)]
    if missing:
        return "Error: source file(s) not found: " + ", ".join(missing)

    r = run_cocotb(abs_files, top_module, python_module, cwd=workspace)
    status = r.get("status")
    tail = ((r.get("stdout") or "") + "\n" + (r.get("stderr") or "")).strip()[-16000:]

    if status == "PASS":
        return f"Cocotb Test PASSED ✅  ({r['passed']} testcase(s)) — verified in the reference container."
    if status == "TIMEOUT":
        return ("Cocotb Test DID NOT TERMINATE ⏱️ — treat this as a FAILURE (likely a combinational "
                f"loop, missing clock, or unbounded test). Output tail:\n{tail}")
    if status == "FAIL":
        return f"Cocotb Test FAILED ❌  ({r['failed']} failing testcase(s)).\nOutput tail:\n{tail}"
    return f"Cocotb Test ERROR ⚠️ (build/collection failure — no test ran).\nOutput tail:\n{tail}"

@tool
def sby_tool(sby_file: str) -> str:
    """
    Run formal verification with SymbiYosys (SBY).

    Proves or disproves assertions/properties about a design by exploring reachable states
    (bounded or unbounded), rather than running specific input vectors. Well suited to checking
    invariants that should hold for all inputs: state-machine legality (one-hot, no illegal states),
    value and occupancy bounds (a counter or FIFO level stays in range), protocol/handshake
    properties (request held until acknowledge, no overflow/underflow), and absence of deadlock or
    combinational loops.

    HOW TO WRITE A WORKING SETUP (these are the common mistakes):
      * Clocks and resets are NORMAL input ports of your design. NEVER drive a clock with $anyseq.
        Use $anyseq / $anyconst only for free DATA inputs you want the solver to range over.
      * Put your `assert property (...)` (and any `assume`) in a thin formal harness module that
        instantiates the DUT — or inline in the DUT under `ifdef FORMAL`.
      * Engine: use `smtbmc z3` (z3 is the installed solver). boolector/yices are NOT available.
      * `[files]` paths are resolved from the workspace root — list them workspace-relative
        (e.g. `rtl/dut.sv`, `verif/dut_formal.sv`). (The tool also auto-resolves/normalizes these.)

    Minimal example — dut_formal.sby:
        [options]
        mode bmc
        depth 20
        [engines]
        smtbmc z3
        [script]
        read -formal dut.sv
        read -formal dut_formal.sv
        prep -top dut_formal
        [files]
        rtl/dut.sv
        verif/dut_formal.sv
    ...with verif/dut_formal.sv:
        module dut_formal(input clk, input rst, input [7:0] data_in);
            wire [3:0] count;
            dut u(.clk(clk), .rst(rst), .data_in(data_in), .count(count));
            always @(posedge clk) assert (count <= 4'd8);   // occupancy bound holds for ALL inputs
        endmodule

    Args:
        sby_file: Name of the .sby configuration file (e.g., 'fifo.sby') describing the design and
            the properties to prove.
    """
    workspace = get_workspace_path()
    abs_file = os.path.join(workspace, sby_file)
    
    if not os.path.exists(abs_file):
        return f"Error: File {sby_file} does not exist."
        
    result = run_sby(abs_file, cwd=workspace)
    status = result["status"]
    tail = ((result.get("stdout") or "") + "\n" + (result.get("stderr") or "")).strip()[-600:]

    if status == "PASS":
        return f"SBY Formal PASSED ✅ — property proven.\nOutput:\n{tail}"
    if status == "FAIL":
        return f"SBY Formal FAILED ❌ — property violated (counterexample found).\nOutput:\n{tail}"
    if status == "TIMEOUT":
        return ("SBY DID NOT FINISH ⏱️ within the time budget — the proof is inconclusive (deepen "
                f"incrementally or simplify the property). Output:\n{tail}")
    if status == "ERROR":
        return ("SBY did not complete ⚠️ — the proof engine errored (NOT a formal-verification dead end; "
                "z3 IS available). Common causes: a clock driven by $anyseq (clocks/resets are normal "
                "input ports — only use $anyseq for free data inputs), invalid Verilog in the formal "
                "harness, or a missing source file in [files]. Use `[engines] smtbmc z3`, fix the harness, "
                f"and retry.\nOutput:\n{tail}")
    return f"SBY Run finished. Status: {status} ⚠️\nOutput:\n{tail}"

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
    Use this to honor synthesis polling guidance from get_synthesis_status.
    Args:
        seconds: Requested sleep time (clamped to 1..30 seconds).
    """
    wait_s = max(1, min(int(seconds), 30))
    time.sleep(wait_s)
    return f"Slept for {wait_s} second(s)."

# New Google XLS / DSLX HLS tools
@tool
def run_dslx_interpreter(filename: str) -> str:
    """
    Runs the DSLX interpreter on a .x file in the active workspace to check syntax
    and execute built-in unit tests (#[test] blocks).
    Args:
        filename: Name of the DSLX file (e.g. 'saturating_add.x').
    """
    from src.tools.run_xls import run_dslx_interpreter as run_interpreter
    workspace = get_workspace_path()
    result = run_interpreter(filename, cwd=workspace)
    return json.dumps(result, indent=2)

@tool
def compile_dslx_to_ir(filename: str, top_module: str) -> str:
    """
    Translates a DSLX (.x) design into XLS Intermediate Representation (IR).
    Args:
        filename: Name of the DSLX file.
        top_module: Name of the top-level function or proc to compile.
    """
    from src.tools.run_xls import compile_dslx_to_ir as compile_to_ir
    workspace = get_workspace_path()
    result = compile_to_ir(filename, top_module, cwd=workspace)
    return json.dumps(result, indent=2)

@tool
def experimental_compile_cpp_to_ir(filename: str, top_name: str, block_from_class: bool = False) -> str:
    """
    Translates C++ hardware description code into XLS IR via xlscc (experimental).
    Args:
        filename: Name of the C++ file (e.g., 'design.cc').
        top_name: Name of the top-level function or class.
        block_from_class: True if compiling a class-based block/stateful system.
    """
    from src.tools.run_xls import experimental_compile_cpp_to_ir as compile_cpp
    workspace = get_workspace_path()
    result = compile_cpp(filename, top_name, block_from_class, cwd=workspace)
    return json.dumps(result, indent=2)

@tool
def optimize_xls_ir(ir_filename: str) -> str:
    """
    Optimizes XLS IR using logic and dataflow optimizations.
    Args:
        ir_filename: Name of the XLS IR file (e.g. 'saturating_add.ir').
    """
    from src.tools.run_xls import optimize_xls_ir as optimize_ir
    workspace = get_workspace_path()
    result = optimize_ir(ir_filename, cwd=workspace)
    return json.dumps(result, indent=2)

@tool
def codegen_xls(
    opt_ir_filename: str,
    generator: str = "combinational",
    pipeline_stages: int = 0,
    clock_period_ps: int = 0,
    delay_model: str = "sky130",
    module_name: str = None,
    use_system_verilog: bool = False,
) -> str:
    """
    Schedules optimized XLS IR and generates synthesizable Verilog.
    Args:
        opt_ir_filename: Name of the optimized IR file.
        generator: 'combinational' or 'pipeline'.
        pipeline_stages: Number of pipeline stages for pipelined designs.
        clock_period_ps: Target clock period in picoseconds.
        delay_model: Delay model (e.g., 'sky130', 'asap7').
        module_name: Optional custom name for the generated Verilog module.
        use_system_verilog: If True, emit SystemVerilog (default is False to ensure Yosys synthesis compatibility).
    """
    from src.tools.run_xls import codegen_xls as run_codegen
    workspace = get_workspace_path()
    result = run_codegen(
        opt_ir_filename=opt_ir_filename,
        generator=generator,
        pipeline_stages=pipeline_stages,
        clock_period_ps=clock_period_ps,
        delay_model=delay_model,
        module_name=module_name,
        use_system_verilog=use_system_verilog,
        cwd=workspace
    )
    return json.dumps(result, indent=2)

@tool
def benchmark_xls(opt_ir_filename: str, delay_model: str = "sky130") -> str:
    """
    Evaluates XLS IR for performance, area complexity, and estimated critical path delay.
    Args:
        opt_ir_filename: Name of the optimized IR file.
        delay_model: Delay model (e.g., 'sky130', 'asap7').
    """
    from src.tools.run_xls import benchmark_xls as run_benchmark
    workspace = get_workspace_path()
    result = run_benchmark(opt_ir_filename, delay_model=delay_model, cwd=workspace)
    return json.dumps(result, indent=2)

@tool
def run_xls_flow(
    dslx_file: str,
    top_module: str,
    generator: str = "combinational",
    pipeline_stages: int = 0,
    clock_period_ps: int = 0,
    delay_model: str = "sky130",
    module_name: str = None,
    keep_intermediates: bool = True,
    run_lint: bool = True,
    use_system_verilog: bool = False,
) -> str:
    """
    Executes the entire high-level XLS synthesis flow:
    DSLX Interpreter -> IR Conversion -> Optimization -> Codegen.
    This is the preferred agent path for compiling DSLX code to Verilog.
    Args:
        dslx_file: Name of the DSLX file (e.g. 'saturating_add.x').
        top_module: Name of the top-level function or proc.
        generator: 'combinational' or 'pipeline'.
        pipeline_stages: Number of pipeline stages for pipelined designs.
        clock_period_ps: Target clock period in picoseconds.
        delay_model: Delay model (e.g., 'sky130', 'asap7').
        module_name: Optional custom name for the generated Verilog module.
        keep_intermediates: Preserve .ir and .opt.ir artifacts for debugging/provenance.
        run_lint: Run Icarus Verilog syntax lint on generated Verilog before returning success.
        use_system_verilog: If True, emit SystemVerilog (default is False to ensure Yosys synthesis compatibility).
    """
    from src.tools.run_xls import run_xls_flow as run_flow
    workspace = get_workspace_path()
    result = run_flow(
        dslx_file=dslx_file,
        top_module=top_module,
        generator=generator,
        pipeline_stages=pipeline_stages,
        clock_period_ps=clock_period_ps,
        delay_model=delay_model,
        module_name=module_name,
        keep_intermediates=keep_intermediates,
        run_lint=run_lint,
        use_system_verilog=use_system_verilog,
        cwd=workspace
    )
    return json.dumps(result, indent=2)

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
    # Design manifest (shared source of truth with the UI)
    get_manifest,
    update_manifest,
    # Verification tools
    linter_tool,
    simulation_tool,
    run_isolated_simulation,
    waveform_tool,
    cocotb_tool,
    sby_tool,
    # Synthesis & Analysis
    start_synthesis,
    retry_pd,
    get_synthesis_status,
    wait_for_synthesis,
    get_synthesis_metrics,
    read_stage_report,
    get_route_drc_summary,
    get_cts_summary,
    get_congestion_summary,
    compare_pd_runs,
    search_logs_tool,
    schematic_tool,
    build_interactive_sim,
    # Reporting & Metrics
    save_metrics_tool,
    generate_report_tool,
    # Analysis (local-only Python analysis tool)
    run_python_analysis,
    # Google XLS HLS tools
    run_dslx_interpreter,
    compile_dslx_to_ir,
    experimental_compile_cpp_to_ir,
    optimize_xls_ir,
    codegen_xls,
    benchmark_xls,
    run_xls_flow,
]

# Tools bound to the in-process architect agent.
# One async contract everywhere: the architect polls with bounded
# wait_for_synthesis loops — no start+wait combo tool (Wave 9).
architect_tools = [*mcp_tools, sleep_tool]
