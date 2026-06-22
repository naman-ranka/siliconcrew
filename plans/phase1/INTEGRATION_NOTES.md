# Phase 1 → Phase 2 Integration Notes

Authored at the end of Phase 1 (frontend + thin action API) to make merging with
the Phase 2 (deployed multi-tenant backend) branch safe. Scope below is **only
my Phase 1 changes** (commits `46250c7..HEAD`, parent `6240270` = the Phase 0
bridge). Field names follow `plans/phase0/data-model.md` (camelCase).

---

## 1. Shared files I changed — what & why

### `src/utils/session_context.py` — **NOT changed in Phase 1**
I depend on it but did not edit it. The Phase 0 bridge (commit `6240270`) added
it. I rely on this exact API: `SessionContext(session_id, workspace, user_id=None)`,
`session_scope(ctx)` (contextmanager), `set_current_session`/`reset_current_session`,
`get_current_session`/`current_workspace`, and the `WorkspaceProvider` /
`LocalWorkspaceProvider` protocol. **Phase 2 owns the evolution of this file;**
keep these names stable or update both call sites (`wrappers.get_workspace_path`
and `actions.run_scoped`).

### `api.py` (+146 / −24)
- Imports: added `session_scope`, `manifest_mod`, and
  `from src.api.actions import build_actions_router`; trimmed the action helpers
  back out (they live in the router now).
- **Mounts the action layer:** `app.include_router(build_actions_router(session_manager.get_workspace_path))`.
- `GET /api/workspace/{id}/files`: now annotates each file with its manifest
  `role` (reads the manifest inside a `session_scope`).
- `GET /api/workspace/{id}/waveform/{path}`: **rewrote the parser** to preserve
  hierarchy — per-signal `scope`, `full_name`, `width`, `isBus`, `valuesStr`,
  `xFlags`, plus top-level `timescale`, `unitSeconds`, `signalCount`.
- Added `GET /api/workspace/{id}/layout/{filename}`: best-effort GDS→SVG (uses a
  pre-rendered `<file>.svg` sidecar, else gdstk with a polygon cap, else a
  structured `{error,…}`). Degrades gracefully when gdstk/ORFS are absent.
- Did **not** touch the WebSocket chat handler's existing `set_current_session`
  binding (Phase 0).

### `src/api/__init__.py` — new, empty (package marker).

### `src/api/actions.py` — **new, 518 lines.** The Phase 1 action layer.
A standalone `APIRouter` built by `build_actions_router(resolve_workspace)` with
**no dependency on the agent stack** (LangGraph/LangChain). Every handler is a
thin wrapper over a SiliconCrew tool function; the same functions back the
agent's `@tool`s, so there is one action layer. Request-scoping via `run_scoped`
(see §3). Uniform `{ok:…}` envelope. This is the file most likely to overlap
Phase 2 — it is deliberately self-contained and provider-injected to make the
swap mechanical.

### `src/tools/manifest.py` — **new, 341 lines.**
The `DesignManifest` (Pydantic) + deterministic role derivation + top inference
(synthTop = RTL hierarchy **root**, preferring the TB's DUT; simTop = TB top) +
persistence to `workspace/manifest.json` + reconciliation against files on disk +
`files_for_stage(manifest, stage)` (lint = rtl+include, simulate = rtl+tb+include,
synthesize = rtl+sdc).

### `src/tools/sim_manager.py` — **new, 360 lines.**
Isolated simulation runs mirroring the synth run model: `sim_runs/sim_NNNN/` with
its own VCD + `run_meta.json` + provenance. Entry point
`run_sim_isolated(workspace, verilog_files, top_module, mode=…, run_id=…,
platform=…, sim_profile=…, pass_marker=…, parent_run_id=…, _runner=run_simulation)`.
Also `list_sim_runs`, `get_sim_run`, `get_sim_run_dir`, `set_sim_run_pinned`.
Allocation is `threading.Lock`-guarded; **process-local** — see §4.

### `src/tools/file_ops.py` — **new, 49 lines.** Single source of truth for writes.
`write_file(workspace, path, content) -> {"path": rel, "bytes": int}` with a
path-traversal guard (`_safe_join`) + manifest reconcile. **Both** the REST save
action and the agent `write_file` tool route through it — the one chokepoint
where Phase 2's git-commit / history / object-storage write-back belongs.

### `src/tools/wrappers.py` (+89)
- New agent `@tool`s sharing the same functions as REST: `get_manifest`,
  `update_manifest`, `run_isolated_simulation` (manifest-driven).
- Refactored the existing `write_file` tool to call `file_ops.write_file`
  (was an inline open/write) — single write path.
- Added the new tools to `mcp_tools`. `get_workspace_path()` is **unchanged**
  (context → `RTL_WORKSPACE` → default).

---

## 2. Public contracts

### REST (all paths prefixed `/api/workspace/{session_id:path}`)
Envelope: success `{ "ok": true, … }`; error → HTTP 4xx/5xx with body
`{ "ok": false, "error": { "code", "message", "details" } }`.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/manifest` | — | `{ok, manifest: DesignManifest}` |
| PUT | `/manifest` | `ManifestUpdate{synthTop?,simTop?,clockPeriodNs?,platform?,files?:[{name,role}]}` | `{ok, manifest}` |
| POST | `/files` | multipart `files[]` | `{ok, uploaded:[name], manifest}` |
| PUT | `/code/{filename:path}` | `{content}` | `{ok, saved, manifest}` |
| POST | `/lint` | — | `{ok, status:"passed"|"failed", warnings[], errors[], byFile, command, files[]}` |
| POST | `/simulate` | `{simTop?, mode?:"rtl"|"post_synth", runId?}` | `{ok, run: SimRun}` |
| POST | `/synthesize` | `{synthTop?,platform?,clockPeriodNs?,utilization,aspectRatio,coreMargin,runEquiv,constraintsMode}` | `{ok, jobId, runId, raw}` |
| GET | `/runs?kind=all\|sim\|synth` | — | `{ok, runs: Run[]}` (newest first, lineage) |
| GET | `/runs/compare?a=&b=` | — | `{ok, diff: PpaDiff}` |
| GET | `/runs/{runId}` | — | `{ok, run}` (sim meta, or synth stages+ppa) |
| GET | `/jobs/{jobId}` | — | `{ok, job}` (synth job status passthrough) |
| POST | `/runs/{runId}/retry` | `{fromStage,maxStage?,overrides?}` | `{ok, jobId, runId, raw}` |
| POST | `/runs/{runId}/pin` | `{pinned}` | `{ok, runId, pinned}` |

Changed existing read endpoints (shapes Phase 2 must preserve):
- `GET /files` items gain `role?: "rtl"|"tb"|"sdc"|"include"|"other"`.
- `GET /waveform/{path}` new shape (see §1 / data shapes).
- Added `GET /layout/{filename}` → `{svg, cell_name, cached?}` or `{error,message,cell_name}`.

### `file_ops.write_file(workspace: str, path: str, content: str) -> dict`
Returns `{"path": <workspace-relative>, "bytes": int}`; raises `ValueError` if
`path` escapes the workspace. Reconciles the manifest for `.v/.sv/.vh/.svh/.sdc`.

### Data shapes (camelCase; mirrored in `frontend/types/index.ts`)
- **DesignManifest**: `{sessionId, files:[{name, role, path}], synthTop, simTop, clockPeriodNs, platform}`.
- **SimRun** (a `Run` with `kind:"sim"`): `{id:"sim_NNNN", kind, status:"passed"|"failed"|"running", createdAt, top, pinned, parentRunId?, provenance:{repoCommit,iverilogVersion,orfsImageDigest,pdk,numCores}, mode, vcdPath, passMarkerFound, failure?:{type,firstFailureLine,timeNs}, compileCommand, simCommand, simStatus, stdoutTail, stderrTail, logTruncated}`.
- **SynthRun** (unified mapper in `actions._synth_to_run`): `{id:"synth_NNNN", kind:"synth", status, createdAt, top, pinned, parentRunId?, provenance:{pdk}, platform, elapsedSec, ppa?:{areaUm2,cells,wnsNs,tnsNs,fmaxMhz,powerMw}, reportAvailable, autoChecks}`.
- **PpaDiff**: `{a, b, rows:[{metric, a, b, deltaPct?}]}`.
- **LintResult**: `{status, warnings:[{file,line,severity,message}], errors:[…], byFile:{file:[…]}, command, files}`.
- Waveform: `{filename, endtime, timescale, unitSeconds, signalCount, signals:[{name, full_name, scope, width, isBus, times[], values[], valuesStr[], xFlags[]}]}`.

### Frontend surface (Phase 2 usually doesn't touch, but for completeness)
- `frontend/types/index.ts`: the TS mirrors above.
- `frontend/lib/api.ts`: `workbenchApi` (manifest/files/saveCode/lint/simulate/
  synthesize/listRuns/getRun/getJob/pinRun/compareRuns) + `workspaceApi.getLayout`.
- `frontend/lib/store.ts`: the workbench Zustand slice (manifest, runs,
  console, actions).

---

## 3. Request-scoping (THE likely conflict with Phase 2)

**My mechanism, exactly** (in `src/api/actions.py`, inside `build_actions_router`):

```python
def require_workspace(session_id) -> str:
    ws = resolve_workspace(session_id)          # injected; Phase1 = session_manager.get_workspace_path
    if not ws or not os.path.exists(ws): raise HTTPException(404)
    return ws

async def run_scoped(session_id, workspace, fn, *args, **kwargs):
    ctx = SessionContext(session_id=session_id, workspace=workspace)
    def runner():
        with session_scope(ctx):                # sets the _current contextvar
            return fn(*args, **kwargs)
    return await asyncio.to_thread(runner)      # copies the contextvar into the worker thread
```

- Tools resolve the workspace via `wrappers.get_workspace_path()` →
  `current_workspace()` (the contextvar) first. So inside `run_scoped`, any tool
  call is bound to this request's workspace.
- **Belt-and-suspenders:** I also pass `workspace=` explicitly to the heavy tools
  (`run_sim_isolated`, `start_synthesis_job`, `run_linter(cwd=…)`), so correctness
  does not *solely* depend on the contextvar — handy if Phase 2 dispatches via a
  primitive that doesn't copy context.
- **Provider injection:** the router takes `resolve_workspace(session_id) -> path`.
  Phase 1 passes `session_manager.get_workspace_path`; Phase 2 passes a
  cloud-backed resolver — **no handler changes**.

**Reconciling with Phase 2's `run_in_session` / `session_request_scope`:** both
sides set the *same* `SessionContext` contextvar from `session_context.py`, so
the seam is already shared. To collapse into ONE mechanism:
1. Make `build_actions_router` accept a **`WorkspaceProvider`** (or an
   async-capable scope helper) instead of a raw `resolve_workspace`.
2. Replace my `run_scoped` body with Phase 2's `session_request_scope` /
   `run_in_session` so off-thread dispatch + context copy + (their) staging and
   write-back are centralized. The handlers call it identically — only the helper
   changes. If Phase 2's helper is `async with session_request_scope(session_id) as ws:`
   then each handler becomes `async with ...: await asyncio.to_thread(...)` with
   the scope active; keep the `to_thread` for blocking EDA work.
3. Keep `get_workspace_path()`'s resolution order; ensure the context is **always**
   set in the deployed path so the `RTL_WORKSPACE`/default fallback can never leak
   across tenants.

Recommendation: **adopt Phase 2's scope helper as canonical** and delete my
`run_scoped`, since Phase 2 also needs to stage/persist workspaces (object
storage), which my local version doesn't do.

---

## 4. Assumptions / stubs / deferrals (a multi-tenant backend may change)

- **Local filesystem workspace.** Tools write directly into the workspace dir:
  `manifest.json`, `sim_runs/sim_NNNN/` (+ VCD, run_meta.json), `synth_runs/…`.
  A run assumes a **stable local path for its whole lifetime**. Phase 2 must
  stage the workspace to local scratch before a run and persist artifacts back
  after (object storage), keyed by `session_id`.
- **Process-local run registries.** `sim_manager` allocates run ids by scanning
  the dir under a `threading.Lock` (single process). `synthesis_manager` keeps an
  in-process job dict + `ThreadPoolExecutor`. Across multiple backend
  workers/pods these are **not shared** — Phase 2 needs a shared job/run store
  (or sticky routing) if it scales horizontally.
- **Provenance from the host:** `repoCommit` = `git rev-parse HEAD` in the
  server cwd; `iverilogVersion` = local `iverilog -V`. In prod these reflect the
  runner image, which is the intent — just be aware they're host-derived.
- **Synth pin** writes `pinned` into the run's `run_meta.json` (no dedicated
  synth-pin store existed); the unified runs mapper reads it back.
- **Manifest is one file, last-write-wins.** Fine for one user per session;
  concurrent writers to the same session could race.
- **No auth/quotas.** `resolve_workspace` trusts the `session_id` path segment.
  Phase 2 must authorize the caller for that session before resolving.
- **Deferred (env-limited here):** real ORFS synthesis (Docker absent → synth
  fails fast and reports it), full GDS→SVG render, post-synth gate-level sim
  verification, file rename/delete, and an agent-parity E2E (needs a model API
  key). See `plans/phase1/SCENARIOS.md` for the boundary notes.

---

## 5. How to run + how to test

**Run (local):**
```bash
# system + python deps
apt-get install -y iverilog            # real lint/sim/waveform need this
pip install fastapi "uvicorn[standard]" aiosqlite python-dotenv pyyaml vcdvcd \
            httpx python-multipart pytest langchain-core langgraph langgraph-checkpoint-sqlite
# backend (note --app-dir so `api:app` imports from the repo root)
RTL_DATA_DIR=/tmp/sc-data python -m uvicorn api:app --app-dir <repo> --host 127.0.0.1 --port 8000
# frontend (proxies /api -> :8000)
cd frontend && npm install && npm run dev      # http://localhost:3000/workbench
```

**Test:**
- Backend unit/API (no browser): `pytest tests/test_manifest.py
  tests/test_sim_isolation.py tests/test_actions_api.py tests/test_file_ops.py`.
  The action API is testable **without the agent stack** — mount
  `build_actions_router(resolve)` on a bare `FastAPI()` with a temp-dir resolver
  (see `tests/test_actions_api.py`).
- **Real EDA flows** (need `iverilog`): `pytest tests/test_real_flows.py`
  (auto-skips if iverilog is absent). Covers single/multi-module, lint/sim/compile
  failures, no-pass-marker, real VCDs.
- Frontend Tier-1: `cd frontend && npm run test` (Vitest/jsdom).
- Frontend Tier-2: `npx playwright install chrome` then `npm run e2e`
  (mock-backed flow; `file:` is blocked — serve over HTTP).
- Tenant isolation: `tests/test_actions_api.py::test_concurrent_sessions_are_workspace_isolated`
  and `tests/test_session_context_propagation.py` (Phase 0).
