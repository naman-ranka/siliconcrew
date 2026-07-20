# SiliconCrew

**An autonomous LLM agent for RTL design, verification, and synthesis.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Framework-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2014-black.svg)](https://nextjs.org/)
[![MCP](https://img.shields.io/badge/Protocol-MCP-blue.svg)](https://modelcontextprotocol.io/)
[![CVDP](https://img.shields.io/badge/CVDP-65%25%20(60%2F92)%20leak--gated-success.svg)](cvdp-pipeline/research/CVDP_FINAL_RESULTS.md)
[![Status: Research](https://img.shields.io/badge/Status-Research%20Prototype-yellow.svg)]()

---

## Overview

SiliconCrew is a research prototype that explores the use of Large Language Models (LLMs) as autonomous agents for digital hardware design. Given a natural language specification, the agent generates synthesizable RTL, writes self-checking testbenches, iterates on verification failures using waveform analysis, and produces physical design outputs through the OpenROAD flow.

The system is accessible through two interfaces — a **Next.js web application** with real-time WebSocket streaming, and an **MCP server** for Claude Desktop and VS Code integration — both sharing the same tool backend, session state, and workspace.

This project investigates the following research questions:
- Can LLM agents effectively close the RTL design loop (spec → code → verify → fix)?
- How should agent workflows be structured for hardware design tasks?
- What tool interfaces enable effective LLM-driven EDA automation?
- How do different interaction modalities (chat UI vs. MCP tool integration) affect the design process?

**Note**: This is an active research project. Contributions, feedback, and collaboration are welcome.

---

## Results

On **CVDP** (NVIDIA's 92 agentic `no_commercial` problems), every verdict is graded in the **official
reference container** (`ghcr.io/hdl/sim/osvb`, digest-pinned), not self-reported:

| | Pass rate |
|---|---|
| March 2026 baseline | 46.7% (43/92) |
| Best pre-leak-gate (retired) | 68.5% (63/92) |
| **Final, leak-gated (July 2026)** | **65.2% (60/92)** |

The drop from 63 to 60 was deliberate. An audit found that some earlier runs could read grader
files from inside the agent workspace, so we built a permanent
[leak detector](cvdp-pipeline/leak_detector.py) and re-checked every run. Anything contaminated
was discarded and re-run sealed, including our previous best. The surviving number comes from one
configuration (Claude Sonnet 5, lean prompt, pass@1, single attempt per problem), with per-problem
verdicts and provenance frozen in
[`FINAL_MANIFEST.json`](bench-orchestrator/final_runs/FINAL_MANIFEST.json). Expect a few problems
of run-to-run swing; LLM sampling has no seed control. Full analysis, including the failure-mode
taxonomy: [`CVDP_FINAL_RESULTS.md`](cvdp-pipeline/research/CVDP_FINAL_RESULTS.md).

---

## Capabilities

- **Specification-First Workflow**: Generates structured YAML specifications before RTL, including port definitions, timing constraints, and SDC files
- **RTL Generation**: Produces synthesizable Verilog-2001 from specifications with coding style enforcement
- **Self-Checking Testbenches**: Generates testbenches with assertions, VCD dumping, and explicit PASS/FAIL reporting
- **Waveform-Based Debugging**: When simulation fails, inspects VCD signals at the point of failure rather than guessing at fixes
- **Iterative Correction**: Analyzes lint, simulation, and synthesis errors across multiple fix-verify cycles
- **Synthesis to GDSII**: Runs the OpenROAD flow via Docker targeting SkyWater 130nm to produce layout outputs
- **PPA Extraction**: Parses area, timing (WNS/TNS), and power from synthesis logs and reports
- **Formal Verification**: SymbiYosys integration for property checking and bounded model checking
- **High-Level Synthesis (XLS)**: Optional Google XLS / DSLX frontend — compiles algorithmic/datapath kernels (`.x`) through IR → optimized IR → Verilog for arithmetic, encoders, and fixed-point math
- **Schematic Generation**: SVG netlist visualization from Verilog sources
- **Design Reports**: Markdown reports comparing specification requirements against achieved metrics
- **Real-Time Streaming UI**: Next.js frontend with WebSocket chat, inline tool call cards, and six artifact viewers (spec, code, waveforms, schematics, layouts, reports)
- **MCP Protocol Support**: Full toolchain exposed via Model Context Protocol (stdio, SSE, and Streamable HTTP transports) for Claude Desktop, VS Code, and other MCP clients
- **Multi-Session Management**: Isolated workspaces with per-session chat history, token tracking, and cost accounting — shared across all interfaces
- **Tool Auto-Discovery**: LangChain tool schemas are automatically converted to MCP format; adding a tool to the backend exposes it to all clients

---

## Benchmarks

The headline number is in [Results](#results) above: **60/92 (65%)**, Claude Sonnet 5 driving the
SiliconCrew MCP toolchain, one attempt per problem, every verdict from the pinned
`ghcr.io/hdl/sim/osvb` container running the dataset's own cocotb harness. Earlier multi-config
and ensemble figures were retired when the leak gate landed; the run-by-run history is in
[`ITERATION_LOG.md`](cvdp-pipeline/research/ITERATION_LOG.md) and the audit that triggered the
recalibration is in [`AUDIT_XLS_TOOLING_LEAK.md`](cvdp-pipeline/research/AUDIT_XLS_TOOLING_LEAK.md).

The full pipeline (problem selection, agent run, container grading, and a provenance-stamped
`results.json` with repo commit, pinned image digest, and agent/model) lives in
[`cvdp-pipeline/`](cvdp-pipeline/). Results detail:
[`cvdp-pipeline/research/CVDP_FINAL_RESULTS.md`](cvdp-pipeline/research/CVDP_FINAL_RESULTS.md).

> CVDP is NVIDIA's benchmark; this repository ships no CVDP data. Provide the dataset yourself and
> comply with NVIDIA's license. The `no_commercial` split is used because the commercial split
> requires proprietary (Cadence) simulators the reference container does not include.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            User Interfaces                                  │
│                                                                            │
│        Next.js Frontend                      MCP Clients                   │
│        (WebSocket chat +                (Claude Desktop, VS Code,          │
│         artifact viewers)                any MCP client)                   │
└──────────────┬───────────────────────────────────┬─────────────────────────┘
               │                                   │
               ▼                                   ▼
     ┌──────────────────┐                ┌──────────────────┐
     │  FastAPI Server   │                │   MCP Server     │
     │  (REST + WS)      │                │ (stdio/SSE/HTTP) │
     │  api.py           │                │ mcp_server.py    │
     └────────┬─────────┘                └────────┬─────────┘
              │                                   │
              └─────────────────┬─────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      Architect Agent (LangGraph ReAct)                      │
│                                                                            │
│   System prompt (~130-line methodology, versioned in prompts/architect/)   │
│   + Provider-selected LLM (Gemini / OpenAI / Anthropic)                                 │
│   + 35 LangChain tools                                                     │
│                                                                            │
│   Workflow: Spec → RTL → Testbench → Lint → Simulate → Debug → Synthesize │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
     ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
     │ Spec & Files   │  │  Verification  │  │   Synthesis    │
     ├────────────────┤  ├────────────────┤  ├────────────────┤
     │ write_spec     │  │ linter_tool    │  │ start_synthesis│
     │ read_spec      │  │ simulation_tool│  │ get_synthesis_metrics│
     │ load_yaml_spec │  │ waveform_tool  │  │ search_logs    │
     │ write_file     │  │ cocotb_tool    │  │ schematic_tool │
     │ read_file      │  │ sby_tool       │  │ save_metrics   │
     │ edit_file_tool │  │                │  │ generate_report│
     │ list_files     │  │                │  │                │
     └───────┬────────┘  └───────┬────────┘  └───────┬────────┘
             │                   │                    │
             ▼                   ▼                    ▼
     ┌──────────────┐   ┌──────────────┐   ┌───────────────────┐
     │  Filesystem  │   │Icarus Verilog│   │ OpenROAD (Docker) │
     │  (YAML, .v)  │   │SymbiYosys    │   │ SkyWater 130nm    │
     └──────────────┘   └──────────────┘   └───────────────────┘
```

### Agent Workflow

1. **Specification Phase**: Agent creates a YAML specification defining module interface, ports, timing constraints, and behavioral requirements. An SDC constraints file is generated automatically.

2. **Implementation Phase**: Agent reads the specification and generates RTL that strictly follows the defined module signature. A self-checking testbench with VCD dumping is also written.

3. **Verification Phase**: Agent lints the RTL via Icarus Verilog, then runs simulation. If tests fail, the agent uses waveform inspection to diagnose the root cause at the signal level before attempting a fix.

4. **Synthesis Phase**: Agent invokes the OpenROAD flow (via Docker container) targeting SkyWater 130nm, then extracts PPA metrics from logs and reports.

5. **Reporting**: Agent generates a Markdown report comparing specification requirements against achieved results.

If any phase fails, the agent analyzes errors and iterates on the design.

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Agent framework | LangGraph | ReAct agent with tool calling and checkpointing |
| LLM backend | Provider-selected (Gemini, OpenAI, Anthropic) | Code generation, reasoning, debugging |
| Backend API | FastAPI | REST endpoints + WebSocket streaming |
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Zustand | Chat UI, state management, artifact viewers |
| MCP server | MCP Python SDK | Model Context Protocol (stdio, SSE, HTTP) |
| Simulation | Icarus Verilog | Verilog compilation and simulation |
| Formal verification | SymbiYosys | Property checking and bounded model checking |
| Waveform analysis | vcdvcd | VCD parsing for signal inspection |
| Synthesis | OpenROAD Flow Scripts (Docker) | RTL-to-GDSII physical design |
| Target PDK | SkyWater 130nm HD | Open-source process design kit |
| Persistence | SQLite | Session metadata + LangGraph checkpoints |

---

## Installation

### Prerequisites

- Python 3.10 or higher
- Node.js 18+ and npm (for the frontend)
- Icarus Verilog (`iverilog`)
- Docker (for synthesis features)
- At least one LLM provider API key (Gemini, OpenAI, or Anthropic)
- (Optional) Claude Desktop or VS Code for MCP access

### Setup

```bash
# Clone the repository
git clone https://github.com/naman-ranka/siliconcrew.git
cd siliconcrew

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Configure API keys (set at least one provider)
cp .env.example .env
# Then edit .env with your keys and desired DEFAULT_MODEL

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### Installing Icarus Verilog

| Platform | Command |
|----------|---------|
| Ubuntu/Debian | `sudo apt-get install iverilog` |
| macOS | `brew install icarus-verilog` |
| Windows | [Download installer](https://bleyer.org/icarus/) |

### Docker Setup (for Synthesis)

```bash
docker pull openroad/orfs:latest
```

### First-Run Standard-Cell Bootstrap (Required for Post-Synthesis Simulation)

The Docker image bakes these standard-cell (PDK) models in at build time, so
hosted and self-host deployments need no bootstrap — they resolve from the
install root and should never report a missing cache. This step is only for a
**local checkout running post-synth outside the image**.

Post-synthesis simulation needs managed standard-cell model caches under the
repo root (the install-global location the resolver reads, `stdcells.stdcell_root`):
- `_stdcells/asap7/sim`
- `_stdcells/sky130hd/sim`

Bootstrap uses pinned upstream sources (not ORFS Docker extraction), so Docker is not required for this step.

Run this once after clone (or whenever you clear `_stdcells`):

```bash
# from repo root
PYTHONPATH=. python scripts/bootstrap_stdcells.py --workspace . --platform asap7
PYTHONPATH=. python scripts/bootstrap_stdcells.py --workspace . --platform sky130hd
```

PowerShell:

```powershell
$env:PYTHONPATH='.'
python scripts/bootstrap_stdcells.py --workspace . --platform asap7
python scripts/bootstrap_stdcells.py --workspace . --platform sky130hd
```

If post-synthesis simulation reports missing stdcells, run the same commands and see this section.

---

## Usage

### Web Interface (FastAPI + Next.js)

```bash
# Terminal 1 — backend
python api.py                      # Runs on http://localhost:8000

# Terminal 2 — frontend
cd frontend && npm run dev         # Runs on http://localhost:3000
```

1. Create a new session (sidebar) with a name and model choice
2. Describe your design in natural language:
   ```
   Design a 4-bit synchronous counter with active-high reset and enable signal.
   Target clock period: 10ns.
   ```
3. Review the generated specification in the **Spec** tab
4. Monitor RTL generation and verification in the **Code** and **Waveform** tabs
5. Run synthesis and view results in the **Layout** and **Report** tabs

### MCP Interface (Claude Desktop, VS Code, etc.)

The MCP server exposes all 35 tools plus session management to any MCP-compatible client.

```bash
# Local (stdio) — for Claude Desktop
python mcp_server.py

# Remote (SSE) — accessible over the network
python mcp_server.py --transport sse --host 0.0.0.0 --port 8080

# Remote (Streamable HTTP)
python mcp_server.py --transport http --host 0.0.0.0 --port 8080
```

**Claude Desktop**: Configure the MCP server in `claude_desktop_config.json` (see the example below), then load the "RTL Design Workflow" prompt.

**VS Code**: Configure via settings and use Copilot Chat with full tool access (same command/args as the example below).

**Quick setup (all OS)**

```bash
# Codex CLI (macOS/Linux)
codex mcp add rtl-codex -- <REPO_ROOT>/.venv/bin/python <REPO_ROOT>/mcp_server.py --codex-tools
```

```powershell
# Codex CLI (Windows)
codex mcp add rtl-codex -- <REPO_ROOT>\.venv\Scripts\python.exe <REPO_ROOT>\mcp_server.py --codex-tools
```

```json
// Claude Desktop (macOS/Linux config)
{
  "mcpServers": {
    "rtl-codex": {
      "command": "/absolute/path/to/RTL_AGENT/.venv/bin/python",
      "args": ["/absolute/path/to/RTL_AGENT/mcp_server.py", "--codex-tools"]
    }
  }
}
```

```json
// Claude Desktop (Windows config)
{
  "mcpServers": {
    "rtl-codex": {
      "command": "C:\\<path-to-RTL_AGENT>\\.venv\\Scripts\\python.exe",
      "args": ["C:\\<path-to-RTL_AGENT>\\mcp_server.py", "--codex-tools"]
    }
  }
}
```

Run `python mcp_server.py --help` for all transport, tool-filter, and host/port options.

Sessions are shared across all interfaces — a design started in Claude Desktop can be resumed in the web UI and vice versa.

### Docker Compose

```bash
docker-compose up                  # Starts backend + frontend together
```

### YAML Specification Input

For precise control, provide a YAML specification directly:

```yaml
counter_4bit:
  description: 4-bit synchronous up-counter with enable
  tech_node: SkyWater 130HD
  clock_period: 10ns
  ports:
    - name: clk
      direction: input
      description: Clock input
    - name: rst
      direction: input
      description: Synchronous reset (active high)
    - name: enable
      direction: input
      description: Count enable
    - name: count
      direction: output
      width: 4
      description: Counter output
```

---

## Project Structure

```
├── api.py                          # FastAPI backend (REST + WebSocket)
├── mcp_server.py                   # MCP server (stdio / SSE / HTTP)
├── docker-compose.yml              # Container orchestration
├── Dockerfile                      # Backend Docker image
├── Dockerfile.xls                  # Google XLS HLS toolchain image
├── requirements.txt
│
├── src/
│   ├── config.py                   # Model and environment configuration
│   ├── model_catalog.py            # Provider/model registry
│   ├── llm/                        # Provider-selected LLM factory (Gemini/OpenAI/Anthropic)
│   ├── agents/
│   │   └── architect.py            # Primary ReAct agent + system prompt
│   ├── state/
│   │   └── state.py                # DesignState TypedDict
│   ├── tools/
│   │   ├── wrappers.py             # 35 LangChain @tool definitions
│   │   ├── spec_manager.py         # YAML spec handling + validation
│   │   ├── run_linter.py           # Icarus Verilog linting
│   │   ├── run_simulation.py       # Simulation orchestration
│   │   ├── run_iverilog.py         # iverilog compile + vvp execute
│   │   ├── run_synthesis.py        # OpenROAD via Docker
│   │   ├── synthesis_manager.py    # ORFS run lifecycle + staged PD tooling
│   │   ├── run_docker.py           # Docker command runner
│   │   ├── run_cocotb.py           # Cocotb runner (osvb reference container)
│   │   ├── run_sby.py              # SymbiYosys formal verification (containerized)
│   │   ├── run_xls.py              # Google XLS / DSLX HLS flow
│   │   ├── get_ppa.py              # PPA metric extraction from logs
│   │   ├── read_waveform.py        # VCD parsing
│   │   ├── search_logs.py          # Log/report grep
│   │   ├── edit_file.py            # Surgical file editing with diff
│   │   ├── generate_schematic.py   # SVG schematic generation
│   │   └── design_report.py        # Markdown report generation
│   └── utils/
│       ├── session_manager.py      # Session CRUD + SQLite metadata
│       └── visualizers.py          # Waveform/layout rendering helpers
│
├── legacy/                         # Earlier multi-agent graph (coder→verifier→synth), kept for reference
├── bench-orchestrator/             # Generic benchmark runner (agents, runs, dashboards)
├── cvdp-pipeline/                  # CVDP glue: select → run → grade-in-container → results.json
│
├── frontend/                       # Next.js 14 application
│   ├── app/                        # App Router (layout, page)
│   ├── components/
│   │   ├── chat/                   # ChatArea, MessageList, ChatInput, ToolCallCard
│   │   ├── sidebar/                # Session list, create/delete dialogs
│   │   ├── artifacts/              # SpecViewer, CodeViewer, WaveformViewer,
│   │   │                           # SchematicViewer, LayoutViewer, ReportViewer
│   │   └── ui/                     # shadcn/ui components
│   ├── lib/
│   │   ├── api.ts                  # Typed REST + WebSocket client
│   │   ├── store.ts                # Zustand store (sessions, chat, artifacts)
│   │   └── utils.ts                # Formatting helpers
│   └── types/
│       └── index.ts                # TypeScript interfaces
│
├── workspace/                      # Session workspaces (shared across interfaces)
├── state.db                        # SQLite database (shared across interfaces)
│
├── prompts/architect/              # Versioned architect system prompts (v0–v2)
└── docs/                           # Setup, MCP, and physical-design reference guides
```

---

## Design Decisions

**Single agent with many tools vs. multi-agent pipeline.** An earlier version used a fixed multi-agent graph (coder → verifier → synthesizer). The current design uses a single ReAct agent with all 35 tools, allowing it to choose its own execution order and recover from failures more flexibly. The legacy graph remains in `legacy/graph/` for reference.

**Waveform-based debugging over guessing.** The system prompt explicitly instructs the agent to never guess at simulation failures. It must call `waveform_tool` to inspect signal values at the point of failure. This improves fix accuracy over blind re-prompting.

**Shared workspace across interfaces.** Sessions created via the web UI, MCP, or Python API all operate on `workspace/<session_id>/` and checkpoint to the same `state.db`. A design started in one interface can be resumed from another.

**Tool auto-discovery for MCP.** Rather than maintaining duplicate tool definitions, the MCP server introspects LangChain `@tool` decorators and converts their Pydantic schemas to MCP format automatically.

---

## Limitations

- RTL quality depends on the underlying LLM's Verilog knowledge; complex designs may require multiple iterations or manual guidance
- Synthesis runs in Docker and can take several minutes for non-trivial designs
- Multi-provider support is available (Gemini, OpenAI, Anthropic); model-specific behavior may still require tuning
- The system targets SkyWater 130nm; other PDKs require OpenROAD configuration changes
- No authentication on the remote MCP server — network-level access control is expected

---

## Roadmap

### Completed
- [x] ReAct agent with iterative debugging
- [x] Specification-first workflow with YAML support
- [x] Icarus Verilog integration (lint, simulate)
- [x] OpenROAD synthesis via Docker
- [x] Waveform-based debugging
- [x] PPA metric extraction and reporting
- [x] Formal verification integration (SymbiYosys)
- [x] Session persistence and management
- [x] Next.js frontend with real-time streaming
- [x] MCP server with remote transport (SSE, HTTP)
- [x] Tool auto-discovery and configurable filtering
- [x] CVDP benchmark harness with reproducible, container-graded results
- [x] Google XLS / DSLX high-level-synthesis frontend

### In Progress
- [ ] Improved handling of parameterized modules
- [ ] Multi-file design support
- [ ] Constraint-driven optimization loops

### Planned
- [ ] Additional provider/runtime integrations (local/self-hosted models)
- [ ] Design space exploration
- [ ] Independent-oracle / interpretation-diff verification to close the self-verification gap

---

## Contributing

Contributions are welcome. Areas where help is particularly needed:

- **Prompt engineering**: Improving agent reliability for complex designs
- **Tool integration**: Adding support for additional EDA tools or PDKs
- **Benchmarking**: Creating test cases and evaluation metrics
- **LLM backends**: Improving model-specific behavior and adding local/self-hosted runtimes
- **Documentation**: Tutorials and example designs

Please open an issue to discuss proposed changes before submitting a pull request.

---

## Citation

If you use this work in your research, please cite:

```bibtex
@software{siliconcrew2026,
  title = {SiliconCrew: An Autonomous LLM Agent for RTL Design},
  author = {Naman Ranka},
  year = {2026},
  url = {https://github.com/naman-ranka/siliconcrew}
}
```

---

## Related Work

- [LangGraph](https://github.com/langchain-ai/langgraph) — Agent orchestration framework
- [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) — Open-source RTL-to-GDS flow
- [Icarus Verilog](https://github.com/steveicarus/iverilog) — Verilog simulation
- [SymbiYosys](https://github.com/YosysHQ/sby) — Formal verification framework
- [Model Context Protocol](https://modelcontextprotocol.io/) — Tool interoperability standard
- [VerilogEval](https://github.com/NVlabs/verilog-eval) — LLM Verilog evaluation benchmark

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

This project builds on the open-source EDA ecosystem, particularly the OpenROAD project and the SkyWater PDK. The agent framework relies on LangGraph and the LangChain tool abstraction. The MCP integration uses the Model Context Protocol SDK.

