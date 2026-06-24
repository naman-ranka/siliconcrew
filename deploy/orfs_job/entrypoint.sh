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
set -euo pipefail

: "${WORKSPACE_BUCKET:?missing WORKSPACE_BUCKET}"
: "${ORFS_RUN_HANDLE:?missing ORFS_RUN_HANDLE}"
: "${ORFS_COMMAND:?missing ORFS_COMMAND}"

RUN_DIR=/workspace
OUT_DIR=/tmp/orfs_out
FLOW_DIR=/OpenROAD-flow-scripts/flow
mkdir -p "$RUN_DIR" "$OUT_DIR"

echo "[orfs-job] downloading staged run dir: $ORFS_RUN_HANDLE"
gcloud storage cp "gs://${WORKSPACE_BUCKET}/orfs-runs/${ORFS_RUN_HANDLE}.tar.gz" /tmp/run.tar.gz
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

# Run ORFS. config.mk references /workspace/... exactly as in local mode.
echo "[orfs-job] running ORFS"
cd "$FLOW_DIR"
set +e
bash -c "$ORFS_COMMAND"
rc=$?
set -e
echo "[orfs-job] ORFS exit code: $rc"

# Map ORFS container outputs back to run-dir-relative subdirs.
if [ -n "${ORFS_VOLUME_MAP:-}" ]; then
  IFS=';' read -ra entries <<< "$ORFS_VOLUME_MAP"
  for entry in "${entries[@]}"; do
    [ -n "$entry" ] || continue
    rel="${entry%%::*}"
    container="${entry##*::}"
    if [ -n "$container" ] && [ -e "$container" ]; then
      mkdir -p "$OUT_DIR/$(dirname "$rel")"
      cp -r "$container" "$OUT_DIR/$rel"
    fi
  done
fi

echo "[orfs-job] uploading results"
tar -czf /tmp/out.tar.gz -C "$OUT_DIR" .
gcloud storage cp /tmp/out.tar.gz "gs://${WORKSPACE_BUCKET}/orfs-runs/${ORFS_RUN_HANDLE}/out.tar.gz"

# Propagate the real ORFS exit code so the Job execution succeeds/fails correctly.
exit $rc
