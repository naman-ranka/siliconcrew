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

## UI findings (skill-ui-nav, verified live in browser)

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F5 | MEDIUM (a11y) | OPEN | ⌘K/Ctrl+K command palette fires a Radix console error every open: `DialogContent requires a DialogTitle`. Missing accessible title on the palette Dialog → screen-reader + console noise. Fix: add a visually-hidden DialogTitle. |
| F6 | MEDIUM (UX/layout) | OPEN | Agent posture: open pinned nav rail (264px) shoves the artifacts slide-over tab strip off the right edge on viewports <~1650px → tabs become unclickable until the rail is closed. Real usability break at common laptop widths. |
| F7 | LOW (UX) | OPEN | Open nav rail overlays its own header hamburger → can only be closed via ⌘O / the rail's collapse control, not the toggle that opened it. |
| F8 | LOW (UX) | OPEN | File save gives no toast/confirmation — the only signal is the Save button re-disabling. Easy to miss. |

(Also documented, not a bug: Monaco now uses the EditContext API — editable `div.native-edit-context`, no textarea/`.inputarea` — the ui_navigation skill records the reliable type recipe for future e2e.)

## Exploration findings

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F9 | HIGH (blocker) | FIXED (04365b2) — DEPLOY PENDING | Hosted spec→GDS dies at CTS with SIGILL: the OpenROAD LEC (logical-equivalence) child exec'd from cts.tcl uses ISA extensions the Cloud Run CPU pool lacks → "illegal instruction" AFTER CTS metrics compute cleanly, blocking all hosted GDS. ASU p1 met timing at place (+0.372ns) but produced no GDS. Owner-directed fix: write `export LEC_CHECK = 0` into ORFS config.mk on HOSTED only (self-host keeps the real equivalence check). Both config.mk builders in synthesis_manager.py covered; regression test tests/test_lec_check_hosted.py. Deployed-CPU root cause = out of scope (owner). DEPLOYED backend-only to **rev siliconcrew-backend-00060** (built from the F1 base ccdb6e0 + LEC-only synthesis_manager.py overlay, EXCLUDING the unreviewed Wave 11 backend — templates/api routes/bundles/transcript — since those aren't gated yet; verified the deploy tree had LEC + none of Wave 11). /api/health 200. Live GDS verification in progress (gds-verify agent). |
| F9b | HIGH | OPEN (explore-mcp F2) | `retry_pd` resume-from-CTS doesn't stage the place checkpoint into the resumed worker's `results/<plat>/<top>/base/` → `ORD-0007 3_place.odb does not exist`. Cloud resume/adoption broken; also reported an artifact that isn't physically present (honest-state violation). Independent of F9. |
| F9c | MEDIUM | OPEN (explore-mcp F3) | Backend/unavailable errors (e.g. during a deploy) are surfaced to the MCP client as JSON-RPC `-32602 "Invalid request parameters"` — a lie that sends external-app devs hunting a nonexistent bad-arg bug. Map to `-32000` server-error + retry hint; health-gate/drain deploys. (This is the -32602 we saw during the F1 roll.) |

## Tenancy sweep result (reports/tenancy-sweep.md) — CLEAN

Read-only red-team of ALL MCP tools + REST /invoke + in-memory registries after
F1: **no new cross-tenant holes.** F1's three defects were the only ones, now
fixed+deployed. Every other surface is structurally safe: regular/run-id MCP
tools carry NO tenant-selecting argument (workspace is bound via current_session,
which the deployed F1 pre-dispatch gate owner-validates); REST /invoke +
/runs/{run_id} all call require_owned first; enforce_file_containment is
caller-scoped; the synth registry is keyed by (abspath(workspace), run_id) so
synth_0001 can't collide across owners; the resource surface gates every read via
_assert_session_readable. One NON-tenancy note (F10 below).

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F10 | LOW (capability, not tenancy) | OPEN | `update_manifest` is in MUTATING_TOOLS but missing from MCP `_PROTECTED_TOOLS` (mcp_server.py:231) → a hosted ANONYMOUS identity could mutate the manifest (still bounded to its own current_session; not cross-tenant). Already REVIEW_FINDINGS P2. One-liner: add "update_manifest" to _PROTECTED_TOOLS. |

## Decisions for the owner (surfaced, not guessed)

- **D1 — `.agents/` is gitignored** ("Local agent customizations and skills",
  .gitignore:220-221). Tonight's skills (gcp_logs verified-working, ui_navigation)
  and the pre-existing gcp_deployment skill live there → functional for local/future
  agent runs on this machine, but NOT in the repo/PR and lost if the dir is cleared.
  The "mature repository for future agents" goal may want them tracked. I HONORED the
  gitignore (did not override an explicit, commented convention). If you want them in
  the repo, say so and I'll move skills to a tracked path (e.g. `docs/agent-skills/`).

## Notes

- Discovered during setup (2026-07-07 ~04:30 UTC) before the run proper.
- Every exploration agent appends new rows here via its report; the
  orchestrator merges and triages.
