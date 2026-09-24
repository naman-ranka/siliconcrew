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
    ir_converter_main, opt_main, codegen_main, benchmark_main) come from
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

    engine = get_tool_engine()
    dslx_path = "/xls" if getattr(engine, "mode", "docker") == "docker" else "/opt/xls"
    result = _xls_run(f"interpreter_main --dslx_path={dslx_path} {safe_file}", workspace)
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
    engine = get_tool_engine()
    dslx_path = "/xls" if getattr(engine, "mode", "docker") == "docker" else "/opt/xls"
    result = _xls_run(f"ir_converter_main --dslx_path={dslx_path} --top={safe_top} {safe_file} > {out_ir}", workspace)
    result["dslx_file"] = safe_file
    result["top_module"] = safe_top
    result["ir_filename"] = out_ir if result.get("success") else None
    return _with_stage(result, "ir_conversion")


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
    use_system_verilog: bool = False,
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
    if not use_system_verilog:
        args.append("--use_system_verilog=false")
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


STOP_AFTER_STAGES = ("interpret", "ir", "opt", "codegen", "lint")


def run_xls_flow(
    dslx_file: Optional[str] = None,
    top_module: Optional[str] = None,
    generator: str = "combinational",
    pipeline_stages: int = 0,
    clock_period_ps: int = 0,
    delay_model: str = "sky130",
    module_name: Optional[str] = None,
    cwd: Optional[str] = None,
    keep_intermediates: bool = True,
    run_lint: bool = True,
    use_system_verilog: bool = False,
    stop_after: str = "lint",
    from_ir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute the SiliconCrew XLS frontend path.

    Stages, in order:
      interpret  DSLX interpreter/tests
      ir         DSLX -> XLS IR
      opt        XLS IR optimization (+ an area/delay estimate, free of charge)
      codegen    XLS codegen -> Verilog
      lint       Icarus Verilog lint of the generated RTL

    ``stop_after`` ends the run after that stage — the debugging path that used
    to be four separate tools. ``from_ir`` enters partway: an IR file skips
    interpret and ir, and an ``.opt.ir`` (this flow's own optimized artifact)
    skips the optimizer too and goes straight to codegen.

    A successful reply's ``stopped_after`` is the stage that actually RAN last,
    not the stage requested — ``run_lint=False`` stops after codegen even with
    ``stop_after='lint'``.
    """
    try:
        workspace = _ensure_workspace(cwd)
    except ValueError as exc:
        return _failure("setup", str(exc))

    if stop_after not in STOP_AFTER_STAGES:
        return _failure(
            "setup",
            f"Invalid stop_after '{stop_after}'. Allowed: {', '.join(STOP_AFTER_STAGES)}.",
        )
    if not from_ir and not dslx_file:
        return _failure("setup", "Pass dslx_file to compile DSLX, or from_ir to enter at the IR.")
    if not from_ir and not top_module:
        return _failure("setup", "top_module is required when compiling DSLX.")

    stage_results: Dict[str, Any] = {}
    artifacts: Dict[str, Optional[str]] = {
        "dslx_file": None,
        "ir_file": None,
        "opt_ir_file": None,
        "verilog_file": None,
    }

    def done(completed: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """A run that stopped where it was asked to stop is a SUCCESS.

        ``stopped_after`` names the stage this run actually COMPLETED, which is
        not always the stage it was asked to stop after: ``run_lint=False`` with
        the default ``stop_after='lint'`` never lints, and reporting "lint" over
        a null ``stage_results.verilog_lint`` reads as generated RTL that WAS
        linted. Each call site passes the stage it just finished, so the field
        cannot drift from what ran.
        """
        result = {
            "success": True,
            "stage": "completed",
            "stopped_after": completed,
            "artifacts": artifacts,
            "stage_results": stage_results,
        }
        result.update(extra or {})
        return result

    # Only artifacts the FLOW created may be cleaned up. A caller-supplied
    # from_ir is an input, and deleting someone's input file because
    # keep_intermediates is False would be destroying evidence, not tidying.
    produced_here: set = set()

    if from_ir:
        # The flow's own optimized artifact is recognised by name — hand back
        # what it produced and it will not redo the optimization.
        already_optimized = from_ir.endswith(".opt.ir")
        artifacts["opt_ir_file" if already_optimized else "ir_file"] = from_ir
        if stop_after in ("interpret", "ir"):
            return _failure(
                "setup",
                f"stop_after='{stop_after}' has nothing to do: from_ir starts after that stage.",
            )
    else:
        interp = run_dslx_interpreter(dslx_file, cwd=workspace)
        artifacts["dslx_file"] = interp.get("dslx_file")
        stage_results["interpreter"] = interp
        if not interp.get("success"):
            return {
                **_failure("interpreter", interp.get("stderr", ""), interp.get("command", "")),
                "artifacts": artifacts,
                "stage_results": stage_results,
                "next_action": "Fix DSLX syntax or failing #[test] blocks, then rerun run_xls_flow.",
            }
        if stop_after == "interpret":
            return done("interpret")

        ir_comp = compile_dslx_to_ir(dslx_file, top_module, cwd=workspace)
        artifacts["ir_file"] = ir_comp.get("ir_filename")
        produced_here.add(artifacts["ir_file"])
        stage_results["ir_conversion"] = ir_comp
        if not ir_comp.get("success"):
            return {
                **_failure("ir_conversion", ir_comp.get("stderr", ""), ir_comp.get("command", "")),
                "artifacts": artifacts,
                "stage_results": stage_results,
                "next_action": "Fix the top function name or DSLX constructs unsupported by IR conversion.",
            }
        if stop_after == "ir":
            return done("ir")

    if not artifacts["opt_ir_file"]:
        opt = optimize_xls_ir(artifacts["ir_file"], cwd=workspace)
        artifacts["opt_ir_file"] = opt.get("opt_ir_filename")
        produced_here.add(artifacts["opt_ir_file"])
        stage_results["optimization"] = opt
        if not opt.get("success"):
            if not keep_intermediates and artifacts["ir_file"] in produced_here:
                _safe_remove(workspace, artifacts["ir_file"])
            return {
                **_failure("optimization", opt.get("stderr", ""), opt.get("command", "")),
                "artifacts": artifacts,
                "stage_results": stage_results,
                "next_action": "Inspect XLS optimization error; simplify the DSLX or lower-level IR path.",
            }

    # Area and estimated critical-path delay for the optimized IR, without
    # running synthesis. This was a tool of its own; it is two numbers about an
    # artifact the flow just produced, so the flow reports them.
    bench = benchmark_xls(artifacts["opt_ir_file"], delay_model=delay_model, cwd=workspace)
    stage_results["benchmark"] = bench
    estimate = {"benchmark": _benchmark_fields(bench)}

    if stop_after == "opt":
        return done("opt", estimate)

    codegen = codegen_xls(
        opt_ir_filename=artifacts["opt_ir_file"],
        generator=generator,
        pipeline_stages=pipeline_stages,
        clock_period_ps=clock_period_ps,
        delay_model=delay_model,
        module_name=module_name,
        use_system_verilog=use_system_verilog,
        cwd=workspace,
    )
    artifacts["verilog_file"] = codegen.get("verilog_filename")
    stage_results["codegen"] = codegen

    if not keep_intermediates:
        for temp_file in [artifacts["ir_file"], artifacts["opt_ir_file"]]:
            if temp_file and temp_file in produced_here:
                _safe_remove(workspace, temp_file)
                if temp_file == artifacts["ir_file"]:
                    artifacts["ir_file"] = None
                if temp_file == artifacts["opt_ir_file"]:
                    artifacts["opt_ir_file"] = None

    if not codegen.get("success"):
        return {
            **_failure("codegen", codegen.get("stderr", ""), codegen.get("command", "")),
            "artifacts": artifacts,
            "stage_results": stage_results,
            **estimate,
            "next_action": "Adjust XLS codegen options or simplify DSLX, then rerun run_xls_flow.",
        }

    generated = {
        "verilog_filename": codegen["verilog_filename"],
        "generated_module": codegen["generated_module"],
        "generator": codegen["generator"],
        "pipeline_stages": codegen["pipeline_stages"],
        "clock_period_ps": codegen["clock_period_ps"],
        "stdout": codegen.get("stdout", ""),
        "stderr": codegen.get("stderr", ""),
        "command": codegen.get("command", ""),
        "next_action": (
            f"Use generated_module='{codegen['generated_module']}' for direct lint/synthesis, "
            "or write a wrapper if the benchmark/spec expects a different module signature."
        ),
    }

    if stop_after == "codegen" or not bool(run_lint):
        # run_lint=False is a supported way to skip lint while stop_after keeps
        # its default: the stage this run finished is codegen, whatever it was
        # asked to stop after.
        stage_results["verilog_lint"] = None
        return done("codegen", {**estimate, **generated})

    lint_result = _lint_generated_verilog(workspace, codegen["verilog_filename"])
    if lint_result.get("unavailable"):
        # No lint engine on this server: nothing was checked, and the generated
        # Verilog is not at fault. Say so and finish at codegen.
        stage_results["verilog_lint"] = {"skipped": lint_result.get("stderr", "no lint engine")}
        return done("codegen", {**estimate, **generated})
    stage_results["verilog_lint"] = lint_result
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
            "stage_results": stage_results,
            **estimate,
            "next_action": "Inspect generated Verilog lint failure; use a wrapper or adjust XLS codegen options.",
        }

    return done("lint", {**estimate, **generated})


_BENCHMARK_LINE = re.compile(
    r"^\s*(Delay|Area|Total delay|Total area|Max reg-to-reg delay)\s*:?\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _benchmark_fields(bench: Dict[str, Any]) -> Dict[str, Any]:
    """The estimate, flattened out of benchmark_main's stdout.

    Honest about not knowing: when the estimator is unavailable (no XLS image)
    or its output does not carry the lines, ``available`` is False and the raw
    stderr says why — the flow itself never fails on it.
    """
    if not bench.get("success"):
        return {"available": False, "reason": (bench.get("stderr") or "").strip()[:400]}
    fields = {
        key.strip().lower().replace(" ", "_"): value.strip()
        for key, value in _BENCHMARK_LINE.findall(bench.get("stdout", "") or "")
    }
    return {"available": True, "delay_model": bench.get("delay_model"), **fields}


def _safe_remove(cwd: str, rel_path: str) -> None:
    try:
        os.remove(_artifact_path(cwd, rel_path))
    except Exception:
        pass
