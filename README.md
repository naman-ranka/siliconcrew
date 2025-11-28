SiliconCrew: The Autonomous ASIC Design System

SiliconCrew is an agentic AI framework designed to automate the digital hardware design loop. By orchestrating three specialized AI agents—an RTL Coder, a Verification Engineer, and a Physical Design Analyst—it transforms natural language specifications into functionally verified, physically realizable silicon designs.

This project leverages LangGraph to create a cyclic state machine (not a linear chain), allowing the system to iterate, debug, and self-correct errors in Verilog code and physical implementation flows.


The Architect (RTL Coder)

Role: Generates and fixes SystemVerilog/Verilog code.

Behavior: Writes code based on specs and strictly adheres to linter feedback. It cannot run simulations; it only writes.

The Auditor (Verifier)

Role: Writes testbenches and analyzes simulation waveforms.

Behavior: Compiles code, runs tests, and parses logs. It acts as the "gatekeeper," rejecting any design that fails functional checks.

The Builder (PPA Analyst)

1. The Architect's Tools (Local Execution)

read_design_spec: Retrieves design requirements (IOs, protocols) from the global state.

write_verilog_file: Creates or overwrites source code files in the workspace.

run_linter: Executes a lightweight syntax checker (Verilator/Icarus) to catch syntax errors immediately, avoiding expensive simulation runs.

2. The Auditor's Tools (Local Execution)

write_testbench: Generates the simulation harness (SystemVerilog or Cocotb).

run_simulation: Compiles the RTL + Testbench and executes the simulation binary. Returns "PASS/FAIL" status and specific error logs.

read_vcd_snippet: Parses specific time windows of the waveform dump to visually debug signal transitions when tests fail.

3. The Builder's Tools (Docker Execution)

generate_openroad_config: Creates the necessary Makefiles/Scripts for the OpenROAD Flow Scripts (ORFS).

run_synthesis_job: Triggers the Docker container to convert Verilog to a Gate-Level Netlist.

run_pnr_job: Triggers the Docker container to perform Placement and Routing.

get_ppa_metrics: A local parser that reads the generated reports to extract Worst Negative Slack (WNS), Total Area, and Power consumption.

📂 Code Structure Overview

The project is organized to separate the "Agent Brains" (Python) from the "Engineering Tools" (Shell/Docker) and the "Construction Site" (Workspace).

/src/agents: Contains the prompt definitions and persona logic for the Coder, Verifier, and Analyst.

/src/tools: The "Hands" of the system. Contains Python wrappers for OS-level commands (File I/O, subprocess execution, Docker volume mounting).

/src/graph: The LangGraph state machine definition. This defines the nodes (agents) and the edges (conditional logic/routing).

/src/state: Defines the data schema (TypedDict) passed between agents. This is the "memory bus" holding the current code, error logs, and metrics.

/workspace: A disposable sandbox directory where agents write .v files and tools dump logs. This directory is mounted to Docker.

/templates: Standard boilerplate code (e.g., standard Makefile for OpenROAD, basic testbench templates) to ground the agents.

✅ Sequential Implementation Task List

Follow this roadmap to build the system layer-by-layer, ensuring stability before complexity.

Phase 1: The Foundation (Infrastructure)

[ ] Project Skeleton: Set up the directory structure and Python environment (poetry or venv).

[ ] Docker Setup: Pull the openroad/orfs image and verify it runs manually.

[ ] Tool Wrapper - File I/O: Implement Python functions for agents to read/write text files to the /workspace.

[ ] Tool Wrapper - Local Exec: Implement a robust subprocess wrapper with timeouts to run iverilog and capture stdout/stderr.


[ ] Metric Parser: Write a Regex parser to extract "Worst Negative Slack" and "Total Area" from OpenROAD logs.

[ ] The "PPA Analyst" Node: Integrate the Docker tools into a third agent node.

Phase 4: Intelligence & Orchestration

[ ] State Management: Finalize the DesignState object to track iteration_count (to prevent infinite loops).

[ ] Routing Logic: Implement the conditional edges (e.g., "If slack < 0, go to Coder; else, Finish").

[ ] Human-in-the-Loop: Add an interrupt breakpoint before the PPA phase to allow user approval.

Phase 5: Testing & Refinement

[ ] Benchmark: Run the system on a simple design (e.g., "Make an 8-bit Counter").

[ ] Prompt Tuning: Refine system prompts to stop agents from being "lazy" or hallucinating non-existent Verilog syntax.

[ ] Error Handling: Ensure the system gracefully handles Docker crashes or compiler timeouts.