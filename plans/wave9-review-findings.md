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
