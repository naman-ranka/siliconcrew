# Codex TTFT warm-keep — lifecycle fixes

Branch: `claude/codex-ttft-warm-keep`. Fixes the two lifecycle defects from
`review-ttft-correctness.md` (F-TTFT-1 HIGH, F-TTFT-2 LOW/MED). Tenant
isolation was confirmed airtight by that review and is **not touched** — no
change to keying, spawn identity, fingerprint, or ownership gates.

Fenced to: `src/agents/codex/codex_warm.py`, `codex_engine.py`,
`tests/test_codex_warm_keep.py`. `deploy/roll_cloudrun.py` (uncommitted deploy
edit) deliberately left alone.

---

## F-TTFT-1 — HIGH — thread-wedge when `thread_resume` fails

**What changed** (`codex_warm.py`, `CodexWorkerPool.acquire`). The
`expected_external` mismatch guard was being applied to a *freshly spawned*
worker in the post-spawn revalidation (was ~`:234-239`). It is now applied
ONLY on the reuse/cache-hit branch (`:205-211`) and dropped from the post-spawn
path. A just-spawned worker's external id is authoritative for this turn:
`spawn_worker` legitimately mints a NEW id when `thread_resume(E1)` raises and
falls back to `thread_start` → `E2`. The docstring now states this contract.

**Pre-fix failure proof.** New regression
`test_resume_failure_accepts_fresh_external_id_and_does_not_wedge` seeds a
persisted external id `E1` whose rollout is gone (fake `thread_resume` raises)
and whose `thread_start` returns `E2`. On pre-fix code the fresh worker was
rejected (`E2 != E1`), `acquire` looped 4× and raised — the turn failed with:

```
AssertionError: {'code': 'codex_turn_failed',
 'error': 'Codex turn failed: codex warm pool: worker validation kept churning; giving up',
 'type': 'error'}
```

`E2` was never persisted, so every retry repeated the failure — the wedge.
Post-fix the test asserts (a) the turn completes (`done`), (b) `E2` is
persisted, (c) the next turn reuses the warm worker and completes (no wedge),
(d) exactly one spawn — one `thread_resume` attempt, one `thread_start`
fallback (no respawn storm). The existing fake `thread_resume` always
succeeded, which is why this path had zero coverage before.

## F-TTFT-2 — LOW/MED — retired worker driven by a second concurrent turn

**What changed** (`codex_engine.py`, `stream_turn`). After acquiring the
worker's `turn_lock`, we now RE-CHECK `worker.closed`. The single
`async with worker.turn_lock` was replaced by a bounded (2-attempt) acquire
loop: acquire worker → `await turn_lock.acquire()` → if `worker.closed`,
release and re-acquire a fresh worker (the pool respawns since the retired
entry is already popped); if both attempts yield a closed worker, fail cleanly
with a retryable `CodexTurnError` rather than a wedged one. The turn body is
wrapped in `try/finally: turn_lock.release()`, preserving the previous
release-on-exit semantics (incl. GeneratorExit / cancel). Non-pool path is
unchanged in effect (a fresh worker is never closed, so it breaks on attempt 1).

**Pre-fix failure proof.** New regression
`test_concurrent_turn_reacquires_after_worker_retired_under_lock` runs two
concurrent same-thread turns queued on one worker's `turn_lock`; the first
crashes mid-stream and retires (closes) the worker. On pre-fix code the second
turn took the lock and drove the dead subprocess, failing with:

```
CodexTurnError: Codex turn failed: SDK stream died
```

Post-fix the test asserts T2 re-acquires a FRESH worker (`spawns == 2`), the
crashed worker is closed (`exited == 1`), T2's fresh worker stays warm
(`exited == 0`), and T2 completes (`done`).

**Residual (documented, not over-reached).** The re-check is a *local* guard,
not full turn-serialization. There remains a vanishingly small window if the
retiring turn yields control between releasing the lock and closing the worker
(it does not in the fake, and in practice the close path has no intervening
await that hands the lock to the waiter before `closed` is set). Concurrent
same-thread turns are already outside the supported supersede model
(X2A-7); this fix removes the common failure and fails cleanly otherwise. Full
serialization would be a larger change and is not warranted here.

---

## Gates

- `tests/test_codex_warm_keep.py` + `tests/test_runtime_prewarm_api.py`: 17
  passed (was 15; +2 new regressions).
- Full suite (`pytest tests/ -q` with the three CLAUDE.md ignores): **11
  failed, 800 passed, 9 skipped** — the 11 are the exact baseline (9 env-gap +
  2 Windows-only incremental-sync artifacts: `test_cold_instance_reconstructs_exact_tree`,
  `test_concurrent_write_between_scan_and_upload_stays_consistent`). Zero new
  failures.
- Both new tests proven to FAIL on pre-fix code (source files stashed) and pass
  after. Fixtures restored (`git checkout -- tests/fixtures/ test_sby_output.txt`).
