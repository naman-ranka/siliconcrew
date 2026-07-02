"""Curated user-initiated tool invocation — the Command Surface's backend.

The v2 Command Surface lets an engineer run ANY catalogued tool directly
(metrics, stage reports, DRC/CTS/congestion summaries, log search, waveform
reads, schematic, cocotb/SBY, XLS flow) — not just the four core flow actions.
Those tools already exist as plain functions under ``src/tools`` (the same
functions the agent's @tool wrappers call); this module gives them one REST
door with a **fixed allowlist**, per-tool argument adaptation, and the same
per-session event logging as every other invocation path.

Deliberately NOT a generic RPC: only registered tools run, each adapter picks
exactly the arguments it accepts (unknown args are dropped), and file-path
arguments are containment-checked against the workspace.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from src.utils.paths import is_within
from src.tools import manifest as manifest_mod
from src.tools.read_waveform import read_waveform
from src.tools.generate_schematic import generate_schematic
from src.tools.search_logs import search_logs
from src.tools.design_report import save_design_report, save_metrics
from src.tools.synthesis_manager import (
    compare_pd_runs,
    get_congestion_summary,
    get_cts_summary,
    get_route_drc_summary,
    get_stage_status,
    get_synthesis_metrics,
    read_stage_report,
)


class InvokeError(Exception):
    """Tool-level rejection with a stable error code (mapped to a 4xx envelope)."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _require(args: Dict[str, Any], key: str) -> Any:
    val = args.get(key)
    if val is None or val == "" or val == []:
        raise InvokeError("missing_arg", f"'{key}' is required.")
    return val


def _workspace_file(workspace: str, rel: str) -> str:
    """Resolve a caller-supplied path inside the workspace or refuse."""
    path = os.path.join(workspace, rel)
    if not is_within(workspace, path):
        raise InvokeError("invalid_path", f"Path escapes the workspace: {rel}", status=404)
    if not os.path.exists(path):
        raise InvokeError("not_found", f"File not found: {rel}", status=404)
    return path


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[[str, str, Dict[str, Any]], Any]  # (workspace, session_id, args) -> result
    signed_in: bool = False  # requires a non-anonymous identity
    mutates: bool = False    # workspace must sync back afterwards (hosted)


def _num(args: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(args.get(key, default))
    except (TypeError, ValueError):
        return default


# --- adapters ---------------------------------------------------------------

def _waveform(workspace: str, _sid: str, a: Dict[str, Any]) -> Any:
    vcd = _workspace_file(workspace, str(_require(a, "vcd_file")))
    signals = _require(a, "signals")
    if not isinstance(signals, list):
        raise InvokeError("bad_arg", "'signals' must be a list of signal names.")
    return read_waveform(vcd, [str(s) for s in signals], int(_num(a, "start_time", 0)), int(_num(a, "end_time", 1000)))


def _schematic(workspace: str, _sid: str, a: Dict[str, Any]) -> Any:
    verilog = str(_require(a, "verilog_file"))
    _workspace_file(workspace, verilog)
    top = str(_require(a, "top_module"))
    return generate_schematic(verilog, top, cwd=workspace)


def _save_metrics(workspace: str, _sid: str, a: Dict[str, Any]) -> Any:
    metric_keys = ("wns_ns", "tns_ns", "area_um2", "cell_count", "power_uw", "power_mw", "fmax_mhz")
    metrics = {k: a[k] for k in metric_keys if a.get(k) is not None}
    if not metrics:
        raise InvokeError("missing_arg", "At least one metric value is required.")
    return save_metrics(workspace, metrics, run_id=a.get("run_id") or None)


def _cocotb(workspace: str, sid: str, a: Dict[str, Any]) -> Any:
    from src.tools.run_cocotb import run_cocotb

    manifest = manifest_mod.read_manifest(workspace, sid)
    files = manifest_mod.files_for_stage(manifest, "simulate")
    rtl = [f for f in files if f.lower().endswith((".v", ".sv"))]
    if not rtl:
        raise InvokeError("no_files", "Manifest has no RTL/testbench files.")
    return run_cocotb(
        [os.path.join(workspace, f) for f in rtl],
        toplevel=str(a.get("top_module") or manifest.synthTop or ""),
        python_module=str(_require(a, "python_module")),
        cwd=workspace,
    )


def _sby(workspace: str, _sid: str, a: Dict[str, Any]) -> Any:
    from src.tools.run_sby import run_sby

    sby = _workspace_file(workspace, str(_require(a, "sby_file")))
    return run_sby(sby, cwd=workspace)


def _xls_flow(workspace: str, _sid: str, a: Dict[str, Any]) -> Any:
    from src.tools.run_xls import run_xls_flow

    return run_xls_flow(
        dslx_file=str(_require(a, "dslx_file")),
        top_module=str(_require(a, "top_module")),
        generator=str(a.get("generator") or "combinational"),
        pipeline_stages=int(_num(a, "pipeline_stages", 0)),
        clock_period_ps=int(_num(a, "clock_period_ps", 0)),
        delay_model=str(a.get("delay_model") or "sky130"),
        use_system_verilog=bool(a.get("use_system_verilog", False)),
        cwd=workspace,
    )


TOOL_REGISTRY: Dict[str, ToolSpec] = {
    # -- analysis over existing runs (read-only) --
    "get_synthesis_metrics": ToolSpec(lambda w, s, a: get_synthesis_metrics(workspace=w, run_id=str(_require(a, "run_id")))),
    "get_stage_status": ToolSpec(lambda w, s, a: get_stage_status(workspace=w, run_id=str(_require(a, "run_id")))),
    "read_stage_report": ToolSpec(lambda w, s, a: read_stage_report(w, str(_require(a, "stage")), run_id=a.get("run_id") or None)),
    "get_route_drc_summary": ToolSpec(lambda w, s, a: get_route_drc_summary(w, run_id=a.get("run_id") or None)),
    "get_cts_summary": ToolSpec(lambda w, s, a: get_cts_summary(w, run_id=a.get("run_id") or None)),
    "get_congestion_summary": ToolSpec(lambda w, s, a: get_congestion_summary(w, run_id=a.get("run_id") or None)),
    "compare_pd_runs": ToolSpec(lambda w, s, a: compare_pd_runs(w, str(_require(a, "child_run_id")), parent_run_id=a.get("parent_run_id") or None)),
    "search_logs_tool": ToolSpec(lambda w, s, a: search_logs(str(_require(a, "query")), workspace_dir=w, run_id=a.get("run_id") or None)),
    "waveform_tool": ToolSpec(_waveform),
    # -- authoring (writes into the workspace) --
    "schematic_tool": ToolSpec(_schematic, mutates=True),
    "generate_report_tool": ToolSpec(lambda w, s, a: save_design_report(w, run_id=a.get("run_id") or None), mutates=True),
    "save_metrics_tool": ToolSpec(_save_metrics, signed_in=True, mutates=True),
    # -- heavy verification / HLS (containerized toolchains; sign-in gated) --
    "cocotb_tool": ToolSpec(_cocotb, signed_in=True, mutates=True),
    "sby_tool": ToolSpec(_sby, signed_in=True, mutates=True),
    "run_xls_flow": ToolSpec(_xls_flow, signed_in=True, mutates=True),
}


def invocable_tools() -> List[str]:
    return sorted(TOOL_REGISTRY)


def run_registered_tool(tool: str, workspace: str, session_id: str, arguments: Optional[Dict[str, Any]]) -> Any:
    """Execute one allowlisted tool. Raises KeyError for unknown tools and
    InvokeError for argument/containment problems; anything else bubbles up
    as the tool's own failure."""
    spec = TOOL_REGISTRY[tool]
    return spec.fn(workspace, session_id, arguments or {})
