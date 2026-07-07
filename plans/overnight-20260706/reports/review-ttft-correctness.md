# Adversarial correctness review — Codex TTFT warm-keep

Branch: `claude/codex-ttft-warm-keep` · Reviewer: adversarial correctness pass
(read-only). Scope: `src/agents/codex/codex_warm.py` (new pool) + wiring in
`codex_engine.py`, `codex_runtime.py`, `api.py`. Verified against
`tests/test_codex_warm_keep.py` and `tests/test_runtime_prewarm_api.py` (both
pass) and reasoned beyond their coverage.

---

## PRIORITY #1 — TENANT ISOLATION VERDICT: **AIRTIGHT BY CONSTRUCTION.**

No cross-tenant worker-reuse sequence exists. The defense is layered and every
entry path is gated:

1. **The pool key carries the tenant.** `WorkerKey = (session_id, thread_id,
   user_id or "")` (`codex_warm.py:41`), composed identically by
   `CodexEngine._worker_key` (`codex_engine.py:326-327`) on both the turn and
   the pre-warm paths. Lookups are by the FULL key only — there is no
   partial-key/late-binding path in `acquire`/`ensure`/`state_for`
   (`codex_warm.py:183-299`). Two owners with a colliding `session_id`/
   `thread_id` still land on distinct keys because `user_id` differs.

2. **Every path is owner-gated before it can reach the key.** The WS turn path
   checks `session_manager.owns_session(session_id, uid)` (`api.py:1441`) and
   passes `user_id=uid` into `RuntimeTurnContext` (`api.py:1538`); prewarm and
   status both call `_require_owned` → `owns_session` (`api.py:1224`, `1198`)
   and pass the same owner-scoped `uid`. `uid = _uid(identity) =
   scoped_user_id(identity)` returns the real tenant id in hosted
   (`auth.py:160-172`; `google_<sub>`/`workos_<sub>`, `identity.py:100,201`) and
   `None`→`""` only in self-host (single tenant, correct). A non-owner gets 404
   and never reaches `acquire`, so user B can never present key `(S, T, A)`.

3. **`user_id` is the essential third component and it is always present and
   distinct** for real hosted tenants. Even in the composite-PK case (two users
   each owning a session string "foo"), `owns_session("foo", uidB)` matches
   *userB's own row* and userB gets key `("foo","foo","uidB")` — a different
   worker. Empty `user_id` occurs only in self-host (`None`) — single tenant.

4. **Anonymous cannot spawn a Codex worker at all.** Anonymous ids are
   `anon_<hint>` (`identity.py:50-52`, never empty). Codex needs a BYOK key or
   connected account; with neither, `prewarm` returns `unavailable` before
   `ensure` (`codex_runtime.py:145-156`) and `run_turn` errors `no_key`
   (`codex_runtime.py:229-246`). No speculative anonymous spawn, so no shared-""
   worker path.

5. **Mid-session auth change retires the stale-auth worker.** The fingerprint
   hashes `api_key || account_home || sandbox || system_prompt`
   (`codex_warm.py:51-65`). A BYOK-key change / BYOK↔account switch / sandbox
   change flips the fingerprint; `acquire`'s reuse check requires
   `entry.fingerprint == fingerprint` (`codex_warm.py:208`) and otherwise pops +
   `close()`s the old worker (`codex_warm.py:215-223`, proven by
   `test_fingerprint_change_respawns_instead_of_reusing`). A stale-auth worker
   can never serve a changed context. Excluding the raw bearer from the
   fingerprint is safe: the bearer proves an identity already in the key, and a
   worker's bound MCP child is pinned to `--bound-session <that session>` and
   re-checks ownership, so even a stale bearer acts only within its own tenant
   (worst case: auth expiry → turn fails → retire → honest cold start).

6. **Pre-warm and run_turn compose the SAME key+fingerprint** (both derive
   `uid`/`session`/`thread` from the owner-verified request and share
   `_system_prompt()` — `codex_runtime.py:110-115`), so pre-warm cannot spawn
   under one identity and be reused under another; a mismatch would only waste
   the pre-warm, never cross tenants.

**No leak sequence found.** Tenant isolation is sound.

---

## OVERALL: **DO-NOT-DEPLOY-UNTIL-FIXED (F-TTFT-1).**

Isolation is airtight, but one HIGH lifecycle defect makes warm-keep *regress*
against the existing cold path for a common hosted scenario (returning user
whose SDK rollout is gone). The fix is small; everything else is sound.

---

## FINDINGS (ranked)

### F-TTFT-1 — HIGH — `expected_external` churns to `RuntimeError` and wedges a thread whenever `thread_resume` fails
`codex_warm.py:199-240` (revalidation) × `codex_engine.py:351-371` (spawn) ×
`codex_engine.py:404-408` (`expected_external=turn.external_thread_id`).

**Mechanism.** `acquire` applies the `expected_external` mismatch check not only
to a *reused* warm worker but also to a *freshly spawned* one
(`codex_warm.py:234-239`). `spawn_worker` produces an external id **different
from the persisted one** exactly when `thread_resume(E1)` raises and it falls
back to `thread_start` → new id `E2` (`codex_engine.py:351-371`) — the very
resume-failure case the history-replay fallback was built for. Since `E2 !=
E1(expected)`, the fresh worker is rejected, `acquire` loops, respawns, rejects
again, and after 4 tries raises `RuntimeError("worker validation kept
churning")` (`codex_warm.py:240`). `stream_turn` maps that to `CodexTurnError`
(`codex_engine.py:442-452`) → the turn fails.

**Concrete failure sequence (hosted, default-on):**
1. Thread `th1` has persisted `external_thread_id = E1`, created on instance A.
2. Instance A recycles / scales to zero. Codex rollout for `E1` lived on A's
   ephemeral disk (`CODEX_HOME`/`CODEX_SQLITE_HOME` under `/app/...`,
   `codex_engine.py:474-476`) — gone.
3. User returns; first turn lands on instance B (cold pool).
4. `acquire(K, FP, spawn, expected_external=E1)` → spawn → `thread_resume(E1)`
   raises → `thread_start` → `E2`. Revalidate: `E1 != E2` → loop → 4 spawns →
   `RuntimeError` → turn fails with "Codex turn failed: …kept churning".
5. Because the turn never completed, `run_turn` never persists `E2`
   (`codex_runtime.py:367`), so the stored id stays `E1`. **Every subsequent
   turn repeats step 4 — the thread is wedged** until warm-keep is disabled or
   the stored id is cleared.

**Why it matters / likelihood.** In hosted the SDK rollout is instance-local, so
`thread_resume` failing on a new instance is the *norm* for returning users, not
an edge. The cold path (`pool=None`) handles this fine — it calls
`spawn_worker` directly with no `expected_external` gate (`codex_engine.py:414`)
— so warm-keep is a strict regression here. Untested: the fake SDK's
`thread_resume` always succeeds returning `id == ext_id`
(`test_codex_warm_keep.py:90-92`), so this path has zero coverage. (Residual
uncertainty: this depends on `thread_resume` *raising* for a lost rollout — the
one unverifiable live-SDK behavior — but the code invests a whole fallback in
that branch, so it is expected reachable.)

**Direction.** Do not apply the `expected_external` mismatch to a *freshly
spawned* worker — a just-spawned worker's id is authoritative for this turn.
Restrict the guard to the *reuse/cache-hit* branch (`codex_warm.py:205-211`)
only, and drop it from the post-spawn revalidation (`234-239`). Add a
regression test with a fake `thread_resume` that raises → asserts one spawn, a
successful turn, and `E2` persisted.

### F-TTFT-2 — LOW/MEDIUM — a retired worker can be handed to a second concurrent turn already blocked on its `turn_lock`
`codex_engine.py:421-452`, `codex_warm.py:301-309`.

Two genuinely concurrent turns on one thread (e.g. two tabs) both `acquire` the
same worker W and queue on `W.turn_lock`. If T1 crashes/cancels mid-turn,
`_retire` → `discard` pops the entry and `close()`s W (`codex_engine.py:460-467`).
T1's `async with turn_lock` releases; T2 then acquires the lock and calls
`worker.thread.turn()` on a **closed** worker (dead subprocess) — T2 does not
re-check `worker.closed` after taking the lock. Result: T2 fails with a turn
error instead of cold-starting. Self-healing (the entry is gone, so the *next*
turn respawns), and concurrent same-thread turns are already outside the
supported supersede model, hence LOW/MEDIUM. Direction: after acquiring
`turn_lock`, re-check `worker.closed` and, if closed, re-`acquire` once.

### F-TTFT-3 — LOW — first real turn inherits a pre-warm spawn failure instead of retrying fresh
`codex_warm.py:224-230`, `258-287`.

If a pre-warm spawn is still in flight and then fails (transient SDK/login), a
first send coalesced onto it via `await asyncio.shield(entry.task)` receives the
exception and `acquire` re-raises without looping to a fresh spawn
(`codex_warm.py:224-230`). The user's first message fails. Parity with cold
(the same inline spawn would fail identically) and self-healing on retry (the
slot is popped by `_spawn_logged`), so LOW — but worth noting the retry loop
does not cover spawn *exceptions*, only fingerprint/external churn.

### F-TTFT-4 — LOW (tests/embedding only) — `_bind_loop` drops workers without closing them
`codex_warm.py:125-135`. On a loop change `self._entries.clear()` abandons live
workers without `close()`; if the old loop is still alive its subprocesses leak.
Documented and hosted runs a single loop, so this is a test/embedding concern
only. No action required for deploy.

---

## Confirmed sound (checked, no defect)

- **Disabled path is byte-for-byte old behavior.** `CODEX_WARM_KEEP=0` / no
  settings.hosted → `_build_pool` returns `None` (`codex_runtime.py:93-108`);
  `stream_turn` spawns per turn and closes after (`codex_engine.py:410-419,
  453-455`). No new failure surface when disabled.
- **Janitor + capacity eviction never kill a busy worker.** Both skip
  `turn_lock.locked()` workers (`codex_warm.py:153`, `170`); `last_used` is
  reset to `now` on every acquire (`codex_warm.py:213,238`), so a just-handed-out
  worker is never the LRU victim in the pre-`turn_lock` window. No zombie: popped
  victims are `close()`d (`codex_warm.py:156-157, 178-179`).
- **Crash/cancel retires honestly** — `test_crashed_stream_retires…`,
  `test_engine_cancellation_retires_worker`; `discard` is idempotent
  (`WarmWorker.close` guards on `self.closed`).
- **Pre-warm coalescing = one worker** (`test_prewarm_then_first_send…`).
- **Loop-bound reuse prevented** — `_bind_loop` rebinds on loop change;
  `close_thread_sync` bridges cross-loop safely (`codex_warm.py:328-341`).
- **`ensure` mutates `_entries` without the guard but is fully synchronous** (no
  await), so it is atomic under cooperative scheduling — no race with `acquire`.
