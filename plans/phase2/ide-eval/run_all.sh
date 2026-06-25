#!/bin/bash
# Run the human-path IDE evaluation across all 8 designs, sequentially.
cd /home/user/siliconcrew
for dir in plans/phase2/ide-eval/designs/*/; do
  name=$(basename "$dir")          # e.g. 01_mux2
  echo "===== $name ====="
  node plans/phase2/ide-eval/run_eval.mjs \
    "$dir" "eval-$name" \
    "plans/phase2/screenshots/ide-eval/$name" 2>&1 | tail -3
  echo
done
echo "ALL DESIGNS DONE"
