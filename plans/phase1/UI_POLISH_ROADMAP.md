# UI Polish — full design-system pass (roadmap & tracker)

Branch: `claude/integration-p1p2`. Goal: take the workbench to leading-app
(Codex / Claude Code) visual quality via a systematic, **frontend-only**,
slice-by-slice pass. This file is the source of truth — the orchestrator and
each slice subagent update it.

## Execution model (context-controlled via subagents)
- Each slice is implemented by **one subagent at a time** (sequential — they
  share the working tree, so parallel source edits would collide).
- A slice subagent: reads this file + the target components → implements
  (frontend-only) → verifies → commits + pushes → reports a concise summary
  (files, what improved, test/build result, SHA). The orchestrator ticks the box
  + records the SHA here.

## Standards (every slice must hold)
- Warm Claude palette; **status colors stay separate from the orange brand**
  (`--status-*`, `--info` vs `--primary`). Tokens live in
  `app/globals.css` + `tailwind.config.ts`.
- Motion via the shared tokens: `--ease`/`--ease-in`, `--dur-fast|base|slow`,
  and the `fade-in`/`fade-in-up`/`scale-in`/`shimmer` animations. Respect
  `prefers-reduced-motion`.
- Elevation via `shadow-e1|e2|e3` (warm-tinted), not ad-hoc black shadows.
- Every interactive element: hover / focus-visible / active / disabled / busy.
- Calm, not busy; artifacts are the star.

## Guardrails (do NOT break)
- **Frontend only** (`frontend/**`). No backend / action-API / auth/tenancy
  changes. If a fix needs backend, note it in this file instead.
- Keep these test/e2e selectors working (or update the tests in the same slice):
  `button[data-stage="..."]`, `[data-run-id]`, `[data-testid]`,
  `button[role="tab"]` by text, button titles **Run Lint / Run Sim / Run Synth /
  Edit / Save**, and existing `aria-label`s.
- Keep green: `cd frontend && npx tsc --noEmit && npm run test && npm run build`.

## Verify + commit (each slice)
```
cd frontend && npx tsc --noEmit && npm run test && npm run build
git add -A && git commit -m "UI polish slice N: <area> …
<body>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P39uSynWVroXgfVcr8Xivd"
git push origin claude/integration-p1p2   # retry w/ backoff on network error
```

## Slices
| # | Area | Status | Commit |
|---|---|---|---|
| 0 | Foundation: motion/elevation tokens, warm "paper" light theme + toggle (fixed build-blocking hook bug) | ✅ done | `85e54d0` |
| 1 | Unified toast system (upload + sim pass/fail), 4 Vitest tests | ✅ done | `d8b68f4` |
| 2 | Shell & rhythm: consistent panel headers/density, tab+panel motion, **skeleton loaders** (runs/manifest/report/code) | ✅ done | `d1a71a2` |
| 3 | Pipeline stepper: refined stage chips (hover/active/busy/disabled), connectors, status dots | ✅ done | `3d67725` |
| 4 | File tree: row states, persistent affordance hints, drag-drop polish, role-badge system | ✅ done | `0a13647` |
| 5 | Runs timeline: elevation/hover/selected/compare states, lineage connectors, pin micro-interaction, loading skeleton (+ midpoint stepper active-highlight & connector-fill bug fixed) | ✅ done | `1315590` |
| 6 | Console: tab styling, command block + copy, peek↔expanded transition, status dots (full scrollable+copyable per-run log; lint result auto-expand/pulse surface) | ✅ done | `921d477` |
| 7 | Waveform: gridlines, hover tooltip, draggable cursor handle, segmented radix control, fit-to-window, dedup aliased nets (+midpoint BUG fixed: viewer now follows `selectedRunId`'s VCD, overriding a stale load, with manual-pick override until the run changes) | ✅ done | `a540753` |
| 8 | Report / empty states / banner / agent rail: one EmptyState primitive, PPA hero polish, calmer welcome (midpoint fixed: ViewingBanner overflow → truncate; empty-state voice unified across viewers; brand-orange de-overloaded on neutral count badges) | ✅ done | `00516ca` |
| 1b | Styled Radix tooltips replacing native `title` (update `getByTitle` tests) | ⬜ todo | |
| 9 | a11y & contrast audit: AA on warm dark+light, reduced-motion, focus order, ARIA live regions | ⬜ todo | |

## Periodic review
After ~every 2–3 slices, a fresh **persona-review subagent** (isolated headless
Playwright over HTTP, real iverilog data) screenshots the live app and reports
blunt feedback; findings feed back into the remaining slices. Screenshots:
`plans/phase1/screenshots/uipolish/sliceN/`.

## Notes / deferrals
- Live `next start` serves the built app; for visual checks use `npm run dev`
  (hot reload) on a spare port. `file:` is blocked — always HTTP.
- Backend follow-ups (out of scope here): `/chat/{id}/history` 500 on fresh
  sessions; sim-retry `parentRunId` lineage; failure→RTL-line source mapping.

## Midpoint review findings (after slices 0–4) → slice mapping
Live persona review (student + engineer, real iverilog). Screenshots:
`screenshots/uipolish/midpoint/`. Fold each into the mapped slice:
- **BUG — ViewingBanner overflow** clips long failure strings (no ellipsis) on
  every center tab → **Slice 8** (quick: truncate/wrap).
- **BUG — Wave tab opens the first VCD, not the selected run's** (view sim_0003 →
  shows sim_0001) → **Slice 7** (sync waveform to selectedRunId even when a VCD
  is already loaded; respect a manual override).
- ~~**BUG — Stepper active-highlight follows the artifact tab, not pipeline
  progress** (ran Sim, box stayed on RTL); connector `reached`→fill inconsistent~~
  → **Slice 5** ✅ fixed (`1315590`): highlight follows `actionPending.*`
  when running, else artifact tab; connectors fill on next-stage reached.
- **Light theme not warm / elevation ladder collapses** (surfaces 0/1/2 ~equal,
  muted-text contrast borderline) → **Slice 9** (+theme): add warm hue shift,
  distinct surface ladder, WCAG AA recheck.
- **Console is a one-liner** — need full scrollable, copyable per-run log (raw
  iverilog + all $display); sync console tab to the viewed run → **Slice 6**.
- **Lint has no visible result surface** (center stays on Code) → **Slice 6**.
- **Toast title machine-first** ("sim_0003 failed") — lead human ("Simulation
  failed @ 6ns"), demote id; reconcile with the persistent API-key banner (two
  notification channels) → **Slice 1b**.
- **Empty-state voice inconsistent** (Report "run synthesis" vs Schem/Layout "ask
  the agent") — standardize + same CTA pattern → **Slice 8**.
- **Icon tooltips missing** in file tree (crown=synthTop, flask=tb, download) →
  **Slice 1b**.
- **Brand orange overloaded** (used for neutral count badges e.g. Code "2") —
  reserve orange for primary/active only → **Slice 8/9**.
- Note: skeleton loaders couldn't be observed (dev loads too fast on a tiny
  workspace) — verify under throttling before claiming slice 2's skeletons land.
