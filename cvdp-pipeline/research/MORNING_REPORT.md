# CVDP Overnight Research — Morning Report (2026-06-10)

*Three prompt-iterations, ~26 container-graded runs, two agents, every verdict from the official
reference container (`ghcr.io/hdl/sim/osvb`, digest-pinned), every workspace leak-scanned (0 leaks).
Full evidence trail: `ITERATION_LOG.md`.*

---

## 1. The night in one table

| iteration | change tested | result | the datapoint |
|---|---|---|---|
| **1b** (15 problems, codex) | Self-Verification Standard (spec-derived test plans, corner classes, hang=FAIL, distrust-your-PASS) | recovered 2 (jpeg, dyn_eq) − regressed 2 (DES, elevator) = ±0 raw; **integrity restored** (leak fixed, probe vindicated) | **Oracle-independence 10/10**: every trace-classified run's verdict was predicted by *where its expected values came from* — spec-derived 3/3 PASS; self-derived/loopback 0/4; ambiguity-blind checklists 0/3 |
| **2** (8 problems: codex 5 + claude 3 after codex credit death) | Anti-loopback + disagreement-protocol clauses | **1/8 conversions** (monte_carlo — via the *claude* arm, not the clauses) | Process compliance is inconsistent (prbs ignored / hdbn drifted its oracle toward the DUT 5× / **csr genuinely executed the protocol** — re-computed independently, changed the correct side) — **and the compliant runs still failed on untested assumptions** (csr's interrupt-bit-order guess, queue's FWFT corner, elevator's door timing) |
| **3** (3 problems, claude) | XLS-retry rule ("after 2 failed Verilog attempts, re-implement kernel in DSLX") | **1/3 conversions** (ph_0015 PASS 45/0 — via claude's Verilog, not XLS); ph_0010 ❌0/18; poly ❌0/1 | **XLS uptake 0/3 — and the reason is the night's deepest insight (§3.3): the rule's trigger is unreachable behind self-judged success** |

## 2. Every container verdict from tonight (26 runs, all leak-clean)

**Iteration 1b (codex, auto):** gcd ✅ · async_filo ✅ · jpeg ✅(rec) · rgb_0004 ✅(probe vindicated) ·
dyn_eq_0004 ✅(rec) · hdbn ❌0/732 · prbs ❌0/73 · poly ❌(hang GONE) · csr ❌0/2 · queue ❌0/1 ·
monte_carlo ❌ · ph_0010 ❌0/18 · ph_0015 ❌29/16 · DES ❌(reg) · elevator ❌0/4(reg)

**Iteration 2 (codex arm):** hdbn ❌0/524 · prbs ❌0/73 · queue ❌0/1 · csr ❌0/2 · elevator ❌0/4
**Iteration 2 (claude arm):** monte_carlo ✅1/0 (**conversion**) · poly ❌0/1 · DES ❌0/1
**Iteration 3 (claude):** ph_0015 ✅45/0 (**conversion**) · ph_0010 ❌0/18 · poly ❌0/1 (0 self-sim
fails — self-passed after a ~2h grind; **poly is now 0/4 across both agents and three oracle styles**,
the benchmark's most robust fail and the prime candidate for the independent-oracle mechanism)

**Night's conversions: 3** (monte_carlo, ph_0015 — both cross-agent; jpeg & dyn_eq in 1b under codex).

## 3. The lever hierarchy (the night's core scientific result)

1. **Layer-1 verification prompts WORK.** Corner coverage, bounded waits, hang=FAIL, iterate-on-failure:
   visible in every trace; poly's simulator-hang class is *retired*; agents verify diligently now.
2. **Oracle-process prompts hit a CEILING.** The anti-loopback/disagreement clauses produce inconsistent
   compliance (1.5/3 where conflicts arose) — and even *perfect* compliance (csr) fails on assumptions
   the agent doesn't know are assumptions (bit orders, FWFT semantics, door timing). **You cannot
   re-derive what you don't know is ambiguous.**
3. **Self-triggered escalation rules are UNREACHABLE.** ph_0010's trace: 4 self-test FAILs → agent fixes
   → self-test green → "still failing after 2 attempts" never fires → XLS fallback never taken. **The
   agent always converges its own oracle to green, so no rule conditioned on self-detected persistent
   failure can ever trigger.** This generalizes: try-XLS, verify-harder, ask-for-help — all dead letters
   if gated on self-assessed failure.

**→ The structural conclusion:** the next capability jump requires mechanisms OUTSIDE the agent's
control loop:
- **Locked pre-RTL vectors:** derive spec→expected-vectors FIRST, freeze them (tool-enforced), then
  write RTL against them. The oracle can't drift toward the DUT if it's locked before the DUT exists.
- **Independent-oracle second agent:** a separate agent derives the checker blind to the RTL;
  disagreement = surfaced ambiguity (would catch csr's bit order, queue's FWFT).
- **External attempt counters / escalation:** N-th sim-iteration triggers (mechanically counted, not
  self-judged) for XLS-retry, agent-switch, or human-flag.
- **Bit-field enumeration discipline:** every register/field in the spec gets a written-down worked
  example before RTL (attacks the ambiguity class directly).

## 4. Variance — single runs lie (matters for the showcase)

- **DES: 1 pass / 2 fails** across three runs (passed the *provided* vectors every time; the hidden
  harness probes deeper; one typo among 512 S-box entries decides it).
- **elevator: original PASS now looks like the lucky draw** (2 consecutive fails since, different
  defensible semantic guesses each run).
- **dyn_eq_0004: recovered but historically flaky.**
→ Intricate problems carry **±1–2 verdict noise per run**. The full-92 showcase should run flaky/
intricate problems **2×** (report best-of or majority, stated openly) or quote an error bar.

## 5. claude vs codex (cross-agent arm, n=6)

- **Reliability:** claude's old hang is FIXED by the stream-json runner change (verbose live traces).
- **Speed:** claude ~2–3× slower/problem; iterates more (9 attempts on poly).
- **Capability:** claude found 3 latent bugs in *provided* context RTL that codex missed twice
  (non-primitive LFSR polynomial, CDC sync-stage mismatch, counter spec-violation) → converted
  monte_carlo; also converted ph_0015 in plain Verilog.
- **2 of the night's 3 conversions came from agent diversity, not prompt changes.** A
  **retry-failed-problems-with-a-different-agent** ensemble is empirically the cheapest pass-rate lever
  observed tonight.
- **Codex credits died twice mid-batch** (~5-10 runs/refill) — plan capacity for the 92-run showcase.

## 6. Updated full-92 prediction

Current trustworthy subset rate: **8/15 distinct problems passing under best-known conditions**
(gcd, async_filo, jpeg, rgb, dyn_eq, monte_carlo, ph_0015 + DES-at-best). The hard core (hdbn, prbs,
ph_0010, poly, csr, queue, elevator) resists prompting and needs the structural levers.
- **Single-agent (codex, current prompt): ~60–70%** of 92 (March-passers mostly hold + recoveries,
  minus variance).
- **With agent-ensemble retry (codex→claude on fail): ~70–78%** (tonight's ensemble effect on the
  hard subset was +2/8).
- Error bar ±3-4 problems from single-run variance. Conditions: container-graded, leak-fixed pipeline,
  2× runs on flaky problems.

## 7. Prioritized next actions

1. **Build the structural oracle mechanism** (highest ceiling): locked pre-RTL vector tool or
   independent-oracle second agent. This is SiliconCrew roadmap work, not prompt work.
2. **Ship the agent-ensemble retry** (cheapest win): orchestrator re-runs container-failed problems
   with the other agent. Tonight: +2 conversions on 8 hard problems.
3. **Full-92 showcase run** after 1–2, with 2× on flaky problems and the error bar stated.
4. **Codex capacity:** stagger batches vs credit refills; claude-max as standing fallback.
5. Commit hygiene: tonight's research docs committed on `feature/cvdp-automate-refactor`; prompt rules
   6–8 live in main repo `feature/xls-flow` (uncommitted — decide after the structural-lever pivot,
   since rule 8 is now known-ineffective as written).

*— Claude (overnight autonomous research), 2026-06-10 ~01:45*
