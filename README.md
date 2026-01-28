# SiliconCrew

**An autonomous LLM agent for RTL design, verification, and synthesis.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Framework-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Status: Research](https://img.shields.io/badge/Status-Research%20Prototype-yellow.svg)]()

---

## Overview

SiliconCrew is a research prototype that explores the use of Large Language Models (LLMs) as autonomous agents for digital hardware design. Given a natural language specification, the agent generates synthesizable RTL, writes self-checking testbenches, iterates on verification failures, and produces physical design outputs through the OpenROAD flow.

This project investigates the following research questions:
- Can LLM agents effectively close the RTL design loop (spec → code → verify → fix)?
- How should agent workflows be structured for hardware design tasks?
- What tool interfaces enable effective LLM-driven EDA automation?

**Note**: This is an active research project. Contributions, feedback, and collaboration are welcome.

---

## Capabilities

- **Specification-First Workflow**: Generates YAML design specifications before RTL implementation
- **RTL Generation**: Produces synthesizable Verilog/SystemVerilog from specifications
- **Self-Checking Testbenches**: Automatically generates testbenches with pass/fail assertions
- **Iterative Debugging**: Uses waveform analysis to diagnose and fix simulation failures
- **Synthesis Integration**: Runs OpenROAD flow via Docker to produce GDSII layouts
- **PPA Analysis**: Extracts area, timing (WNS/TNS), and power metrics
- **Formal Verification**: Optional SymbiYosys integration for property checking
- **Design Reports**: Generates comparison reports (specification vs. achieved metrics)

---

## Architecture

SiliconCrew uses a **ReAct (Reasoning + Acting)** agent pattern implemented with LangGraph. The agent has access to a set of EDA tools and iterates until the design meets specification.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INPUT                                     │
│                    (Natural Language or YAML Spec)                          │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ARCHITECT AGENT                                   │
│                        (LangGraph ReAct Loop)                               │
│                                                                             │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐                 │
│   │ Reason  │ -> │  Plan   │ -> │  Act    │ -> │ Observe │ ──┐             │
│   └─────────┘    └─────────┘    └─────────┘    └─────────┘   │             │
│        ▲                                                      │             │
│        └──────────────────────────────────────────────────────┘             │
│                         (iterate until done)                                │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
                    ▼             ▼             ▼
            ┌───────────┐ ┌───────────┐ ┌───────────┐
            │   SPEC    │ │   VERIFY  │ │ SYNTHESIS │
            │   TOOLS   │ │   TOOLS   │ │   TOOLS   │
            ├───────────┤ ├───────────┤ ├───────────┤
            │write_spec │ │linter     │ │synthesis  │
            │read_spec  │ │simulation │ │ppa_tool   │
            │load_yaml  │ │waveform   │ │search_logs│
            └───────────┘ └───────────┘ └───────────┘
                    │             │             │
                    ▼             ▼             ▼
            ┌───────────┐ ┌───────────┐ ┌───────────┐
            │   YAML    │ │  iVerilog │ │ OpenROAD  │
            │   Spec    │ │    VCD    │ │   GDSII   │
            └───────────┘ └───────────┘ └───────────┘
```

### Agent Workflow

1. **Specification Phase**: Agent creates a YAML specification defining module interface, ports, timing constraints, and behavioral requirements.

2. **Implementation Phase**: Agent reads the specification and generates RTL that strictly follows the defined module signature.

3. **Verification Phase**: Agent writes a self-checking testbench, runs simulation via Icarus Verilog, and analyzes waveforms if tests fail.

4. **Synthesis Phase**: Agent invokes the OpenROAD flow (via Docker) to produce physical design outputs and extracts PPA metrics.

5. **Iteration**: If any phase fails, the agent analyzes errors and iterates on the design.

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Agent Framework | LangGraph | ReAct agent orchestration with tool calling |
| LLM Backend | Google Gemini | Code generation and reasoning |
| Simulation | Icarus Verilog | RTL compilation and simulation |
| Waveform Analysis | vcdvcd | VCD parsing for debug |
| Synthesis | OpenROAD (ORFS) | Logic synthesis and physical design |
| Target PDK | SkyWater 130nm | Open-source process design kit |
| UI | Streamlit | Interactive chat interface |
| Persistence | SQLite | Session and checkpoint storage |

---

## Installation

### Prerequisites

- Python 3.10 or higher
- Icarus Verilog (`iverilog`)
- Docker (for synthesis features)
- Google Gemini API key

### Setup

```bash
# Clone the repository
git clone https://github.com/naman-ranka/siliconcrew.git
cd siliconcrew

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API key
echo "GOOGLE_API_KEY=your_key_here" > .env

# Run the application
streamlit run app.py
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

---

## Usage

### Interactive Mode (Streamlit UI)

1. Start the application: `streamlit run app.py`
2. Create a new session with a descriptive name
3. Describe your design in natural language:
   ```
   Design a 4-bit synchronous counter with active-high reset and enable signal.
   Target clock period: 10ns.
   ```
4. Review the generated specification in the **Spec** tab
5. Monitor RTL generation and verification in the **Code** and **Waveform** tabs
6. Run synthesis and view results in the **Layout** and **Report** tabs

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
      type: logic
      description: Clock input
    - name: rst
      direction: input
      type: logic
      description: Synchronous reset (active high)
    - name: enable
      direction: input
      type: logic
      description: Count enable
    - name: count
      direction: output
      type: logic
      width: 4
      description: Counter output
  module_signature: |
    module counter_4bit(
        input  logic clk,
        input  logic rst,
        input  logic enable,
        output logic [3:0] count
    );
```

---

## Project Structure

```
RTL_AGENT/
├── app.py                      # Streamlit UI application
├── src/
│   ├── agents/
│   │   └── architect.py        # ReAct agent with system prompt
│   ├── tools/
│   │   ├── wrappers.py         # LangChain tool definitions
│   │   ├── spec_manager.py     # YAML specification handling
│   │   ├── design_report.py    # Report generation
│   │   ├── run_linter.py       # Icarus Verilog linting
│   │   ├── run_simulation.py   # Simulation execution
│   │   ├── run_synthesis.py    # OpenROAD integration
│   │   ├── get_ppa.py          # PPA metric extraction
│   │   └── read_waveform.py    # VCD analysis
│   └── utils/
│       ├── session_manager.py  # Session persistence
│       └── visualizers.py      # Waveform/GDS rendering
├── workspace/                  # Agent working directory
├── requirements.txt
└── README.md
```

---

## Roadmap

### Completed
- [x] ReAct agent with iterative debugging
- [x] Specification-first workflow with YAML support
- [x] Icarus Verilog integration (lint, simulate)
- [x] OpenROAD synthesis via Docker
- [x] Waveform-based debugging
- [x] PPA metric extraction and reporting
- [x] Session persistence and management
- [x] Real-time UI updates

### In Progress
- [ ] Improved handling of parameterized modules
- [ ] Multi-file design support
- [ ] Constraint-driven optimization loops

### Planned
- [ ] Alternative LLM backends (Claude, GPT-4, local models)
- [ ] Formal verification integration (SymbiYosys)
- [ ] Design space exploration
- [ ] Benchmark suite for evaluation

---

## Contributing

Contributions are welcome. Areas where help is particularly needed:

- **Prompt Engineering**: Improving agent reliability for complex designs
- **Tool Integration**: Adding support for additional EDA tools
- **Benchmarking**: Creating test cases and evaluation metrics
- **Documentation**: Tutorials and example designs

Please open an issue to discuss proposed changes before submitting a pull request.

---

## Citation

If you use this work in your research, please cite:

```bibtex
@software{siliconcrew2025,
  title = {SiliconCrew: An Autonomous LLM Agent for RTL Design},
  author = {Naman Ranka},
  year = {2025},
  url = {https://github.com/naman-ranka/siliconcrew}
}
```

---

## Related Work

- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent orchestration framework
- [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) - Open-source RTL-to-GDS flow
- [Icarus Verilog](https://github.com/steveicarus/iverilog) - Verilog simulation
- [VerilogEval](https://github.com/NVlabs/verilog-eval) - LLM Verilog evaluation benchmark

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

This project builds on the open-source EDA ecosystem, particularly the OpenROAD project and the SkyWater PDK. We thank the LangChain team for the LangGraph framework.
