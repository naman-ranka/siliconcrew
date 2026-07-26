#!/usr/bin/env bash
# ORFS Cloud Run Job entrypoint — the cloud counterpart of the local Docker run.
#
# Contract (set by CloudJobOrfsRunner via env):
#   WORKSPACE_BUCKET     GCS bucket holding staged run dirs
#   ORFS_RUN_HANDLE      object key under orfs-runs/<handle>.tar.gz
#   ORFS_COMMAND         the make command(s) to run inside ORFS
#   ORFS_VOLUME_MAP      ';'-joined "<rundir-rel>::<orfs-container-path>" pairs
#
# Flow: download the staged run dir -> run ORFS against /workspace/config.mk ->
# copy the ORFS outputs (results/logs/reports) into a run-dir-relative tree ->
# upload to orfs-runs/<handle>/out.tar.gz, which stage_out() pulls back locally.
#
# Reliability (hosted-orfs-reliability, Fix C): while ORFS runs we periodically
# snapshot its logs/ tree to orfs-runs/<handle>/logs_partial.tar.gz, and an EXIT
# trap flushes a final snapshot + result upload on ANY exit — so a job killed by
# the task timeout is still inspectable and its produced artifacts still upload
# (the old script uploaded only on the clean path, losing everything on a kill).
set -euo pipefail

: "${WORKSPACE_BUCKET:?missing WORKSPACE_BUCKET}"
: "${ORFS_RUN_HANDLE:?missing ORFS_RUN_HANDLE}"
: "${ORFS_COMMAND:?missing ORFS_COMMAND}"

RUN_DIR=/workspace
OUT_DIR=/tmp/orfs_out
FLOW_DIR=/OpenROAD-flow-scripts/flow
LOGS_DIR="$FLOW_DIR/logs"
RUN_PREFIX="gs://${WORKSPACE_BUCKET}/orfs-runs/${ORFS_RUN_HANDLE}"
mkdir -p "$RUN_DIR" "$OUT_DIR"

echo "[orfs-job] downloading staged run dir: $ORFS_RUN_HANDLE"
gcloud storage cp "${RUN_PREFIX}.tar.gz" /tmp/run.tar.gz
tar -xzf /tmp/run.tar.gz -C "$RUN_DIR"

# Stage IN: populate the ORFS container dirs from the staged run tree BEFORE the
# run — the mirror of the stage-out below, using the same ORFS_VOLUME_MAP. Locally
# the Docker volume bind makes run_dir/orfs_results and the container's
# flow/results the same directory, so checkpoints (e.g. retry_pd's 3_place.odb)
# are already visible. In the cloud job there is no bind, so without this a
# checkpoint-based retry starts with an empty ./results and OpenROAD aborts
# (ORD-0007 "...3_place.odb does not exist"). The `-d` guard means fresh full
# runs (nothing staged in) are untouched.
if [ -n "${ORFS_VOLUME_MAP:-}" ]; then
  IFS=';' read -ra entries <<< "$ORFS_VOLUME_MAP"
  for entry in "${entries[@]}"; do
    [ -n "$entry" ] || continue
    rel="${entry%%::*}"
    container="${entry##*::}"
    if [ -n "$container" ] && [ -d "$RUN_DIR/$rel" ]; then
      echo "[orfs-job] staging input: $RUN_DIR/$rel -> $container"
      mkdir -p "$container"
      cp -r "$RUN_DIR/$rel/." "$container/" 2>/dev/null || true
    fi
  done
fi

# Snapshot the ORFS logs/ tree to <handle>/logs_partial.tar.gz. The backend reads
# it via store.get_tree("<handle>/logs_partial", ...), which resolves to exactly
# this .tar.gz key. Best-effort; never fails the run. Uses a UNIQUE temp file so
# the periodic loop and the final finalize() sync can never clobber each other's
# in-flight tar (→ a truncated upload).
sync_partial_logs() {
  [ -d "$LOGS_DIR" ] || return 0
  local tmp
  tmp="$(mktemp)" || return 0
  if tar -czf "$tmp" -C "$LOGS_DIR" . 2>/dev/null; then
    gcloud storage cp "$tmp" "${RUN_PREFIX}/logs_partial.tar.gz" 2>/dev/null || true
  fi
  rm -f "$tmp"
}

# Map ORFS container outputs to a run-dir-relative tree and upload out.tar.gz.
# The ONLY result-upload path, so it runs on graceful termination too (the guard
# keeps it single-shot when the EXIT trap fires after a normal return).
staged_out=0
stage_out_results() {
  [ "$staged_out" = 1 ] && return 0
  staged_out=1
  if [ -n "${ORFS_VOLUME_MAP:-}" ]; then
    IFS=';' read -ra entries <<< "$ORFS_VOLUME_MAP"
    for entry in "${entries[@]}"; do
      [ -n "$entry" ] || continue
      rel="${entry%%::*}"
      container="${entry##*::}"
      if [ -n "$container" ] && [ -e "$container" ]; then
        mkdir -p "$OUT_DIR/$(dirname "$rel")"
        cp -r "$container" "$OUT_DIR/$rel" 2>/dev/null || true
      fi
    done
  fi
  echo "[orfs-job] uploading results"
  local tmp
  tmp="$(mktemp)" || return 0
  if tar -czf "$tmp" -C "$OUT_DIR" . 2>/dev/null; then
    gcloud storage cp "$tmp" "${RUN_PREFIX}/out.tar.gz" 2>/dev/null || true
  fi
  rm -f "$tmp"
}

# On ANY exit (normal, ORFS error, or SIGTERM from the task timeout): stop the
# periodic sync, flush a final partial-log snapshot, then attempt the result
# upload. SIGKILL can't be trapped — the background loop below is that safety net.
finalize() {
  trap - EXIT TERM INT
  # Stop the periodic sync AND reap it before our own final sync, so an in-flight
  # background tar/upload can't interleave with the finalize one.
  if [ -n "${SYNC_PID:-}" ]; then
    kill "$SYNC_PID" 2>/dev/null || true
    wait "$SYNC_PID" 2>/dev/null || true
  fi
  sync_partial_logs || true
  stage_out_results || true
}
trap finalize EXIT TERM INT

# Background periodic partial-log sync (survives a hard kill up to the last
# snapshot; the trap covers graceful exits).
( while true; do sleep 30; sync_partial_logs; done ) &
SYNC_PID=$!

# Run ORFS. config.mk references /workspace/... exactly as in local mode.
# Run it in the BACKGROUND and `wait` on it: a foreground child would defer any
# trapped signal until it exits, so a Cloud Run task-timeout SIGTERM (grace, then
# SIGKILL) would never fire finalize() — defeating the graceful flush of partial
# logs and produced artifacts. `wait` IS interruptible by trapped signals.
echo "[orfs-job] running ORFS"
cd "$FLOW_DIR"
set +e
bash -c "$ORFS_COMMAND" &
orfs_pid=$!
wait "$orfs_pid"
rc=$?
# A signal that interrupts `wait` before ORFS exits makes it return >128 (and
# finalize() has already run via the trap). Re-wait to reap ORFS's real exit
# status if it is in fact still running; stop once it's gone.
while [ "$rc" -gt 128 ] && kill -0 "$orfs_pid" 2>/dev/null; do
  wait "$orfs_pid"
  rc=$?
done
set -e
echo "[orfs-job] ORFS exit code: $rc"

# finalize() runs via the EXIT trap (stops the loop, final partial sync, result
# upload) unless a trapped signal already ran it. Propagate the real ORFS exit
# code so the Job execution succeeds/fails correctly.
exit $rc
