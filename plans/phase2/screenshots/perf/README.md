# Slow-UI perf fix — before/after (F1, F6, F4, F5, F7)

Implements `plans/phase2/PERF_SLOW_UI_BRIEF.md`. Hosted-only behavior; self-host
is unchanged (no sync, no GCS) and covered by tests.

## Mechanism-level before → after (what the tests measure)

| | Before | After |
| --- | --- | --- |
| **F1** read-only GET (`/manifest`, `/runs`, `/runs/{id}`, `/jobs/{id}`, `/lint`) | re-tar + **upload** the whole workspace on every read (`run_scoped` synced unconditionally) — tens of seconds post-synth, and a stale read could clobber a concurrent write | `mutates=False` reads **never sync**; only the 7 write endpoints upload. Verified: reads never sync, writes sync once, self-host (no sync) unchanged |
| **F6** blocking I/O | hydration (GCS download+untar), `os.listdir`, file reads, VCD parse ran **on the event loop** — one slow call stalled every request | offloaded via `asyncio.to_thread` (action `require_workspace` + the sync; all api.py workspace GET handlers). Verified: two concurrent reads that block ~0.4s each finish in ~0.4s (overlap), not ~0.8s (serialized) |
| **F4** open fan-out | `refreshWorkspace()` fired **twice** on open (selectSession + mount) × ~18 calls, **each a separate GCS download** → ~10.1s | one **snapshot** `GET /workbench` hydrates **once** and returns manifest+runs+files+spec+code+report; store **single-flight** dedups every trigger; the double load is removed. Verified: snapshot resolves the workspace once (not ~18×), one load per open, concurrent callers share one fetch |
| **F5** synth polling | **two** loops each re-pulled/uploaded the workspace every few seconds → sustained "minutes" | `loadRuns`/`loadWorkbench`/`refreshWorkspace` single-flight → overlapping polls share one fetch; with F1 they no longer upload. Verified: two concurrent `loadRuns` share one call |
| **F7** cold start | first read after an instance spins up paid a full cold download on the loop | workspace prewarmed **once on WS connect** (off-thread); Cloud Run `session_affinity=true` (+ existing `startup_cpu_boost`; `backend_min_instances=1` to keep one warm) |

Out of scope (follow-ups, per the brief): **F3** (skip re-download when the
object generation is unchanged — removes the remaining per-read download) and
**F8** (per-artifact object keys instead of one tarball — retires this class of
problem). **F2** (explicit per-session lock) is subsumed by the frontend
single-flight + F1.

## Live (hosted) capture — deploy-time

The real numbers need a hosted deploy with a **post-synth workspace (big GDS)** —
there's no GCS/Cloud Run in CI. On the deployed app, capture here:

1. **Open timing**: DevTools Network, open a post-synth session. Was ~10s → target
   < ~2s. Save `open-before.png` / `open-after.png` (or a HAR).
2. **During synth**: the UI stays responsive (no "minutes" of lag). Save
   `synth-responsive.png`.
3. **No upload on read**: backend logs show **no** workspace `sync`/`put_tree` on
   GET requests (only on writes). Save `no-sync-on-read.png`.
