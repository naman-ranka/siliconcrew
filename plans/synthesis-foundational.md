# Wave 9 — Foundational synthesis job model

Status: DRAFT (pending 2nd-agent review)

## Intent

One async contract for synthesis/PnR that behaves identically on localhost,
over MCP, and deployed — fundamental changes to bookkeeping and the tool
surface, NOT a rewrite of the synthesis engine.

## Invariants (what "foundational" means here)

1. **The run directory is the database.** `run_meta.json` + artifacts are the
   only authoritative state; process memory is a cache, never load-bearing.
2. **One key.** `run_id` (the durable folder name) addresses everything;
   the process-lifetime `job_id` is eliminated.
3. **One async contract.** dispatch → poll → read. Exactly one blocking
   convenience (`wait_for_synthesis`), defined as bounded polling, identical
   on every platform.
4. **The computer writes its own tombstone.** Terminal state is persisted
   durably by whoever did/observed the work; readers can declare a run dead
   by staleness, so no run is ever stuck at "running".
5. **The UI is a viewer, not an actor.** Actors (agent, MCP client, the USER
   via Refresh) call status; every call and every completion is an activity
   event; the UI updates from events, user gestures, and window focus — no
   autonomous polling loops.

## Locked constraints (user decisions)

- `run_synthesis_and_wait` is REMOVED.
- The ORFS invocation is UNCHANGED: full flow stays one
  `make -B DESIGN_CONFIG=…`; partial/retry flows keep their existing chained
  `do-<stage>` targets. Splitting the full flow per-stage is DEFERRED.
- The 7 report readers (`get_synthesis_metrics`, `read_stage_report`,
  `get_route_drc_summary`, `get_cts_summary`, `get_congestion_summary`,
  `compare_pd_runs`, `search_logs_tool`) are untouched — designers-first,
  each answers a distinct question.
- `retry_pd` stays as a named designer verb (same dispatcher internally).
- Quotas/tier gating (429), PROTECTED gating, run lineage/pin/compare,
  unread + no-auto-switch UX: all unchanged.

## Item 1 — Stage truth from files, not log text

Today `get_synthesis_job_status` infers the live stage by regex over the log
tail while `run_meta.current_stage` sits at "synth" for the whole ORFS run —
the payload carries BOTH (`stage` inferred vs `current_stage` persisted) and
they can disagree.

Change (`src/tools/synthesis_manager.py`):
- New pure helper `stage_progress_from_files(run_dir, plan) ->
  {stage_history: [{stage, ended_at?, status}], current_stage}` driven by the
  deterministic ORFS trail: per-stage logs (`logs/<plat>/<design>/base/N_*.log`)
  and result artifacts (`results/.../N_*.odb|.v|.gds`). A stage is
  *completed* when its artifact exists (mtime = end time), *running* when its
  log exists but its artifact doesn't, *pending* otherwise. Works live AND
  post-mortem (hosted stage_out reconstructs history from pulled files).
- Status responses expose ONE stage field (`stage`) + the `stages` table +
  new `stage_history` (with real timings). The `stage`/`current_stage`
  duality collapses (`current_stage` kept as a mirror only if a consumer
  needs it — verify; prefer removal, pre-users).
- Opportunistic persistence: in-process status reads (and worker milestones)
  write the derived progress into `run_meta.json` via the existing atomic
  `_write_json` — the folder stays the truth for out-of-process readers.
- Log-tail text stays in the payload (`last_log_lines`) as detail, never as
  the stage source.
- Hosted note (honest): during a cloud Job execution the web instance has no
  live file view; stage stays "running (synthesis)" with elapsed time — same
  as today — and `stage_history` backfills at stage_out.

## Item 2 — One key: run_id (tool-surface consolidation)

- `_JOBS` re-keyed by `run_id`; `start_synthesis_job` / `retry_pd_job`
  return `{run_id, status:"queued", poll_after_sec, timeout_sec}` — no
  `job_id` anywhere (pre-users: clean break; `index.json`'s jobs mapping
  becomes unnecessary for new runs, tolerated when reading old dirs).
- `get_synthesis_job` → **`get_synthesis_status(run_id)`** (wrapper rename;
  manager fn renamed to `get_synthesis_status(run_id, workspace)`), keeping
  the FULL rich payload: status, stage, stages, stage_history, elapsed_sec,
  last_log_lines, artifacts_found, summary_metrics, auto_checks, check_notes,
  next_action, poll_after_sec, backend, execution_label (+ new dispatched_at,
  last_activity_at). Lookup order: in-process memory (live queued/running
  detail) → `run_meta.json` → reconcile. Same shape from any source.
- **Delete** `get_stage_status` (content = `stages`/`stage_history` fields)
  and `run_synthesis_and_wait` (architect_tools + prompts updated to
  "start → bounded wait loop").
- `wait_for_synthesis(run_id, max_wait_sec, poll_interval_sec)` — unchanged
  bounded-poll semantics, re-keyed.
- REST (`src/api/actions.py` + `frontend/lib/api.ts`): POST /synthesize →
  `{ok, runId, pollAfterSec}`; `GET …/jobs/{job_id}` replaced by
  `GET …/runs/{run_id}/status`. Retry endpoint returns runId only.
- Update: `tool_catalog.py` sets (ASYNC/MUTATING/PROTECTED;
  EXCLUDED_FROM_UI stays `{wait_for_synthesis}`), `mcp_tools` +
  `architect_tools` lists, architect prompts (v0/v2 + pareto), tests
  (incl. `test_poll_wait_and_mcp_visibility`), Command Surface (schema-driven
  — picks up renames from the catalog automatically; verify run_id param
  conventions still map to the run combobox).

## Item 3 — Tombstones: no run is ever stuck "running"

`run_meta.json` gains: `dispatched_at`, `timeout_sec` (the clamped value),
`orfs_run_handle` (hosted, at stage_in). Liveness needs NO new machinery
locally: **the growing ORFS logs are the heartbeat** (freshest file mtime
under the run dir).

Extend `_reconcile_stale_status` (runs on every status/list read, both
already true today) with a death verdict:
- `running` + target artifacts complete → `completed` (exists today).
- `running` + no in-process future + no file activity for `STALE_GRACE`
  (e.g. 120s) + past `dispatched_at + timeout_sec + grace` → `failed`,
  `check_notes: "orchestrator lost (backend restarted or instance
  recycled); logs end at <ts>"`.
- `running` + fresh file activity → honestly `running` (a run the process
  lost but docker still executes keeps living until its files stop moving —
  then either the completed or the failed leg lands).

**Completion activity event (exactly once):** on any transition to a
terminal status — worker finalize OR reconciler — emit one event to the
existing attempt/event log (`attempt_logger`), guarded by a
`completion_event_recorded` flag in `run_meta` (atomic write). This is the
"trigger" the UI model consumes; it fires instantly when the worker is
alive, and on the next read when it wasn't.

## Item 4 — Hosted durability (worker writes durable state; anyone can finalize)

- **Progressive meta push:** in cloud mode, the worker pushes the tiny
  `run_meta.json` (+ bounded log tail) to the run's object-storage prefix at
  milestones (dispatch, pre-execute, post-stage_out, finalize) — single
  small-object puts via a new minimal stager method (NOT workspace tarball
  syncs). `get_synthesis_status` on any instance answers from the durable
  meta.
- **Adoption / idempotent finalize:** reconciler finding `running` + stale
  on an instance that doesn't own the run: using `orfs_run_handle` from
  meta, attempt `stage_out` — if the Job's `/out` exists, run the normal
  finalize (parse PPA, terminal meta, completion event, workspace sync); if
  nothing and past timeout → the Item-3 failed leg. The dispatching thread
  surviving is no longer required for a run to complete its bookkeeping.
- Cloud Run execution API is used ONLY as an optional liveness fallback
  ("container still running?" → keep `running`); it is never a stage
  source. If the current `job_client` lacks a status probe, ship without it
  (timeout ceiling covers the gap) and note the probe as a follow-up.
- Honest test limit: hosted legs are unit-tested against the existing
  recording-fake runner/stager patterns; no live GCS/Cloud Run in CI.

## Item 5 — UI: viewer, not actor

- **Delete `pollJob`** (`frontend/lib/commands.ts`) and the `synthJob`
  polling publisher. Dispatch = POST, add the run to the slice, toast
  "dispatched", done.
- **Remove the 5s active-run interval** from `useWorkbenchSync`; KEEP
  focus/visibility revalidate ("look when the human looks").
- **Updates arrive three ways only:**
  1. Activity events (agent/MCP status calls stream in as tool cards +
     activity; the completion event from Item 3): a new activity event
     carrying a runId invalidates/reloads the runs slice.
  2. **User Refresh** on a run row (RunsPane + agent-shell Index): calls
     `get_synthesis_status` through the `/invoke` tool path so it lands in
     activity as a source:"ui" call — the SAME primitive every other actor
     uses. Passive hydration (snapshot, focus) stays a plain read, NOT
     logged (gestures are events; ambient loads aren't).
  3. Window-focus revalidate (existing).
- **Honest staleness on run rows:** `running · <stage> · started 12m ago ·
  checked 4m ago · [Refresh]` (from `dispatched_at` + slice fetch time).
  LivePill shows any running run's last-known stage — no fake liveness.
- **Unread on completion:** the runs slice detects the running→terminal
  transition on any reload (whatever caused it) and sets the unread marker —
  replaces the pollJob-terminal hook. No auto-switch (unchanged rule).
- Run detail gains the per-stage table/timings + last_log_lines from the
  status payload (already carried; newly surfaced).

## Tests / gates

- pytest: `stage_progress_from_files` matrix over fixture layouts (fresh /
  mid-flow / complete / partial max_stage / retry); tombstone matrix
  (artifacts-complete→completed · stale+expired→failed · files-growing→
  running · exactly-once completion event); run_id-keyed status (memory hit
  / disk recovery / unknown id); wrapper + REST renames; MCP visibility
  test updated (no run_synthesis_and_wait, no get_stage_status, renamed
  status tool).
- vitest: dispatch-without-poll; activity-event→runs invalidation;
  running→terminal transition sets unread; staleness labels.
- e2e: palette synth flow rewritten for the new model (dispatch → row shows
  running → user Refresh advances → completion event marks unread);
  foreign-run discovery via focus revalidate.
- Gates: pytest suite · tsc · vitest · Playwright · next build. Commit and
  push per item.

## Deferred (documented)

- Splitting the full flow into chained per-stage ORFS invocations (locked:
  keep `make -B` for now).
- SSE/WebSocket push of activity events (pure optimization of the same
  model).
- Cloud Run execution-status probe on the job client (if absent today).
- Simulation-tool async parity; run retention/GC.
