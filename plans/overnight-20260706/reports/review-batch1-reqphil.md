# Review — follow-ups batch-1 vs requirements + philosophy

Branch `claude/followups-batch-1` reviewed against `git diff endgame..HEAD`,
`plans/followups-backlog.md`, and CLAUDE.md (invariants + philosophy + product
posture). READ-ONLY review; no code edits.

## VERDICT

**6 of 7 fully resolved and philosophy-aligned; #3 is PARTIAL.** The backend
half of #3 (the actual foot-gun — request-thread stall / memory blowup) is
fixed with an honest structured payload, but the frontend never consumes the
`tooLarge` signal, so an oversized VCD renders as the misleading "No signals
found in waveform" instead of "too large — download instead" (invariant 4).
Everything else is the simple, fundamental, honest version — no invariant
violations, no machinery, self-host untouched, no Codex naming leaking into the
shared shell. Notably #1 made the *right* call by gating on the account's own
`model/list` rather than the static `CODEX_CATALOG`.

## Per-item

| # | Item | Resolves backlog? | Invariant / simplicity concerns | Evidence |
|---|------|-------------------|----------------------------------|----------|
| 1 | Codex account-auth model gate | **Yes** | Correctly gates on the live account `model/list`, **not** `CODEX_CATALOG` — the explorer found the default `gpt-5.3-codex` (`CODEX_DEFAULT_MODEL`) isn't account-valid, so a static-catalog gate would be wrong. Honest degradation on any error/empty → omit (safe default, no 0-token trap). Per-worker cache defensible in one sentence. Minor: cached list can go stale for a worker's lifetime (bounded by idle retire); multi-shape return parsing is speculative but justified — real SDK surface is unconfirmed (stated honestly in tests). | `src/agents/codex/codex_engine.py:394-460` (`_effective_model`, `_fetch_allowed_models`); wired to worker at `codex_engine.py:511`, `codex_warm.py:83,255-257`; `tests/test_codex_model_gate.py` (a–e), esp. `_ACCOUNT_MODELS` comment L~136 |
| 2 | Thinking heuristic hides real prose | **Yes** | Deleted the positional `isThinkingBlock`; `BlockView` now keys off the *real* block type — `reasoning`→collapse, `text`→always visible. Stops the every-turn prose loss (invariant 4) while genuine reasoning still collapses. Simple, redundant heuristic removed, not replaced with machinery. Provider-agnostic — no Codex leakage. | `frontend/components/chat/MessageList.tsx:97-108` (removed `-blocks/-idx`), `types/index.ts:90-94` (real `reasoning` type); `frontend/test/chat.thinking-prose.test.tsx` |
| 3 | VCD parse size cap | **PARTIAL** | Backend cap fixes the real foot-gun (thread stall / oversized response) with an honest `tooLarge` payload sharing the success shape. BUT the honest *user-facing* signal the backlog asked for is not wired: `WaveformData` has no `tooLarge`/`size` field and `WaveformViewer` never branches on it — a >25 MB VCD renders "No signals found in waveform" (reads as empty/broken, not too-large). This slipped between the backend (#3) and frontend (#2/#7) agents; not listed as deferred. | backend `api.py:2304-2333` (`VCD_PARSE_CAP`, guard); type gap `frontend/types/index.ts:139-146`; no branch — `frontend/components/artifacts/WaveformViewer.tsx:615-616` "No signals found"; `tests/test_vcd_size_guard.py` |
| 4 | `GET /waveforms` recursive | **Yes** | `os.walk` returning workspace-relative POSIX paths (fetchable via the sibling `/waveform/{filename:path}`). Deliberately NOT `iter_workspace_files` (it prunes `sim_runs`/`synth_runs` — the exact dirs the VCDs live in); reason documented in the docstring. Read-only walk, no row materialization (invariant 8). Honest listing now matches the docstring. | `api.py:2254-2280`; `tests/test_waveforms_recursive.py` |
| 5 | PATCH-time model validation | **Yes** | 422s early on an unknown normalized id. `_KNOWN_MODEL_IDS` = catalog ∪ codex-catalog ∪ `PRICING`. Including `PRICING` is sound, not drift: it's a deliberate leniency superset so previous-gen still-priced ids stay pinnable and the greedy-route shadowing regression (which PATCHes `claude-sonnet-4-6`) stays green. Pickers ⊆ known set, so every valid pick passes; consistent with the one-catalog source (a superset of it, never a divergent parallel list). Aliases normalized first. | `api.py:1300-1310` (`_KNOWN_MODEL_IDS`), `api.py:1325-1332`; imports `api.py:31-37`; `tests/test_patch_model_validation.py` |
| 6 | CLAUDE.md known-failure drift | **Yes (with honest caveat)** | Added `test_run_cocotb`/`test_run_sby`/`test_linter_tool_multifile [no iverilog/verilator]` framed under "missing deps/binaries" — the correct env-*dependent* form. The implementer honestly flagged these PASS on their own container (binaries present), so the "~20 KNOWN … in this container" header is now slightly self-contradictory. Cosmetic; the `[no iverilog/verilator]` annotation keeps it honest. | `CLAUDE.md:110-114`; caveat in `reports/backend-followups.md:89-100` |
| 7 | WaveArtifact fallback + stale tab keys | **Yes** | Honest scoping: the literal "reopen by `wavefile:` path from a bare runId" is infeasible (VCD filename is discovered per-run server-side), correctly NOT faked (invariant 4). Feasible honest fallback: keep rendering the already-cached waveform with a "no longer listed — cached waveform" note. Tab-key migration is a proper persist `migrate` (v1→v2), defensive (never throws → won't drop saved tabs), dedups. | `frontend/.../WaveArtifact.tsx:35-56`; `frontend/lib/workbenchUiStore.ts:31-64,265-269`; `frontend/test/waveArtifact.fallback.test.tsx`, `workbenchUi.migrate.test.ts` |

## Cross-cutting checks

- **Self-host untouched:** #1 lives inside `codex_engine`/`codex_warm`, adds no
  cloud import and needs no `settings.hosted` gate; BYOK path is behaviorally
  unchanged (model passed verbatim, `model/list` never queried). No invariant-9
  / engine-selection impact.
- **No Codex naming in the shared shell:** #2/#7 touch generic components
  (`MessageList`, `WaveArtifact`, `workbenchUiStore`); #2 branches on the
  provider-agnostic `reasoning`/`text` types. `_KNOWN_MODEL_IDS` folds
  `codex_catalog_entries` but that's backend validation, not UI branding.
- **One event log / viewer-not-actor / tenancy:** none of these changes poll
  status, materialize rows, or cross owner scope. #4/#5 are read-only /
  owner-checked (`user_id=uid`).
- **Working tree note:** `deploy/roll_cloudrun.py` shows modified but is NOT in
  `endgame..HEAD` (another agent's uncommitted change) — out of this batch's
  scope, correctly not committed here.

## Recommended follow-up (not blocking staging)

- Finish #3's honest signal: add `tooLarge?: boolean` + `size?: number` to
  `WaveformData` and branch in `WaveformViewer` (or `WaveArtifact`/
  `WaveFileArtifact`) to render "waveform too large to render — download
  instead", so the >25 MB case reads honestly instead of "No signals found".
- Reconcile the CLAUDE.md "in this container" wording with the env-dependent
  entries (#6 caveat) — owner call on which base image the list describes.
