# SiliconCrew IDE — Usability Findings & Clean-IDE Proposal

*Phase 2 human-path evaluation. 8 designs (mux → adder → DFF → counter → shiftreg → seqdet → ALU → FIFO), each driven write → lint → simulate → synthesize → inspect through the live UI. Synthesized from 8 first-person critiques plus a firsthand read of `PipelineStepper.tsx`, `app/workbench/page.tsx`, and representative screenshots.*

---

## 1. Executive summary

**Yes — a human can sit down, bring RTL, and get to lint-clean + sim-PASS + a readable waveform today, by themselves, with essentially zero confusion.** Across all 8 designs the core loop worked, fast and legibly: upload two files → Lint → Simulate → Wave, all green, in **~16–23 seconds of interaction** (e.g. mux lint 4.6s / sim 6s / wave 1.3s; FIFO the same shape with a 21-signal/3-scope waveform). Every stage gave correct, clearly-labeled, *reproducible* feedback: the console shows the verbatim `iverilog`/`vvp` command + Copy, lint reports "0 warning(s)", sim surfaces the self-checking `TEST PASSED` and `$finish` line, and the waveform renders named, hierarchical signals with HEX/DEC + zoom. File **role auto-tagging** (RTL/TB) and **auto-inferred synthTop/simTop** mean zero manual config. The write→lint→sim→iterate loop is genuinely good and is **not** where the product is broken.

**Where it breaks down is everything downstream of that loop**, and that is exactly what makes the UI feel "gimmicky":

- **Synthesize never completes here, and worse, it never *says* so.** It enters an indefinite "Running on remote VM / No further output" state with a 6-step ORFS stepper frozen on step 1, then (per environment) fails ~60s later. A first-timer cannot distinguish "working" from "hung."
- **Four-to-five panels are permanently empty on the human path** — Spec, Schem, Layout, Signoff/Report — yet always visible, implying steps the engineer skipped or outputs that should exist.
- **The AI Assistant pane eats ~25–30% of every screen** and is inert, pushing the actual work (editor, console, waveform) into a narrow column.

**Environment caveat (stated once, applies throughout):** this container has **no LLM key** (so the AI architect path could not run) and **no synthesis toolchain** (`yosys`/`openroad` absent, Docker down). So Spec/Report being empty and Synthesize failing are *environment facts, not product bugs*. **But the UX of how those absences are presented is a product problem** — and that is what this report judges. The reachable ceiling here was write → lint → simulate → inspect waveform, which all 8 designs hit cleanly.

---

## 2. Verdict: are the stages gimmicky or needed?

**The pipeline concept is sound; the *presentation* is what feels gimmicky.** The staged spine (Spec → RTL → Lint → Sim → Synth → Signoff) maps correctly to the real RTL mental model, and the live status dots ("0 warn", "passed", "running") genuinely help orientation. The problem is that it shows **six homogeneous chips for a flow that only has two-to-three real actions**, mixes navigation with execution, and front-loads stages (Spec) that don't apply to a human bringing their own RTL. It needs to **degrade to only the stages that can do something** for the current design.

Element-by-element ruling, judged by whether it earned its space *consistently across all 8 designs*:

| Element | Verdict | Evidence |
|---|---|---|
| **Pipeline stepper (as status spine)** | **Earned** — but overbuilt | Doubles as run-control + status across every design; the left-to-right progression and dots are the correct mental model. Cited as "earned / the correct spine" in all 8 critiques. |
| **Pipeline stepper (View vs Run conflation)** | **Gimmicky as presented** | Spec/RTL/Signoff *navigate*; Lint/Sim/Synth *execute* — confirmed in code (`isAction` flag, hover-swaps-to-Play glyph, `PipelineStepper.tsx`). At rest all six chips look identical; "click = run" is only discoverable on hover. Flagged in 7/8 critiques. |
| **Files panel (role tags + synthTop/simTop)** | **Earned, unanimously** | The single biggest UX win: RTL/TB auto-classification and inferred tops removed all manual config for every two-file design. |
| **Console (Lint/Sim/Synth tabs, verbatim command, Copy, re-run)** | **Earned, unanimously** | The core trust-builder. Reproducible `iverilog`/`vvp` commands + PASS/FAIL transcript is exactly what a hardware engineer trusts. (The "edit & re-run command" affordance is genuinely useful but too low-contrast — noted 3×.) |
| **Artifacts: Code** | **Earned** | Always populated, clean source, one click from Wave. |
| **Artifacts: Wave** | **Earned — the headline panel** | The single highest-value surface, especially for sequential/datapath designs. Multi-scope hierarchy exposing internal `count`/`rptr`/`wptr` (FIFO) and FSM states `S0/S1/S10/S101` (seqdet) is precisely what debugging needs. |
| **Artifacts: Spec** | **Noise on the human path** | "No specification yet" + repeated `/spec` 404s in **all 8**. Only meaningful in the AI-first flow; for a human bringing RTL it is a permanent dead-end placed *first* in the pipeline, implying a missed step. |
| **Artifacts: Schem / Layout** | **Noise, unanimously** | Never populated in any lint+sim flow; never even worth screenshotting. Pure tab-bar padding. |
| **Artifacts: Report (Signoff)** | **Noise here / premature CTA** | "No report yet" + a **"Generate the report for synth_0001" button offered while synth is still running** — an inviting click that cannot succeed. Flagged in all 8. |
| **Runs timeline** | **Earned (mild)** | Lightweight re-openable history (sim_0001/synth_0001 with status + age); sets up the iterate loop even with one run. |
| **AI Assistant pane** | **Noise on the human path, unanimously** | Occupies ~25–30% width on *every* screenshot of *every* design, inert (no LLM key), with starter chips ("8-bit counter", "FIFO", "ALU", "FSM") irrelevant to someone who already uploaded RTL — one design even saw "Design a simple ALU" while an ALU was loaded. Pure clutter; narrows the real work column. |
| **Two routes (`/workbench` vs chat-first `/`)** | **Gimmicky / confusing, unanimously** | Two entry points for one product with no signposting of which is "home." The chat-first route ("Select a Session") is a dead-end for the human upload path; the only bridge is an unlabeled "Chat view" toggle. Flagged in all 8. |

**Bottom line:** Keep the stepper-as-status, the Files panel, the Console, Code, Wave, and Runs — these earned their space in every single design. Cut or defer Spec, Schem, Layout, the premature Report CTA, the inert AI pane, and the second route. The user's instinct ("all these stages and I don't know if it's required") is correct: **roughly half of what's on screen does nothing for the human RTL loop.**

---

## 3. Cross-cutting friction (ranked)

**F1 — Synthesize gives no bounded, terminal feedback (MAJOR; recurred in all 8).**
Indefinite "Running on remote VM / No further output", 6-step ORFS stepper frozen on step 1, no ETA, no heartbeat, then a silent ~60s failure to `signoff:fail`. Reads as a frozen tool, not a long job.
*Fix:* On synth start, set expectations ("synthesis runs OpenROAD remotely, ~1–2 min"). Stream a heartbeat/elapsed-vs-typical line into the console body and stderr even on failure. Add a hard timeout + up-front availability check that flips to an explicit, plain-language terminal error ("Synthesis engine unavailable — OpenROAD/Docker not reachable") with a red Signoff dot + toast and a Retry — never leave the last state as silent "running."

**F2 — The pipeline bar conflates View and Run (MAJOR; recurred in 7/8).**
Six identical-looking chips where three navigate and three execute; the distinction is hover-only (`isAction` + Play-glyph swap). A newcomer can't predict whether clicking "Simulate" runs work or just switches tabs.
*Fix:* Visually separate the two classes. Give the three action stages a **persistent** run affordance (a play badge / accent border / "Run" pill) and group them apart from the passive milestones, so "click = run" is unambiguous *before* hover.

**F3 — Permanently-empty panels imply work that doesn't exist (MAJOR cumulative; recurred in all 8).**
Spec, Schem, Layout, Signoff/Report are always visible but never populate on the human path; the "Generate report" button is shown while synth is still running. Spec is placed *first*, implying the engineer skipped a required step.
*Fix:* **Progressive disclosure.** Hide/disable artifact tabs and stages with no producible artifact in the current path: grey out Spec when there's no AI session, gate Schem/Layout/Signoff/Report behind a *successful* synth, and disable "Generate report" until the synth run reaches "passed" ("Report available after synthesis completes").

**F4 — The inert AI Assistant pane permanently consumes ~25–30% width (MAJOR cumulative; recurred in all 8).**
Always-on, inert, irrelevant starter chips; narrows editor + console + waveform for a flow that never needs it.
*Fix:* Make the assistant a **collapsible slide-over, collapsed by default** when a session originates from upload (it already has a collapse chevron). Remember the collapsed state. Reclaim the width for code + waveform + console.

**F5 — Two routes with no signposting (MODERATE; recurred in all 8).**
Chat-first `/` vs `/workbench`, bridged only by an unlabeled "Chat view" toggle; a first-timer can land on the chat list and never find the pipeline.
*Fix:* Make `/workbench` the unambiguous default landing for any session that already has RTL. Relabel the toggle to its destination ("Open Assistant" / "Open Pipeline") so the switch states its consequence. Treat chat as an optional overlay, not a separate place to start.

**F6 — Passing sim doesn't surface its primary output (MODERATE; recurred in several).**
On a green sim the user must manually find and click the Wave tab — the store has no sim→wave switch. The whole point of simulating a counter/FSM/FIFO is the waveform, yet it's a separate hunt.
*Fix:* On a passing sim, auto-select the Wave tab (or show an inline "View waveform →" button in the sim console) so write→test→sim→inspect flows without hunting.

**F7 — Monaco editor cold-start depends on an external CDN (MODERATE; seen on counter, shiftreg, FIFO).**
Fresh uploads briefly show a stuck "Loading editor..." because the jsdelivr Monaco loader fails (`ERR_CONNECTION_CLOSED`); it recovers via fallback, but the transient stuck state is alarming.
*Fix:* Bundle/self-host Monaco (or ship a lightweight fallback viewer) so file content renders instantly and never depends on a CDN; show a skeleton, not an indefinite spinner.

**F8 — Wave doesn't separate DUT ports from TB-internal signals (MINOR; ALU, FIFO).**
TB scaffolding (`ec`, `ey`, `errors`) sits inline with real DUT ports (`a,b,op,y,carry,zero`), so a first-timer can't immediately tell design from testbench.
*Fix:* Group/badge DUT ports vs testbench-internal signals (the scope tree already exists — default-collapse the TB scope, default-expand the DUT).

**F9 — Low-discoverability power features (MINOR; recurred).**
"edit & re-run command" and the auto-inferred synthTop/simTop/clk/PDK chips carry real meaning but are tiny, low-contrast, and unlabeled.
*Fix:* Promote "edit & re-run" to a visible primary affordance on the console; add a one-word label on the inferred-tops row ("auto-detected").

---

## 4. Per-design results

| # | Design | Lint | Sim | Wave | Synth | Friction headline |
|---|--------|:----:|:---:|:----:|:-----:|-------------------|
| 1 | 2:1 mux (combinational baseline) | PASS | PASS | OK | hang→fail | Wave not auto-shown after green sim; synth no ETA |
| 2 | 4-bit adder (multi-bit comb.) | PASS | PASS | OK | hang→fail | Synth unbounded "Running on remote VM"; report CTA premature |
| 3 | D flip-flop (first clocked) | PASS | PASS | OK | hang→fail | Synth streams no sub-output; Spec/Schem/Layout dead weight |
| 4 | 8-bit counter (sequential) | PASS | PASS | OK | hang→fail | View-vs-Run chips ambiguous; ~60s opaque synth wait |
| 5 | 8-bit shift register (sequential) | PASS | PASS | OK | hang→fail | Synth "structured but stuck" stepper; chat route a dead end |
| 6 | 1011 seq detector (FSM) | PASS | PASS | OK (states S0/S1/S10/S101) | hang→fail | Spec stage placed first 404s, implies a missed step |
| 7 | 4-bit ALU (datapath) | PASS | PASS | OK (15 sig, hex) | hang→fail | Wave mixes DUT ports with TB-internal signals |
| 8 | depth-4 FIFO (hardest) | PASS | PASS | OK (21 sig, 3 scopes, pointers) | hang→fail | Monaco CDN cold-start; synth silent "No further output" |

*All 8 reached the environment ceiling (lint+sim+wave) cleanly. All 8 failed synth identically — an environment limit, surfaced poorly.*

---

## 5. Proposed clean IDE

The convergent recommendation from all 8 critiques: **a three-region IDE that foregrounds code + console + waveform, with everything speculative deferred behind progressive disclosure.** The pipeline is kept as a *thin status spine that only shows reachable actions*, not a six-chip marquee.

### Layout

- **Left rail — Files.** Keep exactly as-is: file list with RTL/TB role badges and auto-inferred synthTop/simTop + clk/PDK chips (label them "auto-detected"). This is already a strength.
- **Center — the work surface.** Code editor on top, **Console drawer** on the bottom. A single results surface that flips between **Code** and **Wave** (the only two artifacts that ever hold content in the human loop). On a passing sim it **auto-reveals the Wave**, with DUT ports expanded and the TB scope collapsed.
- **Action bar (the spine).** A compact row of **only the real actions — Lint · Simulate · Synthesize** — each with a *persistent* run affordance and a live status dot. Synthesize is explicitly flagged as needing a remote toolchain and states its expected latency/availability *before* it spins.
- **Right — collapsible assistant.** The AI pane becomes an opt-in slide-over, collapsed by default for upload-driven sessions; the width goes to code + waveform.

### What to MERGE
- The two parallel tab strips (top Artifacts + bottom Console) → one mental model: **Code/Wave** is the center surface; **Lint/Sim/Synth output** is the console drawer beneath it.
- The two routes (`/workbench` + chat `/`) → one workbench, with chat as an overlay.
- Spec / Schem / Layout / Signoff / Report → collapse into **one secondary "Advanced / Backend" affordance** that expands only once a synth job has produced real output.

### What to CUT (from the default human view)
- The always-on AI Assistant pane (→ collapsed slide-over).
- The Spec stage/tab on the human path (no AI = no spec, ever).
- Schem and Layout tabs until synthesis produces them.
- The premature "Generate report" CTA while synth is running.
- The second chat-first landing route as a separate destination.

### What to DEFER (progressive disclosure)
- Synth / Signoff / Report appear only **after a sim passes**, and resolve to a clear pass/fail — **never an open-ended "No further output" spinner.**
- Schem / Layout appear only after a **successful** synth.

### How the loop should feel
> edit → one-click **Simulate** → console shows PASS/FAIL with the failing `$time` and the exact reproducible command → **waveform auto-updates** to that run (DUT signals expanded) → tweak → re-run via the promoted "edit & re-run" affordance → repeat.

The whole drive is the three-button action bar. A 9-line mux should not be surrounded by five empty tabs and an inert chat.

### ASCII wireframe

```
+-----------------------------------------------------------------------------------+
| SiliconCrew - WORKBENCH      Session: evr2-08_fifo            [moon]  [Assistant >]|
+--------------+--------------------------------------------------------------------+
| ACTION BAR:   [> Lint *0warn] - [> Simulate *passed] - [> Synthesize (remote ~2m)] |
+--------------+--------------------------------------------------------------------+
| FILES        |  [ Code ]  [ Wave* ]            *auto-shown on passing sim          |
| +----------+ | +----------------------------------------------------------------+ |
| | fifo.v   | | |  v fifo_tb.dut  (DUT - expanded)                                | |
| |   [RTL]  | | |     clk  din[8]  dout[8]  full  empty  count[3] rptr wptr       | |
| | fifo_tb.v| | |     _|-|_ hex values, HEX/DEC, zoom                             | |
| |   [TB]   | | |  > fifo_tb       (testbench - collapsed)                        | |
| +----------+ | +----------------------------------------------------------------+ |
| synthTop     | +-- CONSOLE  [Lint][Sim][Synth] -------------------------------+   |
|  fifo        | | sim_0001 passed (fifo_tb) - TEST PASSED   $finish @ 86000    |   |
| simTop       | | $ iverilog -g2012 ... ; $ vvp ...            [Copy] [Re-run]  |   |
|  fifo_tb     | +-------------------------------------------------------------+   |
| (auto-det.)  |  RUNS: * sim_0001 passed - 23s ago    (gear) synth_0001 ...       |
+--------------+--------------------------------------------------------------------+
   Spec / Schem / Layout / Report -> behind "Advanced", shown only when produced
```

---

## 6. Quick wins vs bigger bets

**Quick wins (UI/state only, high impact, low effort):**
1. **Collapse the AI pane by default** for upload-driven sessions and remember the state. (Reclaims ~30% width immediately — F4.)
2. **Hide/defer Spec, Schem, Layout, Report** until they have content; **disable "Generate report"** until synth = passed. (F3.)
3. **Auto-open the Wave tab on a passing sim** (or inline "View waveform →" in the sim console). (F6.)
4. **Give the three action chips a persistent run badge** distinct from the passive view chips. (F2.)
5. **Add an up-front ETA + "may take ~1–2 min / can fail" note on synth start.** (Partial F1.)
6. Promote "edit & re-run command" and label the auto-detected-tops row. (F9.)

**Bigger bets (backend/architecture):**
1. **Make Synthesize bounded and honest:** availability pre-check, heartbeat/streamed ORFS log, hard timeout, explicit terminal error + retry instead of silent "running." (Core of F1 — the single most-cited issue.)
2. **Unify the two routes:** `/workbench` as default landing for RTL-bearing sessions; chat becomes an overlay. (F5.)
3. **Self-host Monaco** to kill the CDN cold-start. (F7.)
4. **Restructure to the two-surface model:** merge the Artifacts/Console tab strips into one Code/Wave center + Console drawer, with stages gated by progressive disclosure. (Realizes Section 5.)

---

*Verdict in one line: the write→lint→sim→iterate loop is real, fast, and good today; the "gimmicky" feeling is entirely the half-screen of inert/empty chrome around it. Cut the noise, defer the unreachable stages, make synth honest — and the same engine becomes a clean IDE.*
