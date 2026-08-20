import os
import json
import time
from typing import Any, Literal, Optional
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
from src.utils.session_context import current_session_id


# =============================================================================
# Tool policy — declared AT the tool, read everywhere
# =============================================================================
# One rule: a tool's policy is written once, on the tool itself. Nothing else
# in this repo may hand-maintain a list of tool names to classify them.
#
# Carrier: ``__tool_policy__`` on the undecorated function, which LangChain's
# ``@tool`` keeps reachable as ``StructuredTool.func`` (already relied on by
# ``tool_catalog.validate_and_execute``). ``BaseTool.metadata`` was the
# alternative and was rejected on evidence: ``langchain_core.tools.tool()``
# (1.6.0) takes no ``metadata`` argument, so it could only be assigned AFTER
# the definition — a second site, i.e. exactly the drift this removes.
#
# Readers (there are no others; add one and add it here):
#   category         -> tool_catalog.TOOL_CATEGORIES / category_of / build_catalog;
#                       mcp_server picks Action.SYNTHESIZE vs Action.SAVE from it
#   protected        -> tool_catalog.PROTECTED_TOOLS -> /invoke sign-in gate
#                       (actions.py) and the MCP capability gate
#   mutates          -> tool_catalog.MUTATING_TOOLS -> hosted workspace sync
#                       (mcp_server, actions.run_scoped) and the catalog flag
#   async_job        -> tool_catalog.ASYNC_TOOLS -> catalog flag; the UI renders
#                       dispatch-then-poll instead of blocking
#   surfaces         -> which registries a tool is in: "agent" (architect_tools),
#                       "mcp" (mcp_tools), "ui" (Command Surface; absence is
#                       tool_catalog.EXCLUDED_FROM_UI), "codex" (the extra tool
#                       only a Codex-launched MCP server advertises, on top of
#                       the mcp set)
#   requires_session -> tool_catalog.requires_session() -> the MCP server's
#                       session gate. False ONLY for the session tools below:
#                       the gate fires before every call, so a tool a stranger
#                       needs BEFORE a session exists must say so here. This is
#                       what the gate reads instead of naming those tools.
#   disabled_when_bound
#                    -> mcp_server's bound-session refusal AND the codex
#                       engine's disabled_tools. A server bound to ONE session
#                       (Codex) cannot offer tools that create, list, switch or
#                       delete sessions; the tools say so, the two consumers
#                       read it.
#   attempt_role     -> attempt_logger: which tool calls open a new attempt
#                       (a change) and which close one (a checkpoint)
#   attempt_parser   -> attempt_logger: how THIS tool's result fills the
#                       attempt summary. Declared here so there is no
#                       name-keyed dispatch chain in the logger.

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable

from src.utils.attempt_logger import (
    attempt_lint,
    attempt_simulation,
    attempt_synthesis_dispatch,
    attempt_synthesis_metrics,
)

# Where a tool is offered. "ui" means the Command Surface / REST /invoke;
# "codex" means the Codex-bound MCP server only, which serves it in addition to
# everything on the "mcp" surface.
SURFACE_NAMES = frozenset({"agent", "mcp", "ui", "codex"})
ALL_SURFACES = ("agent", "mcp", "ui")

# How a tool call moves the attempt log forward (see attempt_logger).
ATTEMPT_ROLES = frozenset({"rtl_change", "synth_change", "checkpoint"})


@dataclass(frozen=True)
class ToolPolicy:
    """Everything about a tool that is not derivable from its own schema.

    Every field is required except ``disabled_when_bound`` and the two attempt
    fields, whose honest defaults are "a session-bound server may run this" and
    "this tool does not take part in attempt tracking". Omitting a required
    field is a TypeError at import; omitting the whole policy is caught by
    tests/test_tool_policy.py.
    """

    category: str
    protected: bool
    mutates: bool
    async_job: bool
    surfaces: frozenset
    requires_session: bool
    disabled_when_bound: bool = False
    attempt_role: "str | None" = None
    attempt_parser: "Callable | None" = None

    def __post_init__(self):
        if not self.category or not self.category.strip():
            raise ValueError("ToolPolicy.category must be a non-empty category name")
        surfaces = frozenset(self.surfaces)
        unknown = surfaces - SURFACE_NAMES
        if unknown:
            raise ValueError(f"unknown surface(s) {sorted(unknown)}; known: {sorted(SURFACE_NAMES)}")
        if not surfaces:
            raise ValueError("a tool with no surface is unreachable — delete it instead")
        object.__setattr__(self, "surfaces", surfaces)
        if self.attempt_role is not None and self.attempt_role not in ATTEMPT_ROLES:
            raise ValueError(f"unknown attempt_role {self.attempt_role!r}; known: {sorted(ATTEMPT_ROLES)}")


def policy(**fields):
    """Attach a :class:`ToolPolicy` to the function ``@tool`` will wrap.

    Applied UNDER ``@tool`` so the attribute lands on the plain function that
    survives as ``StructuredTool.func``::

        @tool
        @policy(category="essential", ...)
        def read_file(filename: str) -> str: ...
    """
    p = ToolPolicy(**fields)

    def attach(fn):
        fn.__tool_policy__ = p
        return fn

    return attach



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
@policy(category="essential", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="rtl_change")
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

# Honest large-file window for read_file: unbounded reads of run artifacts
# (sim.log can be multi-MB of per-cycle $display) went whole into the tool
# result. Head + tail with an explicit omission marker — never a silent cut.
#
# DESIGN SOURCES get a far higher threshold: read_file pairs with write_file
# in the agent loop, and a windowed read of a 70 KB generated sbox/LUT that
# is then edited and written back DESTROYS the omitted bytes. Real RTL stays
# well under 1 MiB (this repo's largest example is ~46 KB); anything over it
# is windowed with the marker, at which point editing-by-rewrite was never
# going to be sane anyway.
_READ_FILE_MAX_BYTES = 64 * 1024
_READ_FILE_HEAD_BYTES = 32 * 1024
_READ_FILE_TAIL_BYTES = 16 * 1024
_READ_FILE_SOURCE_EXTS = {".v", ".sv", ".vh", ".svh", ".sdc", ".yaml", ".yml", ".json", ".md", ".tcl", ".py"}
_READ_FILE_SOURCE_MAX_BYTES = 1024 * 1024


@tool(parse_docstring=True)
@policy(category="essential", protected=False, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def read_file(filename: str) -> str:
    """
    Reads content from a file in the workspace. Large files (over 64 KiB) are
    returned as head + tail with an explicit omission marker — for a systematic
    failure the first occurrences are the informative ones, and an unbounded
    read of a multi-MB sim log would swamp the model's context.

    Args:
        filename: File to read, e.g. 'counter.v' or 'sim_runs/sim_0001/sim.log'.
    """
    workspace = get_workspace_path()
    try:
        filepath = resolve_in_workspace(filename, workspace=workspace)
    except ValueError as exc:
        return f"Error: {exc}"

    if not os.path.exists(filepath):
        return f"Error: File {filename} does not exist."

    size = os.path.getsize(filepath)
    ext = os.path.splitext(filepath)[1].lower()
    threshold = (
        _READ_FILE_SOURCE_MAX_BYTES if ext in _READ_FILE_SOURCE_EXTS else _READ_FILE_MAX_BYTES
    )
    if size <= threshold:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    # Binary reads: a byte seek in text mode is undefined for arbitrary offsets.
    with open(filepath, "rb") as f:
        head = f.read(_READ_FILE_HEAD_BYTES).decode("utf-8", errors="replace")
        f.seek(size - _READ_FILE_TAIL_BYTES)
        tail = f.read().decode("utf-8", errors="replace")
    omitted = size - _READ_FILE_HEAD_BYTES - _READ_FILE_TAIL_BYTES
    return (
        f"{head}\n"
        f"... [{omitted} bytes omitted — file is {size} bytes; "
        f"this is the first {_READ_FILE_HEAD_BYTES} and last {_READ_FILE_TAIL_BYTES} bytes of {filename}] ...\n"
        f"{tail}"
    )

@tool(parse_docstring=True)
@policy(category="essential", protected=False, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="checkpoint", attempt_parser=attempt_lint)
def linter_tool(
    verilog_files: list[str] | str,
    engine: Literal["auto", "iverilog", "verilator"] = "auto",
) -> str:
    """
    Lints Verilog files. Supports single-file or multi-file linting.

    Args:
        verilog_files: Filename string or list of filenames (e.g. 'design.v' or
            ['design.v', 'tb.v']). When linting a testbench, include all
            dependent RTL files in the same call (for example
            ['seq_detector.v', 'seq_detector_tb.v']) so module references
            resolve.
        engine: 'auto' picks verilator if installed, else iverilog. 'iverilog'
            is syntax/elaboration only. 'verilator' is a real lint (latches,
            width mismatches, unsynthesizable constructs) — lint RTL only with
            it, not testbenches.
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

@tool(parse_docstring=True)
@policy(category="essential", protected=False, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="checkpoint", attempt_parser=attempt_simulation)
def simulation_tool(
    verilog_files: list[str],
    top_module: str,
    mode: Literal["rtl", "post_synth"] = "rtl",
    run_id: str = None,
    netlist_file: str = None,
    platform: str = None,
    sim_profile: Literal["auto", "pinned", "compat"] = "auto",
    pass_marker: str = "",
) -> str:
    """
    Compiles and runs an iverilog simulation of an EXPLICIT file list, in the
    workspace root. Returns JSON whose `status` is exactly one of:
      compile_failed - iverilog did not build the design
      sim_failed     - the run crashed, or its $readmem data never loaded (a
                       pass marker printed by such a run is NOT believed)
      test_failed    - the run finished without printing the pass marker
      test_passed    - the run printed the pass marker
    plus stdout/stderr tails, the marker actually used, and — for post_synth —
    the run, netlist and stdcell set that were resolved.
    Prefer run_isolated_simulation: it takes the file set from the manifest,
    runs in its own sim_runs/sim_NNNN/ directory, stages $readmem data files
    beside the executable, and keeps a run record. Use this tool when you must
    compile a file set the manifest does not describe. Both write a VCD; this
    one writes it into the workspace root, where the next run overwrites it.

    Args:
        verilog_files: Every file to compile, testbench included.
        top_module: Top module of the testbench.
        mode: 'rtl' compiles the listed sources. 'post_synth' drops the design
            RTL, substitutes the gate netlist from a synthesis run, and links
            stdcell models.
        run_id: post_synth only - which synthesis run's netlist to simulate.
            Omit for the most recent run.
        netlist_file: post_synth only - an explicit gate netlist, overriding the
            one the run recorded.
        platform: post_synth only - the PDK whose stdcell models get linked.
            Omit to use the platform the run itself recorded; that is almost
            always right, and a wrong value here produces unresolved cells.
        sim_profile: 'pinned' links the vendor's real stdcell models. 'compat'
            substitutes SiliconCrew's behavioral models, which exist for asap7
            ONLY and are a no-op on every other platform. 'auto' picks compat
            for asap7 and pinned elsewhere.
        pass_marker: stdout substring that means PASS. Empty uses the manifest's
            passMarker, then "TEST PASSED".
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


@tool(parse_docstring=True)
@policy(category="manifest", protected=False, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def get_manifest() -> str:
    """
    Returns the design manifest: every design file with its role ({roles}),
    synthTop, simTop, clockPeriodNs, platform, passMarker, the derived testbench
    list, and warnings such as two files declaring the same module. Derived by
    scanning the workspace when absent.
    This is what decides which files each stage compiles, and where
    run_isolated_simulation gets simTop and every simulation gets its default
    pass marker.
    """
    workspace = get_workspace_path()
    m = manifest_mod.read_manifest(workspace, session_id=current_session_id())
    return json.dumps(m.model_dump(), indent=2)


@tool(parse_docstring=True)
@policy(category="manifest", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def update_manifest(updates_json: str) -> str:
    """
    Upserts manifest fields. Pass a JSON object with any of:
      synthTop / simTop  - top module for synthesis / simulation
      clockPeriodNs      - target clock period, nanoseconds
      platform           - PDK used for synthesis and post-synth stdcell models
      passMarker         - the stdout substring your testbench prints on
                           success; every simulation uses it as its default
                           pass criterion
      ignore             - fnmatch globs (e.g. ["vendor/**"]) excluded from the
                           file scan; newly ignored files drop out immediately
      files              - [{"path": "rtl/counter.v", "role": "rtl"}] to
                           override a file's role. Address files by path: a
                           bare basename is honored only when it is unique, and
                           is a silent no-op when it is not.
    Roles: {roles}. An unknown role is rejected and nothing is written.
    testbenches and warnings are derived and cannot be set here.

    Args:
        updates_json: The object above, serialized as a JSON string.
    """
    workspace = get_workspace_path()
    try:
        updates = json.loads(updates_json) if updates_json else {}
        if not isinstance(updates, dict):
            return "Error: updates_json must be a JSON object."
    except Exception as exc:
        return f"Error: invalid updates_json ({exc})."
    try:
        m = manifest_mod.write_manifest(workspace, updates, session_id=current_session_id())
    except ValueError as exc:
        return f"Error: {exc}"
    return json.dumps(m.model_dump(), indent=2)


# The role list the agent and MCP clients see is GENERATED from the FileRole
# Literal — a hand-copied list here is exactly how a tool description starts
# advertising roles that no longer exist (or hiding ones that do).
for _t in (get_manifest, update_manifest):
    _t.description = _t.description.replace("{roles}", " | ".join(manifest_mod.ROLES))
del _t


def _with_manifest_warnings(result: dict, workspace: str, compile_files: list) -> dict:
    """Front the dispatch reply with any duplicate-module collision in THIS set.

    The manifest carries the same warnings, but a run is where they cost
    something — so they lead the reply, ahead of the run record, rather than
    waiting to be noticed in metadata. Only the collisions actually present in
    the assembled compile set are reported; the message adds the remedy the
    compiler's own error can't (which file to ignore), it does not restate it.
    Kept INSIDE the JSON so ``/invoke`` still parses a typed result.
    """
    try:
        warnings = manifest_mod.compile_set_collisions(workspace, compile_files)
    except Exception:
        return result
    if not warnings:
        return result
    return {"manifestWarnings": warnings, **result}


@tool(parse_docstring=True)
@policy(category="essential", protected=False, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        # Same attempt record as simulation_tool. Without these the preferred
        # sim path — and the IDE's Simulate button, which routes here — logged
        # rtl_sim: "not_run" for a run that actually passed.
        attempt_role="checkpoint", attempt_parser=attempt_simulation)
def run_isolated_simulation(
    sim_top: str = "",
    mode: Literal["rtl", "post_synth"] = "rtl",
    run_id: str = None,
    sim_profile: Literal["auto", "pinned", "compat"] = "auto",
    pass_marker: str = "",
) -> str:
    """
    Runs the manifest's simulate file set (roles rtl + tb + include) in its own
    sim_runs/sim_NNNN/ directory: its own VCD, its $readmem data files staged in
    beside it, a persisted run record and provenance. The default way to
    simulate.
    Returns JSON. `status` is passed | failed; the finer verdict is `simStatus`
    (compile_failed | sim_failed | test_failed | test_passed). Also `vcdPath` —
    the VCD to hand to waveform_tool — `xDetected` (x/z seen after t=0; a
    warning surface, not a verdict), `stagedDataFiles`, and for post_synth the
    run and netlist that were resolved.
    It compiles what the MANIFEST says. To compile a different set, fix the
    roles with update_manifest, or use simulation_tool.

    Args:
        sim_top: Testbench top module. Empty uses the manifest's simTop.
        mode: 'rtl', or 'post_synth' to simulate a synthesis run's gate netlist.
        run_id: post_synth only - which synthesis run. Omit for the most recent.
        sim_profile: 'auto' | 'pinned' | 'compat', as simulation_tool.
        pass_marker: stdout substring that means PASS. Empty uses the manifest's
            passMarker, then "TEST PASSED".
    """
    workspace = get_workspace_path()
    m = manifest_mod.read_manifest(workspace, session_id=current_session_id())
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
    return json.dumps(_with_manifest_warnings(result, workspace, files), indent=2)


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=True, async_job=True,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="synth_change", attempt_parser=attempt_synthesis_dispatch)
def start_synthesis(
    verilog_files: list[str],
    top_module: str,
    platform: str = "sky130hd",
    clock_period_ns: float = 10.0,
    utilization: int = 40,
    aspect_ratio: float = 1.0,
    core_margin: float = 2.0,
    run_equiv: bool = False,
    constraints_mode: Literal["auto", "strict", "bypass"] = "auto",
    max_stage: Literal[
        "constraints", "synth", "floorplan", "place", "cts", "grt", "route", "finish"
    ] = "finish",
) -> str:
    """
    Starts an ORFS run and returns immediately with `run_id` — the one durable
    handle for it. Poll get_synthesis_status until status is completed or failed
    (a full flow is typically 8-40 minutes), then read get_synthesis_metrics.

    Args:
        verilog_files: RTL to synthesize. Do not include the testbench.
        top_module: Top module to synthesize.
        platform: ORFS PDK. Known good: sky130hd, sky130hs, asap7, nangate45,
            ihp-sg13g2, gf180. Not a closed list — any platform your ORFS image
            provides is passed through.
        clock_period_ns: Target clock period, ALWAYS nanoseconds on every
            platform (converted internally to the PDK's SDC time unit, e.g. ps
            on asap7). Reported metrics are likewise in the units their names
            carry: wns_ns, tns_ns, fmax_mhz, power_mw.
        utilization: Percent of the core area filled with standard cells, 1-100
            (clamped). 40 suits a standard design; raise it to shrink the die
            once routing is comfortable. Lower it for a very small design, or
            after a PDN-0185 failure (floorplan too small for the power grid).
            Whether 40 trips PDN-0185 on a sub-30-cell design is UNMEASURED —
            on a design that small, set core_margin >= 4 (below) and drop
            utilization if the floorplan stage fails.
        aspect_ratio: Core height divided by width. Raise it when
            placement-driven congestion is what is costing timing.
        core_margin: Empty core ring around the placeable area, in microns. Use
            >= 4 for very small designs (under ~30 cells).
        run_equiv: Run the post-synthesis logical-equivalence check. Skipped
            automatically on a partial flow.
        constraints_mode: How this run's SDC gets built. 'auto' uses the spec's
            clock when the spec's module matches top_module, and otherwise falls
            back to a default clock and says so in the run's constraints_note
            and clock_source. 'strict' refuses to run rather than fall back: no
            spec, a spec/module mismatch, or no clk/clock/clk_i input is an
            error. 'bypass' ignores the spec entirely and constrains a port
            literally named 'clk' at clock_period_ns; that port is NOT checked
            against the netlist, so if this design's clock has another name the
            run is UNCONSTRAINED and still reports "completed", with timing
            numbers that mean nothing. Use bypass only to force a run through.
        max_stage: Stop after this stage. 'finish' is the full RTL-to-GDS flow;
            'synth' is a fast area/cell-count estimate with no place-and-route
            timing or power. Later stages are recorded as "skipped"; continue a
            partial run toward GDS with retry_pd.
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
    return json.dumps(_with_manifest_warnings(result, workspace, abs_files), indent=2)


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=True, async_job=True,
        surfaces=ALL_SURFACES, requires_session=True)
def retry_pd(
    run_id: str,
    start_stage: Literal["floorplan", "place", "cts", "grt", "route", "finish"],
    max_stage: Literal["floorplan", "place", "cts", "grt", "route", "finish"] = "finish",
    orfs_overrides_json: str = "",
    timeout_sec: int = 0,
) -> str:
    """
    Creates a CHILD run from an existing synthesis run and reruns only the
    physical-design stages from start_stage onward, reusing the parent's
    checkpoints. The parent is never modified. Async, like start_synthesis: it
    returns a new run_id to poll.
    Use it to try a physical knob without re-synthesizing. When the child is
    terminal, call compare_pd_runs(child_run_id) for the parent-vs-child delta.

    Args:
        run_id: The parent run to branch from.
        start_stage: First stage to rerun. The parent must have produced the
            checkpoint that feeds it, so a partial parent limits how far back
            you can start; the error names the stage you can resume from.
        max_stage: Last stage to run. Must be at or after start_stage.
        orfs_overrides_json: JSON object of ORFS make variables for this child,
            e.g. {"PLACE_DENSITY": 0.15}. Keys must be UPPER_SNAKE_CASE, values
            scalar. Validated in this repo: CORE_UTILIZATION with
            start_stage='floorplan', PLACE_DENSITY with 'place',
            CTS_BUF_DISTANCE with 'cts'. Anything else is passed to ORFS
            unchecked.
        timeout_sec: Seconds. 0 uses the stage-aware ceiling for this run. A
            positive value only LOWERS it; a larger request is capped at the
            ceiling.
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

@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def get_synthesis_status(run_id: str) -> str:
    """
    Full status for a synthesis run by its run_id: status, current stage,
    per-stage table + history, last log lines, artifacts found, best-effort
    metrics, and poll_after_sec guidance. Self-healing: a run whose worker
    died is reconciled from on-disk evidence (completed from artifacts, or
    failed once past its timeout ceiling) instead of reading "running" forever.

    Args:
        run_id: Run to report on, from start_synthesis or retry_pd. Required —
            this reader has no "latest" fallback.
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
    status = None

    # Sample at the TOP of every iteration, including the one that discovers the
    # deadline has passed — so the run going terminal during the last sleep is
    # still caught (F8) — and never sample after the loop. A status call is not
    # free on hosted (it can reconcile and re-tar the workspace), so a post-loop
    # resample made the worst case max_wait + TWO slow calls; that overshoot is
    # what tripped the MCP idle abort in dev#30. Now: max_wait + <1s of residual
    # sleep + ONE call (the sleep floor is 1s, so the deadline-discovering
    # sample can start up to ~1s late).
    while True:
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

    # timeout path returns latest known status with explicit timeout flag
    status["waited_sec"] = round(time.time() - start, 2)
    status["timed_out"] = True
    status["next_action"] = "Call wait_for_synthesis again or poll with get_synthesis_status."
    return status


@tool(parse_docstring=True)
# No "ui" surface: a bounded blocking poll built for agent turn economy. The
# UI is a viewer, not an actor (invariant 6) and has its own live polling.
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=("agent", "mcp"), requires_session=True)
def wait_for_synthesis(run_id: str, max_wait_sec: int = 30, poll_interval_sec: int = 2) -> str:
    """
    MCP-safe bounded wait for synthesis completion — the ONE blocking
    convenience, defined as a bounded poll loop over get_synthesis_status.

    Args:
        run_id: Synthesis run id from start_synthesis / retry_pd.
        max_wait_sec: Max seconds to block in this call (default 30, capped
            120).
        poll_interval_sec: Fallback poll interval, seconds, when the run gives
            no guidance.
    """
    workspace = get_workspace_path()
    result = _wait_for_synthesis_job(workspace, run_id, max_wait_sec, poll_interval_sec)
    return json.dumps(result, indent=2)



@tool(parse_docstring=True)
@policy(category="verification", protected=False, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def waveform_tool(vcd_file: str, signals: list[str], start_time: int = 0,
                  end_time: Optional[int] = None) -> str:
    """
    Reads signal values out of a VCD. Use it when a simulation fails, to find
    where the design diverges — x/z propagation, a shifted output cycle, reset
    behaviour.
    Returns a tab-separated Time / Signal / Value table, one row per value
    change, first 2000 rows, with a footer saying how many were withheld.

    Args:
        vcd_file: The .vcd to read. run_isolated_simulation returns it as
            `vcdPath` (sim_runs/sim_NNNN/...); simulation_tool leaves it
            wherever the testbench's $dumpfile put it, usually the workspace
            root.
        signals: Signal names. A full hierarchical path ('tb.dut.count') always
            resolves; a bare leaf name resolves when exactly one scope has it,
            and is an error listing the candidates when several do.
        start_time: Start of the window, in the VCD's OWN time units — the
            integers after '#' in the file, NOT nanoseconds.
        end_time: End of the window, same units. Omit to read to the end.
    """
    workspace = get_workspace_path()
    abs_file = os.path.join(workspace, vcd_file)
    return read_waveform(abs_file, signals, start_time, end_time)

@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def search_logs_tool(query: str, run_id: str = None) -> str:
    """
    Case-insensitive SUBSTRING search (not regex) across a synthesis run's ORFS
    logs, reports and results — *.log, *.rpt, *.txt, *.v, *.json, *.mk. Returns
    at most 50 matching lines as "File: <path> | Line <n>: <text>", cut off
    silently past that, so narrow the query rather than paging.
    Reach for it only for evidence the structured readers do not surface: PDN
    errors, path-level detail, ORFS-specific warnings. PPA and timing numbers
    come from get_synthesis_metrics — do not grep for them.

    Args:
        query: Substring to look for, e.g. 'PDN-0185'.
        run_id: Synthesis run to search. WITHOUT it this does NOT fall back to
            the latest run the way the other run readers do: it searches the
            workspace's legacy orfs_reports/orfs_logs/orfs_results directories
            and the whole synth_runs/ tree, so hits can come from any run. Pass
            one.
    """
    workspace = get_workspace_path()
    return search_logs(query, workspace, run_id=run_id)


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="checkpoint", attempt_parser=attempt_synthesis_metrics)
def get_synthesis_metrics(run_id: str = None) -> str:
    """
    Returns structured synthesis metrics for a run.
    Parses standard ORFS outputs (6_finish.rpt + synth_stat.txt) and returns JSON.
    Read timing from worst_slack_ns (the REAL margin, signed) and timing_met —
    NOT from wns_ns, which is ORFS's report_wns and clamps positive slack to 0,
    so it reads 0.00 for any design that met timing. fmax_mhz is the achieved
    frequency at timing_corner (null when the run carries no slack data — never
    the clock target); parse_notes says when it was derived rather than read.

    Args:
        run_id: Synthesis run. Omit for the most recent run.
    """
    workspace = get_workspace_path()
    result = collect_synthesis_metrics(workspace=workspace, run_id=run_id)
    return json.dumps(result, indent=2)


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def read_stage_report(
    stage: Literal["floorplan", "place", "cts", "grt", "route", "finish"],
    run_id: str = None,
) -> str:
    """
    Returns the main ORFS artifact for one physical-design stage as a text
    excerpt (first 12000 chars) plus its path. Use it when the structured
    summaries do not carry the detail you need.

    Args:
        stage: floorplan (2_floorplan_final.rpt), place (3_3_place_gp.json),
            cts (4_cts_final.rpt), grt (congestion.rpt), route
            (5_route_drc.rpt) or finish (6_finish.rpt).
        run_id: Synthesis run. Omit for the most recent run.
    """
    workspace = get_workspace_path()
    result = collect_stage_report(workspace=workspace, stage=stage, run_id=run_id)
    return json.dumps(result, indent=2)


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def get_route_drc_summary(run_id: str = None) -> str:
    """
    Structured final-routing DRC summary for a run: `clean`, violation_count,
    unique_violation_count, sample_violations and route_stage_status. An empty
    5_route_drc.rpt counts as clean ONLY when the route stage completed — an
    empty report from an unfinished route is reported as not-clean, with a note
    saying so.

    Args:
        run_id: Synthesis run. Omit for the most recent run.
    """
    workspace = get_workspace_path()
    result = collect_route_drc_summary(workspace=workspace, run_id=run_id)
    return json.dumps(result, indent=2)


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def get_cts_summary(run_id: str = None) -> str:
    """
    Structured clock-tree-synthesis summary for a run: wns_ns, tns_ns,
    worst_slack_ns, clock_fmax_mhz, setup_skew_ns and max_slew / max_fanout
    violation counts, parsed from 4_cts_final.rpt. Read this first when a run
    misses timing.

    Args:
        run_id: Synthesis run. Omit for the most recent run.
    """
    workspace = get_workspace_path()
    result = collect_cts_summary(workspace=workspace, run_id=run_id)
    return json.dumps(result, indent=2)


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def get_congestion_summary(run_id: str = None) -> str:
    """
    Structured global-routing congestion for a run, from congestion.rpt or
    5_1_grt.log: per-layer resource, demand, usage_pct and overflow, plus
    totals. Read it when timing degrades between placement and routing — that
    points at wire delay rather than logic depth.

    Args:
        run_id: Synthesis run. Omit for the most recent run.
    """
    workspace = get_workspace_path()
    result = collect_congestion_summary(workspace=workspace, run_id=run_id)
    return json.dumps(result, indent=2)


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def compare_pd_runs(child_run_id: str, parent_run_id: str = None) -> str:
    """
    Metric delta between a retry_pd child run and its parent — the honest answer
    to "did that knob help". Compares wns_ns, worst_slack_ns, tns_ns, area_um2,
    cell_count and power_uw with the direction that counts as better for each,
    plus the routing-DRC status of both runs.

    Args:
        child_run_id: The retry child run.
        parent_run_id: Run to compare against. Omit to use the parent recorded
            in the child's lineage; it is required when the child records none.
    """
    workspace = get_workspace_path()
    result = collect_pd_run_comparison(
        workspace=workspace,
        child_run_id=child_run_id,
        parent_run_id=parent_run_id,
    )
    return json.dumps(result, indent=2)


from src.tools.edit_file import replace_in_file

@tool(parse_docstring=True)
@policy(category="editing", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="rtl_change")
def apply_patch_tool(unified_diff: str) -> str:
    """
    Applies a unified diff with `git apply` (--recount, so hunk line COUNTS may
    be wrong, but CONTEXT LINES MUST MATCH THE FILE EXACTLY). Nothing is written
    unless the whole patch applies: it is checked first, and a failure returns
    git's own stderr with no partial write.
    Use it to change several files, or several places in one file, in one call.
    For a single edit in one file edit_file_tool is more reliable — a generated
    diff whose context drifted by a line is the usual failure here.

    Args:
        unified_diff: A complete unified diff. Every file needs `---`/`+++`
            headers; `a/` and `b/` prefixes are stripped; an absolute path, or
            one that climbs out of the workspace, is rejected before git runs;
            `--- /dev/null` creates a new file.
    """
    workspace = get_workspace_path()
    result = apply_unified_patch(workspace=workspace, unified_diff=unified_diff)
    return json.dumps(result, indent=2)


@tool(parse_docstring=True)
@policy(category="editing", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="rtl_change")
def edit_file_tool(filename: str, target_text: str, replacement_text: str) -> str:
    """
    Replaces one exact block of text in one file. The match is literal,
    including whitespace and indentation.
    Two hard errors, both of which write nothing: the target text was not found,
    or it was found more than once (extend the block with surrounding lines
    until it is unique).

    Args:
        filename: File to edit, e.g. 'counter.v'.
        target_text: The exact text to find, copied verbatim from read_file.
        replacement_text: What to put in its place. An empty string deletes the
            block.
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
from src.tools.design_report import generate_design_report, save_design_report
from src.tools.spec_manager import (
    DesignSpec, PortSpec, parse_yaml_spec, validate_spec, 
    spec_to_prompt, save_yaml_file, load_yaml_file, create_spec_from_dict
)

@tool(parse_docstring=True)
@policy(category="essential", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="rtl_change")
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
    Creates the design spec `<module_name>_spec.yaml` AND writes (overwriting)
    `constraints.sdc` from clock_period_ns. Call it before writing RTL:
    synthesis reads this spec to build each run's real timing constraints.

    Args:
        module_name: Verilog module name, e.g. 'counter_8bit'. Names the spec
            file.
        description: One line on what the module does.
        ports: Port list. Each entry {name, direction} plus optional type,
            width, description. direction is 'input', 'output' or 'inout';
            width is an int (8) or a parameterized string ('WIDTH-1:0'); omit it
            for 1 bit. Example:
                [{"name": "clk", "direction": "input"},
                 {"name": "count", "direction": "output", "width": 8}]
            Name the clock input clk, clock or clk_i — the generated SDC
            constrains that port, and a differently-named clock leaves the
            design unconstrained rather than failing loudly.
        clock_period_ns: Target clock period in nanoseconds; becomes the SDC
            create_clock period.
        tech_node: Free-text label recorded in the spec and the design report.
            It does NOT select a PDK — start_synthesis's `platform` does that.
        parameters: Verilog parameters, e.g. {"WIDTH": 8, "DEPTH": 16}.
        module_signature: Exact module signature to enforce. Generated from
            ports when omitted.
        behavioral_description: Detailed behavioral requirements, free text.
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
        # An empty port name after parsing means the payload's keys were
        # malformed (e.g. a model emitting {'"name"': ...} or misnamed keys).
        # Echo the keys actually received so the failure is diagnosable in
        # one read instead of a bare "Port name cannot be empty" per port.
        bad_entry_keys = [
            ", ".join(repr(k) for k in raw) or "none"
            for raw, parsed in zip(ports, spec.ports)
            if isinstance(raw, dict) and not parsed.name
        ]
        errors = []
        for err in validation["errors"]:
            if err == "Port name cannot be empty" and bad_entry_keys:
                err = f"{err} (entry keys: {bad_entry_keys.pop(0)})"
            errors.append(err)
        return f"Spec validation failed:\n" + "\n".join(errors)
    
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


@tool(parse_docstring=True)
@policy(category="essential", protected=False, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def read_spec(spec_filename: str = None) -> str:
    """
    Reads a design specification from a YAML file.
    Use this to understand requirements before writing RTL.

    Args:
        spec_filename: Spec file to read, e.g. 'counter_spec.yaml'. Omit to
            read the most recently modified *_spec.yaml in the workspace.
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


@tool(parse_docstring=True)
@policy(category="editing", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="rtl_change")
def load_yaml_spec_file(yaml_path: str) -> str:
    """
    Adopts an existing YAML spec as this design's spec: it is re-saved as
    `<module_name>_spec.yaml` and `constraints.sdc` is regenerated from it,
    replacing whatever write_spec produced.
    Use it when the user supplied a spec file; use write_spec to author one.

    Args:
        yaml_path: The YAML spec file to adopt, e.g. 'problem_spec.yaml'.
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


@tool(parse_docstring=True)
@policy(category="synthesis", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def schematic_tool(verilog_file: str, top_module: str) -> str:
    """
    Renders an SVG schematic of one Verilog module with Yosys + netlistsvg, for
    the workbench's Schematic tab. Self-host only: it needs a local
    Yosys/Docker toolchain and refuses on the hosted platform.

    Args:
        verilog_file: Verilog source, e.g. 'counter.v'.
        top_module: Module to draw.
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

@tool(parse_docstring=True)
@policy(category="verification", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def build_interactive_sim(
    verilog_files: list[str] | str,
    top_module: str,
    parameters: dict[str, int] | None = None,
) -> str:
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
                                           (default 25). The clock pin is
                                           auto-detected for names like clk /
                                           clock / *_clk; for any other name
                                           declare it with a second meta tag:
                                           <meta name="siliconcrew-sim-clock"
                                           content="<port>">.
    NEVER re-implement or approximate the design's behavior in dashboard JS —
    every displayed state must come from onUpdate. If this tool fails, say so;
    do not ship a mock. Only offer dashboards for designs with human-shaped
    I/O (buttons, LEDs, displays, games, controllers); for datapath/protocol
    blocks (FIFOs, bus bridges, ALU pipelines) recommend simulation_tool +
    waveform_tool instead of building a junk switch panel.
    The browser engine sustains roughly 1-10k cycles/sec, so RTL whose time
    constants assume a real clock (debounce counters, ms tick dividers) will
    feel frozen. When the design exposes them as top-module parameters (the
    CLK_FREQ / TICKS_PER_MILLI idiom), pass integer overrides via
    `parameters` to re-elaborate at browser speed — the override is recorded
    in the artifact and shown to the user, never hidden.
    Returns the design's port list so you can wire dashboard widgets to real pins.

    Args:
        verilog_files: RTL file name(s), e.g. 'counter.v' or ['simon.v', 'simon_game.v'].
        top_module: Name of the top-level module.
        parameters: Optional integer top-module parameter overrides,
            e.g. {'TICKS_PER_MILLI': 1}. Timing constants only — do not use
            it to change design behavior.

    """
    workspace = get_workspace_path()
    files = _normalize_verilog_files_arg(verilog_files)
    result = build_websim_netlist(files, top_module, cwd=workspace, parameters=parameters)

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


@tool(parse_docstring=True)
@policy(category="reporting", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True,
        attempt_role="checkpoint")
def generate_report_tool(run_id: str = None) -> str:
    """
    Writes a Markdown design report comparing the spec against measured results
    — lint and simulation outcomes, synthesis metrics, timing verdict — and
    returns its content. Saved as synth_runs/<run_id>/design_report.md, or
    <module>_report.md at the workspace root when there is no run. Call it at
    the end of a design session.

    Args:
        run_id: Run to report on. Omit for the most recent run.
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
@policy(category="analysis", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def run_python_analysis(script_file: str, args: list[str] = None) -> str:
    """
    Run a workspace Python script for engineering-support analysis: golden/
    expected vectors, .mem/.hex/.csv generation, fixed-point/CRC/DSP checks,
    plotting simulation output. SELF-HOST ONLY — off on the hosted platform.
    Write the script with write_file first: this runs a FILE, not inline code,
    and the file is the record of exactly what ran. Isolated subprocess: 30 s
    wall timeout, workspace-only cwd, scrubbed env (no backend secrets), pinned
    libraries (stdlib + numpy + matplotlib + pyyaml + vcdvcd), no pip and no
    network in docker mode. Not a cocotb replacement, a REPL, or a shell.
    Returns JSON with exit_code, output tails, and the files the run produced.
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


@tool(parse_docstring=True)
@policy(category="verification", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
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

    # JSON, not prose: raw simulator output legitimately contains words like
    # "Error", and the API-side substring heuristic would classify a passing
    # run as an error from its own tail. A structured status keeps the verdict
    # out of the tail's hands (same contract as simulation_tool).
    if status == "PASS":
        payload = {
            "status": "test_passed",
            "summary": f"Cocotb Test PASSED ✅  ({r['passed']} testcase(s)) — verified in the reference container.",
            "passed": r["passed"],
            "failed": 0,
            "output_tail": tail[-4000:],
        }
    elif status == "TIMEOUT":
        payload = {
            "status": "timeout",
            "summary": ("Cocotb Test DID NOT TERMINATE ⏱️ — treat this as a FAILURE (likely a "
                        "combinational loop, missing clock, or unbounded test)."),
            "output_tail": tail,
        }
    elif status == "FAIL":
        payload = {
            "status": "test_failed",
            "summary": f"Cocotb Test FAILED ❌  ({r['failed']} failing testcase(s)).",
            "failed": r["failed"],
            "output_tail": tail,
        }
    else:
        payload = {
            "status": "error",
            "summary": "Cocotb Test ERROR ⚠️ (build/collection failure — no test ran).",
            "output_tail": tail,
        }
    return json.dumps(payload, indent=2)

@tool(parse_docstring=True)
@policy(category="verification", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
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

@tool(parse_docstring=True)
@policy(category="essential", protected=False, mutates=False, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def list_files_tool() -> str:
    """
    Lists every file in the workspace, recursively. Includes generated run
    artifacts (synth_runs/, sim_runs/, orfs_*), so on a worked-on design this is
    long. Use it to discover what exists; get_manifest is the design-file list.
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

# New Google XLS / DSLX HLS tools
@tool(parse_docstring=True)
@policy(category="hls", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def run_dslx_interpreter(filename: str) -> str:
    """
    Type-checks a DSLX (.x) source and runs its `#[test]` blocks — the fastest
    way to find out whether DSLX code is valid before compiling it. Writes no
    files.

    Args:
        filename: DSLX file, e.g. 'saturating_add.x'.
    """
    from src.tools.run_xls import run_dslx_interpreter as run_interpreter
    workspace = get_workspace_path()
    result = run_interpreter(filename, cwd=workspace)
    return json.dumps(result, indent=2)

@tool(parse_docstring=True)
@policy(category="hls", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def compile_dslx_to_ir(filename: str, top_module: str) -> str:
    """
    Compiles DSLX to XLS IR. Writes `<top_module>.ir` in the workspace and
    returns it as `ir_filename` — feed that to optimize_xls_ir.
    Step 2 of 4. Use run_xls_flow unless you are debugging one step.

    Args:
        filename: DSLX source file, e.g. 'saturating_add.x'.
        top_module: Top-level DSLX function or proc. Also names the output file.
    """
    from src.tools.run_xls import compile_dslx_to_ir as compile_to_ir
    workspace = get_workspace_path()
    result = compile_to_ir(filename, top_module, cwd=workspace)
    return json.dumps(result, indent=2)

@tool(parse_docstring=True)
@policy(category="hls", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def optimize_xls_ir(ir_filename: str) -> str:
    """
    Runs the XLS IR optimization passes. Writes `<name>.opt.ir` beside the input
    and returns it as `opt_ir_filename` — feed that to codegen_xls or
    benchmark_xls.
    Step 3 of 4. Use run_xls_flow unless you are debugging one step.

    Args:
        ir_filename: IR file from compile_dslx_to_ir, e.g. 'saturating_add.ir'.
    """
    from src.tools.run_xls import optimize_xls_ir as optimize_ir
    workspace = get_workspace_path()
    result = optimize_ir(ir_filename, cwd=workspace)
    return json.dumps(result, indent=2)

@tool(parse_docstring=True)
@policy(category="hls", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def codegen_xls(
    opt_ir_filename: str,
    generator: Literal["combinational", "pipeline"] = "combinational",
    pipeline_stages: int = 0,
    clock_period_ps: int = 0,
    delay_model: Literal["sky130", "asap7", "unit", ""] = "sky130",
    module_name: str = None,
    use_system_verilog: bool = False,
) -> str:
    """
    Schedules optimized XLS IR and emits synthesizable Verilog. Writes
    `<base>.v` in the WORKSPACE ROOT — the input's directory is not preserved —
    and returns `verilog_filename` and `generated_module`.
    Step 4 of 4. Use run_xls_flow unless you are debugging one step.

    Args:
        opt_ir_filename: Optimized IR from optimize_xls_ir.
        generator: 'combinational' emits one cycle of pure logic; 'pipeline'
            inserts registers to meet a timing target.
        pipeline_stages: Pipeline depth. IGNORED unless generator='pipeline'.
        clock_period_ps: Target period in PICOseconds, not nanoseconds. IGNORED
            unless generator='pipeline'.
        delay_model: Timing model used for scheduling: 'sky130', 'asap7',
            'unit', or '' for the tool default. IGNORED unless
            generator='pipeline'.
        module_name: Name for the generated module; defaults to the IR's top.
        use_system_verilog: Emit SystemVerilog. Leave False — the Yosys
            synthesis path downstream expects Verilog.
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

@tool(parse_docstring=True)
@policy(category="hls", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def benchmark_xls(
    opt_ir_filename: str,
    delay_model: Literal["sky130", "asap7", "unit", ""] = "sky130",
) -> str:
    """
    Estimates area and estimated critical-path delay for optimized XLS IR
    without running synthesis — a fast way to compare two DSLX formulations.
    Writes nothing, and is NOT part of run_xls_flow; call it separately.

    Args:
        opt_ir_filename: Optimized IR from optimize_xls_ir, or run_xls_flow's
            artifacts.opt_ir_file.
        delay_model: 'sky130', 'asap7', 'unit', or '' for the tool default.
    """
    from src.tools.run_xls import benchmark_xls as run_benchmark
    workspace = get_workspace_path()
    result = run_benchmark(opt_ir_filename, delay_model=delay_model, cwd=workspace)
    return json.dumps(result, indent=2)

@tool(parse_docstring=True)
@policy(category="hls", protected=True, mutates=True, async_job=False,
        surfaces=ALL_SURFACES, requires_session=True)
def run_xls_flow(
    dslx_file: str,
    top_module: str,
    generator: Literal["combinational", "pipeline"] = "combinational",
    pipeline_stages: int = 0,
    clock_period_ps: int = 0,
    delay_model: Literal["sky130", "asap7", "unit", ""] = "sky130",
    module_name: str = None,
    keep_intermediates: bool = True,
    run_lint: bool = True,
    use_system_verilog: bool = False,
) -> str:
    """
    Compiles DSLX to synthesizable Verilog end to end: interpreter and #[test]
    checks -> IR -> optimization -> codegen -> optional lint. The preferred XLS
    path; the four single-step tools are its stages, exposed for debugging one
    of them.
    Suits algorithmic and datapath kernels — arithmetic, bit manipulation,
    encoders/decoders, fixed-point math, filters. Treat the result as compiler
    output: wrap it in a small adapter module rather than hand-editing it, then
    verify it through the normal linter_tool / simulation flow. Returns the
    artifacts, the generated module name, and per-stage results.

    Args:
        dslx_file: DSLX source, e.g. 'saturating_add.x'.
        top_module: Top-level DSLX function or proc.
        generator: 'combinational' or 'pipeline'.
        pipeline_stages: Pipeline depth. Ignored unless generator='pipeline'.
        clock_period_ps: Target period in PICOseconds. Ignored unless
            generator='pipeline'.
        delay_model: 'sky130', 'asap7', 'unit' or ''. Ignored unless
            generator='pipeline'.
        module_name: Name for the generated module; defaults to top_module.
        keep_intermediates: Keep the .ir and .opt.ir artifacts for provenance.
        run_lint: Lint the generated Verilog before returning success.
        use_system_verilog: Emit SystemVerilog. Leave False for the Yosys path.
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

# =============================================================================
# Session tools — the bootstrap of the MCP surface
# =============================================================================
# These six were hand-written ``Tool(name=..., inputSchema={...})`` objects in
# mcp_server.py: advertised to every MCP client, but invisible to
# build_catalog(), to @policy, to the drift guard and to the schema tests that
# cover every other tool. Their schemas were maintained by hand, which is the
# one thing this repo does not do. They are ordinary registry tools now.
#
# The only thing that makes them special is WHEN they run: a session tool is
# what a stranger calls BEFORE any session exists. So they declare
# ``requires_session=False``, and the MCP server's session gate reads that
# field rather than a list of names it keeps itself.
#
# They also need something no other tool needs — the host that owns the
# active-session pointer: its SessionManager, the caller's scoped identity, its
# workspace resolver (logical on self-host, hydrated on hosted) and the
# architect prompt. That host binds itself for the duration of a call through
# ``session_host()`` below. A ContextVar, not a module global, because the
# hosted server multiplexes tenants: two concurrent calls must never see each
# other's host.
#
# The host contract, in full (mcp_server.RTLDesignMCPServer is the only
# implementation):
#   session_manager               -> SessionManager
#   current_session               -> the active session id, readable AND writable
#   scoped_user_id()              -> the caller's tenant id (None on self-host)
#   workspace_path(session_id)    -> that session's workspace path
#   architect_prompt()            -> (prompt_text, source_label, version)

_SESSION_HOST: ContextVar = ContextVar("siliconcrew_session_host", default=None)


@contextmanager
def session_host(host):
    """Bind ``host`` as the owner of the active session for the calls inside."""
    token = _SESSION_HOST.set(host)
    try:
        yield host
    finally:
        _SESSION_HOST.reset(token)


def visible_session(host) -> Optional[str]:
    """The active session id THIS caller is entitled to see, or ``None``.

    ``host.current_session`` is a PROCESS-GLOBAL pointer, and on hosted the
    streamable-HTTP transport multiplexes many tenants through one process. A
    sessionless tool that reads it directly therefore reports whatever the most
    recent tenant selected — their session id, their workspace path, their
    metadata — to whoever asks next. The regular tool path re-verifies ownership
    before acting, but sessionless tools dispatch *before* that check, which is
    the whole point of them, so they have to do it themselves.

    ``owns_session`` covers both modes by design: a ``None`` user id is
    self-host, where any existing session belongs to the single local user.

    Fails CLOSED. If ownership cannot be established for any reason, the caller
    sees no active session rather than someone else's.
    """
    sid = getattr(host, "current_session", None)
    if not sid:
        return None
    try:
        if host.session_manager.owns_session(sid, host.scoped_user_id()):
            return sid
    except Exception:
        return None
    return None


def _host():
    host = _SESSION_HOST.get()
    if host is None:
        raise RuntimeError(
            "no session host is bound: the session tools run only where something "
            "owns the active-session pointer (mcp_server binds itself with "
            "session_host())"
        )
    return host


@tool(parse_docstring=True)
@policy(category="session", protected=False, mutates=False, async_job=False,
        surfaces=("mcp",), requires_session=False, disabled_when_bound=True)
def create_session_tool(session_name: str, model_name: Optional[str] = "claude-via-mcp",
                        project_id: Optional[str] = "") -> str:
    """Create a new isolated session workspace for a design project.

    Args:
        session_name: Name for the design, such as 'counter_design'. One session
            holds one design block.
        model_name: Label for the model driving the session, recorded with it
            for usage tracking.
        project_id: Optional id of an existing project to group this session
            under. The project must already exist; leave empty for none.
    """
    host = _host()
    try:
        session_id = host.session_manager.create_session(
            # A client sending JSON null for an optional field means "no value",
            # not "the literal None" — coerce rather than reject. This is the
            # FIRST call the server's own instructions tell a stranger to make.
            tag=session_name, model_name=model_name or "claude-via-mcp",
            project_id=project_id or None,
            user_id=host.scoped_user_id(),
        )
        host.current_session = session_id
        workspace = host.workspace_path(session_id)
        project_line = f"\nProject: {project_id}" if project_id else ""
        return (
            f"✅ Created session '{session_id}'\nWorkspace: {workspace}{project_line}\n"
            "This session is now active."
        )
    except FileExistsError:
        return f"❌ Session '{session_name}' already exists. Use set_active_session to switch to it."
    except Exception as e:
        return f"❌ Error creating session: {str(e)}"


@tool(parse_docstring=True)
@policy(category="session", protected=False, mutates=False, async_job=False,
        surfaces=("mcp",), requires_session=False, disabled_when_bound=True)
def list_sessions_tool() -> str:
    """List all available sessions with metadata."""
    host = _host()
    # Tenant scope (F1): pass the caller's scoped uid so hosted users see
    # ONLY their own sessions. Self-host uid is None → full list (parity
    # with the resource path and set_active_session's ownership check).
    uid = host.scoped_user_id()
    sessions = host.session_manager.get_all_sessions(user_id=uid)
    if not sessions:
        return "No sessions found. Create one with create_session_tool."

    session_list = []
    for session_id in sessions:
        meta = host.session_manager.get_session_metadata(session_id, user_id=uid)
        is_current = "← ACTIVE" if session_id == host.current_session else ""
        session_list.append({
            "id": session_id,
            "model": meta.get("model_name") if meta else "unknown",
            "created": str(meta.get("created_at")) if meta else "unknown",
            "tokens": meta.get("total_tokens", 0) if meta else 0,
            "active": is_current,
        })
    return json.dumps(session_list, indent=2)


@tool(parse_docstring=True)
@policy(category="session", protected=False, mutates=False, async_job=False,
        surfaces=("mcp",), requires_session=False, disabled_when_bound=True)
def set_active_session(session_id: str) -> str:
    """Switch to a different session. All tools will use that session's workspace.

    Args:
        session_id: Id of the session to activate, as reported by
            list_sessions_tool.
    """
    host = _host()
    # Tenant check: only switch to a session the caller owns (self-host
    # uid is None → any existing session).
    if not host.session_manager.owns_session(session_id, host.scoped_user_id()):
        return f"❌ Session '{session_id}' not found."
    workspace = host.workspace_path(session_id)

    host.current_session = session_id
    return (
        f"✅ Switched to session '{session_id}'\nWorkspace: {workspace}\n"
        "All tools will now use this workspace."
    )


@tool(parse_docstring=True)
@policy(category="session", protected=False, mutates=False, async_job=False,
        surfaces=("mcp",), requires_session=False)
def get_current_session() -> str:
    """Get the currently active session ID and workspace path."""
    host = _host()
    sid = visible_session(host)
    if not sid:
        return "No active session. Load a prompt or call create_session_tool."

    info = {
        "session_id": sid,
        "workspace": host.workspace_path(sid),
        "metadata": host.session_manager.get_session_metadata(sid),
    }
    return json.dumps(info, indent=2, default=str)


@tool(parse_docstring=True)
@policy(category="session", protected=False, mutates=False, async_job=False,
        surfaces=("mcp",), requires_session=False, disabled_when_bound=True)
def delete_session_tool(session_id: str) -> str:
    """Delete a session and all its workspace files.

    Args:
        session_id: Id of the session to delete. It must not be the active one;
            switch away first with set_active_session.
    """
    host = _host()
    if session_id == host.current_session:
        return "❌ Cannot delete active session. Switch to another session first."

    try:
        # Tenant scope (F1): pass the caller's scoped uid so the ownership guard
        # in delete_session fires. Without it a hosted user could rmtree ANY
        # tenant's workspace/chats/checkpoints by id.
        host.session_manager.delete_session(session_id, user_id=host.scoped_user_id())
        return f"✅ Deleted session '{session_id}' and all its files."
    except PermissionError:
        # Do not leak the existence of another tenant's session.
        return f"❌ Session '{session_id}' not found."
    except Exception as e:
        return f"❌ Error deleting session: {str(e)}"


@tool(parse_docstring=True)
@policy(category="session", protected=False, mutates=False, async_job=False,
        surfaces=("codex",), requires_session=False)
def inject_architect_prompt(session_id: Optional[str] = "") -> str:
    """Return the configured Architect prompt for Codex clients. Optional session_id also sets active session/workspace.

    Args:
        session_id: Existing session to activate before returning the prompt.
            Leave empty to keep whichever session is already active.
    """
    host = _host()
    workspace = None

    if session_id:
        if not host.session_manager.owns_session(session_id, host.scoped_user_id()):
            return f"❌ Session '{session_id}' not found."
        workspace = host.workspace_path(session_id)
        host.current_session = session_id
    else:
        # No session named: fall back to the active one ONLY if this caller owns
        # it. Reading the process-global pointer here is how tenant B learned
        # tenant A's session id and workspace path.
        session_id = visible_session(host)
        if session_id:
            workspace = host.workspace_path(session_id)

    prompt_text, prompt_source, resolved_version = host.architect_prompt()
    payload = f"{prompt_text}"
    if session_id and workspace:
        payload += (
            "\n\n---\n"
            f"CURRENT_SESSION: {session_id}\n"
            f"WORKSPACE: {workspace}\n"
            f"PROMPT_VERSION: {resolved_version}\n"
            f"PROMPT_SOURCE: {prompt_source}\n"
            "All tool calls should operate inside this workspace."
        )
    else:
        payload += (
            "\n\n---\n"
            f"PROMPT_VERSION: {resolved_version}\n"
            f"PROMPT_SOURCE: {prompt_source}\n"
        )

    return payload


# =============================================================================
# The registry
# =============================================================================
# ONE list of the tools that exist, in the order clients see them. Which
# surfaces each one reaches is NOT restated here — it is read off the tool's
# own policy, so a tool can never be in a list its policy contradicts.
ALL_TOOLS = [
    # Session tools — a stranger's first call, so they lead the advertised list
    create_session_tool,
    list_sessions_tool,
    set_active_session,
    get_current_session,
    delete_session_tool,
    inject_architect_prompt,
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
    generate_report_tool,
    # Analysis (local-only Python analysis tool)
    run_python_analysis,
    # Google XLS HLS tools
    run_dslx_interpreter,
    compile_dslx_to_ir,
    optimize_xls_ir,
    codegen_xls,
    benchmark_xls,
    run_xls_flow,
]


def tool_policy(t) -> ToolPolicy:
    """The policy declared on a registry tool. Raises for a tool without one —
    there is no permissive default, by design."""
    p = getattr(getattr(t, "func", None), "__tool_policy__", None)
    if p is None:
        raise ValueError(
            f"tool '{getattr(t, 'name', t)}' declares no @policy — every tool must "
            "(see ToolPolicy above)"
        )
    return p


def tools_on_surface(surface: str) -> list:
    """Registry order, filtered by the tools' own declared surfaces."""
    if surface not in SURFACE_NAMES:
        raise ValueError(f"unknown surface {surface!r}; known: {sorted(SURFACE_NAMES)}")
    return [t for t in ALL_TOOLS if surface in tool_policy(t).surfaces]


# Tools exposed over MCP (no blocking wait tool for the UI; see each policy).
# Includes the session tools, which no other surface offers.
mcp_tools = tools_on_surface("mcp")

# Tools bound to the in-process architect agent.
# One async contract everywhere: the architect polls with bounded
# wait_for_synthesis loops — no start+wait combo tool (Wave 9).
architect_tools = tools_on_surface("agent")
