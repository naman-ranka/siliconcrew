# SiliconCrew IDE Usability Evaluation (Phase 2)

**Goal:** Stress-test the IDE's real usability across 8 RTL designs of increasing
difficulty, each attempting the full flow **write → lint → simulate → synthesize
→ inspect → iterate**. Produce evidence-backed feedback for a clean, IDE-like
redesign — and directly answer: *are the pipeline "stages" necessary, or
gimmicky?*

This is the human-path evaluation: can a hardware engineer sit down and use this
tool by themselves to write code, test it, simulate, synthesize, and inspect
output — without fighting the UI?

## Environment constraints (important — read first)

This evaluation ran in the Claude Code remote container, which has hard limits
that shaped the method. These are environment facts, **not** product bugs:

1. **No LLM API key** is available in this container (no `.env`, no
   GOOGLE/OPENAI/ANTHROPIC keys). → The in-UI **AI architect agent cannot run**,
   so "spec → code by the AI" could not be exercised. We therefore evaluate the
   **human path**: a person bringing/writing RTL and driving the pipeline
   themselves. (This is exactly the stated goal.)
2. **No synthesis toolchain**: `yosys` and `openroad` are not installed and the
   **Docker daemon is down**. → **Synthesis → GDS cannot execute.** We exercise
   the Synthesize button anyway and document the *failure-handling UX* (which is
   itself critical feedback).
3. **What does work natively:** `iverilog` is present → **Lint works** (it is
   iverilog-based) and **Verilog-testbench simulation works**.

So the real ceiling reachable here is **write → lint → simulate → inspect
waveform**, plus the **synth-stage UX up to the point the engine is unavailable**.

## The 8 designs (increasing difficulty)

Authored by hand (no in-UI LLM). Each has a module + a self-checking Verilog
testbench (`TEST PASSED` / `TEST FAILED`). All 8 lint clean and simulate to
PASS under iverilog (verified offline before the UI runs).

| # | dir | design | concept |
|---|-----|--------|---------|
| 1 | `01_mux2`     | 2:1 mux            | pure combinational (baseline) |
| 2 | `02_adder4`   | 4-bit adder        | multi-bit combinational + random TB |
| 3 | `03_dff`      | D flip-flop        | first clocked element (clk + reset) |
| 4 | `04_counter8` | 8-bit counter      | enable/clear sequential logic |
| 5 | `05_shiftreg` | 8-bit shift reg    | load + serial shift, bus concat |
| 6 | `06_seqdet`   | 1011 detector      | two-always Moore FSM |
| 7 | `07_alu4`     | 4-bit ALU          | op-decoded datapath with flags |
| 8 | `08_fifo`     | depth-4 FIFO       | memory + pointers + full/empty (hardest) |

## Method / artifacts

- `gen_designs.py` — regenerates the designs + testbenches under `designs/`.
- `run_eval.mjs` — headless Playwright harness that drives the **live UI** as a
  human: create session → `/workbench` → upload RTL+TB → Lint → Simulate →
  view Wave → Synthesize → inspect viewers → also visit the chat-first route.
  Emits screenshots + `timeline.json` (timings, result text, console output,
  JS errors, failed network requests) per design.
- `run_all.sh` — runs the harness across all 8 designs sequentially.
- Screenshots + timelines: `plans/phase2/screenshots/ide-eval/<design>/`.
- `FINDINGS.md` — the synthesized usability report + redesign proposal (written
  after the per-design evaluator agents run).

## Stack used

Local self-host stack (functionally identical to deployed for the RTL pipeline,
without the auth complexity): backend `:8001` (`SIM_ENGINE=native`, iverilog),
frontend `:3001`.
