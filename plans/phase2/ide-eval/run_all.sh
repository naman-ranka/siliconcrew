#!/bin/bash
# Run the human-path IDE evaluation across all 8 designs, sequentially.
# Unique per-run session tag avoids duplicate-name collisions (which silently
# fail session creation and leave the workbench on a stale session).
cd /home/user/siliconcrew
RUN_TAG="${RUN_TAG:-$(date +%H%M%S)}"
echo "RUN_TAG=$RUN_TAG"
for dir in plans/phase2/ide-eval/designs/*/; do
  name=$(basename "$dir")          # e.g. 01_mux2
  echo "===== $name ====="
  node plans/phase2/ide-eval/run_eval.mjs \
    "$dir" "ev${RUN_TAG}-${name}" \
    "plans/phase2/screenshots/ide-eval/$name" 2>&1 | tail -4
  echo
done
echo "ALL DESIGNS DONE"
