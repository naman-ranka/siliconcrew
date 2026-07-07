# Codex cold-start (~11s time-to-first-token) — attribution & instrumentation

**Question:** the `[CODEX-TIMING] elapsed_setup` bucket is live-measured at **10.96s**
(rev 00060/00063, reports/explore2-codex.md). Where does it actually go? We knew only
the total (~11s) and that `import mcp_server` ≈ 2.3s on a warm box. This report splits
it with evidence, adds sub-timers so the hosted-only pieces fall out of the next
deploy's logs, and recommends quick-cuts vs. warm-keep.

**Method.** (1) Read the code path `codex_runtime.run_turn` → `codex_engine.stream_turn`
→ (app-server) → cold-spawned `python mcp_server.py --transport stdio` →
`RTLDesignMCPServer.__init__`. (2) Added labelled `[CODEX-TIMING] event=coldstart_*`
sub-spans (log-only, additive — see "Instrumentation" below). (3) Measured everything
locally measurable: `python -X importtime -c "import mcp_server"`, a clean import-timer
run, and direct timing of `SessionManager(...)`/`_resolve_identity()`. Hosted-only
costs (Cloud SQL DDL, WorkOS JWKS, the OpenAI app-server binary) cannot be measured in
this container — no live Postgres/WorkOS/codex creds — and are explicitly marked
"needs-hosted-run"; the new sub-timers capture them on deploy.

---

## What `elapsed_setup` spans

`stream_turn` starts `setup_start` at the top and logs `sdk_thread_ready
elapsed_setup` right after the thread is ready (codex_engine.py:324, :364). Between
those two points:

```
setup_start
  ├─ check_available()          (import openai_codex — already warm in-process, ~0)
  ├─ _prepare_paths()           (mkdir per-turn dirs — ms)
  ├─ _sdk_config()              (build config_overrides — ms)
  ├─ async with sdk_factory()   ►►► coldstart_appserver_enter  (NEW)
  │       launches the OpenAI Codex app-server binary AND, because our MCP server
  │       is required=true, cold-spawns `python mcp_server.py` and waits for it.
  │       That child pays, once, INSIDE this span (or thread bring-up, deploy tells):
  │         • coldstart_import        (b) heavy module import   (NEW, mcp_server.py)
  │         • coldstart_init_schema   (c) SessionManager+DDL     (NEW)
  │         • coldstart_identity      (d) token/JWKS verify      (NEW)
  │         • coldstart_owns_session      bound-session DB check (NEW)
  │         • coldstart_wiring            apply_platform_wiring  (NEW)
  ├─ (login_api_key)            ►►► coldstart_login             (NEW, BYOK only)
  └─ thread_start/thread_resume ►►► coldstart_thread_bringup    (NEW)
sdk_thread_ready  (elapsed_setup logged here, unchanged)
```

The two `codex_engine` sub-spans (`coldstart_appserver_enter`, `coldstart_thread_bringup`)
partition `elapsed_setup` at the coarse level; the five `mcp_server` sub-spans decompose
what the cold MCP child spends internally. Together they fully attribute the 10.96s.

---

## Attribution table

| # | Component | Status | Value / bound | Evidence | Fix that targets it |
|---|---|---|---|---|---|
| a | **OpenAI Codex app-server binary launch** (`async with sdk_factory`) | needs-hosted-run | unknown — sized by `coldstart_appserver_enter` minus the MCP child's internal spans | codex_engine.py:331; no codex binary/creds locally | **warm-keep** (4C real fix) — inherent per cold spawn |
| a′ | **MCP child spawn + ready wait** (part of the same `async with` if app-server starts required servers eagerly) | needs-hosted-run | contains b+c+d+owns+wiring below | `required=true`, `startup_timeout_sec=20` (codex_engine.py:456-457) | warm-keep removes it; quick-cuts shrink its internals |
| b | **Python cold import** `import mcp_server` (LangChain/engine/mcp stack) | **measured-local** | **1.59s** clean (warm FS); **2.06s** under importtime; ~2.3s reported. Cold Cloud Run container FS ⇒ higher | `coldstart_import` timer; importtime rollup below | quick-cut: **lazy/trim imports** (bounded — see below) |
| c | **`SessionManager(...)` → `init_schema()` DDL** | **local floor + needs-hosted-run** | sqlite: **~15–31ms** (negligible). Hosted Cloud SQL: connect + 6 DDL round-trips — **needs deploy** (est. 0.3–1.5s) | local timing (5×); metadata_store.py:527-586 (3×CREATE TABLE + ALTER + 2×CREATE INDEX) | quick-cut: **skip init_schema when already provisioned** |
| d | **`_resolve_identity()` token/JWKS verify** | **local floor + needs-hosted-run** | self-host: **~0ms** (no token, trusted local). Hosted: cold JWKS network fetch — **needs deploy** (est. 0.1–0.5s) | local timing (5×); mcp_server.py:221-229 → auth_engine.authenticate | quick-cut: **reuse caller's already-resolved identity** |
| e | **bound-session `owns_session()`** | local floor + needs-hosted-run | sqlite ~0. Hosted: 1 Cloud SQL query on a fresh (unpooled) connection — needs deploy (est. 50–200ms) | mcp_server.py:246-249; no pool (metadata_store.py:520-525, latency §3) | connection-pool the MCP child (latency §3) |
| f | **`apply_platform_wiring()`** | measured-local | ~0 (idempotent wiring) | mcp_server.py:254-258 | n/a |
| g | **thread_start / thread_resume** | needs-hosted-run | sized by `coldstart_thread_bringup` | codex_engine.py:344-361 | warm-keep (resume is cheaper than start) |

**Locally we can firmly attribute only (b), the ~1.6–2.3s Python import.** (c), (d),
(e) are ~0 on self-host/sqlite by construction — their real cost is the hosted Cloud
SQL / WorkOS round-trips, which is exactly what the new timers will size on deploy. The
remaining **~8.5s of the 10.96s is not Python import** — it is the OpenAI app-server
binary launch + MCP-child spawn wait + hosted DB/identity round-trips + thread
bring-up, all codex/hosted-only.

---

## Import profile — ranked (`python -X importtime -c "import mcp_server"`)

Top 15 by **self** time (ms), and the top-level-package rollup. Total self across 1120
imports ≈ **1650ms** (wall with importtime overhead 2.06s; clean 1.59s here).

```
 self_ms    cum_ms  module
   201.6     218.5  mcp.types
    76.1     470.3  src.tools.wrappers        ← pulls the whole LangChain/LangGraph stack
    48.1      48.1  langsmith.schemas
    47.8      47.8  langchain_core.runnables.graph
    42.6      46.0  rich.color
    20.8      22.6  starlette.datastructures
    14.6     136.8  langgraph.prebuilt.chat_agent_executor
    13.6      18.7  jsonschema_specifications
    10.9      10.9  rfc3986_validator
    10.5      14.3  pydantic_core.core_schema
     9.2       9.2  urllib3.util.url
     9.2       9.2  annotated_types
     8.8      21.7  tornado.log
     8.0       8.0  mcp.shared.auth
     7.9       7.9  langchain_core.tracers.schemas

Top-level rollup (summed self, ms):   Biggest subtrees (cumulative, ms):
   310.6  mcp                              879.6  mcp  (mcp.server 879.7, mcp.client.session 595.4)
   159.7  langchain_core                   470.3  src.tools.wrappers
   117.7  src                              279.0  langchain_core.callbacks.manager
    95.6  rich                             218.5  mcp.types
    88.4  pydantic                         214.1  mcp.client.experimental.task_handlers
    70.0  langgraph
    66.7  langsmith
```

**Read of the import cost:** the single biggest chunk is the **`mcp` library itself**
(~310ms self, ~880ms cumulative across `mcp.server` + `mcp.client.session` +
`mcp.client.experimental.task_handlers`) — structurally required by an MCP server and
hard to trim. The **LangChain/LangGraph/langsmith stack** pulled through
`src.tools.wrappers` (cum 470ms; ~160+70+67ms self across the three) is the realistic
lazy-import target, plus `rich` (~96ms) and `langsmith`. A lazy/trim quick-cut therefore
plausibly recovers **~0.5–0.8s of the ~1.6–2.3s import**, not more — the mcp core is a
floor.

---

## Instrumentation added (log-only, additive, zero behavior change)

- **`src/agents/codex/codex_engine.py`** — `_emit_codex_timing()` helper (guarded,
  never raises) + three sub-spans in `stream_turn`: `coldstart_appserver_enter`
  (brackets `async with sdk_factory(...)`), `coldstart_login` (BYOK login), and
  `coldstart_thread_bringup` (brackets thread_start/resume). The existing
  `sdk_thread_ready elapsed_setup` and `sdk_turn_issued` lines are unchanged.
- **`mcp_server.py`** — `_emit_coldstart()` helper (guarded; `CODEX_COLDSTART_TIMING=0`
  to silence) + `coldstart_import` at module-import completion, and inside `__init__`:
  `coldstart_init_schema`, `coldstart_identity`, `coldstart_owns_session`,
  `coldstart_wiring`, `coldstart_init_total`.

All monotonic diffs, all `[CODEX-TIMING]`-prefixed to Cloud Run stderr. No control flow,
import order, or `startup_timeout` budget changed. Verified: backend gate at the exact
9-failure baseline; `test_codex_runtime.py` (8) + `test_codex_engine_env.py`/
`test_synth_codex_round2.py` (13) pass — those drive `stream_turn` through a fake SDK,
so the new spans execute and the async generator is intact.

---

## Recommendation: quick-cuts help turn 1 but are **not** sufficient — warm-keep is the real fix

The Python import (the one thing fully proven locally) is only ~1.6–2.3s of the 10.96s.
Even the best case of the quick-cuts — skip `init_schema` (c), reuse identity (d), trim
imports (b) — removes at most roughly **~1s of DB/identity hosted round-trips + ~0.5–0.8s
of import** ≈ **1.5–2.5s off turn 1**, and touches *only* the MCP-child internals. It
does nothing for the OpenAI app-server binary launch (a), the MCP-child spawn/ready wait,
or thread bring-up (g) — and it helps **turn 1 only**. Every later turn still throws the
warm subprocess away and pays the whole thing again. The structural win is **warm-keep
(4C real fix)**: hold the app-server + MCP child across a thread so turns 2+ pay ~0.

**Do the quick-cuts anyway** (they are cheap, safe, and shrink turn 1), but scope the big
win as warm-keep.

### The ONE thing to confirm on the next deploy
How `elapsed_setup` splits between **`coldstart_appserver_enter`** vs
**`coldstart_thread_bringup`**, and within the former, how much is the MCP child's
`coldstart_import` + `coldstart_init_schema` + `coldstart_identity`. That single split
decides it:
- if `coldstart_appserver_enter` is dominated by the MCP-child internals (import + hosted
  DDL/identity), the quick-cuts move the number materially;
- if it is dominated by the **app-server binary launch** itself, or by
  `coldstart_thread_bringup`, then only **warm-keep** helps and the quick-cuts are a minor
  turn-1 trim.

Grep the next Codex spec→GDS run's logs for `[CODEX-TIMING] event=coldstart_` and read
the split.
