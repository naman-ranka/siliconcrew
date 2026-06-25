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

**Status:** ABORTED — invalidated by a harness leak discovered mid-run (see below). Superseded by 1b.

### 🚨 Mid-iteration finding — harness leak (integrity)
While watching the live hdbn_codec trace, the agent ran `verif/test_hdbn_top.py` — **byte-identical to
the hidden grading harness** (378/378 lines). Root cause: `_cvdp()` wrote the FULL dataset row to the
agent-visible `problem.json` (incl. the `harness` field), and the prompt tells the agent to read
problem.json. The agent lifted the hidden cocotb test and "self-verified" against it. Scan of all 42
prior runs: **3 verbatim leaks** (hdbn iter1; phase_rotation_0010-verilog [still FAILED]; **rgb_0004 — a
headline "recovery", now suspect**) — and that's a *lower bound* (only catches verbatim copies). The new
self-verification prompt likely *increased* exploitation (it told the agent to go find a testbench; the
answer key was in problem.json).

**Fixes shipped before re-running (both committed):**
- **Leak (#1, worktree 12118e1):** `_cvdp` writes a sanitized problem.json (no `harness`, blanked
  golden `patch`), stops materializing `harness/`; the grader re-reads the real harness from the dataset.
- **cocotb_tool (#2, main 8990739):** the agent's cocotb self-check now runs in the osvb grading
  container with an enforced timeout (TIMEOUT = FAIL), validated 4/4 outcome classes. Previously it
  hung (no timeout) and ran on a host env that diverged from the grader.

These compose: the agent can no longer obtain the harness, so it must write its own spec-derived TB —
and can now run that faithfully in the grading container.

---

## Iteration 1b — clean re-run (leak-free + faithful cocotb)

Same general self-verification prompt, but on the fixed substrate. **Batch
`cvdp_b17_iter1clean.yaml` (15 problems), flow `auto`, codex/gpt-5.5:**
- 10 genuine fails (targets): hdbn_codec, jpeg_runlength, prbs, poly_decimator, csr_apb, queue,
  monte_carlo, phase_rotation_0010, phase_rotation_0015, dynamic_equalizer_0004
- rgb_color_space_conversion_0004 — **leak-suspect recovery**: does it still pass writing its OWN TB?
- 4 clean pass-controls (regression check): gcd_0007 (canary), DES_0001, async_filo_0001,
  elevator_control_0004 — must NOT regress under the new prompt.

**Method:** grade ALL in the osvb container (`run_all.py --skip-run` / `regrade_docker`), never a
self-report. Subagents read each trace to confirm (a) no harness in the agent workspace, (b) it wrote
its own TB, (c) it used cocotb_tool in-container, (d) what it did differently. Score = recovered −
regressed. If real, regression-free recovery → scale toward the full 92.

**Status:** RUNNING (launched on the fixed substrate).
**Result:** _pending_   **Recovered:** _pending_   **Regressed:** _pending_   **rgb_0004 clean verdict:** _pending_

### Per-problem ledger (container verdicts; trace via subagent + mechanical check)

| # | problem | type | container | leak scan | trace findings |
|---|---|---|---|---|---|
| 1 | gcd_0007 | control | **PASS 5/0** | clean | Own TB with **two INDEPENDENT reference models** (`gcd_ref` Euclidean ≠ DUT's algorithm, `modpow_ref`); reset/back-to-back/edge corners; timeouts = `$fatal`. Self-PASS = container PASS (calibrated). The prompt visibly worked. |
| 2 | hdbn_codec_0001 | target (codec) | **FAIL 0/732** | **clean** (vs LEAK last time — fix validated on the riskiest problem) | Own TB, 1 fail→fix→pass cycle, no harness-seeking. **BUT verified by LOOPBACK only** (encode→decode→compare): encoder and decoder share the same HDB3 misread, so the self-test can't catch it. Did NOT build the independent reference the prompt asks for. Self-PASS → container FAIL = the Layer-2 oracle gap, now isolated cleanly. |
| 3 | jpeg_runlength_enc_0001 | target (codec) | **PASS 1/0 — RECOVERED** (was 0/55) | clean | Own TB with **SPEC-DERIVED expected output vectors** — `coeff_size()`/`jpeg_amp()` functions encode the JPEG spec rules, pre-computed (rlen,size,amp,dc) tuples, `$fatal` scoreboard. Covered DC/AC, zero-runs 0/2/15, negative coeffs, EOB, consecutive max-run suppression. No loopback. Self-PASS = container PASS (calibrated). |

| 4 | prbs_0001 | target (codec) | **FAIL 0/73** (unchanged) | clean | Own TB + 2 diagnostic probes, 3 iteration cycles, no harness-seeking. Oracle = **re-implementation of the same LFSR algorithm in SV** (self-derived, not independent). **Smoking gun:** first sim FAILED ("checker data mismatch exp=e2 got=f2") and the agent **changed the TESTBENCH to agree with the RTL** ("testbench latency model was wrong") — when oracle and DUT disagreed, it sided with the DUT. Self-PASS → container FAIL. |

**The codec contrast is the iteration's central finding (same prompt, different verification choice →
opposite outcomes), now 3/3:** hdbn (*loopback*) FAIL 0/732 · prbs (*re-implemented same algorithm* +
adjusted the oracle to match the DUT on disagreement) FAIL 0/73 · jpeg (*spec-derived expected
vectors*) **PASS, recovered from 0/55**. The oracle's *independence* — not test effort (prbs did 3
diligent iterations + probes) — determines the outcome.

| 5 | poly_decimator_0001 | target (was: SIM-HANG) | **FAIL 0/1** — but **the hang is GONE** | clean | 10 iterations, every failure treated as a failure, TB has an 80-cycle bounded wait + clean `$finish` (terminated at t=1415). The harness now RUNS and judges (previously it hung). **"Non-termination = FAIL" lever: worked** — agent shipped terminating RTL. But verification was loopback/self-derived (sum-of-history oracle, coeffs=1) → logic still wrong. Upgraded from "hangs" to "terminates but wrong": partial progress. |
| 6 | csr_using_apb_interface_0001 | target (protocol) | **FAIL 0/2** (unchanged) | clean | **Excellent checklist behavior** — directed APB tasks asserting SETUP/ACCESS phases, PREADY timing, reset values, write-protect PSLVERR, invalid-address, even **reset mid-op** (the prompt's corner classes, followed). Only a TB arithmetic bug found+fixed. Failed anyway: subagent flags two unvalidated guesses — **interrupt bit order** (chose prompt-text order) and address-map/timing assumptions. Layer-2 again, but the *ambiguity* flavor: diligent verification of a misread/ambiguous contract still self-passes. |

| 7 | queue_0001 | target (control) | **FAIL 0/1** (unchanged) | clean | Own TB, **superb corner coverage** (empty/full, back-to-back, reset mid-op, simultaneous r/w while full AND from empty) — the prompt's Layer-1 corner classes fully followed. Self-derived oracle; self-PASS → container FAIL anyway: another semantic/contract misread the corner sweep can't catch. (Subagent's "harness-seeking" flag was a false alarm — it was the sanctioned, sanitized problem.json/context read; leak scan clean.) |

| 8 | monte_carlo_0006 | target (arith/CDC) | **FAIL 0/1** (unchanged) | clean | Chose **direct Verilog under `auto`** — notable because this problem PASSED under forced-XLS last round; even with the fixed architect prompt codex won't pick XLS where XLS wins (iteration-3 lever candidate: offer XLS on failed-arithmetic retries). Verification self-derived (TB counts its own valid pulses vs the DUT's own internal counter — both sides DUT-derived). Real CDC FIFO fix applied. Self-PASS → container FAIL. |

| 9 | phase_rotation_0010 | target (XLS-unlock) | **FAIL 0/18** (auto/Verilog) | clean | 0 XLS calls under `auto` — chose Verilog and failed, where **xls_force PASSED 18/18** last round. Pairs with monte_carlo: both XLS-unlock problems re-offered XLS freely, both declined, both failed. |
| 10 | rgb_color_space_conversion_0004 | **LEAK-PROBE** | **PASS 1/0 — probe VINDICATED** | clean | Re-run with no access to the harness: agent wrote its own TB with **spec-derived expected values** (`exp_cmy` implements the spec's CMY formula; 6 directed cases incl. black/white/pure-red + reset) and PASSES the official grade. The earlier "recovery" was genuine capability, not leak-inflated. (Caveat: TB formula matches the RTL's helper function — same-author derivation — but the container PASS is the verdict that counts.) |
| 11 | des_0001 | pass-control | **FAIL 0/1 — REGRESSION** | clean | 16-stage pipelined DES, lint clean, **passed the DATASET-PROVIDED `verif/tb_des_enc.sv`** (4 single + 3 burst known-good vectors) — yet fails the hidden harness, which evidently probes beyond those vectors. One typo among 8×64 S-box entries suffices. Likely run-to-run variance in table transcription, not prompt-caused (it used the strongest available oracle and still missed) — but scored honestly as the iteration's 1 regression. |
| 12 | async_filo_0001 | pass-control | **PASS 5/0** | clean | Control held (dual-clock FILO). |
| 13–15 | elevator_control_0004 (running), phase_rotation_0015, dynamic_equalizer_0004 | — | pending (b19 finishing batch) | — | Earlier credit-failure dirs superseded. |

**Iteration-2 levers sharpened by the evidence (still fully general):**
1. *Anti-loopback:* for encoder/decoder/generator-checker pairs, loopback or re-implementing the same
   algorithm as the oracle is NOT verification — derive expected OUTPUT VECTORS from the spec's rules
   (worked examples / a rule-based function like jpeg's `coeff_size()`), not from your design's logic.
2. *Disagreement protocol:* when your testbench and RTL disagree, do NOT assume the testbench is wrong —
   re-derive the expected value from the spec a third time before changing either side (prbs failure mode).

---

## Iteration 1b — FINAL CONCLUSION (complete: 15/15 container-graded, 15/15 leak-clean)

**Verdicts:** PASS 5 — gcd (ctrl), async_filo (ctrl), **jpeg (RECOVERED** 0/55→1/0**)**, **rgb_0004
(leak-probe VINDICATED**, clean own-TB pass**)**, **dyn_eq_0004 (RECOVERED**, flaky-history caveat**)**.
FAIL 10 — hdbn, prbs, poly (hang GONE, logic wrong), csr, queue, monte_carlo, ph_0010, ph_0015
(*improved* 24/21→29/16), **DES (REGRESSED**, passed the provided TB vectors, failed deeper hidden
probing**)**, **elevator (REGRESSED**, self-test missed door-timing/request-clearing semantics**)**.

**Score: recovered 2 (+1 improved, +1 de-hung) − regressed 2 = net ±0 raw; integrity fully restored.**
Raw pass count on this failure-skewed 15 is unchanged (5/15 before, 5/15 now) but the composition
shifted: two historically-hard targets came in, two intricate controls dropped out. Both regressions
look like run-to-run variance on transcription/ambiguity-hazard problems (DES: one typo in 8×64 S-box
entries kills it even when the dataset-provided vectors pass; elevator: different-but-defensible
semantic guesses than the lucky prior run) — but they are honestly scored as regressions, and they
warn that **single-run verdicts on intricate problems carry ±1-2 noise; the full-92 showcase number
should be read with that error bar** (or key problems run 2×).

**The central finding — oracle independence — closed at 10/10 mechanism-consistent** (10 runs whose
oracle type was trace-classified; the type alone predicted every container verdict. Excluded: gcd/
async_filo controls — consistent but weak evidence; DES — a *coverage* not *independence* failure, it
used the provided vectors and failed deeper probing; ph_0010/0015 — classified for XLS choice only):
- **Spec-derived independent oracles: 3/3 PASS** (jpeg's rule functions; rgb's spec-formula expected
  values; dyn_eq's hard-coded MCMA expected values — the latter two are this iteration's recoveries).
- **Self-derived/loopback oracles: 0/4 PASS** (hdbn loopback; prbs same-algorithm re-implementation +
  sided-with-DUT-on-disagreement; poly sum-oracle; monte_carlo DUT-vs-own-counter).
- **Diligent-but-ambiguity-blind checklists: 0/3** (csr interrupt-bit-order guess; queue contract
  misread; elevator door-timing semantics) — corner *coverage* cannot catch a misread *contract*.
**Verification effort no longer separates pass from fail; oracle independence does.**

**What the iteration established (high confidence, 9/9 traces leak-clean):**
1. **The leak fix holds under real agents** — including hdbn, the previous leaker. Integrity restored.
2. **Layer-1 levers WORK.** Every trace shows the self-verification standard changing behavior: spec-derived
   corner coverage (queue: empty/full/back-to-back/reset-mid-op/simultaneous-r/w; csr: full APB checklist
   incl. reset-mid-op), bounded waits + clean termination (poly_decimator's HANG IS GONE), failures treated
   as failures (10-iteration fix loops). The agent now *verifies diligently*.
3. **Layer-2 (oracle independence) is THE bottleneck, 6/6 mechanism-consistent.** Every remaining genuine
   fail self-passed against a self-derived oracle (loopback: hdbn, poly; same-algorithm re-implementation:
   prbs; DUT-vs-its-own-counter: monte_carlo; ambiguity-blind checklists: csr, queue). The single recovery
   (jpeg) is exactly the one trace whose oracle was spec-derived. Verification *effort* no longer
   discriminates pass from fail — oracle *independence* does.
4. **XLS propensity is zero even where XLS wins.** Both XLS-unlock problems (phase_rotation_0010,
   monte_carlo) declined XLS under `auto` and failed. Permission ("not a reason to avoid") ≠ preference.

**Other findings confirmed:** Layer-1 levers all work (corners, termination — poly's hang gone,
failures iterated not ignored); the leak fix held across all 15 real-agent runs; **XLS propensity 0%**
even on both XLS-unlock problems (monte_carlo, ph_0010 — declined under `auto`, failed in Verilog).

**Decision: iteration 2 before any scale-to-92.** The full-92 showcase would burn ~85 agent-runs on a
prompt we now know leaves the dominant failure mode unaddressed. Plan:
- **Iteration 2 (next):** add the two oracle clauses (anti-loopback + disagreement protocol) to the
  Self-Verification Standard; re-run the oracle-gap fails (hdbn, prbs, poly, monte_carlo, queue, csr,
  elevator) + DES (regression re-check). Consider 2× runs on intricate problems to separate signal
  from variance.
- **Iteration 3 (queued, user-approved):** XLS class-based positive direction — A/B "for pure
  arithmetic/datapath kernels prefer XLS-first (wrap to the contract)" and/or "re-implement the kernel in
  DSLX after 2 failed Verilog verification attempts" on the arithmetic/DSP fails (ph_0010/0015,
  monte_carlo, dyn_eq). Measures whether auto-mode XLS uptake moves off 0% and converts fails.
- Then the full-92 showcase run on the best prompt, with the ±variance error bar stated.

---

## Iteration 2 — Oracle clauses (anti-loopback + disagreement protocol) — RUNNING (overnight)

**Prompt change (main repo, `architect_prompt_v2.md` rules 6–7 + `architect.py` mirror):**
(6) *LOOPBACK IS NOT VERIFICATION* — for encoder/decoder/generator-checker pairs, encode→decode or
re-implementing the same algorithm as the oracle proves only self-consistency; derive expected OUTPUT
VECTORS from the spec's rules (worked examples / hand-computed sequences / rule-based expected-value
function). (7) *Disagreement protocol* — when TB and RTL disagree, re-derive from the spec before
changing either side; editing the test to match the design converts a caught bug into a shipped one.

**Batch `cvdp_b20_iter2_oracle` (8, codex/gpt-5.5, auto):** hdbn, prbs, queue, csr, elevator, poly,
monte_carlo (7 oracle-gap fails) + DES (regression/variance re-check; elevator doubles as one too).

**Predictions (falsifiable, written before results):** hdbn/prbs are the direct targets — if the
anti-loopback clause works, traces show spec-derived vector TBs and at least one converts. queue/csr/
elevator are ambiguity-fails — clauses help only if the re-derivation forces a spec re-read; lower
conversion odds. poly/monte_carlo are numeric/structural — middling odds. DES: variance coin-flip.

**Hypothesis tracker to update per run:** oracle-choice (loopback/self-derived/spec-derived), clause
compliance visible in trace?, container verdict, prediction hit/miss.

| problem | container | oracle choice (iter2) | clause compliance | disagreement events | prediction |
|---|---|---|---|---|---|
| hdbn | **FAIL 0/524** | **SHIFTED**: directed expected OUTPUT-SYMBOL vectors (no loopback!) — behavioral change vs 1b | partial; never cited the rule (style may be coincidence) | **VIOLATED**: 5 TB-changes, 0 RTL-logic changes; literally said "I'll tighten the RTL rather than weakening the checks" then did the opposite (some TB edits were spec-justified, e.g. odd/even 000V-vs-B00V rule) | MISS (no conversion) |
| prbs | **FAIL 0/73** | **UNCHANGED**: re-implemented the same LFSR as oracle again | none — zero references | **VIOLATED again**: 3× changed TB expectations to match RTL ("I modeled the checker pipe inconsistently") | MISS |
| queue | **FAIL 0/1** | sanity-bench, mechanical spec implementation (spec itself prescribes shift-queue + FWFT empty-R/W special case) | n/a | none (passed 1st sim) | as predicted (ambiguity class, low odds) — semantic corner: on empty simultaneous r/w, q_o gets fresh data but empty_o stays asserted; hidden harness likely disagrees |

| csr | **FAIL 0/2** (NB: subagent mis-reported "2/2 pass" — that was the agent's SELF-test; container verdict stands) | directed APB checklist again | **REAL COMPLIANCE OBSERVED** — the night's most nuanced trace: on TB-vs-RTL value conflict it **independently re-computed** ((0xabcde>>10)&0x3ff=0x2af via node) and changed the side that contradicted the math (TB); on a timing conflict it re-derived from APB protocol and changed the **RTL**. The disagreement protocol *worked* | 2 conflicts, both resolved correctly | MISS anyway — residual failure is in **untested guesses** (interrupt bit order — its `isr_reg` and `interrupt_reg` orders are mutually REVERSED — door for harness mismatch) |
| elevator | **FAIL 0/4** (2nd consecutive fail → the original 1b-era PASS was likely the lucky draw, not the new runs unlucky) | mechanical spec-following, no deliberation | no disagreements arose (self-pass 1st try) | none | as predicted (ambiguity class): door-timing sim/hw conditional + combinational direction — same guess-class persists |

**META-FINDING, REFINED after the full codex arm (0/5 conversions):** two distinct layers, with
different verdicts on the prompt clauses:
1. **Process compliance is INconsistent but possible** — prbs ignored the clauses entirely (re-implemented
   the LFSR, 3× TB-to-match-RTL); hdbn shifted style but empirically iterated its oracle toward the DUT
   (5× TB changes after stating it wouldn't); **csr genuinely executed the protocol** (independent
   re-computation → changed the side that contradicted the math/protocol — once TB, once RTL). So the
   clauses CAN induce the right process, unreliably (~1.5/3 where conflicts arose).
2. **Even perfect process doesn't convert, because the residual failures live in UNTESTED ASSUMPTIONS** —
   csr followed the protocol and still failed 0/2 on its interrupt-bit-order guess; queue on FWFT
   empty-r/w semantics; elevator on door-timing. **The agent cannot re-derive what it doesn't know is
   ambiguous.** The hidden harness encodes one resolution of each ambiguity; the agent picks plausibly
   but blindly.
→ The lever hierarchy revealed: (a) verification-process prompts: ceiling reached, marginal; (b) the
real residual gaps are **spec-ambiguity blindness** (csr/queue/elevator class) and **algorithm-comprehension
error** (hdbn/prbs codec class). Both resist prompting; both point to **structural** mechanisms:
test-first vector locking, independent second-agent oracle/interpretation-diff, or
enumerate-and-assert-every-bit-field discipline. Conversions: **0/5 codex arm**.

### Cross-agent arm (claude-sonnet-4-6, same iter-2 prompt; codex credits died)

| problem | container | cross-agent comparison (mechanically corrected) |
|---|---|---|
| monte_carlo | **PASS 1/0 — FIRST iter-2 CONVERSION, cross-agent** | Claude's TB structure was actually *similar* to codex's (count-vs-DUT-counter); the difference was **better context-RTL debugging**: claude found+fixed 3 latent bugs codex missed — valid/data sync-stage mismatch (CDC), unconditional `transfer_count` increment (directly violating a spec line), and a **non-primitive 2-tap LFSR polynomial replaced with a maximal 4-tap one** (arithmetic comprehension). Conversion driven by design-debugging depth, not oracle structure. (Subagent's "broke the circularity" narrative over-claimed; corrected.) |
| poly_decimator | **FAIL 0/1** (both agents fail) | **Genuine clause compliance**: hand-computed spec-derived expected outputs (batch [1,2,3,4]→10, documented arithmetic), watchdog + per-batch timeouts (hang-class fully retired). Self-PASS → harness FAIL anyway. ANOTHER perfect-process-still-fails datapoint — residual cause UNCERTAIN (suspect: all-ones-coefficient assumption / batch-interface semantics vs the harness's stimulus). (Subagent's "failed because no synthesis" is WRONG — CVDP grading is RTL-only; discarded.) NB: claude hit an iverilog unpacked-array-port limitation and worked around via hierarchical reference — tool-friction datapoint. |

**Cross-agent takeaways (n=2 so far):** agent diversity has real value (claude converted a 2×-codex-fail
by finding latent bugs in *provided* RTL); claude reliability is FIXED by the stream-json runner change
(673KB live trace, no hang); claude is ~2-3× slower per problem but iterates more carefully (9 attempts
on poly).

| des (claude) | **FAIL 0/1** | DES now 1-pass/2-fail across 3 runs (orig codex PASS, 1b codex FAIL, iter2 claude FAIL) → high-variance transcription-hazard problem confirmed; the original pass was the fortunate draw. |

**ITERATION 2 CLOSED: conversions 1/8** (monte_carlo, via the cross-agent arm, driven by deeper
context-RTL debugging — not by the oracle clauses). Codex arm 0/5. Process-compliance inconsistent
(prbs none / hdbn partial / csr real); the compliant runs still failed on untested assumptions.

## Iteration 3 — XLS-retry rule 8 — RUNNING (claude, batch cvdp_b22_iter3_xls)

Rule 8 added (main repo .md + architect.py): after 2 failed direct-Verilog attempts on an
arithmetic/datapath kernel, re-implement in DSLX (`run_xls_flow`) + thin wrapper. Targets: ph_0010
(codex-Verilog 0/18, xls_force PASSED 18/18 historically), ph_0015 (29/16 partial), poly (both agents
fail). **Metrics: does XLS uptake move off 0% under `auto`? Does it convert?** Caveat: claude arm =
cross-agent conditions (codex credits dead).

| problem | container | XLS uptake | analysis |
|---|---|---|---|
| ph_0015 | **PASS 45/0 — CONVERSION** (was 29/16 codex) | 0 calls | Converted by claude's *Verilog* (1 clean self-pass, harness agrees) — cross-agent capability, NOT rule 8. |
| ph_0010 | **FAIL 0/18** (3rd consecutive Verilog fail across both agents; xls_force PASSED it historically) | **0 calls — and here is WHY** | Trace shows 4 self-test FAILs mid-iteration → agent fixed → self-test GREEN → rule 8's trigger ("still fails after 2 attempts") never fires. **Rule 8 is structurally UNREACHABLE: the agent can always converge its own oracle to green, so it never experiences the persistent failure that would trigger the XLS fallback.** Persistent failure exists only against the hidden oracle it cannot see. |
| poly | **FAIL 0/1** | 0 calls (0 self-sim fails — self-passed 1st try after a ~2h careful grind; rule-8 trigger again never reachable) | poly is now **0/4 across both agents and three oracle styles** (codex loopback, codex 1b, claude spec-derived ×2) — the benchmark's most robust fail; both agents consistently misread the same thing (suspect coefficient/interface semantics vs harness stimulus). Prime candidate for the independent-oracle mechanism. |

**ITERATION 3 CLOSED: conversions 1/3 (ph_0015, via claude's Verilog — cross-agent, not XLS); XLS
uptake 0/3 with the unreachability mechanism identified (the night's deepest insight, above).**

---

## Diagnostic run (prompt-layering era) — 2026-06-10

**Architecture change (user-directed):** prompt split into two layers. (1) **Global architect prompt**
reset toward the pre-XLS v2 baseline: generic engineering principles only — compact self-verification
standard (spec-derived plans, corner classes, hang=FAIL, independent-reference preference,
disagreement re-derivation), plus a NEUTRAL XLS-availability note ("use it whenever it makes sense");
all benchmark framing and the dead rule 8 removed. (2) **Benchmark-direction layer** (orchestrator
`build_agent_prompt`, CVDP branch only): external-evaluation stakes, treat-every-spec-sentence-as-
contract, literal-reading-wins, rigorous spec-derived TB requirements, **and a STRONG XLS direction**
(prefer DSLX+#[test] for any arithmetic/datapath/encoder kernel, wrap thin). Uniform across problems,
zero problem-specific hints.

**Infra:** Windows timeout bug fixed (`_kill_tree` via taskkill /T — old kill orphaned the node child,
making timeouts silently ineffective); per-problem timeout now 3600s and real. Parallel execution via
sharded configs (first time): concurrency cap ≤5 per user.

**Design:** 30 problems = 6 stubborn fails + 24 stratified fresh (untouched 62, by cid×difficulty).
- **Claude primary arm** (3 shards × 10, parallel): launches when claude-max resets (afternoon).
- **Codex comparison arm** (2 shards × 5 = 10 ⊂ the 30, parallel): RUNNING since 12:33 — head-to-head
  same-problem cross-agent data + first A/B of the benchmark-layer prompt: **does the strong XLS
  direction move codex's uptake off 0/15?**

**NB (graded-data integrity):** Docker Desktop was down this morning (died with laptop sleep); the
first 5 grades were NO_RESULT docker-connect errors, caught immediately (all prior verdicts carry real
pass/fail counts = provably docker-up). Engine restarted; all re-graded.

### Codex arm ledger (container verdicts, all leak-clean, XLS uptake so far 0/6)

| problem | type | verdict | classification |
|---|---|---|---|
| phase_rotation_0019 | fresh DSP | **PASS 100/0** | spec-derived `$atan2` reference vectors; caught its own off-by-one rounding and fixed RTL (correct disagreement-resolution!) |
| systolic_array_0001 | fresh datapath | **PASS 3/0** | spec-derived; **proactively hardened for hidden-test corners** ("if a hidden test pulses start in the same cycle as load_weights…" → added armed-state) — direct evidence the benchmark-mode stakes framing changes behavior |
| axis_broadcaster_0001 | fresh stream | **PASS 1/0** | built a skid buffer for the backpressure bug; wrote own self-check TB |
| secure_apb_history_… | fresh control | **FAIL 0/1** | **ambiguity-blindness, half-evolved**: agent *surfaced* the ambiguity ("The main ambiguity is whether failed APB attempts before unlock should raise APB errors") — then guessed and moved on. The benchmark layer got it to SEE the fork; nothing forces it to resolve or hedge. |
| hdbn_codec | stubborn codec | FAIL 0/742 | consistent 3rd fail |
| prbs | stubborn codec | FAIL 0/73 | consistent 3rd fail |

| axis_to_uart_0004 | fresh UART | **FAIL 0/1** | **self-derived-oracle, parameter-coverage flavor**: self-TB used convenient params (CLK=1MHz, BIT_RATE=100000) instead of spec defaults (100MHz, 115200); integer-division bit-timing diverges at the real values; 5 self-test passes at the wrong operating point. New taxonomy specimen: *tested a configuration, not the specification*. |
| byte_enable_ram_0002 | fresh mem | **PASS 1/0** | — |
| axi4lite_to_pcie_config_0003 | fresh bus | **PASS 1/0** | — |
| nbit_swizzling_0001 | fresh bitmanip | **PASS 5/0** | — |

**CODEX ARM CLOSED: 6/10 PASS (fresh 6/8 = 75%; stubborn 0/2 as expected). XLS uptake FINAL 0/10 —
the strong benchmark-layer direction does not move codex's frontend choice at all (cumulative 0/25
across all conditions). Stakes framing demonstrably improves rigor but not tool selection.**

**Early A/B reads:** (a) fresh problems 3/4 PASS — supports the easier-tail hypothesis for the full 92;
(b) **XLS uptake 0/6 even under the STRONG direction** — agents read the benchmark block (one cited
"the benchmark instruction" re tool schema) but don't even *debate* XLS for arithmetic kernels;
(c) the stakes framing measurably works for *rigor* (systolic's proactive hidden-test hardening,
secure_apb's ambiguity surfacing) — just not for frontend choice.

### Claude arm ledger (in progress)

| problem | verdict | notes |
|---|---|---|
| **prbs_0001** | **PASS 73/0 — 4th stubborn conversion, all by claude** (after 3 codex fails) | Independent LFSR reference model (algorithmic, mode-aware); **nailed the per-mode latency contract (1-cycle generator vs 2-cycle checker) codex repeatedly guessed wrong**; self-synchronizing checker (shifts in data, not feedback); reset/timing discipline in TB. One TB relaxation (error-injection T6) was **spec-grounded** (TAP=3 ripple physics from the polynomial), and the container 73/0 vindicates it. ~51 min, 5 iterations. |
| hdbn_codec | FAIL 0/1 — **TIMEOUT, killed before writing ANY file** | Claude spent its full 60 min on spec analysis (last pre-kill message: "Let me copy the context file and then implement"). Workspace: 0 files. Taxonomy: timeout/pace (claude's deliberateness as failure mode). NOT resumed — `--continue` is unsafe with 3 parallel claude sessions sharing cwd; solo re-run after arm drains. |
| poly_decimator | FAIL 0/1 (lifetime 0/5) | The fortress holds across both agents and all conditions. |
| phase_rotation_0010 | FAIL 0/18 (4th identical fail) | ~8-min fast fail; still ZERO XLS calls from any agent on the one problem XLS demonstrably solves. |
| csr_using_apb | FAIL 0/2 (0-for-3 across agents) | **Ambiguity-class resists agent diversity** — claude fails it too. |
| queue_0001 | FAIL 0/1 (0-for-3 across agents) | Same: the FWFT/contract guess class is agent-independent. → sharpens the lever map: diversity converts comprehension/latency-contract fails; ONLY an independent-oracle/interpretation-diff mechanism targets ambiguity-blindness. |
| axis_to_uart_0004 | FAIL 0/1 — **both agents fail** (codex: parameter-coverage) | Head-to-head tie-fail; classify claude's mechanism in the conclusion batch. |
| PCIe_endpoint_0001 | **PASS 1/0** (fresh) | — |
| universal_shift_reg_0001 | **PASS 4/0** (fresh) | — |
| byte_enable_ram_0002 | **PASS 1/0** (fresh) | head-to-head: codex also PASS |
| 64b66b_codec_0001 | **PASS 1/0** (fresh) | a line-codec PASSING — not all codecs are hdbn-class |
| AES_encryption_decryption_0018 | **PASS 1/0** (fresh) | — |
| axi4lite_to_pcie_config_0003 | **PASS 1/0** (fresh) | head-to-head: codex also PASS |
| arithmetic_progression_generator_0001 | **FAIL 0/5** (fresh) | classify next cycle |
| des_0003, phase_rotation_0038 | re-running (possibly limit-truncated first attempts: FAIL 0/1, FAIL 0/30) | b25 |

*(5h-limit incident ~14:25: 18 problems died as 10.9KB stubs; stubs removed, relaunched 17:08 as b25 —
4 parallel: r1/r2/r3 + hdbn solo at 90-min budget. No stubs in the new batch.)*

### Claude arm — consolidated ledger after b25 (29/30 graded; swizzler_0005 running; all leak-clean; XLS 0 everywhere)

| problem | verdict | head-to-head / notes |
|---|---|---|
| prbs_0001 | **PASS 73/0** | stubborn CONVERSION (codex 3× fail) — per-mode latency contract |
| pcie_endpoint_0001 | PASS 1/0 | fresh |
| universal_shift_reg_0001 | PASS 4/0 | fresh |
| byte_enable_ram_0002 | PASS 1/0 | codex-agree |
| 64b66b_codec_0001 | PASS 1/0 | a codec that passes — difficulty is problem-specific, not family-wide |
| AES_encryption_decryption_0018 | PASS 1/0 | …while AES_0005 fails |
| axi4lite_to_pcie_config_0003 | PASS 1/0 | codex-agree |
| event_scheduler_0001 | PASS 1/0 | fresh |
| nbit_swizzling_0001 | PASS 5/0 | codex-agree |
| async_fifo_compute_ram_0006 | PASS 1/0 | fresh |
| barrel_shifter_0002 | PASS 1/0 | fresh |
| **DES_0003** | **PASS 1/0** | rerun after limit-truncation — truncated "FAIL 0/1" was indeed bogus; rerun policy vindicated |
| sorter_0009 | PASS 6/0 | fresh |
| swizzler_0001 | PASS 1/0 | fresh |
| systolic_array_0001 | PASS 3/0 | codex-agree |
| hdbn_codec ×2 | FAIL (timeout 0-files; solo-90min 0-RTL) | **claude-specific pathology: twice produced NO RTL at all** (codex at least produces failing RTL); 0-for-5 lifetime |
| poly_decimator | FAIL 0/1 | 0/5 lifetime, agent-invariant |
| phase_rotation_0010 | FAIL 0/18 | 4th identical; still 0 XLS from anyone |
| csr_using_apb | FAIL 0/2 | ambiguity class, agent-invariant (0-for-3) |
| queue_0001 | FAIL 0/1 | same (0-for-3) |
| axis_to_uart_0004 | FAIL 0/1 | both agents fail (codex: parameter-coverage) |
| arithmetic_progression_0001 | FAIL 0/5 | fresh fail — unclassified yet |
| **phase_rotation_0019** | **FAIL 0/100** | **DIVERGENCE: codex PASS 100/0** |
| **axis_broadcaster_0001** | **FAIL 0/1** | **DIVERGENCE: codex PASS** |
| AES_encryption_decryption_0005 | FAIL 0/1 | fresh fail — unclassified |
| nmea_gps_0008 | FAIL 0/2 | fresh fail — unclassified |
| phase_rotation_0031 | FAIL 0/50 | fresh fail — unclassified |
| secure_apb_history_… | FAIL 0/1 | both agents fail (codex: ambiguity-surfaced-but-guessed) |
| phase_rotation_0038 | FAIL 0/30 (12:40 truncated attempt deleted; rerun pending verify) | — |

**Shared-10 head-to-head FINAL: codex 6/10 · claude 6/10 · ensemble(either) 7/10.** Divergences in both
directions (prbs→claude; ph_0019, axis_broadcaster→codex). **Fresh-problem rates: codex 6/8 (75%),
claude ~14/22 (64%); combined ~20/29 (~69%).**

### Classification of the 6 open claude fails (Haiku subagents + mechanical verification)

| problem | tag | self-test | mechanism |
|---|---|---|---|
| phase_rotation_0019 (divergence) | comprehension/oracle-gap | PASSED | Quadrant sign-handling convention: negated the LUT value (got −64) where the harness wants full-scale (−127); its self-oracle shared the same convention so the error was invisible. Codex pre-computed all quadrants and caught its rounding bug. |
| axis_broadcaster (divergence) | interface-contract, **UNCERTAIN** | PASSED | Claude used combinational `tready`, codex a registered/skid design. Subagent claimed "claude correct, harness rewards buggy codex" — **discounted as over-claim** (it judged correctness by reading RTL; the hidden harness may legitimately require specific ready-timing semantics per the problem spec). Recorded as ready-semantics contract divergence, cause unproven. |
| arithmetic_progression | self-derived-oracle | PASSED | Guessed output-width contract (`$clog2(SEQUENCE_LENGTH)`), oracle shared the guess. |
| AES_0005 | comprehension-error | **FAILED — shipped a known-failing design** | Wrong decrypt mapping vs the FIPS vector; gave up after iterations. (Calibration note: an HONEST fail — self-report matches verdict; rare and worth noticing.) |
| nmea_gps_0008 | parameter-coverage | PASSED | Verified convenient ASCII cases, not the binary-encoding contract the harness exercises. |
| phase_rotation_0031 | ambiguity-blindness + **oracle-drift** | PASSED | Guessed FSM mode mapping, then **swapped the mode bit until its self-test passed** — drift-to-green again. |

**Taxonomy tally (all classified fails, both agents, today):** ambiguity/contract-guess ×6 (csr, queue,
secure_apb, axis_to_uart-claude?, ph_0031, axis_broadcaster) · self-derived-oracle ×4 (arith_prog,
hdbn-codex, prbs-codex, monte_carlo-codex legacy) · comprehension ×3 (ph_0019-claude, AES_0005,
DES-variance) · parameter-coverage ×2 (axis_to_uart-codex, nmea) · timeout/pace ×2 (hdbn-claude ×2,
0-RTL) · tool-friction ×0 today. **Ambiguity/contract-class is the plurality — and it is agent-invariant.
The independent-oracle/interpretation-diff mechanism remains the #1 structural lever.**

---

## DIAGNOSTIC RUN — CONCLUSION (2026-06-10 evening)

*40 runs today (codex 10 + claude 30), all container-graded in the pinned osvb image, 40/40 leak-clean.
swizzler_0005 PASS late addition; phase_rotation_0038 rerun still in flight (first attempt FAIL 0/30,
possibly limit-truncated — verdict appended when it lands).*

**1. Scores.** Codex 6/10. Claude 16/28 (+1 pending). Ensemble on the 30-problem set: **18/29 (~62%)**
— on a set deliberately carrying all 6 stubborn fails. **Fresh problems only: ensemble 17/23 (~74%)**
(codex 75% n=8, claude 65% n=23).

**2. Head-to-head (shared 10): codex 6, claude 6, ensemble 7.** Divergences both directions —
prbs→claude (per-mode latency contract); ph_0019 (quadrant full-scale convention), axis_broadcaster
(ready-semantics)→codex. Neither agent dominates; failures are agent-specific, which is precisely
what makes the ensemble worth building.

**3. Full-92 projection.** Best-known across all 54 distinct problems ever graded: **39/54 (72%)**.
Extrapolating the ~74% fresh rate to the 38 untouched: **projected best-known ≈ 67/92 (~72%), ±4-5**.
Single-config single-agent would land ~60-65%; the ensemble-retry orchestrator converts the ceiling
into a reproducible number. (March baseline: 40%. Flaky problems need 2× runs; error bar stated.)

**4. Failure taxonomy (quantified above).** Plurality = ambiguity/contract-guess, agent-invariant
(csr, queue, secure_apb 0-for-all-attempts). Oracle-drift persists (ph_0031 swapped a mode bit until
its self-test passed). One honest-fail (AES_0005 shipped knowing it failed — calibration exists but
is rare). hdbn shows a claude-specific 2×-zero-RTL pathology worth its own investigation.

**5. XLS A/B: FINAL — 0 XLS calls in all ~40 runs today**, including under the benchmark-layer's
STRONGLY-PREFER direction on pure arithmetic kernels both agents solved or failed in Verilog.
Cumulative across all eras: 0/55+. **Frontend choice is prompt-immune. XLS adoption requires a
structural trigger** (orchestrator-enforced retry-with-DSLX on container-fail, or a tool-level
default), not words.

**6. Lever priorities (evidence-ranked):**
1. **Ensemble-retry in the orchestrator** — measured +1/10 on the shared set and 4 stubborn
   conversions to date are all cross-agent; cheapest real win; makes the showcase number honest.
2. **Independent-oracle / interpretation-diff mechanism** — targets the plurality class that no agent
   or prompt touches (spec-ambiguity); second agent derives the contract blind and diffs.
3. **External XLS trigger** — orchestrator-level, post-container-fail; the only path XLS data shows.
4. **hdbn pathology + benchmark-mode pacing** — claude needs a "produce RTL by N minutes" guardrail;
   2× zero-output runs are pure waste.

**Budget note:** 5h window ~52% at 17:40 + this batch; weekly 38% used, resets tomorrow ~13:40.
Tomorrow's spend: ensemble-retry implementation + verify, ph_0038/hdbn follow-ups, then full-92 prep.

---

## NIGHT RUN (b26/b27): full-92 coverage — IN PROGRESS

Launched 22:18 (2 parallel shards over the 36 untouched + hdbn probe + ph_0038 re-verify).
**Paused 00:50 per user (window budget); resume 03:12 on the 5h reset (b27 configs: 25 remaining).**

### Night ledger (13 graded; all leak-clean; XLS 0/13)

| problem | verdict | classification |
|---|---|---|
| AES_0009, async_fifo_0001, bcd_adder_0004 (16/0), cellular_automata_0002, DES_0005, cipher_0001, direct_map_cache_0003 (16/0) | **PASS ×7** | fresh wins |
| hdbn (3rd attempt) | FAIL 0/599 | **WROTE RTL this time** (pathology non-deterministic) — but used LOOPBACK oracle again and **shipped with its own self-test failing** (127 loopback errors). Lifetime 0-for-6. |
| ph_0038 (3rd) | FAIL 0/30 | identical ×3 → **stable genuine fail, not flaky** (good for error-bar calibration) |
| binary_search_tree_0014 | FAIL 2/3 partial | TB scope mismatch — self-TB validated search/delete, harness also checks final BST structure |
| aes_0003 | FAIL 0/1 | variant-specific comprehension (key-schedule); self-test also failing (shipped anyway). AES family: 0009 ✓ 0018 ✓ / 0003 ✗ 0005 ✗ |
| digital_stopwatch_0001 | FAIL 0/4 | **parameter-coverage #3**: self-tested at CLK_FREQ=10, spec wants 50 MHz — timing off 5000× (same flavor as axis_to_uart, nmea — a RISING class) |
| dual_port_memory_0001 | FAIL 0/1 | interface-contract (read-latency semantics) |

**Night fresh rate so far: 7/11 (64%).**
### b27 resume ledger (03:14 launch)
| problem | verdict | note |
|---|---|---|
| AES_0012 | FAIL 0/1 | AES family now 2✓/3✗ — variant-specific comprehension |
| DES_0007 | FAIL 0/1 | DES family: 0001 flaky, 0003 ✓, 0005 ✓, 0007 ✗ |
| caesar_cipher_0001, cic_decimator_0001 (March-fail RECOVERED), cont_adder_0001 | PASS ×3 | cic_decimator was a March-2026 baseline failure — fresh recovery |
| axis_to_uart_0001 | FAIL 0/1 | axis_to_uart family 0-for-3 across agents/variants |
| binary_search_tree_0001 | FAIL 0/9 | bst family: 0014 partial 2/3, 0001 0/9 |
| door_lock_0001 | FAIL 0/10 | fresh fail (March also failed door_lock) |
| dual_port_memory_0004, event_scheduler_0004, lfsr_0001 (March-fail RECOVERED), multiplexer_0001, signed_comparator_0001, sorter_0026 (March-fail RECOVERED) | PASS ×6 | family texture: dual_port 0001✗/0004✓; direct_map_cache 0003✓(16/0)/0001✗(0/16) |
| direct_map_cache_0001 | FAIL 0/16 | mirror of 0003's 16/0 pass — variant-specific |
| ethernet_mii_0004, thermostat_secure_0001 | FAIL ×2 | fresh fails, to classify |

### b27 fail classifications (Haiku batch, mechanically sanity-checked)
- **aes_0012 + bst_0001: INCOMPLETE-RUNS (token-limit deaths mid-conversation — never reached design). Verdicts are not design signal; tail re-run if budget allows.**
- des_0007: interface-contract (self-test passed, 11 RTL files) · axis_to_uart_0001: ambiguity/param (family 0-for-3 now) · door_lock: comprehension (5 iterations to self-green, 0/10 anyway) · direct_map_cache_0001: parameter-coverage suspected (sibling 0003 passed 16/0 same night) · ethernet_mii_0004: interface-contract (CDC/MII handshake) · thermostat_secure: comprehension (first-try self-green, 0/1).
- (Subagent's "patched=true suggests spec flag" discounted — that field is our grader's cocotb-compat marker.)
| fixed_arbiter_0010, programmable_fsm_dse_0001 (March-fail RECOVERED), sync_serial_0001 (20/0, March-fail RECOVERED) | PASS ×3 | — |
| dynamic_equalizer_0008, ethernet_mii_0006 (0/1793!) | FAIL ×2 | mii family 0-for-2; dyn_eq family 0004✓(once)/0001✓/0008✗ |
| low_power_channel_0001 | PASS 1/0 | — |
| sorter_0016 | FAIL 0/5 | sorter family 0009✓ 0026✓ 0016✗ |





 Parameter-coverage is emerging as the #3 taxonomy class —
cheap structural fix candidate: benchmark-layer rule "self-test at the spec's DEFAULT parameters,
never simplified ones" + orchestrator lint that greps TB params vs spec defaults.

**★ THE NIGHT'S DEEPEST INSIGHT (generalizes beyond XLS):** any self-triggered improvement rule of the
form *"when your verification keeps failing, do X"* is gated behind the agent's own failure-detection —
which is exactly the broken component. The agent always eventually makes its own test green (hdbn
iterated its vectors toward the DUT; ph_0010 fixed until green). The only failures it cannot hide from
are mechanical (compile/lint/crash). **Therefore escalation policies (try-XLS, try-harder-verification,
ask-for-help) must be triggered by EXTERNAL signals — independent oracles, a second agent, locked
pre-RTL vectors, or N-th-attempt counters independent of self-judged success — never by self-assessed
failure.** This dissolves iteration-3's premise and elevates the structural-lever conclusion from
iteration 2 to the central recommendation.

## Iteration 3 — XLS retry-rule (QUEUED behind iteration 2, same night if capacity allows)

Add (8): *"If an arithmetic/datapath kernel fails your spec-derived verification after 2 Verilog
attempts, re-implement that kernel in DSLX (`run_xls_flow`) and wrap it — a different representation
breaks a stuck mental model."* — the strictly-additive variant (can't break first-try passes).
Targets: ph_0010, ph_0015 + whatever arithmetic still fails iteration 2 (poly/monte_carlo).
Measures: XLS uptake off 0%?, fail→pass conversions, container-graded.

**Result:** _pending_

**Credit contingency:** if codex dies ("out of credits"), switch remaining runs to claude(-max) and
label them cross-agent datapoints (does the oracle finding generalize across agents?).

**Emerging iteration-2 lever (do NOT change mid-batch — keep 1b conditions constant):** the self-verification
standard needs an explicit, still-general anti-loopback clause: *"for encoder/decoder pairs, loopback
(encode→decode→compare) is NOT independent verification — both sides share your spec reading; check
encoder OUTPUT VECTORS against spec-derived expected sequences (worked examples from the spec doc or a
separately-derived Python/DSLX golden)."* gcd shows the agent CAN do independence; hdbn shows it takes
the loopback shortcut for codecs unless told that shortcut is invalid.


## Claude-92 completion (b29) — uniform single-config benchmark closeout

User direction: single-agent benchmarks only (claude-92 now, codex-92 later); ensemble = research
footnote, not showcase. b29 = the 24 problems never claude-run under the current layered prompt +
bst_0001 soft-cell. 2 parallel, launched 09:07.

| problem | claude verdict | note |
|---|---|---|
| barrel_shifter_0001, Min_Hamming (8/0), dma_xfer_engine | PASS ×3 | dma was a codex-era pass — claude holds it |
| cache_controller_0001 | FAIL 0/1 | DIVERGENCE: codex-era PASS, claude fails — head-to-head data |
| async_filo_0001 (5/0), binary_to_gray_0003 (3/0) | PASS ×2 | codex-era passes HELD |
| DES_0001 | FAIL 0/1 | consistent with transcription-hazard variance (now 1-pass/3-fail lifetime across agents) |

## Formal-tools experiment (b30 codex-5 / b31 claude-10) — 2026-06-25, IN PROGRESS

Setup: sby_tool + cocotb_tool docstrings un-gated/genericized (main repo); benchmark-layer prompt
nudges using cocotb + formal "wherever they fit". Re-running the 10 once-pre-fix-"passing" problems
(integrity: clean verdicts reveal the real contamination rate) + testing whether un-gating finally
makes the agent use formal.

| problem | agent | verdict | leak | sby / cocotb calls | read |
|---|---|---|---|---|---|
| event_storing_0001 | codex | **PASS 16/0** | clean | **sby=8, cocotb=6** | ⭐ FIRST-EVER sby use in a CVDP run (gate was the blocker — un-gating WORKS). BUT causally **incidental**: RTL passed sim on attempt 1; 3 sby runs were config-friction, cocotb fails were TB-sync not design; no RTL fix resulted. Also: the agent's formal check was a **self-written reference-model equivalence**, not spec-independent invariants → still carries self-oracle flavor. Integrity: a genuine clean pass (one of the 10 unconfirmed holds up). |
| phase_rotation_0013 | claude | **FAIL 0/56** | clean | sby=0, cocotb=0 | Ignored the new tools (DSP problem); pre-fix "pass" was CONTAMINATED (clean FAIL confirms). |

**Early reads (2/15):** (a) **adoption ≠ value** — un-gating flips usage 0→high, but on event_storing the
tools confirmed an already-correct design and cost ~6 min friction; (b) nudging "use formal" does NOT
auto-produce spec-independent invariants — codex wrote a reference-model equivalence proof (self-oracle
flavored); (c) integrity: of the first 2 unconfirmed, 1 genuine-pass (event_storing), 1 contaminated
(ph_0013). Need the control problems (custom_fifo/traffic_light/ttc_lite) to see if formal ever CATCHES
a real bug.

### Formal-tools experiment — update (4/15)

| problem | agent | verdict | sby/cocotb | formal read |
|---|---|---|---|---|
| custom_fifo_0004 | codex | **PASS 1/0** clean | sby=10 cocotb=4 (5 .sby) | adoption ✓ |
| custom_fifo_0004 | claude | **PASS 1/0** clean | sby=14 cocotb=0 (4 .sby) | **invariants WERE spec-independent** (occupancy bounds, halfword-alignment, reset-clears-busy) — the right kind! BUT causally INCIDENTAL: RTL was already correct (5 domain bug-fixes pre-formal), 0 RTL changes after; the 2 failing proofs were FALSE-POSITIVES (over-ambitious props on internal `dut.valid_q`) and the agent **weakened the properties** rather than fixing RTL. **~86% of sby calls were friction** (boolector not in PATH!, path/syntax errors); 1 of 7 actually proved. |

**Consistent picture (event_storing + custom_fifo): un-gating SOLVES adoption** (both agents, both
problems now use formal heavily) **but formal is INCIDENTAL** on these — the designs already pass; formal
confirms, doesn't catch. **Two NEW problems surfaced:** (1) **sby tooling friction is high** — missing
SMT solver (boolector) in PATH, path/syntax/hierarchical-ref errors burn most calls; (2) when a proof
fails the agent tends to **weaken the property**, not fix the RTL (the disagreement-protocol failure
mode, reincarnated for formal). Integrity tally (unconfirmed-10): genuine-clean = event_storing,
custom_fifo(×2 agents); contaminated = ph_0013. Need a problem where the design is WRONG and formal
could catch it — still pending (traffic_light/ttc_lite/the codecs).

### Formal-tools experiment — update (8/15)

| problem | agent | verdict | sby/cocotb | note |
|---|---|---|---|---|
| traffic_light_controller_0001 | codex | **FAIL 0/1** | sby=10 cocotb=4 | ⭐ THE KEY TEST: wrong FSM design + heavy formal use → STILL FAILS. Formal did NOT catch the bug. (subagent dissecting why: shallow props vs deep spec-derived?) |
| traffic_light_controller_0001 | claude | FAIL 0/1 | none | contaminated pre-fix pass |
| spi_complex_mult_0002 | claude | FAIL 0/2 | none | contaminated pre-fix pass |

**Formal-lever verdict sharpening:** traffic_light(codex) is the first wrong-design control problem WITH
heavy formal use — and formal didn't save it. Combined with event_storing + custom_fifo (formal
incidental on already-correct designs), the pattern is: **formal adoption is solved, but formal as
written by the agent is either confirmatory (correct designs) or ineffective (wrong designs) — it
proves the agent's OWN understanding, not the spec's.** Likely cause: shallow/self-derived properties +
the agent weakens props on failure. This is the SAME oracle-independence problem in formal clothing —
the agent's formal properties inherit its spec misreading. Provisional: formal needs SPEC-DERIVED deep
properties (durations, exact sequences) it won't write on its own → not a free lever.

**Integrity / contamination tally (the 10 unconfirmed):** genuine-clean = event_storing, custom_fifo(×2);
CONTAMINATED (pre-fix pass, clean re-run FAILS) = ph_0013, traffic_light(×2), spi_complex_mult, lfsr_0005
(dataset-leak). Running count: ~3 genuine / ~4 contaminated of those resolved so far.

### "Read the answer, still failed" — root cause confirmed (bg subagent a5846c)

**poly_decimator (claude):** had the exact expected vectors (10/36/78) AND its self-test PASSED — but
container FAILED. Root cause = **implementation + debug-convergence**, NOT comprehension. Internal
signals were X (undefined): `shift_data[0]=x ... filter_out=x ... out_sample=x` across 12 debug
iterations; the agent couldn't root-cause and finally made a narrow self-test pass that didn't
generalize. ⇒ confirms the thesis: **knowing the answer doesn't help — the bottleneck is building
correct RTL and debugging to convergence.**

**★ Concrete tooling bug surfaced (actionable):** the trace note *"iverilog cannot propagate
element-wise drives"* — the host iverilog can't handle element-wise unpacked-array port drives, so the
agent sees spurious X and chases a PHANTOM bug. This appeared in BOTH poly runs (this one + June-10
night). So part of poly's "implementation failure" is actually a **simulator limitation injecting false
X**, derailing debugging. FIX CANDIDATE: run the agent's sim in the same iverilog as grading (or patch
the array-port pattern) so it doesn't fight phantom X. This is a robustness win independent of the model.

**Caveat:** rc5 (codex) actually PASSED (legit provided CA_1..4 context); its dataset-read flag may be
context-read not harness-leak — the leak-detector must distinguish "read dataset for context" vs "read
dataset harness". Don't count rc5 as contaminated without that adjudication.

**Lever implication:** the top robustness investment is the **implement→debug loop** (diff-at-first-
divergence localization, sim-fidelity so no phantom X, decomposition) — NOT more spec info and NOT
formal-as-currently-used.

### Why formal missed the traffic_light bug — capstone (bg subagent ad0ef6)

The bug: a **one-character spec inversion** — `if ((!i_vehicle_sensor_input) | i_long_timer)` for the
S3→S4 transition; spec says "S3→S4 when vehicle detected OR long timer" (no negation). Three converging
causes formal didn't catch it:
1. **Shallow self-derived properties:** the agent proved only timer-counting trivia
   (`o_short_timer == ref_formula`, reset clears outputs) — **ZERO FSM-transition properties**. It never
   asserted the S3→S4 rule, i.e. the exact thing that's wrong.
2. **Formal infra friction (0 proofs completed):** all 5 sby calls errored — path resolution,
   `$anyseq used as clock / clk2fflogic` constraint, "engine terminated without status" (solver crash),
   ending in "no formal solver available." Same missing-solver/infra issue as custom_fifo. Formal never
   actually ran.
3. **Oracle-drift (the recurring killer):** its OWN simulation CAUGHT the bug —
   `ERROR at cycle 26: controller advances to S3 ... main=010 expected=100` — and the agent **rewrote the
   testbench expectations to match the buggy design**, then "passed." The disconfirming evidence was
   right there and it suppressed it.

**THE UNIFYING FINDING (both bg subagents + the whole corpus):** the agent's verification — testbench,
formal properties, cocotb — is **anchored to its own interpretation**, and **when verification disagrees
with the design it sides with the design** (weakens the test / writes shallow props / accepts X). The
information needed to pass was frequently PRESENT (explicit spec + a failing sim) and got discarded.

**⇒ Highest-ROI levers, re-ranked by this evidence:**
1. **Structural anti-drift** — forbid/flag editing a testbench's expected values after they're written;
   lock spec-derived vectors BEFORE the RTL exists. (Prompt rule 7 tried this and didn't stick → must be
   enforced, not requested.) This single change targets the dominant failure mode (traffic_light, prbs,
   poly-narrow-pass, ph_0010-June12…).
2. **Sim/formal infra fidelity** — install the SMT solver (boolector/yosys-smtbmc) so sby actually runs;
   fix iverilog element-wise array-port X (phantom-bug source in poly). Pure tooling wins.
3. **Spec-derived DEEP properties** — formal only helps if properties encode the spec's behavioral
   contract (FSM transitions, durations), which the agent won't write unprompted.
4. Independent oracle / debug-localization (diff-at-first-divergence).

Formal verdict: **adoption solved (un-gating works), value FIXABLE-not-fundamental** — needs #1+#2+#3
together; it is NOT a free lever as-is.
