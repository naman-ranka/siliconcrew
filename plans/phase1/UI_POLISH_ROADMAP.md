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
| 3 | Pipeline stepper: refined stage chips (hover/active/busy/disabled), connectors, status dots | ⬜ todo | |
| 4 | File tree: row states, persistent affordance hints, drag-drop polish, role-badge system | ⬜ todo | |
| 5 | Runs timeline: elevation/hover/selected/compare states, lineage connectors, pin micro-interaction, loading skeleton | ⬜ todo | |
| 6 | Console: tab styling, command block + copy, peek↔expanded transition, status dots | ⬜ todo | |
| 7 | Waveform: gridlines, hover tooltip, draggable cursor handle, segmented radix control, fit-to-window, dedup aliased nets | ⬜ todo | |
| 8 | Report / empty states / banner / agent rail: one EmptyState primitive, PPA hero polish, calmer welcome | ⬜ todo | |
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
