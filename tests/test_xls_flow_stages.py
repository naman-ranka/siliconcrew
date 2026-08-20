"""Five XLS tools became one flow with two arguments.

The interpreter, the IR compiler, the optimizer and codegen were the flow's own
stages, exposed separately so a caller could run one of them. That is now
``stop_after`` (stop here) and ``from_ir`` (start there). The benchmark tool was
two numbers about an artifact the flow produces, so the flow reports them.

Every XLS binary lives in a docker image most installs do not have, so the stage
functions are stubbed: what is under test is which stages run, in what order,
with what arguments — the decisions the merge moved.
"""
import json

import pytest

from src.tools import run_xls
from src.tools import wrappers


@pytest.fixture
def stages(tmp_path, monkeypatch):
    """Record every stage call; each one 'succeeds' with its usual fields."""
    seen: list[tuple[str, dict]] = []

    def interp(filename, cwd=None):
        seen.append(("interpret", {"filename": filename}))
        return {"success": True, "dslx_file": filename, "stdout": "2 tests passed"}

    def to_ir(filename, top_module, cwd=None):
        seen.append(("ir", {"filename": filename, "top_module": top_module}))
        return {"success": True, "ir_filename": f"{top_module}.ir"}

    def opt(ir_filename, cwd=None):
        seen.append(("opt", {"ir_filename": ir_filename}))
        base = ir_filename[:-3] if ir_filename.endswith(".ir") else ir_filename
        return {"success": True, "opt_ir_filename": f"{base}.opt.ir"}

    def bench(opt_ir_filename, delay_model="sky130", cwd=None):
        seen.append(("benchmark", {"opt_ir_filename": opt_ir_filename,
                                   "delay_model": delay_model}))
        return {"success": True, "delay_model": delay_model,
                "stdout": "Delay: 350ps\nArea: 42\n"}

    def codegen(**kwargs):
        seen.append(("codegen", kwargs))
        return {"success": True, "verilog_filename": "adder.v",
                "generated_module": "adder", "generator": kwargs["generator"],
                "pipeline_stages": kwargs["pipeline_stages"],
                "clock_period_ps": kwargs["clock_period_ps"]}

    def lint(cwd, verilog_filename):
        seen.append(("lint", {"verilog_filename": verilog_filename}))
        return {"success": True, "stdout": "", "stderr": "", "command": "iverilog"}

    monkeypatch.setattr(run_xls, "run_dslx_interpreter", interp)
    monkeypatch.setattr(run_xls, "compile_dslx_to_ir", to_ir)
    monkeypatch.setattr(run_xls, "optimize_xls_ir", opt)
    monkeypatch.setattr(run_xls, "benchmark_xls", bench)
    monkeypatch.setattr(run_xls, "codegen_xls", codegen)
    monkeypatch.setattr(run_xls, "_lint_generated_verilog", lint)
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: str(tmp_path))
    return seen


def _flow(**kwargs) -> dict:
    return json.loads(wrappers.run_xls_flow.invoke(kwargs))


def _ran(seen) -> list[str]:
    return [name for name, _ in seen]


def test_the_whole_flow_runs_every_stage(stages):
    res = _flow(dslx_file="adder.x", top_module="adder")
    assert res["success"] is True
    assert _ran(stages) == ["interpret", "ir", "opt", "benchmark", "codegen", "lint"]
    assert res["verilog_filename"] == "adder.v"
    assert res["generated_module"] == "adder"


# --- stop_after: the four single-step tools ----------------------------------

def test_stop_after_interpret_type_checks_and_stops(stages):
    """What run_dslx_interpreter was for: is this DSLX valid, do its tests pass."""
    res = _flow(dslx_file="adder.x", top_module="adder", stop_after="interpret")
    assert res["success"] is True and res["stopped_after"] == "interpret"
    assert _ran(stages) == ["interpret"]
    assert "2 tests passed" in res["stage_results"]["interpreter"]["stdout"]


def test_stop_after_ir_compiles_and_stops(stages):
    res = _flow(dslx_file="adder.x", top_module="adder", stop_after="ir")
    assert _ran(stages) == ["interpret", "ir"]
    assert res["artifacts"]["ir_file"] == "adder.ir"


def test_stop_after_opt_optimizes_and_estimates(stages):
    res = _flow(dslx_file="adder.x", top_module="adder", stop_after="opt")
    assert _ran(stages) == ["interpret", "ir", "opt", "benchmark"]
    assert res["artifacts"]["opt_ir_file"] == "adder.opt.ir"
    assert res["benchmark"]["available"] is True


def test_stop_after_codegen_emits_verilog_without_linting(stages):
    res = _flow(dslx_file="adder.x", top_module="adder", stop_after="codegen")
    assert "lint" not in _ran(stages)
    assert res["verilog_filename"] == "adder.v"


def test_an_unknown_stop_after_is_refused_by_the_engine(stages, tmp_path):
    """The tool's schema closes the set, but the engine is called directly by
    tests and by any future caller — so it checks too, and names the stages."""
    res = run_xls.run_xls_flow(dslx_file="adder.x", top_module="adder",
                               cwd=str(tmp_path), stop_after="nope")
    assert res["success"] is False
    assert "Invalid stop_after" in res["stderr"]
    assert "interpret" in res["stderr"]
    assert _ran(stages) == []


# --- from_ir: entering partway (what optimize/codegen were for) ---------------

def test_from_ir_skips_the_dslx_stages(stages):
    res = _flow(from_ir="adder.ir")
    assert _ran(stages) == ["opt", "benchmark", "codegen", "lint"]
    assert res["artifacts"]["opt_ir_file"] == "adder.opt.ir"


def test_an_already_optimized_ir_goes_straight_to_codegen(stages):
    """What codegen_xls was for: emit Verilog from THIS optimized IR, without
    re-running the optimizer over the flow's own artifact."""
    res = _flow(from_ir="adder.opt.ir")
    assert _ran(stages) == ["benchmark", "codegen", "lint"]
    assert stages[1][1]["opt_ir_filename"] == "adder.opt.ir"
    assert res["verilog_filename"] == "adder.v"


def test_from_ir_with_a_stop_that_already_happened_says_so(stages):
    res = _flow(from_ir="adder.ir", stop_after="interpret")
    assert res["success"] is False
    assert "nothing to do" in res["stderr"]
    assert _ran(stages) == []


def test_neither_dslx_nor_ir_is_refused(stages):
    res = _flow()
    assert res["success"] is False
    assert "dslx_file" in res["stderr"] and "from_ir" in res["stderr"]


def test_dslx_without_a_top_is_refused(stages):
    res = _flow(dslx_file="adder.x")
    assert res["success"] is False and "top_module" in res["stderr"]


# --- the benchmark fields (what benchmark_xls reported) -----------------------

def test_the_estimate_is_parsed_out_of_the_benchmark_output(stages):
    res = _flow(dslx_file="adder.x", top_module="adder", delay_model="asap7")
    assert res["benchmark"] == {"available": True, "delay_model": "asap7",
                                "delay": "350ps", "area": "42"}
    assert stages[3][1]["delay_model"] == "asap7"


def test_an_unavailable_estimator_never_fails_the_flow(tmp_path, stages, monkeypatch):
    """The estimate is informational. No XLS image, no numbers, and the flow
    still delivers Verilog — with the reply saying the estimate is missing and
    why, rather than implying zero."""
    monkeypatch.setattr(run_xls, "benchmark_xls", lambda *a, **k: {
        "success": False, "stderr": "benchmark_main: not found"})
    res = _flow(dslx_file="adder.x", top_module="adder")
    assert res["success"] is True
    assert res["benchmark"]["available"] is False
    assert "not found" in res["benchmark"]["reason"]
    assert res["verilog_filename"] == "adder.v"


# --- failures still stop the flow where they always did -----------------------

def test_a_failing_interpreter_stops_before_the_ir(stages, monkeypatch):
    monkeypatch.setattr(run_xls, "run_dslx_interpreter", lambda filename, cwd=None: {
        "success": False, "stderr": "type error", "dslx_file": filename})
    res = _flow(dslx_file="adder.x", top_module="adder")
    assert res["success"] is False and res["stage"] == "interpreter"
    assert _ran(stages) == []


def test_a_failing_lint_reports_the_generated_module_anyway(stages, monkeypatch):
    monkeypatch.setattr(run_xls, "_lint_generated_verilog", lambda cwd, verilog_filename: {
        "success": False, "stdout": "", "stderr": "syntax error", "command": "iverilog"})
    res = _flow(dslx_file="adder.x", top_module="adder")
    assert res["success"] is False and res["stage"] == "verilog_lint"
    assert res["generated_module"] == "adder"
    assert res["benchmark"]["available"] is True


# --- cleanup never touches what the caller supplied ---------------------------

def test_intermediates_the_flow_made_are_cleaned_up(stages, monkeypatch):
    removed: list[str] = []
    monkeypatch.setattr(run_xls, "_safe_remove", lambda cwd, rel: removed.append(rel))
    _flow(dslx_file="adder.x", top_module="adder", keep_intermediates=False)
    assert set(removed) == {"adder.ir", "adder.opt.ir"}


def test_a_caller_supplied_ir_is_never_deleted(stages, monkeypatch):
    """keep_intermediates tidies what the flow produced. The IR the caller
    handed in is an input — deleting it would destroy evidence, not tidy."""
    removed: list[str] = []
    monkeypatch.setattr(run_xls, "_safe_remove", lambda cwd, rel: removed.append(rel))
    _flow(from_ir="handwritten.ir", keep_intermediates=False)
    assert removed == ["handwritten.opt.ir"]   # the optimizer's output, not the input


def test_a_failed_optimizer_does_not_delete_the_supplied_ir(stages, monkeypatch):
    removed: list[str] = []
    monkeypatch.setattr(run_xls, "_safe_remove", lambda cwd, rel: removed.append(rel))
    monkeypatch.setattr(run_xls, "optimize_xls_ir", lambda ir_filename, cwd=None: {
        "success": False, "stderr": "pass crashed"})
    res = _flow(from_ir="handwritten.ir", keep_intermediates=False)
    assert res["success"] is False and res["stage"] == "optimization"
    assert removed == []
