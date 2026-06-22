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

## Screenshots (committed, from the Playwright E2E)
Captured by `frontend/e2e/workbench.smoke.spec.ts`; copies live in
`plans/phase1/screenshots/` for review (the live `frontend/e2e-artifacts/` is
gitignored and regenerated on each `npm run e2e`).

| Stage | File |
|---|---|
| Shell — pipeline spine + file tree (roles) + runs timeline + agent rail | `screenshots/workbench-shell.png` |
| Upload — manifest auto-tags roles | `screenshots/wb-1-upload.png` |
| Lint — console shows the exact iverilog command + result | `screenshots/wb-2-lint.png` |
| Sim (fail) — drives the waveform + "viewing X" banner + deeplink | `screenshots/wb-3-sim-fail.png` |
| Sim (pass) — re-run after fix, new `sim_0002` in the timeline | `screenshots/wb-4-sim-pass.png` |
| Report — pipeline all green, unified timeline, timing-first PPA | `screenshots/wb-5-report.png` |

## Chat threads (many conversations per workspace)
- ✅ **Data model**: `chat_threads` (sqlite + postgres), tenant-scoped
  `{id, session_id, user_id, title, model, created_at, last_active}` + index
  `(session_id, last_active)`; `SessionManager` wrappers + `ensure_default_thread`
  (zero-migration: default thread `id == session_id`, legacy histories = "Chat 1").
  Tests: `tests/test_chat_threads.py` (CRUD, tenant red-team, back-compat).
- ✅ **Endpoints** (owner-checked, tenant-scoped): `GET/POST /api/sessions/{id}/threads`,
  `GET .../threads/{tid}/history`, `PATCH .../threads/{tid}`, `DELETE .../threads/{tid}`.
  Legacy `/api/chat/{id}/history` still serves Chat 1.
- ✅ **WS** keys the LangGraph checkpoint by `thread_id` (per-message → `?thread_id`
  → Chat 1) while the workspace stays bound from `session_id` — threads share the
  live workspace. Auto-title from first message; new thread → empty → prompt injected.
- ✅ **Frontend**: `ThreadSwitcher` (＋New chat, rename, delete, a11y) + thread-aware
  store/WS. Tests: `frontend/test/chat.threads.store.test.ts` (8),
  `frontend/e2e/chat-threads.spec.ts` (workspace-unchanged + switcher screenshot).

## Model selector (per chat thread)
- ✅ **`GET /api/models`**: registry from `model_catalog` (id/label/provider/tier/
  hint + pricing) with per-request `available` from usable provider keys (env in
  self-host; user BYOK + capped hosted Gemini otherwise) — never offers a model
  that 500s. Tenant-scoped via `get_identity`.
- ✅ **Model lives on the thread**: `chat_threads.model`; the WS reads the active
  thread's model (`thread → session → DEFAULT` via `normalize_model_name →
  create_architect_agent`). New threads inherit the creator's last-used model.
  Set via `PATCH .../threads/{tid}` (or the picker). Tests:
  `tests/test_model_selector.py`.
- ✅ **Picker** (`components/chat/ModelPicker`, composer bottom-left): provider-
  grouped popover (Anthropic/OpenAI/Google) with capability hints + cost,
  checkmark on current, unavailable greyed + "needs key"; a11y (aria
  menuitemradio, focus-visible, Escape/click-outside). Tests:
  `frontend/test/model.picker.store.test.ts` (3), `frontend/e2e/model-picker.spec.ts`
  (+ grouped-popover screenshot).

## Scenario-driven hardening (real, not mocks)
See `plans/phase1/SCENARIOS.md` for the full log. Done in this pass, all run
against **real iverilog 12.0** (lint/sim/waveform) over the live app:
- ✅ Real single-module + real multi-module (cpu) end-to-end flows.
- ✅ Failure paths reproduced + fixed + regression-tested: lint syntax error,
  sim mismatch (`test_failed` + failure cursor), compile failure (missing
  module), no-pass-marker, synth-with-ORFS-unavailable (graceful, no hang).
- ✅ Waveform brought to demo quality: hierarchy/scope tree, bus hex, x/z,
  time ruler, and a **correctly-placed failure cursor** (fixed a real ns-vs-ps
  units bug) with a per-signal value-at-cursor readout.
- ✅ Report: timing-hero + PPA cards + compare-vs-previous (`PpaHero`), honest
  ORFS-aware empty state.
- ✅ Code tab offline fallback (Monaco CDN blocked → syntax highlighter).
- ✅ Calmer AI-key banner; failure reason surfaced in banner + console peek.
- ✅ Fresh-eyes UX review via a Playwright subagent (its findings drove the
  cursor/localization/banner fixes); 10 review screenshots in
  `screenshots/review/`, before/after in `screenshots/after-*.png`.
- Boundary: real synthesis (ORFS/Docker) + PPA/GDS are Phase 2 (not runnable
  here); the synth path is verified to fail fast and explain why.

New tests: `tests/test_real_flows.py` (7 real-iverilog scenarios),
`frontend/test/waveform.test.tsx`, `frontend/test/ppa-hero.test.tsx`.
Totals now: pytest real-subset 36 passing; Vitest 17 passing; Playwright 3.

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
