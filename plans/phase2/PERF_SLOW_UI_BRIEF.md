# Build brief — fix the slow hosted UI (reads that upload, and blocking I/O)

Work on `claude/integration-p1p2`. Honor `plans/phase0/ui-design-language.md` for
any UI. This is a **performance + correctness** fix, not a storage refactor.

## Why (plain)
On the hosted deployment the workbench is slow — ~10s to open a session, and
**minutes** of sustained lag during a synth — and there's a latent data-loss risk.
Measured root causes (see the perf analysis doc):

- **F1 (P0) — read-only GETs upload the whole workspace on exit.** `run_scoped`'s
  `finally` calls `sync_workspace()` **unconditionally** (`src/api/actions.py:271`),
  so `GET /manifest`, `/runs`, `/runs/compare`, `/runs/{id}`, `/jobs/{id}` each
  re-tar-and-upload the entire workspace. After a synth (GDS/ORFS artifacts) a
  single "list my runs" becomes tens of seconds to minutes. It's also a **data-loss
  risk**: a stale read's sync can clobber a concurrent write's object.
- **F6 (P1) — blocking work on the async event loop.** The `sync` in `run_scoped`'s
  finally runs on the loop (not off-thread), and the `api.py` workspace GET handlers
  are `async def` but call `_resolve_workspace()`→`workspace_for()` (blocking GCS
  download+untar), `os.listdir`, and VCD parsing directly. One slow call stalls
  **every** in-flight request.
- **F4 (P1) — frontend fires `refreshWorkspace()` twice on open** (selectSession
  already refreshes, then Workbench calls loadWorkbench→refresh) and fans out ~18
  heavy calls (each a full tarball download). Measured ~10.1s per open. (Prior
  tasks "fix redundant fetches" / "poll active runs" were NOT actually resolved —
  this is still in the code.)
- **F5 (P1) — two polling loops run during a synth**, each re-pulling/re-uploading
  the whole workspace every few seconds → the sustained "minutes."
- **F7 (medium) — cold start**: the first read after an instance spins up pays a
  full cold download.

## Scope of THIS brief
**Implement F1 + F6 + F4 + F5 + F7.** This eliminates the "minutes" and the 10s
opens with low risk and no storage change.

**Explicitly out of scope (follow-ups):**
- **F2** (explicit per-session lock) — largely subsumed by frontend single-flight +
  F1; add later if concurrent hydrations still race.
- **F3** (download cache / skip re-download when the object generation is unchanged)
  — strong optional add; include if cheap, else follow-up. Reads still *download*
  after F1; F3 removes the redundant re-download. Decide with the owner.
- **F8** (per-artifact object keys instead of one tarball) — the strategic refactor
  that retires this whole class of problem; separate, larger effort.

## Hard rule — local unchanged
All of this is hosted-only behavior. In self-host there is no `sync_workspace`
(None) and no GCS, so F1/F6/F7 are no-ops locally — but keep the code paths behaving
identically for self-host and add/keep a test that proves it.

## Slices

### Slice 1 — F1: stop uploading on reads (biggest win, ~10 lines)
- `run_scoped` must sync **only after a mutating action.** Add a `mutates: bool`
  param (default `False`); sync in `finally` only when `mutates` is True.
- Set `mutates=True` on the **write** endpoints only: `PUT /manifest`,
  `POST /files`, `PUT /code/{file}`, `POST /simulate`, `POST /synthesize`,
  `POST /runs/{id}/retry`, `POST /runs/{id}/pin` (anything that writes files/state).
  Leave all GET reads at `mutates=False` → **no upload.**
- `POST /lint` writes nothing persistent → treat as read (no sync) unless it
  produces a saved artifact; confirm.
- Correctness: safe because reads don't modify the workspace, so there is nothing to
  persist; and it removes the stale-read-clobbers-write hazard.

### Slice 2 — F6: get blocking I/O off the event loop
- Run `sync_workspace()` in `run_scoped`'s finally via `await asyncio.to_thread(...)`
  (it currently runs on the loop).
- In `api.py`, the workspace GET handlers must offload the blocking parts —
  `_resolve_workspace()`/`workspace_for()` (download+untar), `os.listdir`, file
  reads, and VCD parsing — via `asyncio.to_thread` / `run_in_executor`, so one slow
  hydration can't block other requests.
- Add a test asserting a slow hydration on one request does not stall a second
  concurrent request.

### Slice 3 — F4: kill the double-open refresh + collapse the fan-out
- Remove the duplicate `refreshWorkspace()` on open: `selectSession()`
  (`frontend/lib/store.ts`) already refreshes; `Workbench` mount then calls
  `loadWorkbench()` which refreshes again. Do it once.
- **Store-level single-flight**, keyed by session id, for `loadWorkbench()` /
  `refreshWorkspace()`: every caller (mount, selectSession, chat-complete, upload,
  manual) shares the same in-flight promise.
- **Recommended:** add a backend **snapshot endpoint** `GET /api/workspace/{sid}/workbench`
  that hydrates **once** and returns files + spec + code + runs + report in one
  response, replacing the ~18-call fan-out on initial load. (Pairs with F6's
  off-thread hydration.)

### Slice 4 — F5: dedupe the polling
- During a synth only **one** poll loop should run (today two do). Route polling
  through the same single-flight so a poll never overlaps a manual/mount refresh.
- With F1 done, polling reads no longer upload; ensure the poll uses the read
  (no-sync) path.

### Slice 5 — F7: warm the first read
- Prewarm the workspace hydration once on session open / WS connect so the first
  read isn't a cold full download. Optionally pair with Cloud Run **startup CPU
  boost** + **min-instances=1** + **session affinity** (Terraform / deploy config)
  so a user's requests hit a warm instance with scratch already materialized.

## Guardrails
- No storage refactor (F8) here; no change to tenancy/auth; no change to what reads
  *return* (correctness identical — reads still hydrate/download so they see writes
  from other instances; they just stop uploading and stop blocking the loop).
- Keep all tests green (backend pytest + frontend vitest).

## Verify
- **Backend pytest:** `run_scoped(mutates=False)` does NOT call `sync_workspace`;
  mutating endpoints DO. A slow hydration does not stall a concurrent request
  (F6). Self-host path unchanged (no sync, no GCS).
- **Frontend vitest:** one `refreshWorkspace` per open (not two); single-flight
  shares the in-flight promise; snapshot endpoint used on initial load.
- **Live (hosted), with a post-synth workspace (big GDS):** open a session (target
  < ~2s, was ~10s); during a synth the UI stays responsive (no "minutes"); a read
  no longer uploads (confirm via logs / no `sync` on GET). Screenshots + before/after
  timings under `plans/phase2/screenshots/perf/`.

## Deliver
Commit per slice on `claude/integration-p1p2`. Summary: reads no longer upload (F1),
blocking I/O moved off the loop (F6), one deduped refresh + snapshot endpoint (F4),
single polling loop (F5), warm first read (F7) — with before/after timings. Note
F2/F3 and the strategic F8 as follow-ups.
