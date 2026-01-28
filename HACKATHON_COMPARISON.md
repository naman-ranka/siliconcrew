# SiliconCrew vs ICLAD 2025 Hackathon Requirements

## Overview

This document compares the **SiliconCrew RTL Agent** project capabilities against the [ASU Spec2Tapeout ICLAD 2025 Hackathon](https://github.com/ICLAD-Hackathon/ASU-Spec2Tapeout-ICLAD25-Hackathon) requirements.

---

## Hackathon Requirements Summary

The hackathon requires an **LLM agent** that can:

| Requirement | Description |
|-------------|-------------|
| **Input** | YAML spec files with module signature, ports, clock period, description |
| **Output 1** | Synthesizable RTL in SystemVerilog |
| **Output 2** | Constraint files (SDC format) |
| **Output 3** | Tapeout-ready ODB (`6_final.odb`) via OpenROAD-flow-scripts |
| **Verification** | Functional verification using iVerilog with provided testbenches |
| **Evaluation** | PPA metrics (timing WNS/TNS, power, area) scored against reference |

### Problem Types
- P1: Sequence Detector (FSM)
- P5: Pipelined Dot Product (parameterized, signed arithmetic)
- P7: Fixed-point Exponential (Taylor series, pipelined)
- P8: FP16 Multiplier (IEEE 754 half-precision)
- P9: FIR Filter (pipelined, parameterized)

---

## Capability Comparison Matrix

| Capability | Hackathon Requirement | SiliconCrew Status | Notes |
|------------|----------------------|-------------------|-------|
| **RTL Generation** | ✅ Required | ✅ **SUPPORTED** | Architect agent generates Verilog via LLM |
| **Testbench Generation** | Not required (provided) | ✅ **SUPPORTED** | Agent can generate self-checking testbenches |
| **Linting** | Required (implicit) | ✅ **SUPPORTED** | `linter_tool` using iVerilog `-t null` |
| **Simulation** | ✅ Required (iVerilog) | ✅ **SUPPORTED** | `simulation_tool` compiles + runs via iVerilog |
| **Waveform Debug** | Helpful | ✅ **SUPPORTED** | `waveform_tool` + VCD viewer in UI |
| **SDC Generation** | ✅ Required | ⚠️ **PARTIAL** | Auto-generates basic SDC; manual is possible |
| **Synthesis (ORFS)** | ✅ Required | ✅ **SUPPORTED** | `synthesis_tool` via Docker + OpenROAD |
| **GDS/ODB Output** | ✅ Required (`6_final.odb`) | ✅ **SUPPORTED** | ORFS flow produces all outputs |
| **PPA Extraction** | ✅ Required | ✅ **SUPPORTED** | `ppa_tool` extracts area, timing, power |
| **YAML Spec Parsing** | ✅ Required | ❌ **NOT SUPPORTED** | Currently uses natural language input |
| **Batch/Script Mode** | ✅ Required (`your_agent.py`) | ❌ **NOT SUPPORTED** | Currently interactive Streamlit UI only |
| **Module Signature Compliance** | ✅ Required | ⚠️ **PARTIAL** | Agent follows prompts, but no strict enforcement |
| **Cocotb Tests** | Optional | ✅ **SUPPORTED** | `cocotb_tool` for Python-based testing |
| **Formal Verification** | Optional | ✅ **SUPPORTED** | `sby_tool` for SymbiYosys formal proofs |

---

## Strengths of SiliconCrew (Advantages)

| Feature | Benefit |
|---------|---------|
| **Interactive Chat UI** | Natural language interaction, easier debugging |
| **Self-Correcting Loop** | Agent iterates on linter/simulation failures automatically |
| **Testbench Generation** | Can create testbenches from scratch (hackathon provides them) |
| **Waveform Visualization** | Built-in VCD viewer for debugging |
| **GDS Visualization** | Can render layout SVGs in UI |
| **Schematic Generation** | `schematic_tool` generates visual netlists |
| **Session Management** | Persistent sessions with token tracking and cost estimation |
| **Cocotb + Formal** | Advanced verification beyond hackathon requirements |

---

## Gaps to Address for Hackathon Compliance

### Critical Gaps

| Gap | Impact | Effort to Fix |
|-----|--------|---------------|
| **No YAML Spec Parsing** | Cannot consume hackathon input format | Medium - Add YAML parser + prompt builder |
| **No Batch/Script Mode** | Cannot run `your_agent.py` for evaluation | Medium - Extract core logic to CLI script |
| **No Strict Signature Enforcement** | Module names/ports may not match exactly | Low - Add signature validation |

### Minor Gaps

| Gap | Impact | Effort to Fix |
|-----|--------|---------------|
| **SDC from spec** | Clock period from YAML not auto-used | Low - Parse `clock_period` from YAML |
| **Problem-specific testbench path** | Hardcoded workspace structure | Low - Make paths configurable |

---

## Verdict

### Overall Assessment: **SiliconCrew is 75-80% Ready**

**What Works Well:**
- Full RTL generation → verification → synthesis → PPA pipeline ✅
- All core EDA tools integrated (iVerilog, ORFS, Cocotb, SBY) ✅
- Iterative self-correction capability ✅
- Rich debugging features (waveforms, schematics) ✅

**What's Missing:**
- YAML spec parsing (currently expects natural language)
- Script/CLI mode for automated evaluation
- Strict module signature enforcement

### Recommendation

To make SiliconCrew hackathon-ready:

1. **Add YAML Parser (2-3 hours)**
   - Parse problem YAML files
   - Build prompts from spec fields

2. **Create CLI Agent Script (2-3 hours)**
   - `solutions/your_agent.py` wrapping core logic
   - Accept `--problem`, `--yaml`, `--output-dir` arguments

3. **Add Signature Validation (1 hour)**
   - Post-process generated RTL to verify module signature matches spec

---

## Architecture Comparison

```
┌─────────────────────────────────────────────────────────────────┐
│                    HACKATHON FLOW                               │
│  YAML Spec → Agent Script → RTL + SDC → ORFS → ODB + Metrics   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    SILICONCREW FLOW                             │
│  Chat UI → Architect Agent → RTL → Lint → Sim → Synth → PPA   │
│            (uses tools)      ↑_____|______|                     │
│                              └── Self-correction loop           │
└─────────────────────────────────────────────────────────────────┘
```

SiliconCrew has a **more sophisticated iterative loop** but lacks the **structured input parsing** the hackathon requires.

---

*Generated: 2026-01-28*
