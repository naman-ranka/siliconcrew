# Phase 1 — Workbench + API: progress checklist

Living checklist of the Phase 1 slices (see `plans/phase0/agent-brief-phase1.md`).
Status: ✅ done · 🟡 in progress · ⬜ not started.

## First task (README required integration step)
- ✅ Session context set **per request**, not via the global `RTL_WORKSPACE`.
  - WS chat path: `set_current_session(...)` (Phase 0 bridge).
  - New action endpoints: each runs inside `session_scope(SessionContext(...))`
    via `run_scoped` (off-thread; contextvar copied into the worker).
- ✅ Propagation gate test: `tests/test_session_context_propagation.py`.
- ✅ Action-layer cross-tenant isolation test (concurrent sessions don't bleed):
  `tests/test_actions_api.py::test_concurrent_sessions_are_workspace_isolated`.
- ✅ Sim-run isolation: `run_sim_isolated` writes `sim_runs/sim_NNNN/` with its
  own VCD + provenance-stamped `run_meta.json` (`src/tools/sim_manager.py`).

## Slices
1. ✅ **Session wiring + sim isolation + manifest read/write API**
   - `src/tools/manifest.py` (DesignManifest, role derivation, top inference,
     persistence + reconciliation), `src/api/actions.py` (GET/PUT `/manifest`,
     POST `/files`). Tests: `test_manifest.py`, `test_sim_isolation.py`,
     `test_actions_api.py`.
2. ✅ **File tree + roles + upload (manifest-driven)**
   - `components/workbench/FileTree.tsx`; `/files` GET extended with `role`.
   - Tests: `test/workbench.components.test.tsx`.
3. ✅ **Run Lint / Run Sim buttons → endpoints → console (command + result)**
   - `PipelineStepper.tsx` (spine doubles as actions), `Console.tsx` (shows the
     exact command; opt-in "edit & re-run" escape hatch). Store: `runLint`,
     `runSim`. Tests: `test/workbench.store.test.ts`.
4. ✅ **Waveform wired to the selected sim run (reuse WaveformViewer)**
   - `selectRun` sets the run's isolated `vcdPath`; `WaveformViewer` honors a
     selected per-run VCD. Verified in the E2E.
5. ✅ **Run Synth (async + poll) → Report (timing-first) + Layout**
   - `synthesize` + bounded job polling in the store; reuse `ReportViewer` /
     `LayoutViewer` (best-effort GDS→SVG endpoint added, degrades gracefully).
6. ✅ **Unified runs timeline (filter, lineage, pin, compare)**
   - `RunsTimeline.tsx` + `GET /runs`, `/runs/compare`, `/runs/{id}/pin`.
     Selecting a run drives viewers + the "viewing X" banner (`ViewingBanner.tsx`).
7. ✅ **Agent rail sharing tools**
   - Reuses `ChatArea` in the workbench; agent gets the same tools
     (`get_manifest`, `update_manifest`, `run_isolated_simulation` added to the
     shared `@tool` layer in `src/tools/wrappers.py`).

## Verification
- **Tier 1 (Vitest/jsdom):** `cd frontend && npm run test` — 9 passing
  (store + components). No browser.
- **Tier 2 (Playwright/Chrome):** `cd frontend && npm run e2e` — 3 passing.
  Drives the real frontend against a stateful mock of the action layer:
  upload → lint → sim (fail) → waveform → fix → re-run (pass) → synth → report,
  screenshotting each stage to `frontend/e2e-artifacts/`.
  First-time setup: `npx playwright install chrome`.
- **API smoke (pytest):** `python -m pytest tests/test_actions_api.py
  tests/test_manifest.py tests/test_sim_isolation.py` — hits each endpoint on a
  bare app + temp workspace; the EDA-dependent path is exercised when `iverilog`
  is present.

## Architecture notes / Phase-2 seams
- The action layer is a standalone `APIRouter` (`src/api/actions.py`) built from
  a `resolve_workspace(session_id)` callable — **no dependency on the agent
  stack** (so it is unit-testable, and Phase 2 swaps the resolver for a
  cloud-backed `WorkspaceProvider` with zero handler changes).
- One action layer: every REST handler and every agent `@tool` call the *same*
  tool functions (`run_linter`, `run_sim_isolated`, `start_synthesis_job`, the
  `manifest` module). The UI never shells raw EDA.
- New API field names follow `plans/phase0/data-model.md` (camelCase), mirrored
  in `frontend/types/index.ts`.

## Known limits (Phase-2 scope, not regressions)
- Synthesis P&R (ORFS) and real lint/sim need the EDA toolchain + Docker; the
  endpoints are wired and tested, the heavy execution is Phase 2 (ORFS as an
  isolated job).
- Full GDS→SVG layout rendering is best-effort (pre-rendered SVG sidecar or a
  bounded gdstk render), otherwise a structured "Phase 2" message.
