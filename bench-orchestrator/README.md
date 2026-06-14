# Benchmark Orchestrator

Repeatable SiliconCrew benchmark runner for ASU, CVDP, XLS, direct Verilog,
and future agent comparisons.

Primary entrypoints:

```bash
python bench-orchestrator/run_benchmark.py --config bench-orchestrator/configs/asu_xls_smoke.yaml
python bench-orchestrator/summarize_runs.py
```

Supported v1 agents:

- `fake`: contract-test runner with no external model call.
- `codex`: `codex exec --json`.
- `claude`: `claude -p --dangerously-skip-permissions`.
- `antigravity`: `agy --print --dangerously-skip-permissions`.

Preflight examples:

```bash
python bench-orchestrator/run_benchmark.py preflight --agent codex --mcp-server rtl-codex
python bench-orchestrator/run_benchmark.py preflight --agent claude --mcp-server rtl-codex
python bench-orchestrator/run_benchmark.py preflight --agent antigravity --mcp-server rtl-codex
```

Continue an existing run without creating a new SiliconCrew session:

```bash
python bench-orchestrator/run_benchmark.py \
  --resume bench-orchestrator/runs/<run_dir> \
  --prompt "Optimize the design and rerun the necessary checks."
```

Resume outputs are stored under `continuations/NNN/`, while the top-level
`run_summary.json`, `agent_trace.md`, and `generated_sources/` are refreshed to
the latest workspace state.

The orchestrator does not replace SiliconCrew sessions. It creates a clean
outer experiment record under `bench-orchestrator/runs/` and reads/copies useful
artifacts from the normal SiliconCrew workspace after the run.
