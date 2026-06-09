# Closing SiliconCrew's self-verification gap (without seeing the hidden harness)

*The #1 cross-cutting learning from the container-verified CVDP results (`CVDP_RESULTS.md`): the genuine
failures are designs the agent **self-reported as PASS** — it verified against a weak/self-written
testbench, then failed the stricter hidden official harness. This doc is the plan to fix that.*

## Can the agent close this gap without the hidden harness? Mostly YES.

The hidden harness tests the **spec** (`specification.md` + `prompt_contract`), which the agent already
has. So a wrong design that "passed its own test" failed from **shallow self-verification**, not missing
information. A rigorous, spec-driven self-check would catch most of what the hidden harness catches —
**no need to leak the test.** But the gap has two layers needing different fixes.

### Layer 1 — Coverage gap (didn't test enough). FIXABLE.
Happy-path testbench, declared victory: no edge cases, parameter sweeps, back-to-back, empty/full,
overflow, reset-mid-op.

### Layer 2 — Oracle gap (its notion of "correct" is wrong). THE HARD HALF.
If it misread the spec, **its RTL and its self-testbench share the same misunderstanding** → it
self-passes a wrong design no matter how much it tests. More testing *by the same agent* can't catch it.
This kills the codecs (hdbn/jpeg/prbs failing 400+ vectors): a subtle HDB3/JPEG-RLE misread baked into
both the design and any reference it writes.

## Three levers, mapped to the layers

| Lever | Fixes | Notes |
|---|---|---|
| **1. Prompts (non-disclosive)** | Layer 1 | Raise the standard, not leak the test: spec-derived test plan covering every requirement/signal/param combo + generic corner classes (reset mid-op, back-to-back, empty/full, min/max/overflow, max latency, X-injection); mandatory `prompt_contract` checklist; "distrust your PASS, list what you did NOT cover." Cheap, generalizes. **Does not fix Layer 2.** |
| **2. Formal — SymbiYosys (`sby_tool` already exposed)** | Layer 1 deep + partial Layer 2 | Explores ALL reachable states. **Invariants are spec-independent & interpretation-free** (FIFO count ∈ [0,DEPTH], never-pop-empty, one-hot state, handshake-stable-until-ack) → catch protocol bugs without knowing expected outputs. **Highest ROI for the control/protocol/FSM failures we saw.** |
| **3. cocotb constrained-random + reference model** | Layer 1 (data/DSP) | Wide stimulus vs a golden. **But the reference is the oracle → same-author blind spot → doesn't fix Layer 2.** |

## Structural fix for Layer 2 (the oracle gap) — independence, not more effort
A single agent can't reliably catch its own spec-misreadings.
- **Independent oracle:** a *separate* agent derives the checker/reference from the spec, **blind to the
  RTL**. Disagreement ⇒ spec ambiguity ⇒ surface it. Multi-agent cross-check breaks the shared blind spot.
- **Cross-paradigm reference:** implement the function once in a *different* representation (**DSLX/Python**)
  and use it as the golden for the Verilog. Two independent implementations rarely share the *same* bug.
  → **This is where XLS/DSLX earns its keep: not as the deliverable, but as an independent self-check oracle.**
- **Contract-as-mechanical-assertions:** `prompt_contract` fields (latency, ports, reset) → assertions with
  zero interpretation → catches interface/latency bugs directly.

## Mapped to our actual failures
- **poly_decimator (hangs):** trivial — treat "sim didn't terminate" as a **FAIL** (self-test timeout +
  liveness check). The agent currently ignores the hang.
- **queue, csr_apb (protocol/control):** **formal invariants (sby)** — biggest, cheapest win.
- **hdbn/jpeg/prbs (codecs — oracle gap):** the hard ones — need the **independent/cross-paradigm reference**.
- **phase_rotation/dyn_eq (DSP precision):** constrained-random + golden with tolerance.

## How to measure it (don't fool ourselves again)
The target isn't "pass more" — it's **calibration**: the gap between the agent's self-verdict and the
hidden harness. Today: says PASS, fails (false confidence). After each intervention, measure: does
self-PASS correlate with harness-PASS, and does the agent start flagging "unsure, edge case X may fail"?
**An agent that knows when it hasn't verified enough is the real win** — it can then iterate / ask for
help instead of shipping false confidence. (Grade with `regrade_docker.py`; compare the agent's
self-report to the container verdict per problem.)

## Priority
1. **Adversarial spec-derived self-verification prompt + "sim-hang = fail"** — cheap, do first.
2. **Formal invariants via `sby_tool`** for control/protocol — high ROI on the failures we saw.
3. **Independent / cross-paradigm oracle** for the codec class (Layer 2).

→ Then re-grade in the container and watch the self-vs-harness calibration.
