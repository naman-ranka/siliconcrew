# UI Polish Pass — persona-driven, real data (integration branch)

A deep UI pass on `claude/integration-p1p2`, driven by **live** Playwright
persona reviews of the running app (real iverilog: lint/sim/waveform carry real
data; synth has no ORFS here so its empty/error states were polished, not
fabricated). Frontend-only, merge-safe — no backend/action-API/auth changes.

Method: three personas reviewed the live app (each its own isolated headless
Chrome + its own session), screenshotting every screen with blunt feedback;
fixes were applied; then **fresh** personas re-reviewed.
- Before screenshots: `screenshots/uipolish/before/{student,engineer,hobbyist}/`
- After screenshots: `screenshots/uipolish/after/{student,engineer,hobbyist}/`

---

## Persona feedback → what changed

### First-time student ("I don't know what to click")
| Feedback (before) | Change |
|---|---|
| No first-run guidance; eye goes to the chat welcome, not the work | **Onboarding** panel in the center on an empty workspace: "Let's build a chip", 4 plain-language steps, **Upload RTL** / **Write a file** CTAs (`Onboarding.tsx`) |
| `"No simTop in the manifest and none provided"` = instant quit-point | **Friendly, actionable errors** (`friendlyError` in `store.ts`): "No testbench found. Simulation needs a testbench (*_tb.v)… add one, then Run Sim." (+ lint/synth variants) |
| Jargon everywhere (RTL/Lint/Signoff/synthTop…) with no hints | **Plain-language tooltips** on every pipeline stage (`PipelineStepper` `title`/`aria-label`: "Check the RTL compiles…", "Run the testbench…", etc.) |
| "Session" looked like a username | **"Session" label** before the picker (`Workbench`) |
| Filename rules only appear as an error after you fail | **Filename hint** under the new-file field: "ends in .v · .sv · .vh · .svh" (`CodeViewer`) |

### Hardware engineer ("I can't tell which signal is wrong / where")
| Feedback (before) | Change |
|---|---|
| Waveform never says which signal failed or expected-vs-actual | **Offending-signal highlight** (red row) + **"exp N" badge**, parsed from the TB failure line (`WaveformViewer`) |
| Fail cursor pinned flush to the right edge; can't place my own | **End padding** + **click-to-place measurement cursor** (blue) with ns label and per-signal value-at-cursor; "cursor @ Nns ✕" to clear |
| Stuck on hex buses | **Per-bus radix toggle** (hex/dec) in the wave header |
| Selecting a historical failing run shows "No sim output yet" | Console **backfills** the selected run's command + ERROR (`store.selectRun`) |
| Comparing two sim runs shows an all-null PPA table | **Sim-aware compare** (Status / Top / Failure @ / Pass marker) in `RunsTimeline` |
| After edit→save→re-run it bounces me off the Code tab | Re-run **keeps the Code tab** when mid-iteration (`store.runSim` keepTab) |

### Hobbyist ("upload was a black box")
| Feedback (before) | Change |
|---|---|
| No idea where files go / can't get them back | **Per-file Download** button + **path tooltip** on each row (`FileTree`) |
| No upload feedback | **Transient "✓ Uploaded N file(s)"** confirmation + `[role=status]` |
| Non-Verilog files silently dropped | Confirmation notes **"N non-design file(s) stored, not shown"** |
| No drag-and-drop | **Drag-and-drop** onto the file tree (ring highlight + drop hint) |
| Role override invisible (hover-only) | Role select now also reveals on **focus** (keyboard reachable) |

### Cross-cutting (UI standards)
- a11y: focus-visible rings + aria-labels/`aria-pressed`/`aria-busy` on pipeline
  stages, run rows (keyboard-activatable), wave controls, file actions, session
  picker (Escape/click-outside).
- Status colors stay separate from the orange brand (warm palette tokens intact).

---

## After-review results (fresh personas, live app)
- **Student:** all 5 newcomer fixes confirmed; onboarding clarity rated **9/10
  vs ~3/10** before. Biggest win: the empty-state "Let's build a chip" card.
- **Engineer:** all 6 debug-loop fixes **confirmed** against a real failing run
  (culprit `y` row red + `exp 5`; fail cursor 28px off the edge; click-drop blue
  cursor with per-signal value-at-cursor; hex/dec rebase; historical-run console
  backfill; sim-aware compare; edit→re-run stays on Code).
- **Hobbyist:** download / drag-drop affordances / non-design-file note / path
  tooltip confirmed. Found the upload banner only fired on the non-design path —
  **fixed**: the confirmation is now store-driven (`uploadNotice`) so design-only
  uploads via *any* surface (file-tree button, drag-drop, onboarding CTA) show it.

## Verification
- `npm run test` (Vitest) — 17 pass. `npm run e2e` (Playwright mock flow) — 3 pass. `tsc --noEmit` clean.
- Core backend suites green (manifest/file_ops/actions/sim_isolation/real_flows/
  waveform = 32 pass). The 12 failing backend tests on this branch are
  environment-only (BYOK/KMS, LLM provider keys, Docker for cocotb/sby, the `mcp`
  package) and unrelated to this frontend-only pass.

## What still needs real synth / real users (flagged by the after-review)
- **Synthesis/Report/Layout with real data** — needs ORFS in Docker (absent
  here). Empty/error states were polished; the PPA hero is unit-tested but a live
  PPA/timing/GDS screenshot awaits a real synth run.
- **Waveform (engineer's remaining Top 3):** dedup aliased nets across
  `tb`/`tb.dut` scopes (the culprit row + `exp` badge currently render twice);
  two-cursor A→B Δt measurement; fit-to-window / zoom-to-failure for very short
  or very long sims.
- **First-run polish (student):** native `title` tooltips are slow to appear — a
  styled hover-card would teach better; the footer's `synthTop/simTop/clk` could
  use the same plain-language treatment.
- **Backend follow-ups (not changed — frontend-only pass):**
  `GET /api/chat/{session}/history` returns 500 on a fresh session (first-run
  console noise); sim retries don't nest because `parentRunId` isn't set on
  re-run; failure→RTL-line jump needs source mapping from the sim error.
- The "AI assistant needs ANTHROPIC_API_KEY" notice is already a calm info banner
  but still draws first-run attention; consider persisting dismissal.
