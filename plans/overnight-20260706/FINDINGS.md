# Findings ledger — overnight 2026-07-06

Status: OPEN | CONFIRMED | FIXED (commit) | DEFERRED | NOT-A-BUG

| ID | Severity | Status | Summary | Detail |
|----|----------|--------|---------|--------|
| F1 | CRITICAL (tenancy, invariant 8) | FIXED (7b9fa8e) — DEPLOY PENDING | Hosted MCP had 3 cross-tenant defects: (1) `list_sessions_tool` leaked all owners' sessions (the 33-session symptom); (2) `delete_session_tool` bypassed the ownership guard → any signed-in user could destroy any tenant's workspace/chats/checkpoints by id (single-request, destructive); (3) process-global `current_session` on the one shared hosted server → cross-tenant read/write under concurrency. Stopgap: scope list+delete by `_scoped_user_id()`, pre-dispatch `owns_session` gate. Durable fix (request-scope current_session) = REVIEW_FINDINGS P0 #1, deferred. | reports/F1-tenancy.md |

## Deploy note (F1) — DEPLOYED

F1 fix DEPLOYED (backend-only) 2026-07-07 ~05:2x UTC. Verified the delta was
provably minimal: live backend was commit e6c5c95 (rev 00058); its backend
source is identical to HEAD except mcp_server.py (the fix), CLAUDE.md (docs),
and the new test — so the deploy shipped exactly the F1 fix, nothing else
runtime. Built ccdb6e0 → pushed digest sha256:06423cd... → rolled backend to
**revision siliconcrew-backend-00059-d5c**, 100% traffic, `/api/health` 200.
Frontend untouched (still rev 00049). The revision swap dropped live MCP client
sessions (-32602 until reconnect) — expected, explorer notified. Live MCP
re-verification (list_sessions returns only the caller's sessions) is pending a
fresh client handshake; code correctness is proven by tests/test_mcp_tenancy_f1.py.

## Codex latency findings (reports/codex-latency.md)

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F2 | HIGH (perf) | CONFIRMED (code) — FIX QUEUED | Every MCP tool call runs `session_request_scope` whose `finally` unconditionally calls `provider.sync()` → `CloudWorkspaceProvider.sync` tars the WHOLE workspace + uploads to GCS (`workspace_provider.py:325`), even for read-only tools (read_file/get_manifest/get_synthesis_status…). A design loop is mostly reads → each pays a full workspace tar+PUT for nothing. This is the primary "codex tool calls are slow" cause. Fix: gate sync to `name in MUTATING_TOOLS` (tool_catalog.py:84) via a `sync: bool` on run_in_session/session_request_scope. **RISK: requires auditing MUTATING_TOOLS covers EVERY workspace-writing tool — a mutating tool missing from the set would silently lose its writes (never uploaded).** ~15-20 LOC. |
| F3 | HIGH (perf) | CONFIRMED (code) — FOLLOW-UP | Codex spawns a fresh MCP subprocess per user turn; each cold-start pays heavy import + `init_schema()` DDL (6 Postgres round-trips) + WorkOS token verify (cold JWKS). This is `[CODEX-TIMING] elapsed_setup` = seconds before first token. Cheap partial: skip init_schema when a sentinel says schema exists. Real fix: keep the Codex app-server + MCP child warm across turns (lifecycle change, own small plan). |
| F4 | MEDIUM (perf) | CONFIRMED (code) — FOLLOW-UP | `PostgresMetadataStore._connect()` opens a new Cloud SQL connection per call (no pool) in the MCP subprocess → TLS+connector handshake (~50-200ms) on every metadata-touching tool. Fix: one long-lived connection / tiny pool in the store. ~10-20 LOC. |

Confirmation pending: a browser Codex run grepping Cloud Run logs for `[CODEX-TIMING]`
to size each bucket (the server is already instrumented).

## Template curation decisions (reports/template-candidates.md)

- A SiliconCrew template = **spec + TB + agent-generated trajectory**; RTL is NOT
  shipped → clean-room spec/TB authoring sidesteps reference-RTL licensing for
  textbook designs.
- **CVDP excluded** from the public gallery (NVIDIA `no_commercial` license) — stays
  an internal benchmark. Only Apache-2.0 Tiny Tapeout designs may be forked verbatim.
  ASU repo has no LICENSE → treat specs as inspiration, author clean-room.
- Gallery top 6: 7-Seg Seconds (TT05, Apache), ASU p1 seq_detector_0011, ASU p9 FIR,
  Traffic-Light FSM (clean-room), LFSR (clean-room), Simon Says (TT06, Apache).
- Phase-2 export BLOCKED on: Wave 11 export utility landing (task #10) + a real
  endgame full-flow session. explore-mcp is running ASU p1 now → flagship-bundle
  candidate if it reaches synth/GDS.

## Notes

- Discovered during setup (2026-07-07 ~04:30 UTC) before the run proper.
- Every exploration agent appends new rows here via its report; the
  orchestrator merges and triages.
