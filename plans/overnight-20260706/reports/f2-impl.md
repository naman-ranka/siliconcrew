# F2 implementation — gate MCP workspace sync to mutating tools

**Commit:** `f095fcb` (branch `claude/overnight-showcase`). Not deployed (orchestrator
batches deploys). Code + tests done; full gate run.

## What changed (3 files, +140/-7)

- `src/platform_engines/request_scope.py` — added `sync: bool = True` to
  `session_request_scope` and `run_in_session`; the `finally` calls
  `provider.sync()` only when `sync=True`. Default True → every existing caller
  (only `mcp_server` in prod) and the tests are byte-compatible.
- `mcp_server.py` — import `MUTATING_TOOLS` from `src.api.tool_catalog`; at the
  `call_tool` dispatch, `mutates = name in _SHARED_MUTATING_TOOLS`, passed as
  `sync=mutates` to `run_in_session`. Read-only tools no longer re-tar+upload the
  workspace. This mirrors the REST action router, which already gates via
  `run_scoped(mutates=…)` (`actions.py:424`) — the MCP path was the straggler.
- `tests/test_mcp_sync_gating.py` — new regression test.

## MANDATORY item 1 — MUTATING_TOOLS completeness audit

Enumerated every tool in the MCP registry, read each wrapper body in
`src/tools/wrappers.py`, classified writer vs reader, and reconciled with
`MUTATING_TOOLS` (`tool_catalog.py:84`). **Result: no writer missing. No change to
the set required.**

| Tool | Writes workspace? | In MUTATING_TOOLS | Verdict |
|---|---|---|---|
| write_spec | yes (spec file) | yes | ✓ |
| write_file | yes | yes | ✓ |
| apply_patch_tool | yes | yes | ✓ |
| edit_file_tool | yes | yes | ✓ |
| load_yaml_spec_file | yes (materializes spec) | yes | ✓ |
| update_manifest | yes (manifest.json) | yes | ✓ |
| simulation_tool | yes (VCD/sim outputs) | yes | ✓ |
| run_isolated_simulation | yes (sim_runs/<id>) | yes | ✓ |
| cocotb_tool | yes (results/logs) | yes | ✓ |
| sby_tool | yes (formal outputs) | yes | ✓ |
| start_synthesis | yes (synth_runs/<id>) | yes | ✓ |
| retry_pd | yes (synth_runs/<id>) | yes | ✓ |
| save_metrics_tool | yes (metrics json) | yes | ✓ |
| generate_report_tool | yes (design_report.md) | yes | ✓ |
| schematic_tool | yes (SVG) | yes | ✓ |
| run_xls_flow / run_dslx_interpreter / compile_dslx_to_ir / optimize_xls_ir / codegen_xls / benchmark_xls / experimental_compile_cpp_to_ir | yes (IR/verilog) | yes (HLS) | ✓ |
| read_spec | no | no | ✓ reader |
| read_file | no | no | ✓ reader |
| list_files_tool | no | no | ✓ reader |
| get_manifest | no | no | ✓ reader |
| waveform_tool | no (parses VCD → text) | no | ✓ reader |
| search_logs_tool | no | no | ✓ reader |
| linter_tool | throwaway compile artifacts only | no | ✓ reader (no persist-worthy output) |
| get_synthesis_status | reconciles run_meta* | no | ✓ reader (*durable via own channel) |
| wait_for_synthesis | reconciles run_meta* | no | ✓ reader (*durable via own channel) |
| get_synthesis_metrics | no (parses reports) | no | ✓ reader |
| read_stage_report | no | no | ✓ reader |
| get_route_drc_summary / get_cts_summary / get_congestion_summary | no | no | ✓ reader |
| compare_pd_runs | no | no | ✓ reader |

**The one subtlety that de-risks the whole change** (`*`): `get_synthesis_status` /
`wait_for_synthesis` DO write `run_meta.json` during self-healing reconciliation
(invariant 5), but that state is persisted through its **own** durable channel —
`_persist_run_meta_durable` → `_push_durable_run_meta` to the run store
(`orfs-runs/<session>/<run_id>`, `synthesis_manager.py:2438`, `:1656-1661`) — which
is **independent of the workspace tarball** `provider.sync()` uploads. So gating
their workspace sync off loses no run-state. Verified in code, not assumed.

`linter_tool` runs iverilog/verilator for diagnostics returned inline; any compile
artifact it drops in the workspace is throwaway (nothing downstream reads it), so a
skipped upload loses nothing.

## MANDATORY item 2 — event-log durability decision

**Decision: flush-on-next-mutation, documented (accepted).** `log_tool_call` /
`log_tool_result` append `attempt_events.jsonl` (the activity log, invariant 3)
inside the workspace on every call, including reads. With sync gated to mutating
tools, a read-only call's activity events stay in ephemeral Cloud Run scratch until
the next mutating call's sync uploads the whole tarball (they share the same file, so
one sync flushes all accumulated events).

**Why not "always flush just the event log":** the activity log lives **inside** the
workspace tarball (the durable unit is one `.tar.gz` per session). A separate
per-file push of `attempt_events.jsonl` to its own object key would be **clobbered by
the next tarball hydration** (`workspace_for` untars the blob over scratch), so it
buys nothing without also teaching hydration to merge a side-channel file back in —
real machinery (provider API + reconcile) for a small honesty gain. That fails the
owner's "simple, fundamental, not machinery" test.

**Exposure accepted:** a design loop interleaves writes constantly (write_file →
lint → sim → synth), so the log flushes at nearly every step. The only lossy case is
a **tail of pure-read calls** followed by an instance recycle with **no** subsequent
write — bounded, and it's a deferred-not-silent drop of low-value read activity. If
the owner later wants zero read-activity loss, the durable path is a side-channel
append + merge-on-hydrate (documented here as the alternative). The decision is
written into the `call_tool` comment so the tradeoff is visible at the code.

## Item 3 (optional put_tree-generation opt) — SKIPPED, noted

`put_tree` returning the new generation so `CloudWorkspaceProvider.sync` can drop its
redundant post-put `_store_generation` GET is a **Store protocol change**
(`ObjectStore.put_tree` signature → `InMemoryObjectStore`, `GcsObjectStore`, +
`test_workspace_hydration_concurrency.py` and any other consumer). Left as its own
item to keep this commit a clean single concern; not folded in.

## Gates

- New test `tests/test_mcp_sync_gating.py`: read-only call → `provider.sync` NOT
  called; mutating call → called once; + a policy guard asserting every writer is in
  `MUTATING_TOOLS` and no reader is. **Fails on pre-fix code** (`run_in_session` had
  no `sync` kwarg → `TypeError`). Passes now.
- `tests/test_mcp_isolation.py`, `tests/test_session_context_propagation.py`: pass
  (the request-scope path this touches).
- `py_compile` clean on both edited files.
- **Full backend subset** (`python -m pytest tests/ -q --ignore=…identity_migration
  --ignore=…test_mcp --ignore=…test_mcp_remote_auth`): **9 failed, 676 passed, 8
  skipped** — exactly the known env-gap baseline (llm_factory, congestion_summary,
  lint_engines norm_file, orfs_job_entrypoint stage_in, sby_engine, xls×2,
  perf_read_no_sync). **ZERO new failures.** `perf_read_no_sync` (the one nearest this
  change) exercises the REST router's own `run_scoped` in `actions.py` — a different
  code path from my `request_scope.py` edit — and is a pre-existing known failure
  (stale `synced==[]` vs lint's `mutates=True`), independent of this change. Dirtied
  fixtures restored (`git checkout -- tests/fixtures/ test_sby_output.txt`).

## Deploy / confirmation

Not deployed (orchestrator batches). Note: a naive `deploy HEAD` would ship the
unreviewed Wave 11 backend alongside F2 (see FINDINGS F9 rev-00060 exclusion) — F2
should go out as a minimal overlay (`request_scope.py` + `mcp_server.py`) onto the
current live base, or after Wave 11 backend is gated. Before/after `[CODEX-TIMING]`
measurement (server already instrumented) is a post-deploy live-Codex-run leg.
