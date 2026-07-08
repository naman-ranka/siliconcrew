# Adversarial correctness review — follow-ups batch-1

Branch `claude/followups-batch-1` vs `endgame`. Scope: the 7 fixes in
`git diff endgame..HEAD` (commits 35eb1d2, eba83ff, e6392c7, 5d81d12,
be28dff, 227347b + doc commits). Read-only review; verified against code.

## Verdict: DEPLOY-SAFE (one HIGH honesty gap to fix before the "open any
## workspace VCD" feature is advertised)

Six of seven items are correct as written. The one real defect (F1) does
**not** crash, stall, leak, or lose data — it degrades to a *misleading*
empty-state, so it is not a deploy blocker, but it directly contradicts the
stated purpose of item #3 and invariant 4 (honest state). Fix it promptly.

---

## Findings (ranked)

### F1 — HIGH — item #3's `tooLarge` waveform signal is dropped by the frontend; an oversized VCD renders as "No signals found in waveform"
**Files:** `api.py:2319-2331` (producer) → `frontend/types/index.ts:139-146`
+ `frontend/components/artifacts/WaveformViewer.tsx:141,615-616,630-631`
(consumer).

The backend cap works: `_parse_vcd_file` now `os.path.getsize`s **before**
`from vcdvcd import VCDVCD` (api.py:2315-2331), so the request thread no
longer stalls / OOMs on a hundreds-of-MB dump. That is the dangerous half
and it is fixed.

But the honest `{"tooLarge": True, "signals": [], "signalCount": 0,
"endtime": None, ...}` payload it returns is **never consumed**:
- `WaveformData` (types/index.ts:139-146) has no `tooLarge` (nor `size`)
  field — the field exists only on the *smart-file* reader type
  (index.ts:351, consumed by CodeArtifact/DataArtifact/TextArtifact).
- `WaveformViewer` branches only on `signals`: with an empty array the group
  reduction (line 141) yields no groups, so line 615-616 renders
  **"No signals found in waveform"**, the footer shows **"0 signals"**
  (line 631) and **"End: null …"** (line 630, since `endtime` is null →
  `|| 1000` for the grid but the raw `null` is printed in the footer).

**Failure sequence:** user opens a >25 MB workspace VCD (exactly the case
the "open any workspace VCD" feature made reachable) → backend returns
`tooLarge` → viewer shows an empty grid captioned "No signals found in
waveform" / "0 signals". The user concludes the simulation produced nothing,
with no hint the file was too large and no download affordance. Item #3's
own docstring promises "the viewer offers the raw download instead"
(api.py:2307-2308) — that half is unimplemented. This is precisely the
"quiet dishonesty" invariant 4 guards.

**Fix direction:** add `tooLarge?: boolean; size?: number` to `WaveformData`
and, in `WaveArtifact`/`WaveformViewer`, branch on `data.tooLarge` to render
an honest "waveform too large to render (N MB) — download instead" state
(mirroring `CodeArtifact.tsx:174`'s `file.tooLarge` branch), with a link to
the raw `/waveform/...` (or a file-download) route. No backend change needed.

### F2 — LOW/INFO — account-auth `model/list` adds one RPC to every cold Codex spawn (TTFT)
**File:** `src/agents/codex/codex_engine.py:353` inside `spawn_worker`.

`_fetch_allowed_models` issues `codex.models()` on every cold bring-up under
account auth, before `thread_start`/`thread_resume`. The warm pool exists to
kill TTFT (~8.5 s cold). This adds one round-trip to the cold path only
(BYOK returns immediately at :420; warm hits reuse the cached
`worker.allowed_models` and never re-call — verified: `stream_turn` passes
`worker.allowed_models` at :511, not a re-fetch). Marginal vs the existing
cold cost and correct by design — flagging only so it's a conscious trade.
**Not a bug.**

### F3 — LOW — recursive `/waveforms` walk does not prune `sim_runs`/`synth_runs` (intentional) — perf note only
**File:** `api.py:2270-2282`.

The walk prunes `__pycache__`, `node_modules`, dotdirs, but deliberately
**not** `sim_runs`/`synth_runs` (that's where the VCDs live — correct, and
documented in the docstring). On a workspace with many run dirs this is O(all
files); it runs off-thread (`asyncio.to_thread`) and this legacy endpoint is
bypassed by the v2 tab model, so impact is negligible. Read-only confirmed:
plain `os.walk` + `os.path.relpath`, no row materialization (invariant 8
respected). `os.walk` does not follow symlinked dirs (`followlinks=False`),
so the walk cannot escape the workspace. **No action needed.**

---

## Items verified correct (no findings)

- **#1 (be28dff) — account-auth model gate.** Fail-safe confirmed:
  `_fetch_allowed_models` returns `None` on non-callable `models`, any
  exception, or empty result (codex_engine.py:422-452); `_effective_model`
  passes the picked id **only** when `turn.api_key` (BYOK bypass, :407) OR
  `model_name in allowed_models` (:409), else omits → account default. No
  path lets an unknown id reach the SDK under account auth (the 0-token
  trap). **Tenant isolation intact:** `allowed_models` is fetched per worker
  from that worker's own account-authed client and stored on the `WarmWorker`
  (codex_warm.py:83), which is keyed by `(session_id, thread_id, user_id)`
  with `account_home` baked into the fingerprint (codex_warm.py:51-65) — no
  cross-account key path exists, so one account's allowed set can never serve
  another. Per-turn model changes are honored: `stream_turn` recomputes
  `_thread_kwargs(..., worker.allowed_models)` with the *current* turn's
  `model_name` each turn (:511). List-shape parsing handles bare list / `.data`
  / `.models` / dict wrappers and skips `hidden` entries. `sys` is imported
  (line 19). Solid.
- **#5 (5d81d12) — PATCH model validation.** `_KNOWN_MODEL_IDS` = CATALOG ∪
  CODEX_CATALOG ∪ PRICING keys (api.py:1304-1308), computed at import (static
  inputs). `normalize_model_name` runs **first** (api.py:1328), so every
  alias target (`gemini-3.5-flash`, `gemini-3.1-flash-lite`) — all present in
  the set — validates. Empty/`""` → `DEFAULT_MODEL` (model_catalog.py:114-118)
  → in set (no false 422 on a clear). Previous-gen ids stay pinnable via
  PRICING (`gpt-5.4`, `claude-opus-4-6`, …). No valid id 422s; no invalid id
  passes. Correct.
- **#2 (35eb1d2) — Thinking heuristic.** `isThinkingBlock` removed; `text`
  blocks now always render via `MarkdownContent`, only the dedicated
  `reasoning` block type collapses into the toggle
  (MessageList.tsx BlockView). Each block renders exactly once by type — no
  double-render, no empty-render regression. Matches the plan (reasoning
  arrives as `reasoning` blocks). Correct.
- **#3 backend cap (eba83ff).** Cap checked before `VCDVCD` load; 25 MB is
  sane for KB–MB sim VCDs; `os.path.getsize` in a guarded `try/except OSError`
  (→ size 0, parses). Only the *frontend* half is missing (F1).
- **#4 read-only/traversal (e6392c7).** See F3 — safe.
- **#7 (227347b) — WaveArtifact fallback + tab-key migrate.** Fallback
  renders a **cached** waveform (real held data) with an honest
  "no longer listed — cached waveform" note (WaveArtifact.tsx:44-55); when
  nothing is cached it falls through to the honest "isn't in the run list"
  empty state (:57-67) — no crash/blank on a genuinely-missing VCD. It does
  **not** attempt a bogus `wavefile:` re-fetch from a bare runId (the commit
  correctly notes the filename can't be reconstructed). persist `migrate`
  v1→v2 is guarded per-shape (never throws → persist won't drop all tabs) and
  dedups remapped keys. Correct.

## Gate note

Not re-run (read-only review; per the task, backend has ~11-13 image-specific
env-gap failures that also fail on base `endgame`, and frontend is green).
F1 is not covered by any existing test — a `WaveformViewer`/`WaveArtifact`
test feeding a `tooLarge` payload should accompany its fix.
