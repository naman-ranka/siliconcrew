# API Contract (frozen)

The interface between the frontend (Phase 1) and the tool/backend layer. Both
workstreams code against this. Shapes are the contract; field names are stable.

## Rules

1. **Action endpoints call SiliconCrew tools, never raw EDA tools.** The tool is
   the single source of truth and already returns the exact command it ran.
2. **One action layer.** Each action endpoint is a thin handler over the same
   function the agent calls as a `@tool`. Factor any JSON-stringify into the
   agent wrapper only; `run_simulation`/synthesis functions return dicts the
   handler returns directly.
3. **Every request carries a session.** The handler resolves the workspace via
   `session_scope(SessionContext(session_id, workspace))` — never the global
   env var (see Phase 0 README).
4. **Long actions are async + polled.** Sim is usually fast (sync OK); synth is
   minutes (job + poll, mirroring the existing synth job model).
5. **Uniform error envelope** (below) on every endpoint.

## Error envelope

```json
{ "ok": false, "error": { "code": "string", "message": "human readable", "details": {} } }
```
Success responses set `"ok": true` and carry the typed payload.

## Read endpoints (already exist in api.py — keep shapes)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/sessions` | session list |
| GET | `/api/workspace/{id}/files` | files (extend with `role`, see data-model) |
| GET | `/api/workspace/{id}/code/{filename}` | file content |
| GET | `/api/workspace/{id}/spec` | spec / manifest |
| GET | `/api/workspace/{id}/waveforms` | waveform list (extend: per-run) |
| GET | `/api/workspace/{id}/synthesis-runs` | synth runs (generalize → `/runs`) |
| GET | `/api/workspace/{id}/report` | PPA report |
| GET | `/api/workspace/{id}/layouts`, `/schematics` | artifact lists |

## NEW: the design manifest

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/api/workspace/{id}/manifest` | `DesignManifest` (see data-model.md) |
| PUT | `/api/workspace/{id}/manifest` | upsert manifest (roles, tops, clock, platform) |
| POST | `/api/workspace/{id}/files` | upload file(s); server auto-tags `role`, returns manifest |

## NEW: action endpoints (the IDE-first buttons)

Each maps 1:1 to an existing tool. Request bodies are derived from the manifest
where possible (so the UI usually sends just the action, not the file list).

### Lint
```
POST /api/workspace/{id}/lint
  → { "ok": true, "status": "passed|failed", "warnings": [...], "errors": [...],
      "byFile": { "decoder.v": [ {line, severity, message} ] },
      "command": "iverilog -tnull ..." }
```

### Simulate (sync; returns a run record)
```
POST /api/workspace/{id}/simulate
  body: { "simTop": "cpu_tb", "mode": "rtl|post_synth", "runId?": "synth_0002" }
  → SimRun  (see data-model.md): includes status enum, vcdPath, failure info,
            compileCommand, simCommand, and the run id (sim_0004)
```
Wraps `run_simulation(...)`. **Phase 1/2 must add per-run isolation** so each
sim gets `sim_runs/sim_NNNN/` and its own VCD (today sims run in `cwd` and VCDs
collide — see data-model.md).

### Synthesize (async job + poll)
```
POST /api/workspace/{id}/synthesize
  body: { "synthTop": "cpu_top", "platform": "sky130hd", "clockPeriodNs": 10.0, ...overrides }
  → { "ok": true, "jobId": "...", "runId": "synth_0003" }

GET  /api/workspace/{id}/runs/{runId}        → SynthRun (status, stages, ppa, artifacts)
GET  /api/workspace/{id}/jobs/{jobId}        → { state, stage, progress }
POST /api/workspace/{id}/runs/{runId}/retry  body: { "fromStage": "route", overrides }
```
Wraps `synthesis_manager` (already has jobs, snapshots, staged retry, index).

### Unified runs + compare
```
GET  /api/workspace/{id}/runs?kind=all|sim|synth   → Run[]  (newest first, with lineage)
GET  /api/workspace/{id}/runs/compare?a=synth_0001&b=synth_0002 → PpaDiff
POST /api/workspace/{id}/runs/{runId}/pin          body: { pinned: true }
```

## Agent path (unchanged, shares the tools)

`WS /api/chat/{id}` streams the LangGraph agent. The agent calls the same tool
functions. The only change: the handler sets the session context (README).

## Streaming / progress

Synth progress and agent tokens stream over the existing WebSocket. Action
endpoints may also emit run/stage updates the UI subscribes to. Keep one event
shape: `{ "type": "run_update", "runId", "stage", "status", ... }`.
