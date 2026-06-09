from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .config import ProblemConfig, write_json


def prepare_problem(problem: ProblemConfig, run_dir: Path) -> dict[str, Any]:
    if problem.kind == "yaml_spec":
        return _yaml_spec(problem)
    if problem.kind == "prompt":
        return _prompt(problem)
    if problem.kind == "cvdp_agentic_jsonl":
        return _cvdp(problem, run_dir)
    raise ValueError(f"Unsupported problem kind: {problem.kind}")


def build_agent_prompt(problem: ProblemConfig, prepared: dict[str, Any], session_name: str, project_id: str | None) -> str:
    project_line = f' with project_id "{project_id}"' if project_id else ""
    common = (
        f'Use MCP server "{problem.mcp_server}".\n\n'
        "Initialize SiliconCrew first:\n"
        f'1. Call create_session_tool with session_name "{session_name}", model_name "{problem.model}"{project_line}.\n'
        "2. Call inject_architect_prompt with the returned session_id.\n"
        "3. Use that session for all remaining SiliconCrew tool calls.\n\n"
    )
    flow_rules = _flow_rules(problem.flow)
    if problem.kind == "yaml_spec":
        body = (
            f"Problem kind: YAML spec.\n"
            f"Load this spec with load_yaml_spec_file: {prepared['path']}\n"
            "Run the complete SiliconCrew flow: implementation, RTL testbench, lint, RTL simulation, "
            "synthesis, metrics, post-synthesis simulation when available, and report generation.\n"
        )
    elif problem.kind == "prompt":
        body = "Problem kind: prompt.\n" + prepared["prompt"] + "\n"
    else:
        body = (
            "Problem kind: CVDP agentic JSONL.\n"
            f"Read the extracted problem JSON at: {prepared['problem_json']}\n"
            "Use its prompt and context files as the design task. Materialize context files in the SC workspace "
            "using their relative paths, modify only required solution files, and stop after RTL-level checks. "
            "Do not run synthesis for CVDP unless the problem explicitly asks for it.\n"
        )
    return common + flow_rules + "\n" + body


def _flow_rules(flow: str) -> str:
    f = flow.lower()
    if f == "xls":
        return (
            "Flow: XLS/DSLX frontend.\n"
            "- Use DSLX/XLS for arithmetic/datapath cores when suitable.\n"
            "- Prefer run_xls_flow, then wrap generated Verilog to the required public interface.\n"
            "- Continue through normal Verilog lint/simulation/synthesis for ASU-style problems.\n"
        )
    if f == "verilog":
        return (
            "Flow: direct Verilog/SystemVerilog.\n"
            "- Do not use XLS/DSLX tools.\n"
            "- Implement the required RTL directly and verify it with self-checking tests.\n"
        )
    return f"Flow: {flow}.\n"


def _yaml_spec(problem: ProblemConfig) -> dict[str, Any]:
    assert problem.path is not None
    return {"path": str(problem.path), "exists": problem.path.exists()}


def _prompt(problem: ProblemConfig) -> dict[str, Any]:
    if problem.text:
        text = problem.text
    else:
        assert problem.path is not None
        text = problem.path.read_text(encoding="utf-8")
    return {"prompt": text}


def _cvdp(problem: ProblemConfig, run_dir: Path) -> dict[str, Any]:
    assert problem.dataset is not None
    row = find_cvdp_datapoint(problem.dataset, str(problem.datapoint_id))
    out = run_dir / "raw" / "cvdp_problem"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "problem.json", row)
    for rel, content in (row.get("context") or {}).items():
        p = out / "context" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8", newline="\n")
    for rel, content in (row.get("harness") or {}).items():
        p = out / "harness" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8", newline="\n")
    return {
        "problem_json": str((out / "problem.json").resolve()),
        "dataset": str(problem.dataset),
        "datapoint_id": problem.datapoint_id,
        "categories": row.get("categories") or [],
        "context_files": sorted((row.get("context") or {}).keys()),
        "patch_targets": sorted((row.get("patch") or {}).keys()),
    }


def find_cvdp_datapoint(dataset: Path, datapoint_id: str) -> dict[str, Any]:
    with dataset.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            row = json.loads(s)
            if row.get("id") == datapoint_id:
                return row
    raise ValueError(f"CVDP datapoint not found in {dataset}: {datapoint_id}")

