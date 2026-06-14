# CVDP × SiliconCrew — Results (authoritative)

*This is the clean, correct results summary. It supersedes `CVDP_XLS_RESEARCH_LOG.md`, which is kept
only as the investigation trajectory (it contains the broken-eval numbers — do not cite them).*

**Grading:** every verdict here was produced in the **official CVDP reference container**
`ghcr.io/hdl/sim/osvb` (Linux, cocotb 2.0-dev, iverilog 13) running the official harness
(`pytest /src/test_runner.py`), with `/code` staged like the official runner (provided **context**
files + the agent's **patch-target** files). Tool: `cvdp-pipeline/regrade_docker.py`.

**Agent:** codex/gpt-5.5 via SiliconCrew MCP. **Sample:** 30 of the 92 `no_commercial` agentic problems.

---

## Headline

**SiliconCrew natural-mode pass rate: 20 / 30 ≈ 67%** (+1 borderline/flaky).

| | pass rate | note |
|---|---|---|
| March-2026 baseline (old SC) | 40% (37/92) | full set |
| Overnight Windows shim (BROKEN) | ~30–40% | ~14/30 verdicts wrong — DO NOT USE |
| **Reference container (this subset)** | **~67% (20/30)** | trustworthy |

The overnight "SiliconCrew fails most control/protocol problems" story was a **Windows-eval artifact**.

---

## 1. What SiliconCrew was able to do (the 20 passes)

It solved a broad spread of design classes:
- **Combinational / datapath:** binary_to_gray, barrel_shifter, Min_Hamming_Distance_Finder, rgb_color_space_conversion
- **Arithmetic / crypto:** DES, gcd (RSA-style crypto accel), rc5, spi_complex_mult
- **Memory / buffers / DMA:** async_filo (dual-clock!), custom_fifo, cache_controller, dma_xfer_engine, event_storing
- **FSM / control / timers:** elevator_control, traffic_light_controller, ttc_lite
- **DSP:** sigma_delta_audio, dynamic_equalizer_0001, phase_rotation_0013

→ Strength across datapath, control/FSM, memory, and a solid chunk of DSP/crypto. Notably it handled
**dual-clock CDC** (async_filo), multi-module **crypto** (gcd), and stateful **control** correctly.

## 2. How XLS helped (controlled Verilog-vs-XLS pairs, both container-verified)

| problem | Verilog | XLS | effect |
|---|---|---|---|
| phase_rotation_0010 | FAIL | **PASS** | XLS unlocked it |
| monte_carlo | FAIL | **PASS** | XLS unlocked it |
| spi_complex_mult | **PASS** | FAIL | XLS broke a working design |
| phase_rotation_0013 / sigma_delta | PASS | PASS | no difference |
| dynamic_equalizer_0004 / phase_rotation_0015 | FAIL | FAIL | no difference |

**XLS: helped 2, hurt 1, no-diff 4 (n=7).** It can unlock a hard arithmetic/DSP kernel the agent
flubs in Verilog (phase_rotation_0010, monte_carlo), but can also break one it solves in Verilog
(spi_complex_mult — the XLS core was fine, the hand-written sequential wrapper drove an output to X).
**Verdict: inconclusive at this sample, slight net-positive.** XLS is worth offering as an *optional*
tool for pure arithmetic/datapath kernels — not forcing. (Independent finding that still holds: the
agent never *chose* XLS on its own because the architect prompt told it to avoid XLS for fixed/legacy
interfaces — = all of CVDP; that prompt was fixed.)

## 3. The genuine failures + learnings (how to improve SiliconCrew)

| failure | nature | learning |
|---|---|---|
| hdbn_codec (0/429), jpeg_runlength (0/55), prbs (0/73) | encoders/codecs wrong across many vectors | **Bit-level protocol/encoding precision** is the agent's biggest weakness — exact multi-state encoding schemes. |
| poly_decimator | **hangs the simulator** (infinite/comb loop) | Add a **termination/comb-loop check** before submitting; the agent can emit non-terminating RTL. |
| phase_rotation_0010 (fail), phase_rotation_0015 (partial 24/21), dynamic_equalizer_0004 (flaky) | borderline numerical/DSP | Marginal arithmetic precision / edge cases; XLS helped one. |
| csr_apb (0/2), queue (0/1), monte_carlo (0/1) | interface/protocol + arithmetic | Smaller logic/protocol bugs. |

**The #1 cross-cutting learning — the self-verification gap.** Across the genuine fails, the agent
**self-reported PASS**: it verified against the weaker context testbench (or one it wrote) and shipped,
then failed the stricter hidden official harness. The single highest-leverage improvement is **stronger,
more adversarial self-verification** (edge cases, full parameter sweeps, use `prompt_contract` as a
checklist, be skeptical of its own "pass") — so it stops shipping designs it only *thinks* are correct.

**Prioritized actions:**
1. **Adversarial self-verification** (biggest lever — closes the false-confidence gap).
2. **Comb-loop / termination lint** (poly_decimator hang).
3. **Codec/protocol precision** — better spec extraction + reference checking for encoders.
4. **Offer XLS** (not force) for pure arithmetic/datapath kernels.

## 4. Caveats
- Sample = 30/92. Full-92 numbers require running SiliconCrew on the other 62 (agentic phase) + grading.
- All grading must use the **reference container** (`regrade_docker.py`), never the deprecated Windows
  shim. See `EVAL_BROKEN_HANDOFF.md` for why.
