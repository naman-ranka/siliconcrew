# Tenancy sweep — all MCP tools + REST /invoke + in-memory registries

**Scope:** after F1 (MCP `list_sessions_tool`/`delete_session_tool` silently forgot to
pass `user_id`), red-team every other session-id / run-id-taking surface for the same
class of bug — missing owner scoping, cross-tenant read/write/destroy, in-memory
registries keyed by bare ids, and the resource surface. Read-only; no code changed.

**Result: CLEAN. No new cross-tenant holes.** F1's three defects were the only ones,
and the F1 stopgap now deployed (list/delete scoping + a pre-dispatch
`owns_session(current_session)` gate) closes them. Every other tool surface either
carries **no tenant-selecting argument at all** (workspace is bound, not passed) or
scopes correctly through `require_owned`. Two CLAUDE.md sharp edges this sweep
targeted are already fixed in code. Evidence below, keyed to the ranked summary.

---

## 1. MCP regular + run_id tools — no independent tenant surface; now fully gated (SAFE)

Non-session-management tools dispatch through `TOOL_REGISTRY` bound to
`self.current_session` (`mcp_server.py:872-896`): `active_workspace =
get_workspace_path(active_session)`, then `run_in_session(active_session, ...)`. The
wrappers resolve their workspace **only** from the task-local `get_workspace_path()`
(`src/tools/wrappers.py:29` and every tool body: `:96,111,135,187,225,237,267,311,
350,370,429,446,459,469,481,492,503,513,524,541,803,834`; `waveform_tool:446`,
`schematic_tool:760`, `save_metrics_tool:803`, `generate_report_tool:834`).

**No wrapper accepts a `session_id`, `workspace`, or absolute-path argument** that
could redirect it to another tenant. The run-id family — `get_synthesis_status`,
`get_synthesis_metrics`, `read_stage_report`, `get_route_drc_summary`,
`get_cts_summary`, `get_congestion_summary`, `compare_pd_runs`, `search_logs_tool`,
`retry_pd`, `wait_for_synthesis`, `generate_report_tool`, `save_metrics_tool`,
`waveform_tool` — each takes `run_id`/filename and resolves it **inside**
`get_workspace_path()`. A `run_id` can only ever name a run under the currently-bound
session's `synth_runs/`; there is no argument by which user B names user A's run.

**Failure sequence that WOULD have existed (now closed):** the only way to point these
at a foreign session was to make `current_session` foreign. `set_active_session` is
owner-checked (`mcp_server.py:746`), so the only remaining vector was the F1 #3
shared-instance race (one process-global `current_session` multiplexing all hosted
users). **That is now gated:** `call_tool` re-verifies ownership before every regular
dispatch — `mcp_server.py:857-869`:

```python
if (self._hosted and not self.bound_session
        and not self.session_manager.owns_session(self.current_session, self._scoped_user_id())):
    return [TextContent(... "No active session for this user. Select one with set_active_session.")]
```

So even if a concurrent tenant flips `current_session` between B's
`set_active_session` and B's tool call, the dispatch is refused. **Covered by the
deployed F1 gate.** (Durable fix — request-scope `current_session` off the shared
instance, REVIEW_FINDINGS P0 #1 — remains the recommended follow-up; the gate is
defense-in-depth, not the structural fix.)

`get_synthesis_job` / `get_stage_status` (named in the task) are **not** in the
current source — the live name is `get_synthesis_status`, already covered. Those names
are advertised by the **codex-bound** MCP server, which is single-tenant *by
construction*: `bound_session` ownership is verified at init (`mcp_server.py:205-208`)
and any tool given `session_id != bound_session` is refused (`:690-698`). No
cross-tenant vector regardless of tool naming; bound mode is intentionally exempt from
the pre-dispatch gate because it is already constrained to one owner-validated session.

## 2. REST `/invoke` + all `/runs/{run_id}` handlers — owner-scoped; containment is caller-scoped (SAFE)

Every `build_actions_router` handler (`src/api/actions.py:380`) calls
`require_owned(session_id, identity)` **before** touching the workspace — `/manifest`
(`:465,472`), `/files` (`:480`), `/code` (`:507`), `/lint` (`:526`), `/simulate`
(`:576`), `/synthesize` (`:618`), `/activity` (`:696`), `/dir` (`:712`), `/tools`
(`:738`), `/invoke` (`:752`), `/workbench` (`:807`), `/runs` (`:838`), `/runs/compare`
(`:855`), `/runs/{run_id}` (`:887`), `/runs/{run_id}/status` (`:938`),
`/runs/{run_id}/retry` (`:945`), `/runs/{run_id}/pin` (`:983`). `require_owned` →
`_require_owned` 404s a non-owner via the metadata store `_owner_clause`, and every
`run_id` is then resolved strictly within that owned workspace
(`get_run_dir(workspace, run_id)`, `get_synthesis_metrics(workspace=..., run_id=...)`).
`/invoke` additionally re-checks the sign-in capability flag (`:762`).

**`enforce_file_containment` is confirmed caller-scoped** (the CLAUDE.md point). On
`/invoke`, `work()` runs inside `run_scoped(session_id, workspace, ...)` where
`workspace = require_workspace(session_id)` — the very path `require_owned` just
validated. That call chains `validate_and_execute(name, workspace, args)`
(`tool_catalog.py:209`) → `enforce_file_containment(workspace, args)`
(`:197-206`), which rejects any `filename`/`file_path`/`*_file(s)` arg escaping
**that** workspace (`is_within(workspace, ...)`), and the wrapper's own
`get_workspace_path()` is bound by `run_scoped` to the **same** caller-owned
workspace. Both the containment check and the tool's resolution point at the caller's
owned workspace — never "a" workspace, never another tenant's. **No cross-tenant run
read/write/retry/pin/destroy via REST.**

## 3. In-memory synth registry keyed by (workspace, run_id) — sharp edge ALREADY FIXED (SAFE)

`synthesis_manager._JOBS / _POLL_CACHE / _POLL_BACKOFF_STATE`
(`synthesis_manager.py:288-290`) are keyed through `_job_key(workspace, run_id)`
(`:293-303`) → `f"{abspath(workspace)}::{run_id}"`, with the docstring stating the
exact invariant ("two tenants' synth_0001 must never share a _JOBS/_POLL_CACHE/…
slot"). All accessors pass the workspace (`:2016, :2125, :2157`). Because a hosted
workspace path embeds the globally-unique `session_id` (PRIMARY KEY), the key is
tenant-scoped: a bare-id lookup **cannot** return another tenant's run object. A
workspace-less caller falls back to the bare id, which then simply *misses* the scoped
entry (safe degradation). **No collision across owners.**

## 4. Resource surface (`list_resources`/`read_resource`) — scoped, no bypass (SAFE)

Both paths route session enumeration through `_resource_sessions()`
(`mcp_server.py:262-271`, owner-scoped in hosted / bound-session in Codex) and gate
every session/file read with `_assert_session_readable()` (`:273-282`) BEFORE touching
the workspace (`:391,421`), plus an exact-or-under realpath containment check on file
reads (`:398-403`). `rtl://sessions` lists only `_resource_sessions()` (`:358-360`).
No branch reaches a workspace or metadata without first passing the owner/bound gate.

## 5. Other in-memory maps — not tenant data (SAFE)

`sim_manager._PROVENANCE_CACHE` (`sim_manager.py:33`) is keyed only by
`"repoCommit"` / `"iverilogVersion"` (`:103,114,120,130`) — process-wide tool-version
provenance, no per-tenant content. No leak.

## Adjacent, NOT tenancy — one capability gap

`update_manifest` is in `MUTATING_TOOLS` but missing from the MCP `_PROTECTED_TOOLS`
sign-in gate (`mcp_server.py:231`; already REVIEW_FINDINGS P2). A hosted **anonymous**
identity could mutate the manifest — a capability gap, **not** cross-tenant (still
bounded to `current_session`, which the pre-dispatch gate owner-validates). Optional
one-liner: add `"update_manifest"` to `_PROTECTED_TOOLS`.

---

## Test coverage note

`tests/test_tenancy_redteam.py` asserts store-level `get_all_session_rows`
disjointness per owner; the F1 fix adds the MCP list/delete + pre-dispatch-gate
regressions. No new tenancy tests are needed for the surfaces swept here because they
carry no tenant-selecting argument — the guard is structural (workspace binding),
covered by `tests/test_session_context_propagation.py`.
