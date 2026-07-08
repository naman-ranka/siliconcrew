from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os

from .config import ProblemConfig, write_json


def prepare_problem(problem: ProblemConfig, run_dir: Path) -> dict[str, Any]:
    if problem.kind == "yaml_spec":
        return _yaml_spec(problem)
    if problem.kind == "prompt":
        return _prompt(problem)
    if problem.kind == "cvdp_agentic_jsonl":
        return _cvdp(problem, run_dir)
    raise ValueError(f"Unsupported problem kind: {problem.kind}")


def _lean_cvdp_prompt(problem: ProblemConfig, prepared: dict[str, Any], session_name: str, project_id: str | None) -> str:
    """Self-contained CVDP prompt (gated by env CVDP_LEAN_PROMPT). Drops inject_architect_prompt — the
    general architect prompt is built for the full RTL->GDSII flow (~half is synthesis/PD, irrelevant to
    RTL-sim-only CVDP, and its "write RTL + self-checking testbench" step competes with the golden flow).
    This makes golden-model-first the PRIMARY, authoritative flow, and routes verification through a
    cocotb (Python) testbench so the Python golden integrates without the SV-vector friction that orphaned
    it before."""
    project_line = f' with project_id "{project_id}"' if project_id else ""
    context_dir = str(Path(prepared["problem_json"]).parent / "context")
    patch_targets = prepared.get("patch_targets") or []
    targets = ", ".join(patch_targets) if patch_targets else "(see problem.json patch keys)"
    return (
        f'Use MCP server "{problem.mcp_server}".\n\n'
        "Initialize SiliconCrew first:\n"
        f'1. Call create_session_tool with session_name "{session_name}", model_name "{problem.model}"{project_line}.\n'
        "2. Use that session for all SiliconCrew tool calls. (Do NOT call inject_architect_prompt — this "
        "prompt is self-contained.)\n\n"
        "Available SiliconCrew MCP tools (already provided — use them directly, no need to search/discover "
        "tools): create_session_tool, write_file, read_file, list_files_tool, linter_tool, simulation_tool, "
        "cocotb_tool, sby_tool, waveform_tool.\n\n"
        "You are an expert RTL design agent solving a Chip Verification & Design Problem (CVDP). Deliver a "
        "correct, spec-matching SystemVerilog/Verilog design verified by RTL simulation. RTL-SIMULATION "
        "ONLY: do NOT run synthesis, post-synthesis simulation, retry_pd, or report generation — stop when "
        "RTL simulation against your golden-derived testbench is correct.\n\n"
        f"Read the extracted problem JSON at: {prepared['problem_json']}\n"
        "Use its `prompt` as the design task and `prompt_contract`/`context` as requirements.\n"
        f"Context files are already materialized at: {context_dir}\n"
        "Copy each context file into your session workspace at the SAME relative path before coding. Do "
        "not modify provided context files.\n"
        f"Write only the solution files (patch targets): {targets}\n\n"
        "YOUR SOLUTION IS GRADED BY AN EXTERNAL, HIDDEN TESTBENCH stricter than anything you write; passing "
        "your own test is necessary but NOT sufficient. Treat EVERY sentence of the spec as a testable "
        "contract — exact bit orders/field positions, reset values, latencies, status-flag semantics, "
        "interface timing, and the spec's REAL parameter defaults (use them, never simplified/convenient "
        "values). Where the spec permits two readings, implement the most LITERAL one and note the "
        "ambiguity in your final report.\n\n"
        "VERIFICATION — GOLDEN-MODEL-FIRST (this is THE flow; do these IN ORDER, do not skip step 1-2):\n"
        "1. Write a PYTHON reference model of the required behavior, derived directly from the SPEC's rules "
        "(NOT from your RTL), at the spec's real parameters. This is your independent oracle.\n"
        "2. Write your testbench as a COCOTB (Python) testbench that drives the RTL and checks every output "
        "against the reference model, cycle by cycle, over directed cases AND corner classes (reset "
        "mid-op, min/max/overflow, back-to-back, empty/full, max-latency). Keeping the golden and the "
        "checker both in Python makes the comparison direct — import/reuse the reference model in the "
        "cocotb test. Run the golden ONLY through cocotb_tool (it executes Python inside the simulator "
        "container) — do NOT invoke `python` in your shell to run the golden; the host has no Python on PATH "
        "and the call fails with 'Python was not found'. Do NOT write a self-consistency testbench (e.g. "
        "'wait for the event, then assert it "
        "happened'), do NOT use loopback, and do NOT compute 'expected' values from your own RTL's logic — "
        "those prove only self-consistency, not correctness.\n"
        "3. Implement the RTL, then run the cocotb testbench with cocotb_tool (it runs in the SAME "
        "simulator image used for grading, so a PASS predicts the real verdict). A run that hangs or "
        "yields no result is a FAILING design.\n"
        "4. When the RTL disagrees with the golden, the RTL is the likely culprit — DEBUG AND FIX THE RTL. "
        "Do NOT edit the reference model or the testbench's expected values to match the RTL unless you "
        "find concrete evidence in the spec (cite the exact rule) that the golden itself misread it. "
        "Bending the test to the design hides the bug the hidden harness will catch.\n\n"
        "For FSM/control/protocol/buffer designs, ALSO prove structural invariants with sby_tool (state "
        "legality, occupancy/value bounds, handshake stability, no deadlock/comb-loop) — these hold across "
        "all reachable states without needing expected outputs.\n\n"
        "Before declaring done, list which spec requirements you DID and did NOT verify and report residual "
        "risk honestly. Tool argument contract: pass verilog_files to linter_tool/simulation_tool as a "
        'JSON-array string (e.g. "[\\"rtl/dut.sv\\",\\"verif/tb.sv\\"]"), including DUT, TB, and '
        "dependencies.\n"
    )


def build_agent_prompt(problem: ProblemConfig, prepared: dict[str, Any], session_name: str, project_id: str | None) -> str:
    if problem.kind == "cvdp_agentic_jsonl" and os.environ.get("CVDP_LEAN_PROMPT"):
        return _lean_cvdp_prompt(problem, prepared, session_name, project_id)
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
        context_dir = str(Path(prepared["problem_json"]).parent / "context")
        patch_targets = prepared.get("patch_targets") or []
        targets_line = ", ".join(patch_targets) if patch_targets else "(see problem.json patch keys)"
        body = (
            "Problem kind: CVDP agentic JSONL (RTL-simulation-only).\n"
            f"Read the extracted problem JSON at: {prepared['problem_json']}\n"
            "Use its `prompt` as the design task and `prompt_contract`/`context` as requirements.\n"
            f"Context files are already materialized at: {context_dir}\n"
            "Copy each context file into your active SC session workspace at the SAME relative path "
            "(write_file with the relative path) before coding. Do not modify provided context testbenches.\n"
            f"Write only the solution files (patch targets): {targets_line}\n"
            "Tool argument contract: pass verilog_files to linter_tool/simulation_tool as a JSON-array "
            "string (e.g. \"[\\\"rtl/dut.sv\\\",\\\"verif/tb.sv\\\"]\"), including DUT, TB, and dependencies; "
            "do not pass space-separated filenames.\n"
            "Verify with RTL simulation against the provided/context testbench and iterate until it passes.\n"
            "DO NOT run synthesis, post-synthesis simulation, retry_pd, or report generation for CVDP. "
            "Stop after RTL simulation is correct.\n"
            "\n"
            "BENCHMARK MODE — external evaluation (applies uniformly to every problem; contains no "
            "problem-specific information):\n"
            "Your solution will be graded by an external, hidden testbench you cannot see, which is "
            "stricter than anything you write. Your own simulation passing is necessary but NOT "
            "sufficient. Direction:\n"
            "- Treat EVERY sentence of the problem spec as a testable contract: exact bit orders and "
            "field positions, reset values, latencies, status-flag semantics, interface timing. Where "
            "the spec permits two readings, implement the most LITERAL one and note the ambiguity in "
            "your final report.\n"
            "- VERIFICATION FLOW (do these IN ORDER, before finalizing the design):\n"
            "  1. FIRST write a small PYTHON reference model of the required behavior, derived directly "
            "from the spec's rules (NOT from your RTL). You have a shell — run it with `python` to "
            "GENERATE a table of expected input->output vectors covering normal cases AND corner classes "
            "(reset mid-op, min/max/overflow, back-to-back, empty/full, max-latency).\n"
            "  2. Write your testbench to check the RTL against THOSE Python-generated golden vectors. Do "
            "NOT compute 'expected' values inside the testbench by reusing your design's own logic, and "
            "do NOT use loopback (encode->decode) — both prove only self-consistency, not correctness.\n"
            "  3. Implement the RTL and run it against that testbench (with a watchdog timeout).\n"
            "  4. When the RTL disagrees with the golden vectors, the RTL is the likely culprit — DEBUG "
            "AND FIX THE RTL. Do NOT edit the golden model or the testbench's expected values to match "
            "the RTL unless you find concrete evidence in the spec (cite the exact rule) that the golden "
            "itself misread the spec. Bending the test to the design hides the bug the hidden harness "
            "will catch.\n"
            "- A simulation that hangs or produces no result is a FAILING design.\n"
            "- Verification tools: beyond RTL simulation, USE cocotb_tool (run a Python cocotb "
            "testbench) and sby_tool (prove formal properties with SymbiYosys) wherever they fit the "
            "design. Formal invariants are especially valuable for FSM/control/protocol/buffer designs: "
            "they check correctness across ALL reachable states without needing expected output values, "
            "so they catch state/protocol/contract bugs a hand-written vector testbench misses (illegal "
            "states, occupancy/value out of range, handshake violations, deadlock). Use them when they "
            "make sense for the problem.\n"
            "- XLS/DSLX: USE IT WHEREVER IT FITS. For any arithmetic, datapath, encoder/decoder, "
            "bit-manipulation, fixed-point, or filter kernel, STRONGLY PREFER implementing the kernel "
            "in DSLX with built-in #[test] value checks (run_xls_flow), then wrap the generated module "
            "to the exact required interface with a thin hand-written Verilog wrapper. The #[test] "
            "blocks force value-level verification of the kernel in isolation and eliminate "
            "hand-translation slips. Reserve direct Verilog for FSM/control/protocol/multi-clock logic "
            "and the wrapper itself.\n"
        )
    prompt = common + flow_rules + "\n" + body
    if problem.flow.lower() == "xls_force":
        docs_dir = Path("C:/Users/naman/.gemini/antigravity-cli/brain/b2ffa41e-9c19-4480-b005-97d2e424b868/scratch/xls_docs")
        docs_content = []
        for doc_name in ["dslx_reference.md", "what_is_a_proc.md", "how_to_use_procs.md", "dslx_ffi.md"]:
            doc_path = docs_dir / doc_name
            if doc_path.exists():
                docs_content.append(f"### FILE: {doc_name}\n\n" + doc_path.read_text(encoding="utf-8"))
        if docs_content:
            prompt += "\n\n=== GOOGLE XLS/DSLX REFERENCE MANUAL ===\n"
            prompt += "Use the following documentation to write correct DSLX code, procs, and Verilog FFI instantiations.\n\n"
            prompt += "\n\n".join(docs_content)
    return prompt



def _flow_rules(flow: str) -> str:
    f = flow.lower()
    if f == "auto":
        return (
            "Flow: agent's choice (XLS/DSLX frontend is AVAILABLE but OPTIONAL).\n"
            "- You decide the implementation path. You MAY use the XLS/DSLX HLS frontend "
            "(run_xls_flow, run_dslx_interpreter, codegen_xls, ...) if you judge it beneficial for "
            "arithmetic/datapath cores, OR write Verilog/SystemVerilog directly. Your call.\n"
            "- If you use XLS, wrap the generated Verilog so the public module matches the EXACT "
            "required interface (port names, widths, reset style) and latency/handshake contract.\n"
            "- Pick whichever path most reliably satisfies the provided testbench and contract.\n"
        )
    if f == "xls_force":
        return (
            "Flow: XLS/DSLX MANDATORY (overrides any 'optional XLS' guidance).\n"
            "- IMPORTANT: ignore any instruction — INCLUDING the injected architect prompt — that says "
            "to avoid XLS for existing-Verilog/legacy/exact-interface/bug-repair tasks. For THIS run, XLS "
            "is REQUIRED regardless of the interface being fixed.\n"
            "- You MUST implement the core combinational/datapath logic in DSLX and generate Verilog via "
            "run_xls_flow (DSLX -> IR -> codegen_xls). Writing the core logic directly in Verilog/"
            "SystemVerilog is NOT allowed for this run.\n"
            "- You MAY hand-write ONLY a thin SystemVerilog WRAPPER that instantiates the XLS-generated "
            "module and adapts it to the exact required interface (port names, widths, reset, latency).\n"
            "- If a specific part genuinely cannot be expressed in DSLX, state which part and why, then "
            "implement only that minimal glue in the wrapper.\n"
        )
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
    # SECURITY (no harness leak): the agent must never see the hidden grading harness or the golden
    # patch. Write an agent-facing problem.json with `harness` removed and `patch` values blanked
    # (target names kept so the prompt can list them). The grader re-reads the FULL datapoint from
    # the dataset at grade time (cvdp-pipeline/regrade_docker.py), so nothing is lost.
    agent_row = {k: v for k, v in row.items() if k != "harness"}
    if isinstance(agent_row.get("patch"), dict):
        agent_row["patch"] = {k: "" for k in agent_row["patch"]}
    write_json(out / "problem.json", agent_row)
    for rel, content in (row.get("context") or {}).items():
        p = out / "context" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8", newline="\n")
    # NOTE: harness/ is intentionally NOT materialized — it was a leak surface (sibling of context/,
    # and the prompt hands the agent this directory). Grading stages it from the dataset instead.
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

