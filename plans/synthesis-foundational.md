# Wave 9 — Foundational synthesis job model

Status: ACCEPTED with amendments (2nd-agent review folded in; implementation
awaiting user go)

## Intent

One async contract for synthesis/PnR that behaves identically on localhost,
over MCP, and deployed — fundamental changes to bookkeeping and the tool
surface, NOT a rewrite of the synthesis engine.

## Invariants (what "foundational" means here)

1. **The run directory is the database.** `run_meta.json` + artifacts are the
   only authoritative state; process memory is a cache, never load-bearing.
2. **One key.** `run_id` (the durable folder name) addresses everything;
   the process-lifetime `job_id` is eliminated. (Non-goal: the internal
   remote-ORFS service layer has its own unrelated `job_id` —
   `src/platform_engines/orfs_service.py`, `src/orfs_client/` — that
   namespace is NOT touched.)
3. **One async contract.** dispatch → poll → read. Exactly one blocking
   convenience (`wait_for_synthesis`), defined as bounded polling, identical
   on every platform.
4. **The computer writes its own tombstone.** Terminal state is persisted
   durably by whoever did/observed the work; readers can declare a run dead
   by staleness, so no run is ever stuck at "running".
5. **The UI is a viewer of the event log, not a status actor.** Actors
   (agent, MCP client, the USER via Refresh) call status; every call and
   every completion is an activity event; the UI updates from events, user
   gestures, and window focus. The UI never calls run-status on its own.

## Locked constraints (user decisions)

- `run_synthesis_and_wait` is REMOVED.
- The ORFS invocation is UNCHANGED: full flow stays one
  `make -B DESIGN_CONFIG=…`; partial/retry flows keep their chained
  `do-<stage>` targets. Splitting the full flow per-stage is DEFERRED.
- The 7 report readers are untouched. `retry_pd` stays as a named designer
  verb (same dispatcher internally). Quotas (429), PROTECTED gating, run
  lineage/pin/compare, unread + no-auto-switch: all unchanged.

## Item 1 — Stage truth from files, not log text

Reality check (review): a deterministic file→stage layer ALREADY exists —
`_STAGE_COMPLETION_MARKERS`, `_find_stage_completion_marker`,
`_find_stage_artifacts`, `_refresh_stage_metadata`,
`_load_run_meta_with_inferred_stages` (synthesis_manager.py). The problem is
only that the LIVE status path ignores it and regex-guesses from the log
tail instead. So Item 1 is a REFACTOR, not a new table:

- One helper `stage_progress_from_files(run_dir, plan, floor_ts)` built ON
  TOP of the existing marker/artifact tables (no third stage-truth table):
  a stage is *completed* when its marker artifact exists (mtime = end
  time), *running* when its stage log exists without the artifact,
  *pending* otherwise. Correct repo paths: `orfs_logs/<plat>/<design>/base/
  N_*.log`, `orfs_results/<plat>/<design>/base/N_*.odb` (intermediate
  stages emit .odb/.sdc only; .v/.gds exist only for finish; grt =
  `5_1_grt.odb`).
- `floor_ts = dispatched_at`: only files with mtime ≥ dispatched_at count
  as THIS run's progress. Retry runs copy parent checkpoints with
  `shutil.copy2` (parent mtimes preserved) — those render as status
  "inherited", never as this run's timings.
- The live status path uses this instead of log-regex; `stage` (payload)
  becomes file-derived truth; `last_log_lines` stays as detail, never the
  stage source. New `stage_history` (per-stage status + end timestamps).
- **`current_stage` STAYS** (mirrors the derived value): it is load-bearing
  in `_refresh_stage_metadata` failure attribution, `actions.py`
  `currentStage`, the frontend `toSynthJobStatus`/RunsPane, and multiple
  test fixtures. No removal this wave.
- Persistence discipline (race fix from review): readers NEVER write
  run_meta — stage progress is derived on read (cheap stat calls). Only the
  worker (milestones) and the reconciler (terminal transitions) write, so
  reader writes can't clobber the worker's whole-dict persists.
- Hosted note (honest): during a cloud/remote execution the web instance
  has no live file view — stage stays "running (synthesis)" with elapsed
  time; `stage_history` backfills after stage_out from pulled file mtimes.

## Item 2 — One key: run_id (tool-surface consolidation)

- Initial `run_meta.json` written AT DISPATCH (before submit) with
  `status:"queued", dispatched_at, timeout_sec` — a queued run is visible
  and tombstone-able out-of-process from second zero (today meta first
  appears inside the worker).
- `_JOBS`, `_POLL_CACHE`, `_POLL_BACKOFF_STATE`, `_recommended_poll_after_sec`
  re-keyed by `run_id`; `start_synthesis_job`/`retry_pd_job` return
  `{run_id, status:"queued", poll_after_sec, timeout_sec}` — no `job_id`.
  index.json's jobs mapping stops being written (tolerated when reading old
  dirs).
- `get_synthesis_job` → **`get_synthesis_status(run_id)`** keeping the FULL
  rich payload (status, stage, stages, stage_history, elapsed_sec,
  last_log_lines, artifacts_found, summary_metrics, auto_checks,
  check_notes, next_action, poll_after_sec, backend, execution_label,
  dispatched_at). Lookup: in-process memory → run_meta.json → reconcile
  (Item 3). Same shape from any source.
- **Delete** `get_stage_status` (content = stages/stage_history fields) and
  `run_synthesis_and_wait`. `wait_for_synthesis(run_id, …)` unchanged
  semantics, re-keyed.
- REST: POST /synthesize → `{ok, runId, pollAfterSec}`;
  `GET …/runs/{run_id}/status` replaces `GET …/jobs/{job_id}`; retry
  returns runId only; `_ui_log_result` payloads drop job_id.
- Full consumer sweep (from review — ALL of these change):
  - backend: wrappers.py (tools + start_synthesis/sleep_tool/next_action
    docstrings), mcp_server.py imports + mcp_tools, tool_catalog.py
    (TOOL_CATEGORIES["synthesis"] must list the RENAMED tool or it silently
    loses PROTECTED status), architect.py:100-102/228-229 hardcoded tool
    table, prompts v0 + **v1** + v2 + pareto, actions.py.
  - frontend: types (SynthJobStatus.jobId), api.ts (synthesize/getJob/
    retryRun), store.ts synthJob slice + toSynthJobStatus, RunsPane,
    commands.ts, commandSurface.ts:112 desc string, CommandSurface.tsx:79
    icon map key. schemaForm's RUN_ID_KEYS convention gives
    `get_synthesis_status(run_id)` the run combobox automatically (today's
    job_id param never had one — small UX win).

## Round-2 amendments (codex review of the amended plan)

1. **A reconciling status read is a WRITE — give it a durable path.**
   `get_synthesis_status` is a self-healing read: when the reconciler flips
   a run to completed/failed it writes run_meta. Hosted REST only syncs the
   workspace when `mutates=True` (actions.py:425) and status tools are
   rightly NOT in MUTATING_TOOLS — so the tombstone write would strand in
   instance scratch. Resolution: reconciler terminal writes go through the
   Item-4 `put_file` helper to the run's `orfs-runs/<session>/<run_id>`
   prefix DIRECTLY (tiny object, no tarball), in addition to local scratch.
   Durable truth never depends on the mutates flag; status stays a
   non-mutating endpoint.
2. **Completion-event idempotency across INSTANCES, not just threads.** The
   `O_EXCL` marker only guards one instance's scratch. The event gets a
   deterministic id — `tool_call_id = "completion:<run_id>"`, with
   `arguments: {run_id}` — and `build_activity_events` dedupes orphan
   results by id, so double emission from two instances collapses at read
   time. O_EXCL stays as the cheap local fast-path guard.
3. **Hosted stage TIMINGS are not promised.** The Cloud Run entrypoint
   `cp -r`s outputs and tars them (deploy/orfs_job/entrypoint.sh:59), so
   pulled mtimes reflect staging, not stage ends. Honest contract: file
   evidence gives stage PRESENCE/completion everywhere; per-stage timings
   are local-docker-only (hosted timings would need mtime-preserving
   staging or ORFS log-timestamp parsing — deferred).
4. **The runner seam change is explicit:** `OrfsRequest` gains a
   `run_handle` field set by the manager (deterministic prefix);
   `CloudJobOrfsRunner.run()` uses it instead of minting a UUID;
   `make_run_stager` takes the handle as an argument. The manager persists
   nothing extra — the handle is reconstructable — but the seam files
   (`src/orfs_client/__init__.py`, orfs_runner.py, workspace_provider.py)
   are all touched.
5. **`GET /runs/{run_id}` (run detail) also calls `get_stage_status` today**
   (actions.py:887) — it moves to the unified status payload; the plan's
   endpoint list includes it.
6. **`wait_for_synthesis` clamps `max_wait_sec`** (≤120s server-side;
   prompts keep recommending 30–60s) — bounded means bounded even for a
   creative caller.
7. **The activity→runs observer is named mechanically:** `loadActivity`
   diffs incoming events; any NEW event carrying a runId triggers
   `loadRuns()`, whose running→terminal transition detector owns unread
   marking (re-homed from pollJob). `TOOL_DIR_INVALIDATION` keeps doing
   dirs only.

## Item 3 — Tombstones: no run is ever stuck "running"

- **Add reconcile to the status-read path** (review: today
  `_reconcile_stale_status` runs ONLY in `list_synthesis_runs`; the status
  read and /runs/{id} return stale meta raw). After this item, EVERY read
  (status, run list, run detail) reconciles.
- Death verdict added to the reconciler:
  - `running` + target artifacts complete → `completed` (exists today).
  - `running` + no in-process future + past `dispatched_at + timeout_sec +
    grace` + liveness signal cold → `failed`, check_notes "orchestrator
    lost (backend restarted or instance recycled)".
  - Liveness signal is BACKEND-SPECIFIC and stated honestly: local_docker →
    freshest file mtime under the run dir (logs grow live via bind mounts);
    remote/cloud_job → NO live files exist during execution, so liveness is
    the timeout ceiling plus Item 4's durable meta pushes. No universal
    heartbeat is claimed.
- **Completion activity event, exactly once:** on any transition to
  terminal (worker finalize OR reconciler), emit a SYNTHETIC ORPHAN
  `tool_result` event (source "system", runId, honest summary) —
  `build_activity_events` already renders orphan tool_results; no new event
  type needed. Exactly-once via an `O_CREAT|O_EXCL` marker file
  (`completion.event`) in the run dir — atomic claim, no read-modify-write
  race between concurrent readers. Plumbing: `_job_worker` gains the
  session context (captured ctx in `_submit_with_quota_release` is rebound
  inside the worker thread) so `log_tool_result(workspace, session_id, …)`
  has what it needs; the reconciler emits with the session it's reading.

## Item 4 — Hosted durability (any instance can finalize)

- **Deterministic run handle** (review simplification): the object-storage
  prefix becomes `orfs-runs/<session_id>/<run_id>` instead of a UUID minted
  inside `CloudJobOrfsRunner.run()`. Any instance can reconstruct it from
  the run alone — nothing to plumb through OrfsRequest/OrfsResult, nothing
  extra in run_meta. (`make_run_stager` gains an explicit handle argument.)
- **Progressive meta push:** cloud mode pushes the tiny run_meta.json (+
  bounded log tail) to the handle prefix at worker milestones (dispatch,
  pre-execute, post-stage_out, finalize) — single small-object puts.
  Requires a new `put_file`/`exists` on the ObjectStore protocol → ripples:
  Protocol + InMemoryObjectStore + GcsObjectStore + make_run_stager/
  build_run_stager return shape + orfs_runner._build_cloud_runner
  unpacking. All listed, all small.
- **Adoption / idempotent finalize:** reconciler finding `running` + past
  ceiling on any instance: check `store.exists(f"{handle}/out")` (NEW —
  review: `get_tree` today silently creates an empty dir on absent blobs,
  so existence MUST be explicit). If outputs exist → stage_out (confirmed
  idempotent: pure tar-extract) → normal finalize (parse PPA, terminal
  meta, completion event, workspace sync). If absent and past ceiling → the
  Item-3 failed leg.
- Cloud Run execution API: confirmed `GcpCloudRunJobClient` has only
  `execute()` — no status probe exists. Ship without it (timeout ceiling
  covers the gap); probe noted as follow-up.
- Honest test limit: hosted legs unit-tested against recording-fake
  runner/stager patterns; no live GCS/Cloud Run in CI.

## Item 5 — UI: viewer of the event log

- **Delete `pollJob`** (commands.ts) and the run-status polling. Dispatch =
  POST → run appears `queued` → toast "dispatched". Everything pollJob's
  terminal hook did re-homes to the runs-slice transition detector below
  (unread marking, synth-artifact refresh, `invalidateDirs(["",
  "synth_runs"])`, completion/failure toast).
- **The one background behavior the UI keeps: watching the ACTIVITY FEED,
  not run status.** Review flagged the honest gap — with pollJob and the 5s
  interval both gone, a completion event has no delivery path to an
  already-focused tab. Resolution consistent with the user's model ("some
  kind of activity is automatically generated, and because of that
  activity, it automatically updates the UI"): while any non-terminal run
  exists, the activity slice revalidates on a slow cadence (~15s, cheap
  head fetch); a new event carrying a runId triggers `loadRuns()`. The UI
  subscribes to the LOG; it never calls run-status itself. (SSE push later
  replaces the cadence without changing the model.) `useWorkbenchSync`'s
  5s whole-workbench poll is deleted; focus/visibility revalidate stays.
- **User Refresh** on a run row (RunsPane + agent Index): calls
  `get_synthesis_status` through `/invoke` (logged as source:"ui" activity
  — the SAME primitive every actor uses) and applies the response to the
  row. Hosted honesty: /invoke for a non-mutating tool does not sync the
  workspace, so that activity line persists only best-effort until the
  next mutating sync — accepted (a Refresh is not worth a tarball upload).
  Passive hydration (snapshot, focus) stays a plain unlogged read.
- **Honest staleness:** run rows show `running · <stage> · started 12m ago
  · checked 4m ago · [Refresh]` (dispatched_at + slice fetch time).
- **LivePill (behavior CHANGE, per review):** today it renders the latest
  activity event; it additionally gets a running-run chip (last-known
  stage from the slice) — no fake liveness, clearly labeled as last-known.
- **Unread on completion:** the runs slice detects running→terminal on any
  reload (whatever caused it) and marks unread. No auto-switch (unchanged).
- Run detail surfaces stage_history (per-stage table + timings) and
  last_log_lines.

## Tests / gates (full inventory from review)

- pytest — update: test_synthesis_manager, test_synthesis_wrapper,
  test_synthesis_wait_and_metrics (bounded-loop + the run_synthesis_and_wait
  test is DELETED), test_stage_status_tool (folds into status-payload
  tests), test_stage_metadata_runtime, test_synth_max_stage,
  test_retry_pd_tool, test_quota_enforcement, test_workbench_v2_api
  (synthesize dispatch stub + shared-policy test),
  test_poll_wait_and_mcp_visibility, test_mcp, test_mcp_tool_registry,
  test_synth_status_reconcile; fixtures retry_pd_workspace /
  manager_runtime_workspace / stage_status_workspace run_meta.json
  (job_id/current_stage fields). New: stage_progress_from_files matrix
  (fresh/mid/complete/partial/retry-inherited), tombstone matrix
  (artifacts→completed · stale+expired→failed · growing-files→running ·
  queued-with-initial-meta), exactly-once completion event (O_EXCL race),
  status-read reconciles, deterministic handle + exists()/adoption with
  fake store.
- vitest — update: commands.test.ts (pollJob gone), workbench.components
  (synthJob), useWorkbenchSync.test.ts (interval deleted),
  commandSurface.test.ts, schemaForm.test.ts, agentShell.test.tsx. New:
  activity-event→loadRuns invalidation, running→terminal→unread, staleness
  labels.
- e2e — workbench.smoke.spec.ts:414-416 mock (`jobId`, /jobs route) →
  runId + /runs/{id}/status; palette flow rewritten (dispatch → queued row
  → Refresh advances → completion event via activity mock → unread).
- Gates: pytest suite · tsc · vitest · Playwright · next build. Commit and
  push per item.

## Deferred (documented)

- Splitting the full flow into chained per-stage ORFS invocations (locked:
  `make -B` stays).
- SSE/WebSocket push of activity events (replaces the slow activity
  cadence; same model).
- Cloud Run execution-status probe on the job client (doesn't exist today).
- Simulation-tool async parity; run retention/GC.
