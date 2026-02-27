# SiliconCrew

**An autonomous LLM agent for RTL design, verification, and synthesis.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Framework-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2014-black.svg)](https://nextjs.org/)
[![MCP](https://img.shields.io/badge/Protocol-MCP-blue.svg)](https://modelcontextprotocol.io/)
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

## Capabilities

- **Specification-First Workflow**: Generates structured YAML specifications before RTL, including port definitions, timing constraints, and SDC files
- **RTL Generation**: Produces synthesizable Verilog-2001 from specifications with coding style enforcement
- **Self-Checking Testbenches**: Generates testbenches with assertions, VCD dumping, and explicit PASS/FAIL reporting
- **Waveform-Based Debugging**: When simulation fails, inspects VCD signals at the point of failure rather than guessing at fixes
- **Iterative Correction**: Analyzes lint, simulation, and synthesis errors across multiple fix-verify cycles
- **Synthesis to GDSII**: Runs the OpenROAD flow via Docker targeting SkyWater 130nm to produce layout outputs
- **PPA Extraction**: Parses area, timing (WNS/TNS), and power from synthesis logs and reports
- **Formal Verification**: SymbiYosys integration for property checking and bounded model checking
- **Schematic Generation**: SVG netlist visualization from Verilog sources
- **Design Reports**: Markdown reports comparing specification requirements against achieved metrics
- **Real-Time Streaming UI**: Next.js frontend with WebSocket chat, inline tool call cards, and six artifact viewers (spec, code, waveforms, schematics, layouts, reports)
- **MCP Protocol Support**: Full toolchain exposed via Model Context Protocol (stdio, SSE, and Streamable HTTP transports) for Claude Desktop, VS Code, and other MCP clients
- **Multi-Session Management**: Isolated workspaces with per-session chat history, token tracking, and cost accounting — shared across all interfaces
- **Tool Auto-Discovery**: LangChain tool schemas are automatically converted to MCP format; adding a tool to the backend exposes it to all clients

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
│   System prompt (500+ lines of RTL design methodology)                     │
│   + Google Gemini LLM (2.5 Flash / 3 Pro)                                 │
│   + 18 LangChain tools                                                     │
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
| LLM backend | Google Gemini (2.5 Flash, 3 Pro) | Code generation, reasoning, debugging |
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
- Google Gemini API key
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

# Configure API key
echo "GOOGLE_API_KEY=your_key_here" > .env

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

Post-synthesis simulation needs managed standard-cell model caches under:
- `workspace/_stdcells/asap7/sim`
- `workspace/_stdcells/sky130hd/sim`

Bootstrap uses pinned upstream sources (not ORFS Docker extraction), so Docker is not required for this step.

Run this once after clone (or whenever you clear `workspace/_stdcells`):

```bash
# from repo root
PYTHONPATH=. python scripts/bootstrap_stdcells.py --workspace workspace --platform asap7
PYTHONPATH=. python scripts/bootstrap_stdcells.py --workspace workspace --platform sky130hd
```

PowerShell:

```powershell
$env:PYTHONPATH='.'
python scripts/bootstrap_stdcells.py --workspace workspace --platform asap7
python scripts/bootstrap_stdcells.py --workspace workspace --platform sky130hd
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

The MCP server exposes all 18 tools plus session management to any MCP-compatible client.

```bash
# Local (stdio) — for Claude Desktop
python mcp_server.py

# Remote (SSE) — accessible over the network
python mcp_server.py --transport sse --host 0.0.0.0 --port 8080

# Remote (Streamable HTTP)
python mcp_server.py --transport http --host 0.0.0.0 --port 8080
```

**Claude Desktop**: Configure the MCP server in `claude_desktop_config.json`, then load the "RTL Design Workflow" prompt. See [MCP_SETUP.md](MCP_SETUP.md).

**VS Code**: Configure via settings and use Copilot Chat with full tool access. See [MCP_VSCODE_SETUP.md](MCP_VSCODE_SETUP.md).

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
├── app.py                          # Legacy Streamlit interface
├── docker-compose.yml              # Container orchestration
├── Dockerfile.backend              # Backend Docker image
├── requirements.txt
│
├── src/
│   ├── config.py                   # Model and environment configuration
│   ├── agents/
│   │   ├── architect.py            # Primary ReAct agent + system prompt
│   │   ├── rtl_coder.py            # RTL generation node (legacy graph)
│   │   ├── verifier.py             # Verification node (legacy graph)
│   │   ├── synthesis_agent.py      # Synthesis node (legacy graph)
│   │   └── ppa_analyst.py          # PPA analysis node (legacy graph)
│   ├── graph/
│   │   └── graph.py                # Multi-agent state graph (legacy)
│   ├── state/
│   │   └── state.py                # DesignState TypedDict
│   ├── tools/
│   │   ├── wrappers.py             # 18 LangChain @tool definitions
│   │   ├── spec_manager.py         # YAML spec handling + validation
│   │   ├── run_linter.py           # Icarus Verilog linting
│   │   ├── run_simulation.py       # Simulation orchestration
│   │   ├── run_iverilog.py         # iverilog compile + vvp execute
│   │   ├── run_synthesis.py        # OpenROAD via Docker
│   │   ├── run_docker.py           # Docker command runner
│   │   ├── run_cocotb.py           # Cocotb test runner
│   │   ├── run_sby.py              # SymbiYosys formal verification
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
├── MCP_SETUP.md                    # MCP configuration (Claude Desktop)
├── MCP_VSCODE_SETUP.md             # MCP configuration (VS Code)
└── MCP_SESSION_GUIDE.md            # Session management documentation
```

---

## Design Decisions

**Single agent with many tools vs. multi-agent pipeline.** An earlier version used a fixed multi-agent graph (coder → verifier → synthesizer). The current design uses a single ReAct agent with all 18 tools, allowing it to choose its own execution order and recover from failures more flexibly. The legacy graph remains in `src/graph/` for reference.

**Waveform-based debugging over guessing.** The system prompt explicitly instructs the agent to never guess at simulation failures. It must call `waveform_tool` to inspect signal values at the point of failure. This improves fix accuracy over blind re-prompting.

**Shared workspace across interfaces.** Sessions created via the web UI, MCP, or Python API all operate on `workspace/<session_id>/` and checkpoint to the same `state.db`. A design started in one interface can be resumed from another.

**Tool auto-discovery for MCP.** Rather than maintaining duplicate tool definitions, the MCP server introspects LangChain `@tool` decorators and converts their Pydantic schemas to MCP format automatically.

---

## Limitations

- RTL quality depends on the underlying LLM's Verilog knowledge; complex designs may require multiple iterations or manual guidance
- Synthesis runs in Docker and can take several minutes for non-trivial designs
- Currently supports Google Gemini models only; other LLM backends would require adapting the agent constructor
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

### In Progress
- [ ] Improved handling of parameterized modules
- [ ] Multi-file design support
- [ ] Constraint-driven optimization loops

### Planned
- [ ] Alternative LLM backends (Claude, GPT-4, local models)
- [ ] Design space exploration
- [ ] Benchmark suite for evaluation

---

## Contributing

Contributions are welcome. Areas where help is particularly needed:

- **Prompt engineering**: Improving agent reliability for complex designs
- **Tool integration**: Adding support for additional EDA tools or PDKs
- **Benchmarking**: Creating test cases and evaluation metrics
- **LLM backends**: Adapting the agent to work with other models
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
