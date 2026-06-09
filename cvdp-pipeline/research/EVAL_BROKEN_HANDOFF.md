# CVDP eval was broken — handoff context for re-running harnesses

**TL;DR:** The overnight grading did NOT use CVDP's official Docker harness. It used a hand-rolled
Windows-native cocotb shim (`cvdp-pipeline/replay_cvdp_harness.py`). That produced **~half-wrong
verdicts** (both false negatives and false positives). Any pass/fail number from the Windows replay or
`bench-orchestrator` dashboards is **untrustworthy** and must be re-graded in the container.

## Root cause: wrong environment
CVDP harnesses are written for / meant to run in **`ghcr.io/hdl/sim/osvb`** (Linux, **cocotb 2.0.0-dev**,
**iverilog 13**). The Windows shim ran them on **cocotb 2.0.1 + iverilog 12 on Windows** — different
simulator + a flaky cocotb Python/VPI embedding. Harnesses are **mixed**: some written for cocotb-1.x
(`from cocotb.runner import get_runner`, `.value.to_unsigned()`), some for 2.0 (`cocotb_tools.runner`).

## Why verdicts were wrong (3 mechanisms)
1. **False negatives (passing design → "FAIL"):** on Windows, cocotb's VPI crashes vvp at init for many
   harnesses → "Simulation terminated abnormally / result xml not found", regardless of the RTL.
   ~11 passing designs were marked failed. Also iverilog-12 vs -13 semantic diffs flipped verdicts
   (sigma_delta: "10 failed" on Windows, **10 passed** in Docker).
2. **False positives (failing design → "PASS"):** simulator-semantic divergence (uninitialized/X/race);
   a latent-bug design can pass on one iverilog and fail on another (e.g. `queue`).
3. **Compat-patch side effects:** the shim regex-patches harnesses (`to_unsigned`→`int`, `to_signed`,
   odd-`Clock`→`period_high`) to bridge cocotb-1.x→2.0. These can **alter test semantics and flip
   verdicts** (sigma_delta PASSES unpatched, FAILS patched). **Applying patches universally is wrong.**
4. Red herring: `TypeError: load_entry() takes 0 positional arguments` is harmless **atexit noise**,
   present in passing runs too — NOT the failure cause.

## The correct way to run (use this)
Run each harness in **`ghcr.io/hdl/sim/osvb`** (`docker pull ghcr.io/hdl/sim/osvb`):
- Mount harness `src/` → `/src` (ro); solution RTL dir → `/code` so `/code/rtl/*.sv` matches the
  `.env` `VERILOG_SOURCES`; `-w /code/rundir`; command `pytest /src/<test_runner.py> -v`.
- **Unpatched-first:** run the harness AS-IS. Only apply the cocotb-1.x **import shim** (`cocotb.runner`
  → try/except `cocotb_tools.runner`) **if it fails to load** (`ModuleNotFoundError`). Do NOT apply the
  value/Clock patches to 2.0-native harnesses.
- Handle the **nested layout**: some harnesses are `src/<test>/test_runner.py` + nested `.env`.

## Gotchas (will bite an agent)
- `.env` has spaces around `=` (`VERILOG_SOURCES = /code/...`) → docker `--env-file` mishandles it;
  parse and pass `-e KEY=VALUE` with values stripped. Set `WAVE=0`.
- Git Bash mangles docker `-w /code/rundir` (→ `C:/Program Files/Git/...`); run docker from **PowerShell**
  or set `MSYS_NO_PATHCONV=1`.
- Container is cocotb **2.0.0-dev** (has `cocotb_tools.runner`, NOT `cocotb.runner`), iverilog **13**.

## Tooling already built
- `cvdp-pipeline/regrade_docker.py` — implements the correct flow (container + unpatched-first +
  nested-harness + import-shim-on-load-fail). Usage: `python cvdp-pipeline/regrade_docker.py --ids <a,b>`
  (needs `RTL_WORKSPACE` exported + Docker engine running). This is the trustworthy grader.
- **Best path forward:** stop hand-rolling — feed SiliconCrew's written RTL to CVDP's official
  `cvdp_benchmark/run_benchmark.py` (`-a/--answers` or `--model local_import --prompts-responses-file`),
  which applies solutions + runs each harness in the pinned image + scores authoritatively.

## Verified result on the 30-problem subset (trustworthy container grade)
SiliconCrew natural mode: **20/30 PASS (~67%)** — vs the broken Windows eval's ~30–40% (~14/30 verdicts
wrong) and the March-2026 baseline 40%. Genuine fails (study these): csr_apb, dynamic_equalizer_0004,
hdbn_codec, jpeg_runlength, monte_carlo, phase_rotation_0010, phase_rotation_0015, poly_decimator (hangs
sim), prbs, queue.
