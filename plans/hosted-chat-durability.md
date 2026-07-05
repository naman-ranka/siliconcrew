# Wave 10 — Hosted chat durability (Postgres checkpointer)

Status: IMPLEMENTED + reviewed (adversarial pass F1-F4 fixed; commits through the fix push)

## The bug (grounded)

Two stores; only one is durable on hosted:
- Session/thread ROWS → Cloud SQL Postgres (`persistence_engine=postgres`,
  settings.py:173) → survive restart/redeploy/scale. ✅
- Conversation CONTENT (every message) → LangGraph checkpoints in
  `AsyncSqliteSaver` on `state.db` at `~/.siliconcrew` (api.py:25,58-60,312)
  → ephemeral, per-instance. The only mounted volume is `/cloudsql`
  (main.tf:246); there is NO persistent volume for state.db. ❌

Consequence on the deployed app: thread list survives, but opening a thread
after any restart/redeploy shows an EMPTY conversation; and with
`containerConcurrency=1` + `max_instances=10`, even without a restart the
next turn can hit a different instance whose state.db never saw the history.

## The fix (one seam)

The checkpointer is the ONE component still on ephemeral local disk. Move it
to the database already running — this finishes the Postgres migration
already done for metadata, it is not a new migration. `open_checkpointer`
(api.py:299) is already the seam every caller uses (_read_thread_history:870,
WS chat:1251); make it engine-selected on the SAME `persistence_engine` flag
that already picks the metadata store.

- **Self-host / local: UNCHANGED.** SQLite per-call (AsyncSqliteSaver on
  state.db). Perfect there — one process, real disk. `langgraph-checkpoint-
  postgres` / psycopg imported ONLY in the postgres branch (lazy), so local
  needs no new runtime deps.
- **Hosted: Postgres, pooled, app-scoped.** An async connection pool built
  ONCE in the lifespan; a single shared `AsyncPostgresSaver(pool)`;
  `.setup()` run once at startup (idempotent migrations). `open_checkpointer`
  yields the SHARED saver (pool manages connections) — never a per-turn
  connect/setup.

## Item 1 — Deps + settings

- requirements.txt: add `langgraph-checkpoint-postgres>=2.0.0` and
  `psycopg-pool>=3.2.0` (psycopg itself is already used lazily by the
  metadata store).
- settings.py: add pool sizing env (conservative, scale-to-zero friendly):
  `CHECKPOINT_POOL_MIN` (default 0 — hold no idle connections when idle),
  `CHECKPOINT_POOL_MAX` (default 3). Expose on PlatformSettings.

## Item 2 — Engine-selected checkpointer (api.py)

- Module globals `_CHECKPOINTER` (shared saver, None in sqlite mode) +
  `_CHECKPOINTER_POOL`.
- Lifespan (api.py:324): if `persistence_engine=="postgres" and
  database_url`:
  - `AsyncConnectionPool(database_url, min_size=MIN, max_size=MAX,
    open=False, kwargs={"autocommit": True, "row_factory": dict_row})`;
    `await pool.open()`.
  - `saver = AsyncPostgresSaver(pool)`; `await saver.setup()` (creates the
    checkpoints/checkpoint_blobs/checkpoint_writes/checkpoint_migrations
    tables — idempotent).
  - stash both globals. On shutdown: `await pool.close()`.
  - Wrap in try/except with a loud log: a checkpointer that fails to init
    must fail startup (not silently fall back to ephemeral sqlite in
    production) — fail-fast is the honest behavior.
- `open_checkpointer(db_path)`:
  - postgres mode (`_CHECKPOINTER is not None`): `yield _CHECKPOINTER` — no
    connect, no setup, no close per call. The pool owns lifecycle.
  - sqlite mode: current behavior verbatim (fresh aiosqlite conn + the
    is_alive shim + close in finally).
- No caller changes: `create_architect_agent(checkpointer=memory, …)` and
  `_read_thread_history` keep working — `memory` is just the shared saver now.
  Verify `AsyncPostgresSaver` satisfies the same BaseCheckpointSaver
  interface create_react_agent expects (it does — same base class).

## Item 3 — Delete cascade closes the Wave 9 loose end

Wave 9 left `_purge_local_checkpoints` (session_manager.py) best-effort on
LOCAL sqlite because checkpoints lived there. In postgres mode the session's
thread checkpoints now live in Cloud SQL. Extend the purge: when the metadata
store is Postgres, delete from `checkpoints`/`checkpoint_blobs`/
`checkpoint_writes` WHERE `thread_id = ANY(<the session's thread ids + the
legacy session-id thread>)`, through the metadata store's own connection.
Best-effort, guarded — a purge failure never blocks the session delete.
(Keeps delete honest: Wave 9's cascade already removes chat_threads rows;
this removes the conversation bytes too.)

## Item 4 — Connection budget (docs + sizing, no silent failure)

- Formula (RUNBOOK + a terraform note): `CHECKPOINT_POOL_MAX ×
  backend_max_instances + metadata connect-per-op headroom ≤ Cloud SQL
  max_connections`. Defaults: 3 × 10 = 30 + headroom → recommend Cloud SQL
  `max_connections ≥ 50` (or lower max_instances / pool max). Document that
  db-f1-micro's ~25 default is too low for 10 instances — either raise the
  flag or cap scaling.
- `min_size=0` keeps scaled-to-zero / idle instances from holding
  connections, so the budget is a peak-load ceiling, not an idle cost.

## Item 5 — Optimistic send (native feel; small, safe, separable)

Storage durability makes history *real and instant* on thread-open (one
indexed query over the local Cloud SQL socket, single-digit ms). The one
frontend polish for "native feel": verify the store appends the user's
message to the thread IMMEDIATELY on send (before the WS echo) and reconciles
on server ack; if it already does, no-op this item. Keep it low-risk — do NOT
refactor the WS streaming path.

## Metadata-store pooling — DEFERRED (with rationale)

I am NOT pooling the metadata store in this wave, reversing the earlier lean.
Reason: it is a SYNC path (psycopg.connect), so it needs a SEPARATE sync pool
(ConnectionPool) — a second pool competes for the SAME scarce Cloud SQL
connections. On small tiers a second pool worsens the budget more than
connect-per-op (bursty, short-lived, low-frequency) costs. Pool it as a fast
follow ONCE the Cloud SQL tier / max_connections is sized for it. Documented,
not silently dropped.

## Tests / gates

- pytest (no real Cloud SQL in CI — honest limit; use recording-fakes /
  monkeypatch):
  - open_checkpointer sqlite path yields an AsyncSqliteSaver on a fresh conn
    and closes it (existing behavior unchanged).
  - postgres path: with `_CHECKPOINTER` set to a sentinel, open_checkpointer
    yields THAT (identity), no connect/close.
  - lifespan postgres branch: builds pool + saver + calls setup + closes on
    shutdown (fake AsyncConnectionPool/saver recording open/setup/close);
    sqlite branch: no pool built.
  - fail-fast: a setup() that raises aborts startup (doesn't yield a broken
    app).
  - delete cascade in postgres mode issues the checkpoint-table DELETEs for
    the session's thread ids (recording fake store); sqlite mode still hits
    the local purge.
  - settings: pool env parsing + defaults.
  - REGRESSION: the existing chat-thread / history tests (self-host sqlite
    default) all still pass unchanged.
- verify (self-host, real): boot the app on sqlite, drive a chat turn,
  reopen the thread → history present (proves the seam didn't regress the
  local path). Real Postgres path is unit-tested via fakes + documented as
  needing a live Cloud SQL to exercise end-to-end.
- Gates: pytest suite · (frontend only if Item 5 touches it: tsc · vitest ·
  Playwright) · next build if frontend touched. Commit per item.

## Deferred (documented)
- Metadata-store connection pooling (budget rationale above).
- Dedicated `messages` table (app-owned transcript, checkpointer as
  resumption-only) — the deeper decouple-from-LangGraph refactor; do when
  rich message querying / framework independence is needed.
- Postgres pipeline mode for the saver (perf; default no-pipeline is safest).
