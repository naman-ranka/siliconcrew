# CVDP Night Run 2 — Morning Report (2026-06-11)

*Goal achieved: near-total benchmark coverage in one night. 40 claude runs across three 5-hour windows
(b26 22:18 → paused 00:50 per budget → b27 03:14 → tails 07:00), 2-parallel, every verdict from the
pinned osvb container, every workspace leak-scanned (0 leaks all night).*

## 1. THE MEASURED NUMBER

**Best-known across the benchmark: 63 PASS / 90 covered of 92 (70%)** — vs the March-2026 baseline
of 37/92 (40%). Four tail runs in flight at report time can move this to at most 67/92:
- aes_0012 + bst_0001 (token-limit incompletes re-running — their current FAILs are not design signal)
- ph_0028 + rgb_0001 (the last 2 never-graded problems — first-overnight casualties, now running)

This is a *best-known-across-configs* ceiling (two agents, several prompt eras), not one reproducible
run — the ensemble-retry orchestrator (today's build item) is what makes ~70% a legitimate single
showcase number.

## 2. Night yield (38 problems + 2 tails)

- **PASS ×22**: AES_0009, async_fifo_0001, bcd_adder (16/0), cellular_automata, DES_0005, cipher,
  direct_map_cache_0003 (16/0), caesar_cipher, **cic_decimator**, cont_adder, dual_port_0004,
  event_scheduler_0004, **lfsr_0001**, multiplexer, signed_comparator, **sorter_0026**, fixed_arbiter,
  **programmable_fsm_dse**, **sync_serial (20/0)**, low_power_channel, universal_shift_reg_0003 (4/0),
  event_scheduler_0001*  *(bolded = March-2026 baseline failures recovered tonight)*
- **FAIL ×16** (all classified): see taxonomy below.
- Night fresh-problem rate: **22/36 (61%)**; combined with yesterday's arms, the benchmark's
  never-before-touched problems landed at **~65-70%** — consistent with the projection.

## 3. The night's new finding: VARIANT-SPECIFICITY IS SYSTEMATIC

Same problem family, same agent, same night — opposite verdicts:
**AES 2✓/2✗** (0009, 0018 ✓ / 0003, 0005 ✗) · **DES 2✓/1✗** · **sorter 2✓/1✗** · **dual_port 1✓/1✗** ·
**direct_map_cache 1✓/1✗** (0003 passed 16/0, 0001 failed 0/16!) · **bst 0✓/2✗** · **ethernet_mii 0✓/2✗**.
Difficulty lives in the *variant's specific contract*, not the design family. Implication: pass-rate
gains come from contract-extraction tooling, not domain knowledge.

## 4. Final failure taxonomy (all container-failed problems, classified by trace)

| class | count | examples | structural fix |
|---|---|---|---|
| **ambiguity / contract-guess** | ~9 | csr, queue, secure_apb, ph_0031, axis_to_uart ×2, axis_broadcaster, dual_port_0001, des_0007 | **independent-oracle / interpretation-diff agent** |
| **comprehension (incl. variant-specific)** | ~8 | hdbn (0-for-6), AES_0003/0005, door_lock, thermostat, sorter_0016, ph_0019-claude, bst_0014 | cross-paradigm reference; ensemble retry |
| **self-derived oracle** | ~5 | arith_prog, dyn_eq_0008, poly (0/5 lifetime), monte_carlo-codex, prbs-codex | locked pre-RTL vectors |
| **parameter-coverage** | 3 | digital_stopwatch (CLK=10 vs 50MHz), nmea, axis_to_uart-codex | "self-test at spec DEFAULTS" rule + TB-param lint (cheap!) |
| **interface-contract** | 3 | ethernet_mii ×2 (0/1793!), dual_port_0001 | contract-as-assertions |
| **timeout/pace/incomplete** | 4 | hdbn-claude ×2 (zero-RTL, non-deterministic), aes_0012, bst_0001 (token deaths) | pacing guardrail; window-aware launching |

## 5. Stability datapoints
- **ph_0038: FAIL 0/30 three identical times** → genuine stable fail; single-run verdicts on *most*
  problems are trustworthy. - **dyn_eq family confirms flake risk is variant-specific** (0004 passed
  once, failed before; 0008 clean fail). - **hdbn non-determinism**: zero-RTL twice, full-RTL (still
  0/599, loopback again) once — pacing, not capability, drove the zero-RTL runs.
- **XLS: 0 calls in every run, all eras, all prompts (~95+ runs). CLOSED as a prompt problem.**

## 6. Today's plan (weekly resets ~13:40)
1. **Ensemble-retry in bench-orchestrator** (codex-first, claude-retry on container-fail, both logged)
   — turns the 70% ceiling into a reproducible showcase number; measured divergences guarantee gains.
2. **Reproducible showcase full-92** with that config (2× on known-flaky variants), provenance-stamped
   `results.json` via `run_all.py`.
3. **Parameter-coverage rule** (cheap): benchmark-layer line + orchestrator TB-param lint.
4. **Independent-oracle mechanism** design doc — the biggest remaining lever (~9 ambiguity fails).

*— Claude, overnight autonomous research #2, 2026-06-11 ~07:15*
