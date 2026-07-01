# Workbench Performance — Findings & Ranked Fixes

Measurements taken against the deployed backend with a signed-in bearer token, session `p1_seq_detector_0011`, 2026-07-01.

## TL;DR

The reported root cause is **confirmed and refined**. Every per-session workspace request materializes the *entire* session as one `.tar.gz` in GCS. Read-only GETs on the actions router (`/manifest`, `/runs`, `/runs/{id}`, `/runs/compare`, `/jobs/{id}`) additionally **re-tar and re-upload the whole workspace on exit** via `run_scoped`'s `finally: sync_workspace(...)`. That upload is the dominant cost (~3.0s here, and it scales with total workspace size — after a synth with ORFS/GDS artifacts it becomes tens of seconds to minutes) and it is the part that **serializes** (tar step is GIL-bound Python). Downloads are cheap and parallelize fine.

Two frontend behaviors multiply it: a **double `refreshWorkspace`** on open, and **two independent polling loops** during a synth that each re-pull (and via the read-GETs re-upload) the whole workspace every few seconds. That is the "network APIs take minutes."

### Steady-state measurements (warm instance)

| Endpoint | Code | Downloads? | Uploads? | Measured |
|---|---|---|---|---|
| `/api/health` | `api.py:1702` | no | no | 0.59s |
| `/api/workspace/<sid>/files` | `api.py:1283` | yes | **no** | 0.75s |
| `/api/workspace/<sid>/synthesis-runs` | `api.py:1521` | yes | **no** | 0.70s |
| `/manifest` GET | `actions.py:280` | yes | **yes** | 3.67–3.78s |
| `/runs?kind=all` GET | `actions.py:445` | yes | **yes** | 3.61–3.88s |
| `/jobs/<id>` GET | `actions.py:545` | yes | **yes** | 3.99s |

Derived: download+untar ≈ 0.70–0.75s; **upload (sync) ≈ 3.0s** — ~4× the download, and it's what serializes.

### Concurrency / serialization measurements

| Scenario | Wall | Interpretation |
|---|---|---|
| 3× `/manifest` sequential | 11.1s | baseline |
| 3× `/manifest` parallel | **9.7s** | ≈ serial → uploads do NOT parallelize |
| 5× `/synthesis-runs` parallel (download-only) | **1.6s** | downloads DO parallelize |
| burst {files, manifest, runs} parallel | 7.2s | two uploads serialize (~3.7+3.7) |
| cold-open fan-out (16 downloads + manifest + runs) | **10.1s** | one workbench open |

Serialization is **not** a per-session lock and **not** Cloud Run `containerConcurrency` (unset in `deploy/terraform/main.tf:231-236`, defaults to 80; the service is 2 vCPU / 2Gi). It is the CPU/GIL-bound `tar+gzip` in `put_tree` (`_tar_dir_to_bytes`) plus blocking I/O on the asyncio event loop in `api.py` (F6). Skipping the upload on reads removes read serialization entirely.

---

## Findings (ranked by impact ÷ effort)

### F1 — [P0] Read-only GETs re-upload the entire workspace (biggest win)
- **Where:** `src/api/actions.py:250-276` — `run_scoped`, the `finally: sync_workspace(session_id)` at `271-276`. Reached by every actions GET: `get_manifest` (`:280`), `list_runs` (`:445`), `compare_runs` (`:462`), `get_run` (`:494`), `get_job` (`:545`).
- **Cost:** ~3.0s/call now (measured), and **grows with workspace size** — `put_tree` tars the whole scratch incl. `synth_runs/` (ORFS logs, GDS, reports). After a tape-out the tarball is tens–hundreds of MB → a single read GET takes tens of seconds to minutes. This is the concrete "minutes" path.
- **Root cause:** `run_scoped` was built for mutations (sim/synth/save) and unconditionally persists on exit; it's (mis)used for pure reads.
- **Correctness/data-loss (also P0):** a read re-uploads local scratch, last-writer-wins on the whole tarball; if another instance/MCP/second tab wrote meanwhile, a stale read-triggered upload silently clobbers it.
- **Fix:** don't sync on reads. Add `mutates: bool = False` (or a `run_read` helper) and only `sync_workspace` for true mutations: `put_manifest`, `upload_files`, `save_code`, `lint`(if it writes), `simulate`, `synthesize`, `retry_run`, `pin_run`. ~10 lines.
- **Impact:** the five read endpoints drop 3.7s→~0.7s, read concurrency stops serializing, and it directly fixes the synth-poll amplifier (F5, `getJob` is a read). **Risk:** low — audit that each real mutation still syncs (list above is complete).

### F2 — [P0, correctness] Concurrent requests share one scratch dir → torn/lost writes
- **Where:** `src/platform_engines/workspace_provider.py:150-160` (`CloudWorkspaceProvider.workspace_for`/`sync`). One scratch dir + one monolithic `.tar.gz` per session.
- **Failure:** two concurrent same-session requests (trivially produced by the frontend's own fan-out): A's `sync` runs `_tar_dir_to_bytes` over the dir while B's `workspace_for` is mid-`extractall` into it → A uploads a torn tree, or B's write is lost when A wins. Whole-tarball last-writer-wins loses any concurrent writer's changes.
- **Fix:** (a) per-session `asyncio.Lock`/file lock around stage-in/sync; (b) upload with GCS `if_generation_match` + retry-on-conflict; (c) strategic fix is F8. **Risk:** medium — scope the lock per session so it doesn't re-serialize; largely mitigated once F1 removes read-uploads.

### F3 — [P1] No download cache/generation guard — every request re-downloads the whole tarball
- **Where:** `workspace_provider.py:150-156` (`workspace_for` always `get_tree` when blob exists) and `:117-122` (`get_tree` → `download_as_bytes` + full untar, unconditional).
- **Cost:** ~0.7s/call even when scratch is warm & unchanged. Cold open triggers ~16 → ~11s of redundant re-download+re-untar.
- **Fix:** guard by GCS object generation/etag — keep `{session_id: generation}`, do a cheap `blob.reload()` (metadata HEAD ~30–50ms) and skip download+untar if unchanged. Turns 16 downloads into 1 download + 15 HEADs. **Risk:** medium — must bump recorded generation on our own uploads.

### F4 — [P1] Frontend fan-out on open: double `refreshWorkspace` + heavy `loadWorkbench`
- **Where:** `Workbench.tsx:76-94` calls `selectSession(list[0])` **and then** `loadWorkbench()`; `store.ts:405-410` `selectSession` already calls `refreshWorkspace()`; `store.ts:1072-1074` `loadWorkbench` = `Promise.all([loadManifest, loadRuns, refreshWorkspace])` → **second** `refreshWorkspace`; `store.ts:848-887` `refreshWorkspace` fires 5 list endpoints (`/files`,`/waveforms`,`/layouts`,`/schematics`,`/synthesis-runs`) then up to 3 more (`/spec`,`/code`,`/report`) — **each independently downloads the whole tarball** via `_resolve_workspace`.
- **Cost:** cold open ≈ 2×refreshWorkspace (up to 16 downloads) + manifest (dl+ul) + runs (dl+ul) ≈ **~18 heavy calls, 2 uploads**. Measured fan-out **10.1s** (+~3.5s on true cold start, F7).
- **Fixes:** (1) drop the redundant second `refreshWorkspace` — `loadWorkbench` should fetch only manifest+runs (or gate on already-loaded). (2) Collapse the 5 lists into 1: `/files` already returns typed `FileInfo[]` (`api.py:1283-1329`) — derive waveforms/layouts/schematics/hasSpec/hasCode from it instead of 4 extra whole-tarball downloads. (3) Add request dedup/caching — none exists today (`api.ts:39-63,238-249` are bare `fetch`, no SWR/react-query, no in-flight map); add an in-flight promise map keyed by URL + short TTL. **Risk:** low.

### F5 — [P1] Two concurrent polling loops during synth re-pull/re-upload the whole workspace
- **Where:** `useWorkbenchSync.ts:29,71-74` polls every `POLL_MS=5000` while any run is non-terminal → `loadWorkbench()` (manifest dl+ul, runs dl+ul, refreshWorkspace ~8 dl). Concurrently `store.ts:1296-1343` `runSynth` polls `getJob` every 3s→30s; `getJob` is a read GET that (pre-F1) does dl+ul (**measured 4.0s** for a bogus id).
- **Cost:** both loops run at once; workspace grows during synth so uploads balloon → dozens of full-tarball transfers/min → "minutes."
- **Fixes:** (1) F1 makes `getJob` a ~0.7s read. (2) Read job status without staging the full tree (F8). (3) In `useWorkbenchSync`, during an active synth don't run heavy `loadWorkbench` — poll only `/runs` (or `/jobs/{id}`), back off to ≥15–30s, and pause the sync poll while `runSynth`'s own poll is live (the two watch the same thing). **Risk:** low.

### F6 — [P1] Blocking I/O on the asyncio event loop in `api.py` workspace endpoints
- **Where:** every `/api/workspace/...` handler is `async def` yet does blocking work on the loop thread: `_resolve_workspace`→`workspace_for`→GCS `download_as_bytes`+untar (`api.py:1286,1335,1369,1411,1524,1534,1579,1602,1648,1658`), plus `os.listdir`/`os.walk`/`open().read()`, and the synchronous VCD parse in `get_waveform_data` (`api.py:1430-1513`). The actions router correctly offloads via `asyncio.to_thread` (`actions.py:270`); these do not.
- **Effect:** blocking in an `async def` stalls the single event loop → blocks all in-flight requests (process-wide serialization on top of F1). Explains why 5 parallel downloads took 1.6s not ~0.7s, and why one VCD parse / GDS render freezes the whole API.
- **Fix:** make these handlers plain `def` (FastAPI threadpools them) or wrap blocking sections in `run_in_threadpool`. **Risk:** low.

### F7 — [P2] Cold-start amplification: GCS client + scale-to-zero
- **Where:** `workspace_provider.py:98-103` (`storage.Client()` constructed lazily on first use); `deploy/terraform/main.tf:227-235` (`min_instance_count` → scale-to-zero if 0).
- **Cost:** first request to a cold instance pays client construction + metadata-server auth (~3.5s; matches "`/files` 4.4s first, 0.8s repeat").
- **Fix:** pre-warm in FastAPI `lifespan` (`api.py:304-347`) — touch `get_workspace_provider()._bucket()`; consider `backend_min_instances >= 1`. `startup_cpu_boost` is already on. **Risk:** low.

### F8 — [P2, strategic] Monolithic per-session tarball is the structural root cause
- **Where:** `workspace_provider.py:35-41,105-122,144-160` — one `.tar.gz`/session; both directions scale with total size, not need/delta. Every finding above is a symptom of "the unit of transfer is the whole workspace." Note `deploy/RUNBOOK.md:210` suggests `containerConcurrency=1` as a workaround — **do not** apply it; it serializes the whole service and causes cold-start scale-out per concurrent request.
- **Fix (incremental):** per-artifact / per-run object keys (the run stager `make_run_stager`, `:180-195`, already does per-run keys). Reads fetch only what they need; job status reads a small index without staging the tree; writes upload only the changed object with a generation precondition (subsumes F2/F3). **Risk:** medium — touches the tools' POSIX assumption; stage lazily per accessed path.

### F9 — [P2] Inline GDS→SVG layout render on the request thread
- **Where:** `api.py:1593-1642` (`get_layout_svg`) renders with `gdstk` inline (≤2M polygons) on the event-loop thread when no sidecar exists (already prefers a cached `*.svg` sidecar at `:1610-1613`).
- **Fix:** render the sidecar once at synth completion (write `*.gds.svg` into the run dir so it rides the normal sync) and always serve cached; at minimum move the render off the loop (F6). **Risk:** low.

## Recommended execution order
1. **F1** (skip sync on read GETs) — first; removes ~3s from 5 endpoints, kills read serialization, fixes synth-poll.
2. **F4** (drop double refresh, collapse 5 lists→`/files`, dedup) — halves+ cold-open fan-out.
3. **F5** (polling narrow/backoff/dedupe loops) — fixes active-synth "minutes."
4. **F6** (unblock event loop).
5. **F3** (generation-guarded download) + **F7** (pre-warm client).
6. **F2** (per-session lock + generation precondition) — correctness.
7. **F8** (per-artifact keys) — strategic; retires F2/F3/F5's cause.
8. **F9** (layout SVG caching).

Do **not** adopt `containerConcurrency=1`.

Note: existing task list (#3 "fix redundant/sequential fetches", #4 "revalidate-on-focus + poll active runs") shows prior attempts, but the current code still has the double `refreshWorkspace`, the two un-deduped polling loops, and no request caching — so those items are not fully resolved.
