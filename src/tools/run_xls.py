"""
Google XLS / DSLX tool execution helpers.

This module intentionally keeps the XLS integration as a frontend compiler:
DSLX -> XLS IR -> optimized XLS IR -> generated Verilog.  SiliconCrew's
existing Verilog lint, simulation, synthesis, and reporting tools remain the
downstream flow.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from src.platform_engines.tool_engine import get_tool_engine
from src.tools.run_linter import run_linter

XLS_IMAGE = os.environ.get("XLS_DOCKER_IMAGE", "siliconcrew-xls:latest")
# Hard ceiling for an XLS stage (compiles are fast). Preserves the prior implicit
# run_docker_command default while bounding native runs.
XLS_TIMEOUT = int(os.environ.get("XLS_TIMEOUT", "3600"))


def _xls_run(command: str, workspace: str) -> Dict[str, Any]:
    """Execute one XLS command through the selected ToolEngine.

    The command is cwd-relative (no ``/workspace`` paths), so it runs the same
    whether the docker engine mounts ``workspace`` at ``/workspace`` or the
    native engine runs directly in ``workspace``. Binaries (interpreter_main,
    ir_converter_main, opt_main, codegen_main, benchmark_main, xlscc) come from
    the XLS image (docker) or PATH (native / hosted image).
    """
    return get_tool_engine().run(
        image=XLS_IMAGE, command=command, cwd=workspace, timeout=XLS_TIMEOUT, name_prefix="sc_xls"
    )

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_RELATIVE_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
_MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_VALID_GENERATORS = {"combinational", "pipeline"}
_VALID_DELAY_MODELS = {"", "unit", "asap7", "sky130"}


def _failure(stage: str, message: str, command: str = "") -> Dict[str, Any]:
    return {
        "success": False,
        "stage": stage,
        "stdout": "",
        "stderr": message,
        "command": command,
    }


def _with_stage(result: Dict[str, Any], stage: str) -> Dict[str, Any]:
    result.setdefault("stdout", "")
    result.setdefault("stderr", "")
    result.setdefault("command", "")
    result["stage"] = stage
    return result


def validate_safe_relative_path(filename: str) -> str:
    """
    Validate a workspace-relative artifact path.

    Accepted examples:
      - design.x
      - kernels/design.x

    Rejected examples:
      - ../design.x
      - /tmp/design.x
      - C:/tmp/design.x
      - design.x; rm -rf /
    """
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Filename cannot be empty.")

    raw = filename.strip().replace("\\", "/")
    if not _SAFE_RELATIVE_PATH_RE.match(raw):
        raise ValueError(f"Invalid path characters detected: '{filename}'")
    if raw.startswith("/") or os.path.isabs(filename) or ":" in raw:
        raise ValueError(f"Absolute path or drive letter detected: '{filename}'")

    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Path traversal detected: '{filename}'")

    normalized = os.path.normpath(raw).replace("\\", "/")
    if normalized.startswith("../") or normalized == "..":
        raise ValueError(f"Path traversal detected: '{filename}'")
    return normalized


def validate_identifier(value: str, label: str = "identifier") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be empty.")
    value = value.strip()
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid {label}: '{value}'. Use a Verilog/XLS identifier.")
    return value


def validate_generator(generator: str) -> str:
    generator = (generator or "combinational").strip()
    if generator not in _VALID_GENERATORS:
        raise ValueError(f"Invalid generator '{generator}'. Use 'combinational' or 'pipeline'.")
    return generator


def validate_nonnegative_int(value: Any, label: str) -> int:
    try:
        number = int(value or 0)
    except Exception as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if number < 0:
        raise ValueError(f"{label} must be non-negative.")
    return number


def validate_delay_model(delay_model: Optional[str]) -> str:
    value = (delay_model or "").strip()
    if value not in _VALID_DELAY_MODELS:
        allowed = ", ".join(sorted(x or "<empty>" for x in _VALID_DELAY_MODELS))
        raise ValueError(f"Invalid delay_model '{value}'. Allowed values: {allowed}.")
    return value


def _ensure_workspace(cwd: Optional[str]) -> str:
    if not cwd:
        raise ValueError("Workspace path is required.")
    workspace = os.path.abspath(cwd)
    os.makedirs(workspace, exist_ok=True)
    return workspace


def _artifact_path(cwd: str, rel_path: str) -> str:
    return os.path.join(cwd, rel_path.replace("/", os.sep))


def _artifact_exists(cwd: str, rel_path: Optional[str]) -> bool:
    return bool(rel_path) and os.path.exists(_artifact_path(cwd, rel_path))


def extract_module_name(verilog_content: str) -> str:
    """Extract the first Verilog module name from generated text."""
    match = _MODULE_RE.search(verilog_content or "")
    return match.group(1) if match else "unknown"


def _read_generated_module(cwd: str, verilog_filename: str) -> str:
    path = _artifact_path(cwd, verilog_filename)
    if not os.path.exists(path):
        return "unknown"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return extract_module_name(f.read())


def run_dslx_interpreter(filename: str, cwd: str) -> Dict[str, Any]:
    """Run DSLX syntax checks and built-in #[test] tests."""
    try:
        workspace = _ensure_workspace(cwd)
        safe_file = validate_safe_relative_path(filename)
    except ValueError as exc:
        return _failure("interpreter", str(exc))

    if not _artifact_exists(workspace, safe_file):
        return _failure("interpreter", f"DSLX file not found: {safe_file}")

    result = _xls_run(f"interpreter_main {safe_file}", workspace)
    result["dslx_file"] = safe_file
    return _with_stage(result, "interpreter")


def compile_dslx_to_ir(filename: str, top_module: str, cwd: str) -> Dict[str, Any]:
    """Compile DSLX source to XLS IR."""
    try:
        workspace = _ensure_workspace(cwd)
        safe_file = validate_safe_relative_path(filename)
        safe_top = validate_identifier(top_module, "top_module")
    except ValueError as exc:
        return _failure("ir_conversion", str(exc))

    if not _artifact_exists(workspace, safe_file):
        return _failure("ir_conversion", f"DSLX file not found: {safe_file}")

    out_ir = f"{safe_top}.ir"
    result = _xls_run(f"ir_converter_main --top={safe_top} {safe_file} > {out_ir}", workspace)
    result["dslx_file"] = safe_file
    result["top_module"] = safe_top
    result["ir_filename"] = out_ir if result.get("success") else None
    return _with_stage(result, "ir_conversion")


def experimental_compile_cpp_to_ir(
    filename: str,
    top_name: str,
    block_from_class: bool = False,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compile C++ to XLS IR via xlscc.

    This is intentionally labeled experimental.  SiliconCrew's primary HLS
    frontend is DSLX; C++ support should not be the default agent path.
    """
    try:
        workspace = _ensure_workspace(cwd)
        safe_file = validate_safe_relative_path(filename)
        safe_top = validate_identifier(top_name, "top_name")
    except ValueError as exc:
        return _failure("cpp_ir_conversion", str(exc))

    if not _artifact_exists(workspace, safe_file):
        return _failure("cpp_ir_conversion", f"C++ file not found: {safe_file}")

    out_ir = f"{safe_top}.ir"
    args = [f"--top={safe_top}"]
    if bool(block_from_class):
        args.append("--block_from_class")

    result = _xls_run(f"xlscc {' '.join(args)} {safe_file} > {out_ir}", workspace)
    result["source_file"] = safe_file
    result["top_name"] = safe_top
    result["ir_filename"] = out_ir if result.get("success") else None
    return _with_stage(result, "cpp_ir_conversion")


def optimize_xls_ir(ir_filename: str, cwd: str) -> Dict[str, Any]:
    """Run XLS IR optimization passes."""
    try:
        workspace = _ensure_workspace(cwd)
        safe_ir = validate_safe_relative_path(ir_filename)
    except ValueError as exc:
        return _failure("optimization", str(exc))

    if not _artifact_exists(workspace, safe_ir):
        return _failure("optimization", f"IR file not found: {safe_ir}")

    base_name = os.path.splitext(safe_ir)[0]
    out_opt_ir = f"{base_name}.opt.ir"
    result = _xls_run(f"opt_main {safe_ir} > {out_opt_ir}", workspace)
    result["ir_filename"] = safe_ir
    result["opt_ir_filename"] = out_opt_ir if result.get("success") else None
    return _with_stage(result, "optimization")


def codegen_xls(
    opt_ir_filename: str,
    generator: str = "combinational",
    pipeline_stages: int = 0,
    clock_period_ps: int = 0,
    delay_model: str = "sky130",
    module_name: Optional[str] = None,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate Verilog/SystemVerilog from optimized XLS IR."""
    try:
        workspace = _ensure_workspace(cwd)
        safe_opt_ir = validate_safe_relative_path(opt_ir_filename)
        safe_generator = validate_generator(generator)
        safe_pipeline_stages = validate_nonnegative_int(pipeline_stages, "pipeline_stages")
        safe_clock_period_ps = validate_nonnegative_int(clock_period_ps, "clock_period_ps")
        safe_delay_model = validate_delay_model(delay_model)
        safe_module_name = validate_identifier(module_name, "module_name") if module_name else None
    except ValueError as exc:
        return _failure("codegen", str(exc))

    if not _artifact_exists(workspace, safe_opt_ir):
        return _failure("codegen", f"Optimized IR file not found: {safe_opt_ir}")

    base_name = os.path.basename(os.path.splitext(safe_opt_ir)[0].split(".")[0])
    out_v = f"{base_name}.v"

    args = [f"--generator={safe_generator}"]
    if safe_generator == "pipeline":
        if safe_pipeline_stages > 0:
            args.append(f"--pipeline_stages={safe_pipeline_stages}")
        if safe_clock_period_ps > 0:
            args.append(f"--clock_period_ps={safe_clock_period_ps}")
        if safe_delay_model:
            args.append(f"--delay_model={safe_delay_model}")
    if safe_module_name:
        args.append(f"--module_name={safe_module_name}")

    result = _xls_run(f"codegen_main {' '.join(args)} {safe_opt_ir} > {out_v}", workspace)
    result["opt_ir_filename"] = safe_opt_ir
    result["generator"] = safe_generator
    result["pipeline_stages"] = safe_pipeline_stages
    result["clock_period_ps"] = safe_clock_period_ps
    result["delay_model"] = safe_delay_model
    if result.get("success"):
        result["verilog_filename"] = out_v
        result["generated_module"] = _read_generated_module(workspace, out_v)
    else:
        result["verilog_filename"] = None
        result["generated_module"] = None
    return _with_stage(result, "codegen")


def benchmark_xls(opt_ir_filename: str, delay_model: str = "sky130", cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run optional XLS IR benchmarking."""
    try:
        workspace = _ensure_workspace(cwd)
        safe_opt_ir = validate_safe_relative_path(opt_ir_filename)
        safe_delay_model = validate_delay_model(delay_model)
    except ValueError as exc:
        return _failure("benchmark", str(exc))

    if not _artifact_exists(workspace, safe_opt_ir):
        return _failure("benchmark", f"Optimized IR file not found: {safe_opt_ir}")

    args = []
    if safe_delay_model:
        args.append(f"--delay_model={safe_delay_model}")
    args.append(safe_opt_ir)
    result = _xls_run(f"benchmark_main {' '.join(args)}", workspace)
    result["opt_ir_filename"] = safe_opt_ir
    result["delay_model"] = safe_delay_model
    return _with_stage(result, "benchmark")


def _lint_generated_verilog(cwd: str, verilog_filename: str) -> Dict[str, Any]:
    path = _artifact_path(cwd, verilog_filename)
    if not os.path.exists(path):
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Generated Verilog file not found: {verilog_filename}",
            "command": "",
        }
    return run_linter([path], cwd=cwd)


def run_xls_flow(
    dslx_file: str,
    top_module: str,
    generator: str = "combinational",
    pipeline_stages: int = 0,
    clock_period_ps: int = 0,
    delay_model: str = "sky130",
    module_name: Optional[str] = None,
    cwd: Optional[str] = None,
    keep_intermediates: bool = True,
    run_lint: bool = True,
) -> Dict[str, Any]:
    """
    Execute the preferred SiliconCrew XLS frontend path.

    Stages:
      1. DSLX interpreter/tests
      2. DSLX -> XLS IR
      3. XLS IR optimization
      4. XLS codegen -> Verilog
      5. Optional Icarus Verilog lint of generated RTL
    """
    try:
        workspace = _ensure_workspace(cwd)
    except ValueError as exc:
        return _failure("setup", str(exc))

    artifacts: Dict[str, Optional[str]] = {
        "dslx_file": None,
        "ir_file": None,
        "opt_ir_file": None,
        "verilog_file": None,
    }

    interp = run_dslx_interpreter(dslx_file, cwd=workspace)
    artifacts["dslx_file"] = interp.get("dslx_file")
    if not interp.get("success"):
        return {
            **_failure("interpreter", interp.get("stderr", ""), interp.get("command", "")),
            "artifacts": artifacts,
            "stage_results": {"interpreter": interp},
            "next_action": "Fix DSLX syntax or failing #[test] blocks, then rerun run_xls_flow.",
        }

    ir_comp = compile_dslx_to_ir(dslx_file, top_module, cwd=workspace)
    artifacts["ir_file"] = ir_comp.get("ir_filename")
    if not ir_comp.get("success"):
        return {
            **_failure("ir_conversion", ir_comp.get("stderr", ""), ir_comp.get("command", "")),
            "artifacts": artifacts,
            "stage_results": {"interpreter": interp, "ir_conversion": ir_comp},
            "next_action": "Fix the top function name or DSLX constructs unsupported by IR conversion.",
        }

    opt = optimize_xls_ir(ir_comp["ir_filename"], cwd=workspace)
    artifacts["opt_ir_file"] = opt.get("opt_ir_filename")
    if not opt.get("success"):
        if not keep_intermediates and artifacts["ir_file"]:
            _safe_remove(workspace, artifacts["ir_file"])
        return {
            **_failure("optimization", opt.get("stderr", ""), opt.get("command", "")),
            "artifacts": artifacts,
            "stage_results": {"interpreter": interp, "ir_conversion": ir_comp, "optimization": opt},
            "next_action": "Inspect XLS optimization error; simplify the DSLX or lower-level IR path.",
        }

    codegen = codegen_xls(
        opt_ir_filename=opt["opt_ir_filename"],
        generator=generator,
        pipeline_stages=pipeline_stages,
        clock_period_ps=clock_period_ps,
        delay_model=delay_model,
        module_name=module_name,
        cwd=workspace,
    )
    artifacts["verilog_file"] = codegen.get("verilog_filename")

    if not keep_intermediates:
        for temp_file in [artifacts["ir_file"], artifacts["opt_ir_file"]]:
            if temp_file:
                _safe_remove(workspace, temp_file)
                if temp_file == artifacts["ir_file"]:
                    artifacts["ir_file"] = None
                if temp_file == artifacts["opt_ir_file"]:
                    artifacts["opt_ir_file"] = None

    if not codegen.get("success"):
        return {
            **_failure("codegen", codegen.get("stderr", ""), codegen.get("command", "")),
            "artifacts": artifacts,
            "stage_results": {
                "interpreter": interp,
                "ir_conversion": ir_comp,
                "optimization": opt,
                "codegen": codegen,
            },
            "next_action": "Adjust XLS codegen options or simplify DSLX, then rerun run_xls_flow.",
        }

    lint_result = None
    if bool(run_lint):
        lint_result = _lint_generated_verilog(workspace, codegen["verilog_filename"])
        if not lint_result.get("success"):
            return {
                "success": False,
                "stage": "verilog_lint",
                "stdout": lint_result.get("stdout", ""),
                "stderr": lint_result.get("stderr", ""),
                "command": lint_result.get("command", ""),
                "artifacts": artifacts,
                "verilog_filename": codegen["verilog_filename"],
                "generated_module": codegen["generated_module"],
                "stage_results": {
                    "interpreter": interp,
                    "ir_conversion": ir_comp,
                    "optimization": opt,
                    "codegen": codegen,
                    "verilog_lint": lint_result,
                },
                "next_action": "Inspect generated Verilog lint failure; use a wrapper or adjust XLS codegen options.",
            }

    return {
        "success": True,
        "stage": "completed",
        "artifacts": artifacts,
        "verilog_filename": codegen["verilog_filename"],
        "generated_module": codegen["generated_module"],
        "generator": codegen["generator"],
        "pipeline_stages": codegen["pipeline_stages"],
        "clock_period_ps": codegen["clock_period_ps"],
        "stage_results": {
            "interpreter": interp,
            "ir_conversion": ir_comp,
            "optimization": opt,
            "codegen": codegen,
            "verilog_lint": lint_result,
        },
        "stdout": codegen.get("stdout", ""),
        "stderr": codegen.get("stderr", ""),
        "command": codegen.get("command", ""),
        "next_action": (
            f"Use generated_module='{codegen['generated_module']}' for direct lint/synthesis, "
            "or write a wrapper if the benchmark/spec expects a different module signature."
        ),
    }


def _safe_remove(cwd: str, rel_path: str) -> None:
    try:
        os.remove(_artifact_path(cwd, rel_path))
    except Exception:
        pass
