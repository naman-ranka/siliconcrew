# Code review findings — recorded 2026-07 (for future action)

Adversarial review of the work that landed on `claude/integration-p1p2` after the
BYOK set: MCP remote auth (WorkOS), chat streaming/lifecycle (F1–F6), synth
concurrency, workbench freshness, and the sby/xls/cocotb tool fixes. Findings that
were **verified in code** are marked CONFIRMED; uncertain ones PLAUSIBLE.

> **MCP status: DEFERRED on purpose.** The hosted MCP works after a lot of
> iteration and we are **not** changing it now. The MCP findings below are recorded
> so they can be addressed **before scaling hosted MCP to real concurrent
> multi-user traffic** — not as immediate work.

---

## P0 (blockers — before the relevant feature is trusted at scale)

### 1. MCP hosted: cross-tenant via shared `current_session` — CONFIRMED (DEFERRED)
`self.current_session` is a single field on the one shared `RTLDesignMCPServer`
instance (`mcp_server.py:195`); in hosted HTTP one `self.server.run()` task
multiplexes all users. `create_session`/`set_active_session`/`get_prompt` mutate it;
`call_tool` reads `active_session = self.current_session` (`:863`) and operates on
that workspace. Identity is per-request, but **session selection is a process
global** → concurrent users can operate on each other's workspaces.
*Fix (later):* request-scope the active session like identity/workspace already are,
and enforce `owns_session(active_session, uid)` on every tool.
*Why deferred:* MCP works for current single-user-at-a-time usage; this bites under
concurrent multi-user hosted load. Fix before that.

### 2. Chat: heartbeat cancels the long synth it protects — CONFIRMED
`await asyncio.wait_for(_stream.__anext__(), timeout=_WS_HEARTBEAT_SEC)`
(`api.py:1163`) cancels the `__anext__` on timeout, throwing `CancelledError` into
LangGraph's `astream` generator and finalizing it → premature `done` with truncated
content + aborted run. Fires exactly on the 60s+ silent-synth case the heartbeat was
added for. `test_chat_heartbeat.py` only asserts ping/done exist, not that content
survives, so it stays green.
*Fix:* drain the generator in a background task feeding an `asyncio.Queue`; `wait_for`
on the queue, never on `__anext__`.
*Note:* not MCP — this one is worth fixing soon (breaks long-run chat UX), independent
of the MCP deferral.

## P1

### 3. MCP audience not required — CONFIRMED (DEFERRED)
`workos_configured` is true on issuer+jwks alone (`settings.py:97`); if
`WORKOS_AUDIENCE` is unset the verifier accepts WorkOS tokens with **no audience
check**, incl. the audience-less web SPA token (confused-deputy, defeats RFC 8707
binding). *Fix (later):* make audience mandatory on the MCP resource server.

### 4. Chat F4 false "interrupted" label — CONFIRMED
After a WS drop, `finalizeDrop` refetches history 1.5s later (agent may still be
running); the checkpoint's last turn ends on the in-flight tool call, so F4 appends
"reply was interrupted" to a run that's still executing and about to succeed, and the
socket was nulled so the user never sees the real completion (`store.ts:435`).
Client-only (no checkpoint corruption) but wrong UX, deterministic for the long-tool
drop case.

## P2

- **`update_manifest` ungated — CONFIRMED (DEFERRED, MCP).** Newly dispatchable via the
  single-source tool map but missing from `_PROTECTED_TOOLS` (`mcp_server.py:236`),
  while `write_file`/`write_spec` require `Action.SAVE`. Add it (or confirm anonymous
  identities can't hold hosted sessions).
- **Synth reservation-leak window — CONFIRMED.** If anything between
  `_reserve_synth_quota()` and `_submit_with_quota_release()` raises
  (`synthesis_manager.py:1401`), the concurrency slot leaks; only Postgres has the
  30-min reclaim (`quotas.py:178`), in-memory leaks until restart. *Fix:* reserve in a
  try/except that releases on any pre-submit error.
- **MCP loose default issuer — CONFIRMED (DEFERRED).** Defaults to
  `https://api.workos.com/`; isolation leans on the client-scoped JWKS only; tests
  mint tokens with that exact `iss`, which isn't the real shape.
- **Chat drop-recovery can transiently drop the typed message — CONFIRMED.**
  `loadChatHistory` replaces `messages` wholesale with server history that may not
  have checkpointed the turn yet (`store.ts:626`). Bounded, low impact.
- **Identity migration collision + misleading `--dry-run` — PLAUSIBLE (DEFERRED).**
  Re-key can hit a unique constraint if a user has both a Google-direct and WorkOS id
  (rolled back per-user with only a logged error); `--dry-run` always reports 0 moved.

### PLAUSIBLE — needs a real-transport test (DEFERRED, MCP)
- **Per-request identity handoff may not survive the real streamable-HTTP transport.**
  Tests only prove two `Request` objects over a hand-built scope share state; they
  never drive `StreamableHTTPServerTransport`. If `request_context.request` is the
  connect-time scope, identity falls back to the process identity → users collapse to
  one. Compounds P0 #1. Add a real-transport integration test before multi-user.

## Verified CLEAN (no action)
- Local stays authless (gated by `hosted`; no PyJWT/WorkOS imported in self-host);
  reject-unauth returns 401 + `WWW-Authenticate`; token crypto sound (RS256 pinned,
  JWKS, exp, iss-when-set); no open redirect; no secret logging.
- Synth concurrency (5/user): atomic per-user, no TOCTOU, both start paths gated,
  anonymous rejected.
- Status reconcile: gated on the finish report, terminal states short-circuit, no
  persistent false completion.
- Workbench freshness: no infinite-loop/dep bug, `inFlight` guard, visibility-gated
  polling. (Its every-focus full reload feeds the perf work — see
  `PERF_SLOW_UI_BRIEF.md`.)
- sby/xls/cocotb: no shell injection, deterministic cwd, null-safe parsing.

## Coverage gap (not yet reviewed)
Three landed WorkOS commits were not reviewed due to a reviewer branch-freshness
glitch: `b655a45` (browser refresh), `912883c` (hosted MCP OAuth), `b5eef07`
(Terraform WorkOS). Give them a dedicated pass when MCP work resumes.

---

## Suggested sequencing when we act
1. **Now / near-term (non-MCP):** chat heartbeat P0 (#2), synth reservation leak,
   chat F4 label — none touch MCP.
2. **Before hosted MCP multi-user:** MCP P0 (#1), audience-required (#3),
   `update_manifest` gating, the real-transport identity test, and the 3 unreviewed
   WorkOS commits.
