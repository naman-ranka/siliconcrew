# Review — TTFT warm-keep vs requirements

**Branch:** `claude/codex-ttft-warm-keep` · **Diff:** `git diff fe610ad..HEAD`
(3 commits: bb568f0 3A warm-keep, 8346b18 3B pre-warm, 7aa4910 3C setup indicator)
**Reviewer:** adversarial requirements audit against `plans/codex-ttft-remediation.md`

## VERDICT: requirement-complete and safe to ship to staging.

Every hard constraint in §4 is met, and the #1 make-or-break — tenant isolation
by construction — holds and is proven by test. The design keys workers on the
FULL `(session_id, thread_id, user_id)` triple, looks them up only by that full
key, and spawns each worker bound to that same identity; there is no partial-key
path and no cross-tenant pool. The token-exclusion in the fingerprint is
**sound, not a leak**: the bound MCP child runs `--transport stdio` and resolves
identity ONCE at spawn (`mcp_server.py:237-245` → cached `self.identity`), never
per-call, so a warm worker's identity is byte-for-byte what a cold start would
have had. I ran the new tests (15 backend + 6 frontend) and the existing Codex
suite (27) — all green; the `None`-pool path is behaviorally unchanged.

What keeps this from "unconditionally done": the two UI-legibility success
criteria in §5 are proven at the store/unit layer but **not** by the automated
Playwright/UI test the plan names (inspection-only for the ChatArea wiring), and
there is a narrow concurrency edge (below) worth a staging watch. Neither is a
blocker; neither is a tenant/correctness risk.

## Requirement table

| # | Requirement | Met? | Evidence (file:line) | Gap / risk |
|---|-------------|------|----------------------|------------|
| 3A | Turn 2+ reuses a warm worker (no rebuild); `elapsed_setup≈0`, `warm=hit` | **yes** | `codex_engine.py:398-419` (acquire; `warm=hit` at 409; `sdk_thread_ready` log 422-426), `codex_warm.py:183-240` (reuse path). Test `test_codex_warm_keep.py:164-180`: `spawns==1`, `thread.turns==2`, `exited==0` | — |
| 3A | Worker kept alive across turns (not torn down) | **yes** | `codex_engine.py:453-456` — `close()` only when `pool is None`; pool-managed workers stay warm | — |
| 3B | Pre-warm fires on tab open / thread mount, BEFORE first send | **yes (wiring) / partial (auto-test)** | `ChatArea.tsx:47-52` useEffect deps `[agentRuntime, activeThreadId, currentSession?.id]` → `prewarmAgentRuntime`; endpoint `api.py:1205-1240`; `store.ts:1424-1478` | useEffect-on-mount verified by inspection only; no Playwright test (see §5 row) |
| 3B | Early send reuses pre-warmed worker (spawn coalescing), no 2nd spawn | **yes** | `codex_warm.py:200-225` — an in-flight entry is awaited via `asyncio.shield(entry.task)`, never re-spawned. Test `:317-334`: prewarm then immediate send → `spawns==1` | — |
| 3B | Fingerprint parity so first send doesn't discard its own pre-warm | **yes** | `codex_runtime.py:110-115` `_system_prompt` shared by `run_turn`+`prewarm`; `prewarm` builds turn identically `:165-180`; `worker_fingerprint` excludes rotating token by design `codex_warm.py:51-65` | — |
| 3C | "Setting up… / Ready" shown truthfully; nothing when nothing truthful | **yes** | `store.ts:1435-1447` (cold/unavailable→`null`); `ChatArea.tsx:212-234` chip only when `starting`/transient-ready; `worker_state` `codex_runtime.py:122-128`. Tests `codexSetup.test.ts` (6, all pass) | — |
| 3C | Bounded poll ONLY while starting (not run-polling) | **yes** | `store.ts:1461-1477` — `pollOnce` continues only while `watching` (state==starting); stops at ready/cold, thread switch (token guard), 2-min give-up | — |
| 3C | Dead/recycled worker → honest "setting up" again, never fake ready | **yes** | `codex_warm.py:289-299` `state_for` returns `cold` when closed; chip only mirrors backend. Tests `test_engine_cancellation_retires_worker:221-245` (state COLD), `test_worker_state_reports_honestly:359-376` | — |
| 4.1 | **Tenant isolation by construction** (full key, bound spawn, no partial lookup, no cross-tenant pool) | **yes (make-or-break MET)** | Full triple key `codex_warm.py:41,326-327`; lookup only by full key `:203-217`; spawn bound from same turn (`--bound-session`, per-user CODEX_HOME) `codex_engine.py:337-373,513`; stdio identity validated-once-at-spawn `mcp_server.py:225-245`. Proof test `:250-285` (same session+thread, different owner → different worker; each carries own spawn identity) | — |
| 4.4 | Lifecycle: idle teardown, LRU cap, crash retires, cleanup on delete | **yes** | janitor `codex_warm.py:143-157`; LRU evict `:161-179`; `_retire`/`discard` `codex_engine.py:460-467`, `codex_warm.py:301-309`; `close_thread` `:311-341` via `register.py:54-59`. Tests: cap `:381-399`, idle `:403-422`, crash `:201-218`, delete `:425-439` | — |
| 4.5 | Twelve-factor: worker is a cache, losing it costs only a re-cold-start | **yes** | docstring `codex_warm.py:17-20`; transcripts/external-id persist via `codex_store` in `run_turn` `codex_runtime.py:361-368`, independent of worker | — |
| 4.6 | Self-host untouched by default; opt-in `CODEX_WARM_KEEP=1`; `None` pool = old behavior | **yes** | `_build_pool` `codex_runtime.py:93-108` (unset→hosted-on/self-host-off; `=0` off everywhere); `None`-pool path `codex_engine.py:410-419,453-456`. Existing Codex suite (27) passes unchanged | — |
| 4.7 | Behavior/results identical (transcripts, tool results, honesty) | **yes** | `test_transcripts_identical_warm_vs_cold:183-198` (roles, content, external-id match cold); `run_turn` event translation unchanged | — |
| 5 | Tenant-isolation regression test present + proves the property | **yes** | `test_workers_never_shared_across_sessions_threads_or_owners:250-285` — strong, adversarial (mallory shares session+thread, gets a distinct worker) | — |
| 5 | Pre-warm-on-tab-open proven by test/QA; UI legibility verified in Playwright | **partial** | Store action + coalescing proven (`test:317-334`, `codexSetup.test.ts`) | No Playwright/e2e for the ChatArea useEffect firing on mount or the chip render; "verified in the UI (Playwright)" is inspection-only |
| 5 | No regressions: full gate at baseline | **not re-run here** | New (15+6) + existing Codex (27) tests pass; `None`-pool path byte-for-byte | Full backend/frontend gate is the separate deploy task (#3), not this review; flag to run before prod |

## Adversarial notes (non-blocking risks to watch on staging)

1. **Concurrent same-thread drivers can spuriously fail a queued turn.** The
   Codex dispatch path (`api.py:1517-1543`) has NO `_ACTIVE_TURNS`/supersede
   dedup (that lives only in the native branch, `:1626-1630`) — pre-existing
   X2A-7. Two concurrent sockets on one thread now share ONE warm worker and
   serialize on `turn_lock` (correct), but if the lock holder is cancelled
   (stop/disconnect) it `_retire`s (closes) the shared worker while the waiter
   is queued → the waiter calls `.turn()` on a dead subprocess → honest
   `CodexTurnError`, then the next turn cold-starts. Narrow (needs two live
   drivers of one thread); degraded UX, not a leak or corruption. Worth a note,
   not a fix.

2. **UI legibility is unit-proven, not e2e-proven.** The chip states, poll
   gating, and thread-switch supersede are covered by `codexSetup.test.ts`, but
   the plan's §5 "verified in the UI (Playwright)" and "pre-warm starts on tab
   open, not on first send" have no browser-level test. Recommend one Playwright
   assertion (mount a Codex thread → `data-testid=codex-setup-state` appears; a
   prewarm request fires before any send) before calling §5 fully closed.

3. **Full gate not executed in this review.** I verified the new + existing
   Codex tests; the complete backend/frontend baseline belongs to the staging
   deploy task and should be green before prod.
