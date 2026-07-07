# Codex latency — code profile (read-only, no live run)

**Question:** why are the Codex agent's tool calls + inference noticeably slower
than the native LangChain architect? **Answer:** the Codex path pays two costs the
native path does not — (1) a **full-workspace GCS upload on *every* MCP tool call**,
including read-only ones, and (2) a **cold-spawned MCP server subprocess per user
message** (heavy import + Postgres schema DDL + token verify + no connection pool).
Both are architectural asymmetries, both are in code, and the biggest one is a small
fix.

Traced end-to-end: `codex_runtime.py` → `codex_engine.py` → `mcp_server.py` call
path → `request_scope.py` → `workspace_provider.py` / `metadata_store.py`. Compared
against the native WS chat path in `api.py`. No live MCP/Codex calls made.

Good news up front: the server already has `[CODEX-TIMING]` instrumentation
(`codex_runtime.py:98-227`, `codex_engine.py:364-381`) that buckets *setup*
(`sdk_thread_ready elapsed_setup`), *turn issue* (`sdk_turn_issued`), and
*per-tool-call* elapsed. The browser confirmation run should grep Cloud Run logs
for `[CODEX-TIMING]` to get exact numbers per bucket — the analysis below predicts
where they'll be large.

---

## How a Codex turn runs (the cost structure)

Native architect: LangGraph in-process; one WS turn binds ONE session scope
(`api.py:1322-1333` — `workspace_for` once on connect, `set_current_session` for the
whole connection) and tools resolve that bound workspace in-process. No per-tool
GCS/subprocess/DB cost.

Codex: a **different brain** — the OpenAI Codex SDK app-server running as a
subprocess, reaching SiliconCrew tools only over **MCP** (`mcp_server.py` spawned in
stdio bound-session mode). Per user message (`CodexRuntimeHandler.run_turn`):

- `engine = self._engine_factory()` then `engine.stream_turn(...)` →
  `async with sdk_factory(config=config) as codex:` (`codex_engine.py:331`) spawns a
  **fresh Codex app-server subprocess every turn**.
- Its `config_overrides` (`codex_engine.py:435`) register our MCP server:
  `python mcp_server.py --transport stdio --codex-tools --bound-session <sid>`,
  `startup_timeout_sec=20` — so the app-server **cold-spawns a Python MCP subprocess**.
- Each tool the model calls is a stdio JSON-RPC round-trip into that MCP subprocess →
  `mcp_server.call_tool` → `run_in_session(tool.invoke, ...)` (`mcp_server.py:882`).

So the Codex path adds, versus native: subprocess IPC per tool, a cold MCP process
per turn, and — the killer — a per-tool-call session scope with a write-back.

---

## Ranked latency sources

### 1. HIGH — Full-workspace GCS tar+upload on EVERY MCP tool call, incl. read-only (per-tool-call)

`mcp_server.call_tool` runs every tool through `run_in_session`
(`mcp_server.py:882`), which enters a fresh `session_request_scope` **per call**
(`request_scope.py:78`). Its `finally` unconditionally calls `provider.sync()`
(`request_scope.py:49-53`), and in hosted/cloud mode that is
`CloudWorkspaceProvider.sync` (`workspace_provider.py:325-338`):

```python
def sync(self, session_id):
    ...
    self._store.put_tree(key, scratch)   # tar the ENTIRE workspace + upload to GCS
    new_gen = _store_generation(...)      # + another GCS metadata GET
```

`put_tree` (`workspace_provider.py:168-171`) tars the whole scratch workspace and
uploads it to GCS. Entry (`workspace_for`, `:272-298`) also does a GCS generation
GET each call (the F3 generation-skip avoids the *download*, but nothing skips the
*upload*).

**This fires on every tool call, unconditionally — including pure reads**
(`read_file`, `list_files_tool`, `get_manifest`, `read_stage_report`,
`get_synthesis_status`/`_metrics`, `get_*_summary`, `search_logs_tool`,
`compare_pd_runs`). A design loop is mostly reads, so most calls pay a full workspace
tar + GCS PUT for nothing. For a real RTL+synthesis workspace (RTL, TBs, VCDs, ORFS
run dirs with reports/GDS) that is easily hundreds of ms to multiple seconds **per
call**.

**Native does NOT do this** — it binds one scope per connection and syncs only at
deliberate points (`api.py:2175` report gen; the action router `:2340-2346`), not
per tool. This asymmetry alone plausibly explains "the tool calls Codex does are
very slow."

**Cheapest high-impact fix:** only sync after **mutating** tools.
`src/api/tool_catalog.py:84` already defines `MUTATING_TOOLS` (and `ASYNC_TOOLS`).
In `call_tool`, gate the write-back: run read-only tools with sync suppressed and
call `provider.sync()` only when `name in MUTATING_TOOLS`. Concretely, give
`run_in_session`/`session_request_scope` a `sync: bool` param (default True for
back-comp) and pass `sync=(name in MUTATING_TOOLS)`. Removes the full GCS upload from
the majority of Codex tool calls; zero behavior change for writes. Also drop the
redundant post-`put_tree` generation GET on the sync path. ~15-20 lines, no schema
change. **Do this first.**

### 2. HIGH — Cold MCP subprocess per turn: heavy import + Postgres schema DDL + token verify (per-turn setup)

Because a fresh app-server is created per turn (§above), the MCP subprocess is
**cold-started on every user message** (`startup_timeout_sec=20` budget). Its
`RTLDesignMCPServer.__init__` (`mcp_server.py:169-215`) pays, every spawn:

- **Python import of the whole tool stack** — `mcp_server` imports
  `src.tools.wrappers` (LangChain tools, engines, etc.); multi-second cold import.
- **`SessionManager(...)` → `init_schema()`** (`session_manager.py:28-29`). On
  Postgres that runs full DDL on a **fresh connection every spawn**
  (`metadata_store.py:527-586`: `CREATE TABLE IF NOT EXISTS`×3 + `ALTER TABLE … ADD
  COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`×2 + commit) — idempotent, but
  a Cloud SQL connect + 6 DDL round-trips on the hot path of *every turn*.
- **`_resolve_identity()`** (`mcp_server.py:194,217-225`) → `auth_engine.authenticate`
  → WorkOS/Google token verify. On a cold process the verifier's JWKS cache is empty,
  so it's a network fetch per spawn.
- `apply_platform_wiring()` (`:211-212`).

This is the `[CODEX-TIMING] sdk_thread_ready elapsed_setup` bucket — seconds before
the first token, every turn. It's the "latency and inference speed feels slow"
symptom (time-to-first-token), distinct from per-tool cost.

**Cheapest fixes (incremental):**
- Skip `init_schema()` when a cheap sentinel says the schema already exists (e.g. an
  env flag set by the parent app that already ran DDL at boot, or a one-time
  process-guard) — removes the connect + 6 DDL round-trips from the spawn hot path.
- Set `PYTHONDONTWRITEBYTECODE`/ensure warm bytecode; trim the MCP import surface so
  cold import is cheaper.
**Real fix (larger, flag as follow-up):** keep the Codex app-server + its MCP child
**warm across turns** for a thread (don't recreate `AsyncCodex` per `run_turn`); the
current per-turn `async with sdk_factory(...)` throws away a warm subprocess every
message. That removes the cold-spawn cost entirely but is a lifecycle change worth
its own small plan.

### 3. MEDIUM — No Postgres connection pooling in the MCP subprocess (per-tool-call, additive)

`PostgresMetadataStore._connect()` (`metadata_store.py:520-525`) does
`psycopg.connect(self._dsn)` **per call** — no pool. The app's pooled checkpointer/
metadata connections do not exist in the subprocess. Every tool that touches session
metadata (`owns_session`, stats updates, thread lookups, logging reconciliation)
opens a fresh Cloud SQL connection = TLS + Cloud SQL connector handshake (~50-200ms)
each. Additive on top of §1 for every metadata-touching call.

**Cheapest fix:** reuse one long-lived connection (or a tiny `psycopg_pool.
ConnectionPool`) in `PostgresMetadataStore`, so a subprocess reuses a connection
across its turn's calls instead of reconnecting each time. ~10-20 lines, contained to
one class.

### 4. LOW (inherent) — stdio IPC + thread hop per tool call

Each tool call is a `loop.run_in_executor` thread hop (`request_scope.py:75-81`) plus
a stdio JSON-RPC round-trip to a separate process. Inherent to the MCP-subprocess
design and small next to §1-§3; note it, don't optimize it yet.

---

## Not a factor (checked)

- Auth token refresh is **not** per-tool-call — identity is resolved once at
  subprocess init (`mcp_server.py:194`), not per call. (It *is* part of §2's per-turn
  setup.)
- No obvious sync `requests.*` inside an async handler on the tool hot path; the
  blocking work (GCS, psycopg) is correctly pushed to a worker thread via
  `run_in_executor` — but that just moves the wall-clock cost off the loop, it
  doesn't remove it, and §1 is the wall-clock cost.

## Suggested confirmation (browser run, later)

Grep Cloud Run logs for `[CODEX-TIMING]` during a Codex spec→GDS run:
`elapsed_setup` confirms §2; per-`tool=…elapsed=` lines confirm §1 (expect read-only
tools like `read_file`/`get_manifest` to still show ~seconds — that's the GCS upload).
Compare a read_file elapsed on an empty vs a large (post-synthesis) workspace to size
the §1 win.
