# Codex time-to-first-token (TTFT) remediation — requirements & intent

**Status:** IMPLEMENTED (3A warm-keep, 3B pre-warm, 3C setup indicator) on
`claude/codex-ttft-warm-keep`. This section is authoritative over the body
below (the owner's original direction document, kept unchanged).

**What shipped — the design chosen, with reasoning:**

- **3A warm-keep** (`src/agents/codex/codex_warm.py` + engine/runtime wiring):
  a per-process `CodexWorkerPool` keeps a thread's worker (the SDK app-server
  subprocess + its bound MCP child + the resumed SDK thread) alive across
  turns. Turn 1 pays cold start; turns 2+ log `warm=hit` with
  `elapsed_setup≈0`. Design answers to §7:
  - *Where does it live?* One pool per process, owned by the
    `CodexRuntimeHandler` and injected into the engines its factory builds —
    NOT in the runtime registry (the registry stays codex-agnostic; the pool is
    a codex-internal cache). Keyed by the FULL `(session_id, thread_id,
    user_id)` triple; the worker's spawn config was built from that same triple
    (`--bound-session`, per-user CODEX_HOME, caller's token), so isolation
    holds **by construction**: there is no partial-key lookup and no
    cross-tenant pool. A fingerprint (BYOK key, account home, sandbox, system
    prompt) retires workers on auth/config changes; an
    expected-external-thread-id check retires stale ones.
  - *Bounds:* idle-timeout janitor (`CODEX_WARM_IDLE_SEC`, default 900s) and a
    soft LRU cap (`CODEX_WARM_MAX`, default 3 — busy workers are never
    evicted, so the true bound is cap + concurrently-active turns). Workers
    are loop-bound (SDK transports belong to their event loop) and are pure
    caches — losing one costs exactly one honest re-cold-start.
  - *Crash/recycle:* any abnormal turn end (SDK error, user stop/cancel)
    retires the worker instead of reusing an unknown stream state; the next
    turn cold-starts and 3C shows "Setting up" again. Thread/session delete
    tears the worker down via the existing runtime-registry cleanup hook.
  - *X2A-7 coherence:* the pool is process-local, exactly like the turn
    supersede — same affinity assumption, and per-worker turn serialization
    (one turn at a time, later turns queue) doesn't widen it.
  - *Gating:* hosted default-on; self-host untouched by default (opt-in
    `CODEX_WARM_KEEP=1`); `CODEX_WARM_KEEP=0` disables everywhere. A `None`
    pool is byte-for-byte the previous per-turn cold behavior.

- **3B pre-warm** (`POST /api/sessions/{sid}/threads/{tid}/runtime/prewarm`):
  fires when the Codex chat surface mounts (tab open / thread switch — the
  cheapest reliable signal that precedes "send"), kicks the spawn without
  waiting, and hydrates the workspace as a side effect. The pool's
  spawn-coalescing means an early send simply awaits the same in-flight spawn
  — the "queue the message and fire on ready" requirement falls out of the
  design rather than being a bolted-on queue. Speculative cost is bounded by
  the idle timeout + cap. `handler.prewarm` resolves auth exactly like a real
  turn (no key → "unavailable"; it never spawns without resolvable auth) and
  composes the same fingerprint as `run_turn` so the first send reuses the
  pre-warmed worker instead of discarding it.

- **3C honest setup state** (`GET .../runtime/status`, store + ChatArea chip):
  the readiness channel is a tiny status endpoint + a bounded poll that runs
  ONLY while the state is "starting" (setup is a short explicit window — this
  is not run polling; it stops at ready/cold, on thread switch, and after a
  2-minute honest give-up). The chip shows "Setting up Codex…" (or "Starting
  your first turn…" if a send is already streaming), a transient "Codex
  ready", and NOTHING when there's nothing truthful to show (native runtime /
  warm-keep unavailable). A dead/recycled worker reads "cold" → the next open
  pre-warms and shows "Setting up" again — never fake readiness. The endpoints
  are a generic runtime seam (`getattr(handler, "prewarm"/"worker_state")`);
  the shared shell never names Codex.

**Measured/measurable:** `[CODEX-TIMING]` gained `warm=hit|join|miss|off` on
`sdk_thread_ready`, `event=warm_worker_spawned`, and `event=prewarm` lines —
the before/after on staging reads directly from logs (turn 2+ `elapsed_setup`
with `warm=hit` ≈ 0; turn 1 with a pre-warm shows the spawn overlapped typing).

**Deferred / accepted:** cross-instance warmth (explicit non-goal — a routing
miss is an honest cold start); fine-grained coldstart_* sub-timers (the split
doesn't change the design); SSE push of readiness (the bounded setup poll is
deliberately boring; revisit with the SSE-activity deferral).

---

The owner's original direction document follows, unchanged.

**Status (original):** DRAFT for the implementer. This is a *direction*
document — it states the problem, the evidence, the intent, and the hard
constraints. It deliberately does **not** prescribe the implementation.
**Implementer: use your own judgment and reason about the design.** The three
directions below (pre-warm, setup indicator, warm-keep) are the *intent* — you
decide the mechanism, the lifecycle, the data structures, and where each piece
lives, grounded in a real read of the code. Where a constraint below is
load-bearing (especially tenant isolation), treat it as non-negotiable;
everything else is yours to design. Produce your own implementation-grade
reasoning first (what you'll change, why, the failure modes), then build.

**Owner intent, verbatim in spirit:** writes are fast now, but **Codex
time-to-first-token is still slow** — there's a long pause before the first
response of a conversation. Fix it the honest, industry-standard way. Make the
first turn fast, keep later turns fast, and if there's any unavoidable wait, make
it *legible* (the user should see "setting up" and know when it's ready), never a
silent freeze.

---

## 1. Context — what already shipped (do not re-solve)
On staging (backend rev 00064, branch `claude/hosted-latency-remediation-obkib4`):
- **4A incremental sync + 4B once-per-turn background sync** — DONE. File writes /
  tool calls are now fast (owner-confirmed). This is unrelated to TTFT; leave it.
- **4C quick cuts** — DONE (skip provisioned `init_schema`, file-cache JWKS, lazy
  agent import). These only help **turn 1** and only by ~1.5–2.5s. TTFT is **still
  slow** (owner-confirmed) — the quick cuts were never going to be enough.

This document is the remaining, deferred **4C real fix**.

## 2. The problem (root cause + evidence)
Every Codex user turn rebuilds the whole worker from scratch: `stream_turn` does
`async with sdk_factory(config=config)` **per turn** (`src/agents/codex/
codex_engine.py:~331`), and `run_turn` recreates the engine each turn
(`codex_runtime.py:~145`). That cold-spawns a fresh Codex app-server + a fresh
Python MCP subprocess (`--transport stdio`, `startup_timeout_sec=20`).

Measured/attributed cold-start (`[CODEX-TIMING] elapsed_setup`, ~10.96s live):
- ~1.6–2.3s: our Python MCP cold import (the quick-cut lazy-import target; largest
  trimmable chunk is LangChain/LangGraph via `src.tools.wrappers`).
- ~0 locally / real on hosted: Cloud SQL schema DDL + WorkOS JWKS fetch (the other
  quick-cut targets — already addressed).
- **~8.5s (the bulk): the OpenAI Codex app-server binary launch + MCP subprocess
  spawn + hosted round-trips + thread bring-up.** Nothing we can *trim* removes
  this — it is paid in full on every turn because the worker is rebuilt every turn.

**Key conclusion:** the ~8.5s bulk is a *per-turn rebuild* cost. The fix is to
stop rebuilding — not to trim.

(Optional, if you want the exact app-server-vs-rest split from live logs before
designing: fine-grained `[CODEX-TIMING] event=coldstart_*` sub-timers were
prototyped once and reverted; you may re-add equivalents, deploy staging, and read
the split. Not required — the direction below holds regardless of the exact split,
because all of the ~8.5s is per-turn startup that warm-keep/pre-warm amortize.)

## 3. Intent — what "fixed" looks like
Three reinforcing pieces. Implement them so they compose; each is intent, not a
prescribed mechanism.

### 3A. Warm-keep — fast *subsequent* turns
Keep a thread's Codex worker (app-server + its MCP child) **alive across turns**
instead of tearing it down after each message. Turn 1 still pays cold start; every
later turn in the conversation reuses the warm worker and is near-instant. This
alone does NOT help the first turn — that's what 3B is for.

### 3B. Pre-warm — fast *first* turn
Start the worker **before the user sends their first message** — on Codex-tab
open / session entry — so the cold start overlaps with the human's read-and-type
time instead of blocking the first response. Because the session and owner are
already known at open time, you can spawn the **correctly session-bound** worker
ahead of time (see the tenant-isolation constraint — this is why pre-warm is safe:
no generic shared pool needed).

### 3C. Honest "setting up… / ready" state — make any residual wait legible
Surface the worker's readiness truthfully in the Codex UI: **"Setting up Codex…"**
while it warms, **"Ready"** when it's up. This is the CLAUDE.md honest-state rule
applied to warm-up:
- If the user types and sends before it's ready, **queue the message and fire it
  the moment setup completes** — with a visible "starting your first turn…" state,
  never a silent freeze. (This covers the open-and-instantly-send edge case.)
- If warm-keep already has a live worker, show "Ready" instantly — no fake setup.
- If the instance recycled and the worker died, honestly show "Setting up" again —
  never pretend readiness that isn't there.

The indicator is a first-class part of the fix, not an afterthought: it is what
turns an unavoidable cold start into legible progress.

## 4. Hard constraints (non-negotiable — reason carefully about each)
1. **Tenant isolation (INVARIANT 8) — the #1 safety constraint.** A warmed or
   pre-warmed worker is bound to exactly one `session_id` + one owner (the MCP
   server is spawned `--bound-session <sid>`). It MUST NEVER be reused for a
   different session or a different owner, under any concurrency or instance-reuse
   scenario. A cross-tenant worker reuse is a critical leak (cf. the F1 class of
   bug). Design so this is true *by construction*, not by check-and-hope. No
   generic cross-tenant warm pool unless you can prove late-binding is airtight —
   the session-scoped pre-warm avoids needing one.
2. **Cloud Run affinity reality.** A warm worker lives on ONE instance. If the next
   turn for a thread routes to a DIFFERENT instance, the warm worker isn't there →
   honest cold start again (and 3C must show "setting up"). This is acceptable —
   do NOT try to share workers across instances. But note the interaction with the
   existing process-local turn-supersede issue (**X2A-7** in
   `plans/overnight-20260706/FINDINGS.md`): both assume affinity; keep them
   consistent, and don't make X2A-7 worse.
3. **Honest state (INVARIANT 4).** No fake "ready" before the worker is actually
   up; no silent freeze; staleness shown truthfully (a dead warm worker reads as
   "setting up", not "ready").
4. **Lifecycle safety.** Warm/pre-warmed workers are real subprocesses: bound
   memory (idle-timeout teardown; a cap on how many live at once per instance),
   crash recovery (a dead worker → transparent re-cold-start + honest UI, never a
   wedged turn), and cleanup on session close / thread delete (reuse the runtime
   registry's per-thread cleanup hook, `runtime_registry.py` cleanup path).
5. **Twelve-factor (INVARIANT 9).** A warm worker is a *cache*, never durable
   truth. Losing it (instance recycle) must only cost a re-cold-start, never
   correctness or data. Nothing durable lives in the warm process.
6. **Self-host untouched / optional.** Priority is hosted. Self-host cold start is
   already cheap (local deps); applying the same pattern there is optional and must
   not add a cloud dependency or change self-host behavior. The engine-selection
   idiom stays intact.
7. **Behavior/results identical.** Same transcripts, same tool results, same
   honesty. This is a latency + UX-legibility change only — not a change to what
   Codex does or produces.
8. **Don't regress what shipped.** 4A/4B/4C-quick-cuts stay working. Reuse the
   existing `[CODEX-TIMING]` instrumentation so the win is measurable, not asserted.

## 5. Success criteria (how we'll know it worked)
- **Subsequent turns:** with a warm worker, `elapsed_setup` on turns 2+ drops to
  ~0 (near-instant first token) — measurable via `[CODEX-TIMING]` before/after.
- **First turn:** when the user opens Codex and then types for a few seconds before
  sending, the first turn's *perceived* wait is dramatically reduced (the cold
  start happened during pre-warm). A test/QA proves pre-warm starts on tab open,
  not on first send.
- **Legibility:** the UI shows "Setting up… → Ready" truthfully; an early send
  queues and fires on ready; a dead warm worker re-shows setup. Verified in the UI
  (Playwright) and by unit tests on the state machine.
- **Tenant isolation:** a test proves a warm/pre-warmed worker is only ever used
  for its own session+owner — never reused across sessions/owners. This is the
  test that must exist and pass before this ships anywhere near production.
- **No regressions:** full gate suite at the known baseline; self-host behavior +
  timings unchanged.

## 6. Non-goals / do-NOT
- Do NOT re-solve writes (4A/4B) or the quick cuts (4C) — done.
- Do NOT build a cross-tenant shared worker pool unless late-binding is provably
  leak-free; the session-scoped pre-warm is the safer default.
- Do NOT try to keep workers alive across Cloud Run instances — accept the
  affinity boundary and show honest setup when it's missed.
- Do NOT fake readiness to make a demo look fast — legible honesty is the whole
  point of 3C.
- Do NOT change tool behavior, transcript persistence, or any verdict/honesty logic.

## 7. Open questions to reason about (your call — justify your choice)
- **Where does the warm worker live?** Per-thread in the runtime registry? A small
  per-instance manager keyed by (session_id, owner)? What's the idle-timeout and
  the max-live cap, and how do they interact with Cloud Run memory limits?
- **Pre-warm trigger:** tab open? session route? first keystroke? What's the
  cheapest signal that reliably precedes "send" without over-spawning for users who
  open and leave? How is the speculative-spawn cost bounded (idle teardown)?
- **The readiness channel:** how does the frontend learn "setting up → ready"?
  Reuse an existing status/activity channel, or a small dedicated one? How does an
  early send get queued and fired on ready without racing?
- **Crash/recycle:** how does a dead warm worker surface (honest "setting up"
  again) without wedging or double-spawning?
- **Interaction with X2A-7** (process-local turn supersede): does warm-keep change
  the affinity assumptions? Keep them coherent.
- **Measurement:** confirm the win the same way the F2/write fix was proven — a
  `[CODEX-TIMING]` before/after on turns 1 (pre-warmed) and 2+ (warm-kept).

## 8. Suggested sequence (you may re-order with reasoning)
1. Warm-keep (3A) — the core lifecycle; unlocks fast turns 2+.
2. Pre-warm (3B) — layer on top; unlocks fast turn 1.
3. Setup-state indicator (3C) — the honest UI; makes any residual wait legible and
   covers the early-send edge.
(3A and 3C are independently valuable; 3B depends on 3A's worker being reusable.)
