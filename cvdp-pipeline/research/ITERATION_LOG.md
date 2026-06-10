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
