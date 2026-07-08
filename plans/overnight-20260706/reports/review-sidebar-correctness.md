# Adversarial correctness review — sidebar branch

Branch: `claude/sidebar-ui-tooling-improvements-bnmxhb` (5 commits over `endgame`).
Scope: frontend-heavy (chat density, Codex model picker, loose-VCD waveform
opening) + `src/model_catalog.py` / `api.py` Codex-registry backend change.
Method: read `git diff endgame..HEAD` in full; traced each priority area to
source; verified containment/session-reset/cache-key claims against code;
ran `npx tsc --noEmit` (clean, exit 0). Frontend vitest reported green
(415/415) by the lead; backend at env-gap baseline.

## Verdict

**Test-repair (commit f4b38fd): LEGITIMATE — not masking.** Both repairs
correct the test to the actual, pre-existing behavior; one even *tightens* the
assertion. Details below.

**Overall: DEPLOY-SAFE.** No high/critical correctness bugs found. Three
low-severity cosmetic notes, none blocking.

---

## 1. Test-repair verdict (priority #1) — LEGIT

### 1a. `frontend/test/chat.threads.store.test.ts` — LEGIT
Change: `expect(threadsApi.create).toHaveBeenCalledWith("s1")` →
`toHaveBeenCalledWith("s1", undefined, undefined, undefined)`.

Verified the 4-arg signature **predates this branch**: on base `endgame`,
`api.ts` already declares `create: (sessionId, title?, model?, runtime?)` and
`store.ts` `newThread` already calls
`threadsApi.create(currentSession.id, undefined, undefined, runtime)`. A plain
`newThread()` passes `undefined` for `runtime`, so the actual call is
`("s1", undefined, undefined, undefined)`. `toHaveBeenCalledWith("s1")` does
strict arg-array equality (length 1 ≠ length 4) → it was genuinely failing on
base. The repair matches real behavior; it loosens nothing. The same commit
also *adds* a real assertion (`selectThread flips agentRuntime to FOLLOW the
target thread`) that directly guards the new store logic — net stronger.

### 1b. `frontend/e2e/workbench.smoke.spec.ts` — LEGIT (tightened)
Change: `getByText(/240\s?ns/)` → `getByText(/failed @ 240\s?ns/)`.

The Runs table (`RunsPane.tsx:151`) renders the status chip as
`failed @ 240ns`, and the sibling run-reason line (`RunsPane.tsx:158-166`,
`failureReason` → `r.failure.firstFailureLine`) commonly also contains the
failure time (`…at time 240ns`). Two elements matching `/240ns/` → Playwright
strict-mode collision. Anchoring on `failed @ 240ns` targets only the status
chip — a *more specific* assertion, not a weaker one. (This e2e is not in the
CI gate regardless.)

---

## 2. VCD / loose-waveform opening (priority #2) — SAFE

Traced the full path: `artifactKeyForFile` / `artifactKeyForToolCall` →
`wavefile:<path>` → `openArtifact` → `WaveFileArtifact` →
`loadWaveformFileArtifact` → `workspaceApi.getWaveform` → backend
`GET /api/workspace/{sid}/waveform/{filename:path}`.

- **Path traversal: blocked.** `api.py:2256-2260` checks `os.path.exists`
  (404) then `is_within(workspace, vcd_path)` (403) *before* parsing. A `../`
  path that resolves outside the workspace returns 403; the frontend surfaces
  it as `ViewerError`. Endpoint is pre-existing; the branch only newly routes
  loose VCDs to it. Verified.
- **Missing / deleted file: honest.** 404 → `loadArtifact` catch → slice
  `status:error` → `WaveFileArtifact` renders `ViewerError` with a Retry. No
  crash.
- **Non-VCD opened as waveform:** `_parse_vcd_file` wraps in try/except; a
  parse failure returns an error payload, not a 500 crash of the row.
- **Cross-session collision (the "ids collide" sharp edge):** loose keys are
  path-based (`wavefile:dump.vcd`) and *do* collide across sessions, BUT
  `artifactCache` is reset to `{}` on every session switch
  (`store.ts:783`), and `loadArtifact` singleFlight + write-back are
  session-guarded (`store.ts:2281,2284,2301`). No stale leak. Cache-key
  consistency confirmed: `makeArtifactKey("wavefile", path)` and
  `WaveFileArtifact`'s `artifactCache[`wavefile:${path}`]` produce the same
  string.
- **Failure-cursor scoping:** `WaveformViewer.tsx:49` now
  `effectiveRunId = overridden ? (runIdProp ?? null) : selectedRunId`. Loose
  VCD (`<WaveformViewer data={data}/>`, no runId) → `null` → never inherits
  the globally-selected run's failure time. Checked all 2 production callers:
  `WaveArtifact` passes `data`+`runId` (unchanged), `WaveFileArtifact` passes
  `data` only. No caller passes `runId` without `data`, so the one path where
  the new branch would differ from base is dead code — no regression.

## 3. Codex model picker + `model_catalog.py` (priority #3) — SAFE

- **No frontend/backend drift.** The Codex picker renders `codexModels`,
  which is exactly `codex_catalog_entries()` (from `CODEX_CATALOG`) served by
  `/api/models` — same source, by construction. Every Codex id
  (`gpt-5.3-codex`, `gpt-5.5`, `gpt-5.4-mini`) is in `PRICING`
  (`model_catalog.py:26-28`), covered by the new
  `tests/test_model_selector.py` assertions.
- **Backend accepts the picked id.** `normalize_model_name` passes ids
  through (alias map only); it rejects nothing. An invalid id would fail at
  the OpenAI call and surface as an honest chat error, not a silent wrong-model.
- **Correct default (a real fix in this branch).** `api.py:135` now sets the
  Codex runtime `default_model=CODEX_DEFAULT_MODEL` (`gpt-5.3-codex`) instead
  of the app-wide Gemini `DEFAULT_MODEL` — previously an unpinned Codex thread
  would resolve a *Gemini* key and hand it to Codex. Picker display
  (`codexDefaultModel`) now matches backend resolution.
- **Native ModelPicker still works.** Refactor removed the OpenAI-filter
  branch (that logic moved to `CodexModelPicker`); native picker now shows the
  full catalog grouped by provider with key-based availability. `tsc` clean;
  `modelPicker.codexBypass.test.tsx` rewritten to target `CodexModelPicker`
  with a decoy-native-model "must never appear" assertion + a
  default-fallback test — meaningful coverage, not gutted.

## 4. Store changes (priority #4) — SAFE

- `codexModels` / `codexDefaultModel` are a **global registry** (loaded from
  `/api/models`), correctly NOT session-scoped — no reset needed, no leak.
- `selectThread` flips `agentRuntime` to follow the target thread
  (`store.ts:1487-1495`); `loadThreads` derives it from the active thread on
  session switch (`store.ts:1378`). Consistent both directions.
- No populated-data-blanks violation: the `loadModels` catch clears
  `codexModels` only on fetch failure (same policy as `models`), never mid-flight.

## 5. Chat density (priority #5) — SAFE

- **No ResizeObserver leak:** effect returns `ro.disconnect()`;
  `typeof ResizeObserver === "undefined"` guard is SSR-safe (`ChatArea.tsx`).
- **No SSR/hydration mismatch:** `compact` initial state is `false` on both
  server and client first render (RO fires only post-mount) → identical markup.
- **No measurement loop:** the root div's width is parent-controlled; toggling
  `compact` changes only inner padding, not the observed `contentRect.width`,
  so no oscillation. `setCompact` also bails when unchanged.
- **Provider wraps consumers:** `MessageList` (`ChatArea.tsx:243`) and
  `ChatInput` (`:273`) are inside the `ChatDensityProvider`; `useChatCompact`
  defaults to a safe `false` if ever rendered outside.
- CSS specificity claim holds: `[data-density] .prose h1{}` element rules beat
  the stripped utility classes; the report viewer's `.prose` is outside any
  `[data-density]` container, so its absolute sizes are untouched.

---

## Low-severity notes (non-blocking)

1. **`ModelPicker.tsx:72`** — `currentId = … || defaultModel || ""`. Before
   `loadModels` resolves `defaultModel`, `currentId=""` → the button shows an
   empty label (dot + chevron only) for one frame. Base hardcoded
   `"gemini-3.5-flash"` as the fallback. Cosmetic; `loadModels` runs on mount.
   Direction: fall back to `codexDefaultModel`/first catalog entry, or render a
   "Model" placeholder.
2. **Container-density first-paint flash** — a rail-narrow chat renders one
   comfortable frame before the ResizeObserver fires. Inherent to RO-driven
   container queries; cosmetic only.
3. **`useChatCompact` outside provider** defaults to `false` — safe today (both
   consumers are always inside `ChatArea`), noted only against future reuse.
