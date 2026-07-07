# Findings ledger — overnight 2026-07-06

Status: OPEN | CONFIRMED | FIXED (commit) | DEFERRED | NOT-A-BUG

| ID | Severity | Status | Summary | Detail |
|----|----------|--------|---------|--------|
| F1 | HIGH (tenancy, invariant 8) | OPEN | Hosted MCP `list_sessions_tool` returned 33 sessions across owners to test user rockstarme.the5@gmail.com (frontend correctly shows 2). MCP writes as the test user (probe session appeared in its Launcher), so the list path appears unscoped. Must also check `set_active_session`/read tools for cross-owner workspace access. | reports/F1-tenancy.md |

## Notes

- Discovered during setup (2026-07-07 ~04:30 UTC) before the run proper.
- Every exploration agent appends new rows here via its report; the
  orchestrator merges and triages.
