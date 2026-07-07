# TTFT warm-keep — review against CLAUDE.md philosophy

**Scope:** `git diff fe610ad..HEAD` (3A warm-keep `codex_warm.py` + engine/runtime
wiring, 3B pre-warm, 3C setup chip). Read-only review; no code changed.

## VERDICT: ALIGNED — ship-ready, minor follow-ups (not over-machined)

The #1 risk of the whole change — tenant isolation (INV 8) — is genuinely
**by construction**, not check-and-hope, and it is proven by a real test. The
worker is a pure cache (INV 9 holds), self-host is provably untouched by
default, the runtime seam stays codex-agnostic (INV 3), and the honest-state
chip (INV 4) is truthful in its main paths. The pool is not over-built: every
piece maps to a stated requirement. Findings below are edges and polish; none
are blockers, none are leaks or corruption.

### Why isolation holds by construction (the load-bearing check)

- The pool is keyed ONLY by the full `(session_id, thread_id, user_id)` triple
  (`codex_warm.py:41`), and every lookup is full-key (`acquire`/`ensure`/
  `state_for`) — there is no partial-key path, no bare-id registry, no
  cross-tenant pool. `test_workers_never_shared_across_sessions_threads_or_owners`
  (`tests/test_codex_warm_keep.py:250`) exercises same-session/same-thread/
  DIFFERENT-owner and confirms distinct workers carrying their own spawn identity.
- The worker's MCP child is spawned `--bound-session <sid>` with a per-user
  CODEX_HOME and the caller's token (`codex_engine.py:513`, `:470-477`), all
  derived from the same triple — so the key can't disagree with what the
  subprocess was bound to.
- **Confirmed safe (and it resolves the obvious "stale token" worry):** the
  bound MCP child resolves identity ONCE at spawn from `SILICONCREW_MCP_TOKEN`
  (`mcp_server.py:237-241`; stdio transport — the per-request
  `HostedMCPAuthMiddleware` is HTTP-only). A warm worker's identity is therefore
  fixed at spawn = its key's `user_id`, and a rotating/expiring bearer on later
  turns neither breaks it nor can re-point it at another tenant. The fingerprint
  correctly EXCLUDES the raw bearer (`codex_warm.py:51-65`) for exactly this
  reason.

INV 9 (twelve-factor): nothing durable lives in the worker; transcript +
external_thread_id persist via `codex_store` as before, and losing a worker
(recycle/crash/evict) costs exactly one honest cold start. Confirmed.

Self-host (sacred): `_build_pool` returns `None` unless `CODEX_WARM_KEEP` is
truthy or `get_settings().hosted` (`codex_runtime.py:93-108`); a `None` pool is
byte-for-byte the old per-turn cold path (`codex_engine.py:453-456`). No cloud
dep added (settings import is always available). Provably opt-in.

---

## Findings (ranked)

### 1. [MEDIUM] Worker can be closed between `acquire()` and the `turn_lock` — queued turn runs on a dead SDK context
`codex_engine.py:428-436` acquires the worker, then `async with worker.turn_lock`,
then calls `worker.thread.turn(...)` **without re-checking `worker.closed`**.
The Codex WS path has NO shell-level per-thread supersede guard — the native
`_ACTIVE_TURNS` supersede (`api.py:1626`) lives in the native branch, AFTER the
extension branch has already `continue`d (`api.py:1517`, `:1616`). So two
sockets on one thread (two tabs / reconnect) drive two concurrent turns that
coalesce onto ONE worker and serialize on `turn_lock`. If the lock-holder
abends and `discard()` closes the worker (`codex_warm.py:301-309`,
`cm.__aexit__`) while the second turn waits on the lock, the second turn then
runs `turn()` on a torn-down context.
- **Impact:** an honest `codex_turn_failed` error (not a leak, not corruption);
  the retry cold-starts. Narrow (requires genuine same-thread concurrency).
- **Fix:** after obtaining `turn_lock`, re-check `worker.closed` and, if closed,
  treat as a miss (re-`acquire`/cold-start) instead of issuing the turn. Or
  confirm the shell serializes extension turns per thread (then it's moot —
  worth stating explicitly, since the native path bothered to guard this).

### 2. [LOW–MEDIUM] `state_for`/`ensure` ignore fingerprint → a brief "Ready" the next turn won't honor (INV 4)
`state_for` (`codex_warm.py:289-299`) and `ensure` (`:258-275`) key only on the
triple, not the fingerprint or `expected_external`. If auth material or the
system prompt changes between pre-warm and send, the chip can read "ready" while
the first real turn's `acquire` will detect the fingerprint mismatch, retire the
pre-warmed worker, and cold-start (`codex_engine.py:328-336`). That is a short
"fake ready" window — the exact thing INV 4 forbids.
- **Impact:** narrow (auth/prompt change during the setup window); the turn is
  still correct, just not actually instant.
- **Note:** `_system_prompt()` was deliberately unified (`codex_runtime.py:110`)
  to keep the common case matching, so this only bites on a real mid-setup auth
  change. Either fold the fingerprint into `state_for`, or document the window.

### 3. [LOW] `prewarm()` runs blocking store/key reads on the event loop
`codex_runtime.py:169,174` call `self._store.get_external_thread_id(...)` and
`list_messages(...)` (and `_resolve_key` at `:149`) synchronously inside the
async `prewarm`, which the endpoint awaits directly (`api.py:1235`). The
endpoint carefully offloaded `workspace_for` to a thread (`api.py:1231`) but not
these — in hosted (Postgres) they block the loop. Consistent with `run_turn`'s
existing pattern, but pre-warm is fire-and-forget speculative work, so blocking
the loop for it is more wasteful. Consider `asyncio.to_thread`.

### 4. [LOW] Pre-warm fires on every Codex mount/switch with no debounce — speculative GCS hydration + spawn per glance
`ChatArea.tsx:50-52` calls `prewarmAgentRuntime` on every
`[agentRuntime, activeThreadId, currentSession?.id]` change; each POST hydrates
the workspace (GCS in hosted, `api.py:1231`) and spawns a subprocess even for a
user who just glances at a thread. Bounded by cap (3) + idle (900s), and the
frontend token supersedes stale *watches* — but the in-flight POSTs still
complete server-side, so rapid thread-flipping churns subprocesses and GCS
downloads. The design accepts this; a small debounce would reduce waste.

### 5. [LOW] Idle-reap-then-send shows no "setting up" chip (misses 3C legibility for that path)
The status poll runs ONLY while state is "starting" (`store.ts:1459-1476`) and
the chip isn't re-armed on send. If a worker idle-reaps (900s) while the chip is
already hidden and the user then sends, the ensuing ~8.5s cold start shows no
"Setting up / Starting your first turn" affordance — only the normal stream
spinner. Not fake-ready (honest), but the 3C intent ("make any residual wait
legible") is unmet for this case. Optional: on send, if `worker_state` is
cold/starting, surface the chip.

### 6. [INFO] Cancellation retire path awaits `cm.__aexit__` during cancel
`codex_engine.py:446` awaits `_retire` (→ `worker.close`) inside the
`BaseException` handler before re-raising `CancelledError`. `_retire`'s
`suppress(Exception)` won't swallow a *re-raised* `CancelledError` from
`__aexit__`, but the net effect is still a `CancelledError` propagating, so
teardown-vs-cancel is semantically fine. No action; noted for completeness.
`test_engine_cancellation_retires_worker` covers the happy path.

### Simplicity / machinery check
Not over-built. Guard lock, per-entry spawn task (coalescing), janitor, LRU
cap, fingerprint, loop-rebind — each is one-sentence-defensible against a stated
requirement. The one borderline-clever piece is the 4-iteration fingerprint
**revalidation loop** in `acquire` (`codex_warm.py:199-240`), which handles a
coalesced awaiter whose fingerprint differs from the spawner's; it converges and
has a `RuntimeError` safety net, so it earns its keep, but it's the first place
to look if this ever needs simplifying.

### Coherence with X2A-7
The pool is process-local, exactly like the turn-supersede's affinity
assumption — it does not widen it. Per-worker `turn_lock` serialization is
strictly narrower than independent per-turn subprocesses were. Finding #1 is the
only place the two interact adversarially.
