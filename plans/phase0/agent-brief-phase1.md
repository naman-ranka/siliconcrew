# Agent Brief — Phase 1: Frontend + API

You are a senior frontend engineer **and** senior product designer who deeply
understands the digital hardware design domain (RTL → lint → sim → synth →
GDSII, timing closure, waveforms, PPA). Your job is to build the SiliconCrew
**workbench UI** and the **thin API layer** over the existing tools.

Read first: `plans/phase0/README.md`, `api-contract.md`, `data-model.md`, and
open `mockups/workbench.html` (the target UX). Honor every principle in the
README.

## Mission

A hardware-design-first, artifact-first online workbench where a user can bring
or generate RTL, run lint/sim/synth via buttons, inspect waveforms/PPA/layout,
and ask the agent for help — all on the same tools and workspace.

## High-level requirements (decide the details yourself, as a senior would)

- **Same app, new shell.** Build a `workbench/` route in the existing Next.js
  app. **Reuse the existing artifact viewers** (`components/artifacts/*`) and
  the Zustand store — do not fork the frontend into a second project. Use a git
  worktree/branch for isolation.
- **The pipeline is the spine.** Surface Spec→RTL→Lint→Sim→Synth→Signoff with
  live status; it doubles as the run actions. The result artifacts (waveform,
  timing report, layout) are the star; the code editor is secondary.
- **Runs make sense to a non-expert.** Latest run = status; a unified
  sim+synth timeline with lineage, pin, compare; selecting a run drives the
  viewers + shows a "viewing X" banner. (See the mockup; it is non-functional —
  make it real.)
- **Buttons call SiliconCrew tools via the new action endpoints, never raw
  EDA.** Show the returned command for transparency; offer an opt-in
  "edit & re-run command" escape hatch, not as the default.
- **The agent shares everything.** Same tools, same workspace, same runs.

## API layer (your responsibility)

Implement the action + manifest endpoints in `api-contract.md` as thin handlers
over the tool functions (return dicts, not stringified JSON). **First task:**
do the README "required integration step" — set the session context per request
instead of mutating the global env var — and add the propagation gate test.
Extend `run_simulation` to write isolated `sim_runs/sim_NNNN/` with its own VCD.

## Build order (slice by slice; each ends runnable + tested)

For every slice, reason explicitly through the user flow before coding: *what
does the user click → which tool runs → what files/artifacts appear → what is
the run called → what does the user do next.* Then build, then test.

1. **Session context wiring** + sim-run isolation + manifest read/write API.
2. **File tree + roles + upload** (manifest-driven).
3. **Run Lint / Run Sim** buttons → endpoints → console with command + result.
4. **Waveform** wired to the selected sim run (reuse WaveformViewer).
5. **Run Synth** (async + poll) → Report (timing-first) + Layout.
6. **Unified runs timeline** (filter, lineage, pin, compare) driving the viewers.
7. **Agent rail** sharing tools; tool-call cards as artifacts.

## Verification (mandatory feedback loop)

- Component/store unit tests per slice.
- API smoke tests hitting each endpoint against a local workspace.
- Prefer Playwright (or equivalent) for the key flow: upload → lint → sim
  (fail) → open waveform → fix → re-run → synth → report.
- Keep a checklist artifact of slices done / in progress.

## Non-goals (Phase 1)

Multi-tenant infra, cloud storage, auth, quotas, ORFS-as-cloud-job — those are
Phase 2. You run against `LocalWorkspaceProvider`. Do not optimize for scale;
do make every action go through the one shared tool layer so Phase 2 can swap
the runtime underneath you.
