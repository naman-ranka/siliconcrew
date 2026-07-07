# Small backend fixes — F10 + F9c

Branch: `claude/overnight-showcase`. File fence honored: only `mcp_server.py`,
new test files under `tests/`, and this report were touched. Baseline backend
gate = exactly 9 known failures; after these changes still exactly 9 (zero new).

---

## ITEM 1 — F10: `update_manifest` capability gating (already closed; now locked)

### Finding as written (stale)
FINDINGS.md F10: "`update_manifest` is in MUTATING_TOOLS but missing from MCP
`_PROTECTED_TOOLS` (mcp_server.py:231) → a hosted ANONYMOUS identity could mutate
the manifest ... One-liner: add `update_manifest` to `_PROTECTED_TOOLS`."

### What the code actually shows (verified before changing anything)
The premise is out of date. `mcp_server.py`'s `_PROTECTED_TOOLS` is no longer a
hand-maintained list — since commit **c072d5c** (schema-driven tool platform) it
aliases the shared set:

- `mcp_server.py:235` → `_PROTECTED_TOOLS = _SHARED_PROTECTED_TOOLS`
- `_SHARED_PROTECTED_TOOLS` is imported from `src/api/tool_catalog.PROTECTED_TOOLS`
  (`mcp_server.py:131-135`)
- `src/api/tool_catalog.py:71-77` — `PROTECTED_TOOLS` already contains
  `"update_manifest"` (added in c072d5c, same commit that introduced the alias).

Runtime confirmation:
```
class _PROTECTED_TOOLS is shared PROTECTED_TOOLS: True
update_manifest in gate: True
update_manifest advertised over MCP: True
```

The gate in `call_tool` (`mcp_server.py:877-881`) therefore already fires for
`update_manifest`: it is in the `"manifest"` category (not `"synthesis"`), so it
authorizes `Action.SAVE`. An anonymous identity is refused because
`ANONYMOUS_ALLOWED = {LINT, SIMULATE}` (`src/platform_engines/identity.py:30`,
`authorize` at :60-70). **The F10 exposure was closed the moment PROTECTED_TOOLS
was unified; it is not reachable in current code.** No code change was correct or
needed here — the finding was written against a pre-c072d5c mental model.

### What I did instead: lock it so it can't silently reopen
Added `tests/test_mcp_protected_policy.py` (F2-style drift guard):

1. `test_update_manifest_is_capability_gated` — asserts `"update_manifest"` is in
   the real `RTLDesignMCPServer._PROTECTED_TOOLS`. Direct F10 regression.
2. `test_mutating_mcp_tools_are_protected_or_explicitly_open` — the broader
   invariant. It does NOT hold verbatim: `simulation_tool` and
   `run_isolated_simulation` are in `MUTATING_TOOLS` but legitimately unprotected
   (the anonymous trial explicitly covers sim). So, per the fallback the task
   allowed, the test asserts every MUTATING tool exposed over MCP is either
   PROTECTED **or** in a small, documented `_INTENTIONALLY_UNPROTECTED_MUTATORS`
   allowlist `{simulation_tool, run_isolated_simulation}`. Any new mutating tool
   added without a protection decision trips this test.

### Evidence the guard catches the regression
There is no in-repo "pre-fix" state to `git stash` (the fix predates the
finding). I proved the guard's sensitivity by reconstructing the pre-fix set
(`update_manifest` removed) and running the assertion:
```
AssertionError: ASSERTION FAILS (as expected on pre-fix): update_manifest missing from gate
exit=1
```
So had `update_manifest` never been added / were it removed, the test fails
loudly.

Both tests pass on current code (`python -m pytest tests/test_mcp_protected_policy.py -q` → 2 passed).

---

## ITEM 2 — F9c: the post-restart `-32602 "Invalid request parameters"` lie

### Root cause (fully traced; the mis-map is in the vendored SDK)
The `-32602` string `"Invalid request parameters"` is emitted in exactly one
place that matches the report: `mcp/shared/session.py:385-395`. It is the base
session receive loop's `except Exception` handler, which wraps
`await self._received_request(responder)` (:376) and hardcodes
`code=INVALID_PARAMS, message="Invalid request parameters"` for **any** exception
raised there — it cannot tell a genuine bad-argument error from anything else.

What raises inside that block after a deploy:
`mcp/server/session.py:191-193` —
```python
case _:
    if self._initialization_state != InitializationState.Initialized:
        raise RuntimeError("Received request before initialization was complete")
```
A `ServerSession` starts `NotInitialized` unless constructed with
`stateless=True` (`server/session.py:96-97`), and only becomes `Initialized`
after an `initialize` handshake (:187).

Our deployment wiring creates a **session-less** Streamable HTTP transport
(`mcp_session_id=None`) but runs the server with the **default `stateless=False`**:
- Hosted mount: `api.py:411-430` builds `get_http_app()` (transport
  `mcp_session_id=None`, `mcp_server.py:1013-1015`) then
  `mcp_server.server.run(streams[0], streams[1], create_initialization_options())`
  — no `stateless=True`.
- Standalone `--transport http`: same shape at `mcp_server.py:1108-1151`.

So a single long-lived `ServerSession` sits in `NotInitialized`. On a Cloud Run
revision swap the claude.ai connector reuses its old session and sends
`tools/call` WITHOUT re-handshaking (see F15) → the fresh process's session
raises the pre-init `RuntimeError` → the SDK blanket-maps it to `-32602`. The
client is told "Invalid request parameters" for what is really "server restarted,
please reconnect." That is the lie, and it persists until a manual reconnect
(F15).

`_handle_request` in `server/lowlevel/server.py:772-775` proves the flip side:
when OUR handler (`call_tool`) raises, the SDK maps it to `code=0`, never
`-32602`. And `call_tool` already catches tool errors and returns them as
`TextContent` (successful result). **So no SiliconCrew handler path produces
`-32602`; the only trigger is the pre-init session-state raise above.** There is
nothing to remap inside `call_tool`.

### The correct server-side fix (better than remapping)
The SDK's own `StreamableHTTPSessionManager` pairs a session-less transport with
`app.run(..., stateless=True)` (`server/streamable_http_manager.py:181-185`), and
FastMCP passes `stateless=self.settings.stateless_http`
(`server/fastmcp/server.py:961`). A `stateless=True` session starts
`Initialized`, so a post-restart request is treated as post-init and **just
works** — no spurious `-32602`, no re-handshake required. This is strictly better
than remapping the error to `-32000`: the request succeeds instead of failing.

Applied (in fence): `mcp_server.py` `run(transport="http")` now calls
`self.server.run(..., stateless=True)` to match its session-less transport
(with a comment explaining the pairing and F9c). This fixes the standalone
self-host remote-MCP path.

### STOPPED (out of fence) — the hosted one-liner
The hosted path that the finding is actually about runs the session in
**`api.py:425-429`**, outside the `mcp_server.py`/tests fence. The identical fix
belongs there:
```python
mcp_task = asyncio.create_task(
    mcp_server.server.run(
        streams[0], streams[1],
        mcp_server.server.create_initialization_options(),
        stateless=True,          # <-- add: match get_http_app()'s session-less transport
    )
)
```
Per the fence I did not edit `api.py`; this is the documented, ready one-liner.
(Note: `stateless=True` removes init-state enforcement, appropriate precisely
because the transport is session-less — there is no per-connection session
identity to protect. The SSE path is left stateful: each SSE connection is its
own session and re-handshakes on reconnect, so it is not affected.)

### Reproduction / regression test
`tests/test_mcp_preinit_error_mapping.py` reproduces the mechanism with in-memory
streams (no live probing; async via `asyncio.run`):
- `test_default_session_raises_preinit_error_that_maps_to_invalid_params` —
  `stateless=False` + pre-init request → the exact `RuntimeError(... before
  initialization was complete)` the SDK maps to `-32602`.
- `test_stateless_session_tolerates_preinit_request` — `stateless=True` → no
  raise (the fix direction).
- `test_preinit_runtime_error_is_caught_as_generic_exception` — pins WHY it is a
  lie: the failure is not a `ValueError`/`TypeError` argument error, yet the
  SDK's broad `except Exception` reports it as `-32602`.

"Fails pre-fix": the first/third tests assert the buggy behavior is real (they
demonstrate the pre-fix `-32602` path); the second asserts the fixed pairing
eliminates it. The `run(transport="http")` branch itself starts uvicorn and is
not unit-testable in isolation, so the tests validate the exact session-level
mechanism the one-line change flips, which is the load-bearing part.

All three pass (`python -m pytest tests/test_mcp_preinit_error_mapping.py -q` → 3 passed).

---

## Gates
- `python -m pytest tests/test_mcp_protected_policy.py tests/test_mcp_preinit_error_mapping.py -q` → 5 passed.
- Full backend gate (standard ignores): **9 failed, 686 passed, 8 skipped** —
  the exact known baseline (congestion x2, lint norm_file, llm_factory, orfs_job
  stage_in, perf_read_no_sync, sby_engine, xls x2). Zero new failures.
- `git checkout -- tests/fixtures/ test_sby_output.txt` run after the suite.
