# Legibility frontend lane — F11/F12 render, F5, F8

Branch `claude/overnight-showcase`. Three commits, all pushed. Fence honored:
`frontend/**` only; no store changes; no polling added; Launcher/TemplatePreview
untouched. Authoritative source: `legibility-contract.md` (items 3–5) + FINDINGS
(F5, F8, F11, F12).

## Commits

1. `4b9993c` feat(ui): legible sim/synth failure reasons on run rows + report (F11/F12)
2. `31a45db` fix(ui): accessible title for command palette (F5)
3. `ee5d0e6` feat(ui): save confirmation feedback (F8)

## Item 1 — F11/F12 render

**types/index.ts `RunSummary`** — added optional `passMarker` (sim),
`currentStage`, `checkNotes` (synth), matching the contract names the backend
lane is populating. No other type churn.

**RunsPane.tsx** — added a pure `failureReason(r)` helper and render it as a
truncated muted span in the Result cell (full text + stdout tail in `title` —
the "existing lightweight affordance", no new heavy component, no fetch):
- Failed **sim**: `failure.firstFailureLine` when present; else if
  `passMarkerFound === false` → `no pass marker — expected "<passMarker ??
  'TEST PASSED'>"`, stdout tail in the title.
- Failed **synth**: status line gains `@ <currentStage>` (mirrors the existing
  sim `@ <n>ns`); `checkNotes` renders as the one-line reason.
- The existing running-stage display (`synthJob.currentStage`), started-ago,
  and Refresh button are all left intact — I only changed the failed-row path
  and switched the status span from `truncate` to `shrink-0` so the reason gets
  the truncation instead.

**viewers/ReportArtifact.tsx** — new branch before the generic error state: a
FAILED run with no report data renders an honest failure panel — "Synthesis
failed at `<currentStage>`" + `checkNotes` (or an explicit "no stage detail
recorded"), PPA hero kept when present, and `lastLogLines` shown ONLY when
`synthJob.runId === runId` (invariant 6: the UI is a viewer, never fetches the
tail). Non-failed error cases keep the old "No report for this run yet".

## Item 2 — F5 (command palette a11y)

cmdk owns the Radix Dialog and renders no `DialogTitle`, so every ⌘K open logged
`DialogContent requires a DialogTitle`. Added `<Dialog.Title className="sr-only">`
(from `@radix-ui/react-dialog`, already a dep; `sr-only` is the repo's existing
hidden-text idiom, see ThreadSwitcher/dialog.tsx) as the first child of
`Command.Dialog`. It registers with cmdk's internal Dialog context → screen
readers get a name, console error gone, zero visible change.

## Item 3 — F8 (save feedback)

The success toast (`pushToast({kind:"success", title:"Saved"})` after the API
resolves) already existed at CodeArtifact.tsx and the Toaster is mounted in
Workbench — so F8's "no confirmation" was only half-true: the **failure** path
set an inline `saveError` that was easy to miss. Routed it through the same
toast mechanism: `Couldn't save <file>` + the real error message, still only
after the promise rejects (no fake optimism). Inline error kept for persistence.

## Pre-fix failure proof

`git stash push` on the four source files (types/tests kept), then
`vitest run` on the three test files → **5 assertions fail pre-fix**:
- F11 failed-sim no-pass-marker reason — "Unable to find … no pass marker — expected \"TEST PASSED\""
- F12 failed-synth stage + notes
- F12 ReportArtifact failure panel — "Unable to find … /Synthesis failed at route/"
- F5 DialogTitle console error present
- F8 save-error toast (`Couldn't save design.v`) absent

The F8 **success** test passes pre-fix (that toast pre-existed) — expected.
Stash popped; all 9 pass post-fix.

## Tests added

- `test/workbench.components.test.tsx`: failed-sim no-pass-marker reason;
  failed-synth stage+notes; new `ReportArtifact` describe for the failure panel
  (stage + notes + live log tail).
- `test/commandPalette.a11y.test.tsx` (new): asserts no DialogTitle console
  error on open.
- `test/codeArtifact.save.test.tsx` (new): success toast after resolve, error
  toast after reject, via the fallback (no-Monaco) editor.
- `test/setup.ts`: added jsdom `ResizeObserver` + `scrollIntoView` no-op stubs
  (cmdk needs them to render under test). Shared, harmless to other suites.

## Gates

- `npx tsc --noEmit` — clean.
- `npx vitest run` — 373 passed, **1** failure = the known pre-existing
  `chat.threads.store.test.ts` only. Zero new.
- `npx next build` — green.
- Playwright NOT run (browser owned by another agent tonight) — flagged for the
  orchestrator's endgame run. Worth an e2e pass over: ⌘K open (no console
  error), a failed run row's reason text, and a save-failure toast.

## Honest caveats

- Render is implemented against the **contract field names** the backend lane is
  adding in parallel; vitest fixtures mock the run objects, so this lane is green
  independent of that lane. If the backend ships different casing than
  `currentStage`/`checkNotes`/`passMarker`, the mapping in `_synth_to_run` /
  sim run_meta must match these exact keys or the reasons render blank (never
  wrong — absent fields just omit the line).
- The ReportArtifact failure panel shows the log tail only for the one live
  `synthJob` run; a historical failed run shows stage + notes but no tail (by
  design — no fetch).

---

# Follow-up lane — F6 + F7 (nav-rail area)

Two commits, pushed. Same fences (frontend/** only, no store changes).

- `2b16187` fix(ui): reachable nav-rail toggle while open (F7)
- `06f4e11` fix(ui): floor artifacts slide-over width so its tab strip never clips (F6)

## F6 — the real mechanism was NOT a pinned rail

The finding described "open pinned nav rail (264px) shoves the artifacts
slide-over tab strip off the right edge on viewports <~1650px". Verified in
code + git: the NavRail has been a `fixed` overlay with a full-viewport scrim
since Wave 8 (`NavRail.tsx:138-148`) — it never participates in the flex
layout, so it cannot shove anything. The live-exploration note (X2U-4) reached
the same conclusion ("NOT reproducible live … rail is an overlay"). The `<1650`
figure fits a *pinned* 264 + wide-artifacts 760 + ~600 conversation layout that
no longer exists.

But there IS a real, reproducible "slide-over loses its tab strip" bug, just
with a different cause: the panel's inner body carried `minWidth: 360` while its
`overflow-hidden` wrapper was `width: min(42vw, 520px)` (AgentShell). When
`42vw < 360` (viewport <~857px) the inner outgrew the wrapper and the tab
strip's right edge was clipped. Fix (option a — max-width math): floor the
width preset at `max(360px, …)` for both normal and wide, so wrapper == inner
and nothing clips; dropped the now-redundant inner `minWidth`. `PANEL_W` is now
exported and unit-guarded (both presets contain the 360 floor).

## F7 — reachable toggle while open

The open rail (fixed, z-90) paints over the shell header's ☰ opener, so it
could only be closed via Esc / ⌘O / the scrim / the rail's own top-right
collapse glyph — not the toggle that opened it. Fix (the finding's "duplicate
the toggle inside the rail header" idiom): moved a ☰ (Menu) into the rail
header's top-LEFT, the exact screen position of the opener, so the same corner
control both opens and closes. Replaced the top-right `PanelLeftClose` glyph.

## Tests (all in test/agentShell.test.tsx, reusing its Workbench harness)

- F7: open the rail, click `rail-collapse`, assert `navRailOpen === false` and
  the rail's `data-open` flips to false.
- F6: `PANEL_W.normal`/`.wide` both contain the `max(360px` floor.
- Pre-fix proof: stashed AgentShell.tsx + NavRail.tsx → both new tests fail
  ("Unable to find [data-testid=rail-collapse]"; `PANEL_W.normal` lacks the
  floor). Popped; 7/7 pass.

## Gates

- tsc clean; vitest 375 passed, 1 failure = the known `chat.threads.store.test.ts`
  only; `next build` green (below).

## Browser-only (for the endgame Playwright pass)

- F6: at a narrow width (e.g. 800px) with the artifacts panel open, the tab
  strip renders whole (no right-edge clip). The unit test only guards the width
  floor constant, not the rendered pixels (jsdom doesn't compute vw/`max()`).
- F7: with the rail open, clicking the top-left ☰ visibly closes it, and the
  ☰ sits over the same spot as the header opener (pixel alignment).
