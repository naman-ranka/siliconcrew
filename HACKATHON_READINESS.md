# Hackathon Problem Readiness & Execution Guide

This document explains how to run the [ICLAD 2025 Hackathon](https://github.com/ICLAD-Hackathon/ASU-Spec2Tapeout-ICLAD25-Hackathon) example problems using **SiliconCrew**.

---

## Prerequisites

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.\.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Required Tools

| Tool | Purpose | Installation |
|------|---------|--------------|
| **Icarus Verilog** | Simulation & Linting | Windows: [Download](https://bleyer.org/icarus/), Linux: `apt install iverilog` |
| **Docker** | Synthesis (ORFS) | [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Google API Key** | LLM Access | Create `.env` file with `GOOGLE_API_KEY=your_key` |

### 3. Verify Setup

```bash
# Check iVerilog
iverilog -v

# Check Docker
docker --version

# Pull OpenROAD image (one-time)
docker pull openroad/orfs:latest
```

---

## Running the Example Problem (P1: Sequence Detector)

### Method 1: Using SiliconCrew UI (Recommended for Development)

```bash
# Start the app
streamlit run app.py
```

1. **Create New Session**: Name it `p1_seq_detector`
2. **Enter Prompt** (copy from YAML spec):

```
Design a sequence detector module named "seq_detector_0011" that detects the binary sequence "0011" in an input stream.

Requirements:
- Module name: seq_detector_0011
- Clock period: 1.1ns (SkyWater 130HD)
- Ports:
  - input clk: Clock input
  - input reset: Synchronous reset (active high)
  - input data_in: Serial data input
  - output reg detected: Asserted high for one cycle when '0011' is detected

The module should implement an FSM that:
1. Monitors data_in on each rising clock edge
2. Detects overlapping sequences (e.g., 00110011 should detect twice)
3. detected output should be registered (one clock delay after pattern match)

Sample I/O:
- Input:  0001100110110010
- Output: 0000010001000000
```

3. **Let the Agent Work**:
   - Agent writes RTL → Lints → Generates testbench → Simulates
   - If simulation fails, agent debugs using waveform_tool
   
4. **Run Synthesis**:
   - Say: "Run synthesis with clock period 1.1ns"
   - Agent runs ORFS, produces GDS and reports
   
5. **Extract Results**:
   - Copy generated files from `workspace/<session_name>/` to hackathon solutions folder

### Method 2: Manual CLI Workflow (For Evaluation)

```bash
# Step 1: Generate RTL manually (or copy from successful UI session)
# The agent generates: design.v

# Step 2: Verify with hackathon testbench
cd ASU-Spec2Tapeout-ICLAD25-Hackathon/evaluation
python evaluate_verilog.py \
  --verilog ../../workspace/<session>/seq_detector_0011.v \
  --problem 1 \
  --tb ../example_problem/intermediate/iclad_seq_detector_tb.v

# Step 3: Run synthesis (from SiliconCrew workspace)
# The synthesis_tool generates files in workspace/<session>/orfs_results/

# Step 4: Evaluate PPA
python evaluate_openroad.py \
  --odb ../../workspace/<session>/orfs_results/sky130hd/<module>/base/6_final.odb \
  --sdc ../../workspace/<session>/constraints.sdc \
  --flow_root /path/to/OpenROAD-flow-scripts \
  --problem 1
```

---

## Problem-Specific Prompts

### P1: Sequence Detector (seq_detector_0011)

```
Design a sequence detector FSM for pattern "0011" with:
- Module: seq_detector_0011
- Ports: clk, reset, data_in, detected (output reg)
- Use 3-bit state encoding, overlapping detection
- Target: SkyWater 130HD, 1.1ns clock
```

### P5: Dot Product Engine

```
Design a pipelined dot product module with:
- Module: dot_product
- Parameters: N=8 (vector length), WIDTH=8 (element bits)
- Ports: clk, rst, A[N-1:0][WIDTH-1:0] (signed), B[N-1:0][WIDTH-1:0] (signed), 
         dot_out[2*WIDTH+3:0] (signed), valid
- Compute sum of A[i]*B[i] with registered output and valid flag
- Target: SkyWater 130HD, 4.5ns clock
```

### P7: Fixed-Point Exponential

```
Design exp_fixed_point using 3-term Taylor series (e^x ≈ 1 + x + x²/2 + x³/6):
- Module: exp_fixed_point
- Parameter: WIDTH=8
- Ports: clk, rst, enable, x_in[WIDTH-1:0], exp_out[2*WIDTH-1:0]
- Input: UQ1.(WIDTH-1) format, Output: UQ1.(2*WIDTH-1) format
- 2-stage pipeline
- Target: SkyWater 130HD, 4.5ns clock
```

### P8: FP16 Multiplier

```
Design IEEE 754 half-precision floating-point multiplier:
- Module: fp16_multiplier
- Ports: a[15:0], b[15:0], result[15:0]
- Handle zero detection, rounding to nearest even
- Combinational (single-cycle)
- Target: SkyWater 130HD, 9ns clock
```

### P9: FIR Filter

```
Design pipelined N-tap FIR filter:
- Module: fir_filter
- Parameters: WIDTH=16, N=8
- Ports: clk, rst, x_in[WIDTH-1:0] (signed), h[N-1:0][WIDTH-1:0] (signed), 
         y_out[2*WIDTH+$clog2(N):0] (signed)
- Implement as multiply-accumulate pipeline with tap delay line
- Target: SkyWater 130HD, 8ns clock
```

---

## Expected Output Structure

For each problem, you need:

```
solutions/visible/p1/
├── seq_detector_0011.v     # Generated RTL
├── 6_final.sdc             # Timing constraints
└── 6_final.odb             # OpenROAD database
```

### Copying Files from SiliconCrew

```bash
# After successful synthesis
cp workspace/<session>/seq_detector_0011.v \
   ASU-Spec2Tapeout-ICLAD25-Hackathon/solutions/visible/p1/

cp workspace/<session>/constraints.sdc \
   ASU-Spec2Tapeout-ICLAD25-Hackathon/solutions/visible/p1/6_final.sdc

cp workspace/<session>/orfs_results/sky130hd/*/base/6_final.odb \
   ASU-Spec2Tapeout-ICLAD25-Hackathon/solutions/visible/p1/
```

---

## Current Limitations & Workarounds

| Limitation | Workaround |
|------------|------------|
| No YAML parsing | Manually convert YAML to natural language prompt |
| No batch mode | Run each problem in separate UI session |
| Module naming | Explicitly state module name in prompt |
| SDC clock period | Tell agent the target clock explicitly |

---

## Readiness Checklist

- [x] **RTL Generation**: Works via chat interface
- [x] **Linting**: Automatic via linter_tool
- [x] **Simulation**: Works with iverilog
- [x] **Synthesis**: Works via Docker + ORFS
- [x] **PPA Extraction**: Works via ppa_tool
- [ ] **YAML Input**: Not yet supported (manual conversion needed)
- [ ] **Batch Execution**: Not yet supported (requires CLI wrapper)

---

## Quick Test Run

To verify your setup works end-to-end:

```bash
# 1. Start SiliconCrew
streamlit run app.py

# 2. Create session "test_counter"

# 3. Enter: "Design a 4-bit counter with synchronous reset"

# 4. Wait for RTL generation + verification

# 5. Say: "Run synthesis"

# 6. Check workspace/test_counter/ for outputs
```

If this works, you're ready to tackle the hackathon problems!

---

*Generated: 2026-01-28*
