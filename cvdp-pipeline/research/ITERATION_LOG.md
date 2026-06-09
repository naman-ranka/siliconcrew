# SiliconCrew × CVDP — prompt-improvement iteration log

The research loop: **learn → encode a GENERAL prompt change → re-run the failed batch → grade in the
container → if fails recover without regressions, scale toward the full 92.** Progress is measured as
*recovered − regressed*, container-verified (`regrade_docker`/`run_all`), with provenance — never a
self-report. General principles only; nothing problem-specific (no leaking the hidden harness).

Baseline (container-verified, codex/gpt-5.5, 30-problem subset): **20/30 ≈ 67%**. Genuine fails being
targeted: hdbn_codec, jpeg_runlength, prbs (codecs); poly_decimator (sim hang); csr_apb, queue,
monte_carlo; phase_rotation_0010/0015, dynamic_equalizer_0004 (DSP precision).

---

## Iteration 1 — Adversarial self-verification standard (the #1 lever)

**Learning encoded (general):** the genuine fails all *self-reported PASS* against a weak/self-written
testbench, then failed the stricter hidden harness. Added a mandatory **Self-Verification Standard** to
the architect prompt (`architect_prompt_v2.md` + inline fallback in `architect.py`, main repo
`feature/xls-flow`): derive the test plan from the SPEC (every requirement/port/param + interface
contract as a checklist), always cover generic corner classes (reset-mid-op, back-to-back, empty/full,
min/max/overflow, max-latency, X-injection), **treat non-termination as a FAIL**, distrust your own PASS
(list what you did/didn't verify), and for data/arithmetic/encoder kernels check against an
**independent reference** (separate Python/DSLX golden), not values re-derived from your own RTL.

**Run:** `cvdp_b16_iter1_selfverify.yaml`, 10 genuine fails, flow `auto` (agent's natural choice),
codex/gpt-5.5. Launched 2026-06-09 ~14:19. Prompt confirmed live (MCP `_load_architect_prompt` re-reads
the file per `inject_architect_prompt` call — no server restart needed).

**Hypotheses to test in the traces (via subagents):**
- poly_decimator: does "non-termination = FAIL" make the agent detect/fix the hang?
- codecs (hdbn/jpeg/prbs): does the "independent reference" instruction get it to build a separate
  golden and catch the bit-level misread? (Layer-2 oracle gap — the hardest; may NOT recover yet.)
- DSP precision (phase_rotation/dyn_eq): does corner-class + sweep coverage catch the edge it missed?

**Status:** RUNNING. Grade with `run_all.py --config cvdp_b16_iter1_selfverify.yaml --skip-run` when done.

**Result:** _pending_
**Recovered:** _pending_   **Regressed:** _pending (run a small passing-sample regression check next)_
