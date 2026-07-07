# Findings ledger — overnight 2026-07-06

Status: OPEN | CONFIRMED | FIXED (commit) | DEFERRED | NOT-A-BUG

| ID | Severity | Status | Summary | Detail |
|----|----------|--------|---------|--------|
| F1 | CRITICAL (tenancy, invariant 8) | FIXED (7b9fa8e) — DEPLOY PENDING | Hosted MCP had 3 cross-tenant defects: (1) `list_sessions_tool` leaked all owners' sessions (the 33-session symptom); (2) `delete_session_tool` bypassed the ownership guard → any signed-in user could destroy any tenant's workspace/chats/checkpoints by id (single-request, destructive); (3) process-global `current_session` on the one shared hosted server → cross-tenant read/write under concurrency. Stopgap: scope list+delete by `_scoped_user_id()`, pre-dispatch `owns_session` gate. Durable fix (request-scope current_session) = REVIEW_FINDINGS P0 #1, deferred. | reports/F1-tenancy.md |

## Deploy note (F1)

F1 fix touches ONLY `mcp_server.py` (backend). The live hosted backend is
vulnerable to single-request cross-tenant deletion until redeployed. Plan:
backend-only Cloud Run roll of a clean commit once it won't contend with the
fleet's docker sims (impl-templates uses docker sim_engine). Frontend unchanged.

## Notes

- Discovered during setup (2026-07-07 ~04:30 UTC) before the run proper.
- Every exploration agent appends new rows here via its report; the
  orchestrator merges and triages.
