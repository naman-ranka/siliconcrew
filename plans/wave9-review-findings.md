# Wave 9 adversarial review findings — ALL FIXED (see test_synth_review_fixes.py)

F1 HIGH stage_progress_from_files floor: naive .timestamp() is LOCAL-tz
  (synthesis_manager.py:845-853). Fix: keep tz-aware; floor_ts =
  datetime.fromisoformat(...).replace(tzinfo=utc if naive).timestamp()
  like _reconcile_stale_status:2413 does. Symptom: non-UTC host marks all
  stages inherited (west) or parent checkpoints as own (east).
F2 HIGH _JOBS/_POLL_CACHE/_POLL_BACKOFF_STATE keyed bare run_id →
  cross-workspace clobber (hosted). Fix: key ALL THREE by
  f"{workspace}::{run_id}" (dispatchers know workspace; status has it;
  reconciler _JOBS lookup needs workspace passed — thread it through).
F3 HIGH reconciler completed-leg runs BEFORE has_live_future check →
  emits completed while worker may still fail signoff/equiv. Fix: move
  the live-future check FIRST; if a live future exists (right workspace),
  return meta untouched (trust worker) — both legs.
F4 MED-HIGH store.ts selectSession/createSession don't reset runs/
  selectedRunId/synthJob → cross-session transition-detector false
  fires + missed real ones. Fix: reset all three in both resets.
F5 MED actions.py retry endpoint: map retry_pd_job status=="error" to
  400 invalid_request like synthesize does (actions.py:969-974);
  commands.ts already handles !ok.
F6 MED ceiling counts queue wait: dispatched_at + timeout. Fix: worker
  writes "started_at" when it begins (in _job_worker/_retry_pd_worker
  meta as created_at already exists = worker start); death verdict uses
  max(created_at, dispatched_at)+timeout+grace AND if status=="queued"
  require BOTH a much larger grace (e.g. +1 extra timeout) — simplest:
  deadline base = created_at (worker start) if present else
  dispatched_at, and for queued-status runs use dispatched_at +
  timeout + QUEUED_EXTRA_GRACE (timeout again).
F7 MED stage_progress_from_files ignores retry_start_stage: stages
  BEFORE retry_start_stage with no marker should render "inherited"
  (implicit), not become `current`. Fix: skip stages <
  retry_start_stage when picking `current` (mark "inherited" if no
  marker) using meta retry_start_stage.
F8 LOW wait loop exits without final re-check: after the sleep,
  do one last status sample before returning timed_out.

All fixes in synthesis_manager.py + store.ts + actions.py + wrappers.py;
add regression tests per finding (tz floor via monkeypatched TZ or
explicit aware datetimes; workspace-scoped keys; reconciler live-future
priority; store reset; retry 400; queued grace; retry current stage;
wait final sample). Then gates + commit + push + mark task 10 complete.

# Round 2 (codex, post-F1-F8) — C1-C6

C1 HIGH one stage truth in the PAYLOAD: _build_status_response returns
  persisted `stages` (run_meta) next to file-derived `stage_history` +
  `stage` — they can disagree (stages.synth "running" while history says
  floorplan completed; failed runs: top-level stage "synth" while
  history marks it "running"). Fix: for NON-terminal runs, overlay the
  file-derived statuses onto the stages table in the RESPONSE only
  (readers still never write meta); keep persisted artifacts detail.
  For terminal FAILED runs, stage_progress_from_files marks the first
  unfinished in-plan stage "failed" (not "running") when meta status is
  failed, so history/stage/stages agree. Terminal completed: persisted
  stages already refreshed by the worker — verify consistency.
C2 HIGH durable meta is write-only: add ObjectStore.get_file(key,
  local_path)->bool (protocol + InMemory + GCS); in the no-live-future
  path of get_synthesis_status (and reconciler pre-check), cloud mode:
  pull <handle>/meta/run_meta.json; prefer the remote meta when local is
  missing or remote is terminal and local isn't (persist it locally).
  Test with fake store: instance B answers terminal from durable meta
  pushed by instance A.
C3 MED/HIGH adoption should not wait for the ceiling: in the reconciler
  death leg, try _try_adopt_cloud_outputs (exists() is cheap) BEFORE the
  deadline check whenever there is no live future — outputs present →
  finalize completed immediately on the next read.
C4 MED get_synthesis_status future-exception path builds "failed" but
  persists nothing: persist failed meta (check_notes = job execution
  error), _refresh_stage_metadata(terminal failed), durable push,
  _append_index failed, _emit_completion_event — so later readers agree.
C5 LOW 15s activity cadence: ACCEPTED deviation, documented in the plan
  (the UI watches the LOG while a run is live; SSE replaces it later).
  No code change; note here for the record.
C6 LOW docs/pd_knob_catalog.md:161 references deleted get_stage_status —
  update to get_synthesis_status stages/stage_history.
