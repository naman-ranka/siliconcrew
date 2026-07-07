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
Frontend untouched (still rev 00049).

**F1 LIVE-CONFIRMED ✅** (explore-mcp, 05:43 UTC, rev 00059): `list_sessions_tool`
returned exactly 3 sessions — all owned by the test account (rockstarme.the5 /
same workos_user_id); ZERO foreign-tenant sessions. The 33-session multi-owner
leak is gone on the deployed backend. (Durable structural follow-up — request-scope
current_session off the shared instance, REVIEW_FINDINGS P0 #1 — still recommended;
the deployed pre-dispatch gate is defense-in-depth covering it meantime.)

## Codex latency findings (reports/codex-latency.md)

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F2 | HIGH (perf) | FIXED (f095fcb) — DEPLOY BATCHED | Every MCP tool call runs `session_request_scope` whose `finally` unconditionally calls `provider.sync()` → `CloudWorkspaceProvider.sync` tars the WHOLE workspace + uploads to GCS (`workspace_provider.py:325`), even for read-only tools (read_file/get_manifest/get_synthesis_status…). A design loop is mostly reads → each pays a full workspace tar+PUT for nothing. This is the primary "codex tool calls are slow" cause. Fix: gate sync to `name in MUTATING_TOOLS` (tool_catalog.py:84) via a `sync: bool` on run_in_session/session_request_scope. **RISK: requires auditing MUTATING_TOOLS covers EVERY workspace-writing tool — a mutating tool missing from the set would silently lose its writes (never uploaded).** ~15-20 LOC. |
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
| F9 | HIGH (blocker) | FIXED (04365b2) — DEPLOY PENDING | Hosted spec→GDS dies at CTS with SIGILL: the OpenROAD LEC (logical-equivalence) child exec'd from cts.tcl uses ISA extensions the Cloud Run CPU pool lacks → "illegal instruction" AFTER CTS metrics compute cleanly, blocking all hosted GDS. ASU p1 met timing at place (+0.372ns) but produced no GDS. Owner-directed fix: write `export LEC_CHECK = 0` into ORFS config.mk on HOSTED only (self-host keeps the real equivalence check). Both config.mk builders in synthesis_manager.py covered; regression test tests/test_lec_check_hosted.py. Deployed-CPU root cause = out of scope (owner). DEPLOYED backend-only to **rev siliconcrew-backend-00060** (built from the F1 base ccdb6e0 + LEC-only synthesis_manager.py overlay, EXCLUDING the unreviewed Wave 11 backend; verified the deploy tree had LEC + none of Wave 11). /api/health 200. **REFINED understanding (explore-mcp):** the CTS SIGILL is a HETEROGENEOUS-CPU-POOL FLAKE — on the OLD rev (no fix) CTS passed only ~1-in-3 (synth_0001 fail, synth_0003 fail, synth_0004 PASS→real GDS by luck). So hosted GDS was a **coin-flip per run**; the LEC_CHECK=0 fix makes it **dependable by construction** (no LEC child exec'd → no SIGILL regardless of CPU). explore-mcp's asu_p1_mcp_20260706 already has a real 6_final.gds (lucky pass). **F9 FIX DEFINITIVELY CONFIRMED ✅** (gds-verify, rev 00060, via UI): read `synth_runs/synth_0005/config.mk` on a FRESH run — it contains `export LEC_CHECK = 0`. The LEC child is disabled by construction → no SIGILL possible regardless of CPU (proof-of-mechanism, not luck). Full-flow GDS run polling for final metrics. |
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

## UI-as-human findings (explore-ui — full spec→GDS by hand, verdict: engine capable, FAILURE-LEGIBILITY is the weak point)

Headline insight: a hardware designer CAN reach spec→GDS unaided, but a first-timer
would likely quit at an opaque "failure" — the engine is honest+capable; where it
fails the human is making failures legible. explore-ui independently hit the CTS
coin-flip a 3rd time (synth_0001 fail → synth_0002 pass → GDS).

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F11 | HIGH (UX/legibility) | OPEN | A PASSING sim is reported "failed" when the TB prints "ALL TESTS PASSED" but not the exact substring the tool greps ("TEST PASSED", run_simulation.py:11,437). The failed card shows NO reason; the truth (passMarkerFound:false, stdout says PASSED) is buried in sim_runs/.../run_meta.json. Fix: surface the expected pass-marker + stdout tail on the failed card. A first-timer gives up here. |
| F12 | HIGH (UX/legibility) | OPEN | Synth failure is opaque in the UI: "failed" + partial metrics + a Retry button, but the real error is ~7 folders deep in orfs_logs/.../4_1_cts.log. Fix: surface the FAILING STAGE + that stage's log tail on the run card / Report. |
| F13 | LOW (editor) | OPEN | Monaco auto-close strands a `)` when a line ends in a bare `(` (U4). |
| F14 | LOW (UX) | OPEN | Top-module chips are display-only (U6) — can't act on them. |
| F15 | MEDIUM (ops) | OPEN | The claude.ai Silicon_crew MCP connector does NOT re-handshake after a Cloud Run revision swap — it returns -32602 indefinitely until a MANUAL reconnect on the claude.ai side. So every backend deploy breaks the hosted MCP integration until someone reconnects it. Compounds F9c (backend-unavailable mis-mapped to -32602). Ops implication: MCP-driven verification can't survive a mid-run deploy; the UI/Playwright path can. |

(Confirmed dups: U5 = F8 no-save-toast; U7 = F5 ⌘K Radix a11y; U2 = F9 CTS SIGILL.)
Positives to NOT regress (explore-ui): manifest auto-population; /invoke tags UI gestures as "You" in Activity (inv.3); honest per-run status + retained failures (inv.4); dispatch→poll(Refresh)→read behaved as documented; good waveform / GDS-layout / report viewers.

## Wave 11 adversarial review (reports/review-templates.md) — SAFE TO KEEP

Verdict: safe; build the landing gallery on it. A1–A8 all verified honored (create-first,
netlist rewrite over every run_meta, manifest sessionId clear, aware-UTC forked_at,
hosted hard-gate as first statement, delete_session rollback, no api.py import in the
reader, single-segment template routes avoid the greedy /sessions catch-all, caller-owned
fork). Gate claims re-verified true (26 pytest pass; the 1 vitest failure is pre-existing
from af0124b). Two real-but-minor defects to fix:

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F16 | MEDIUM (privacy) | FIXED (8e90f1b) | Export sanitizer (`templates.py:383` `_sanitize_exported_workspace`) redacts author host-paths ONLY in run_meta.json; `attempt_events.jsonl`/`attempt_log.json` are copied verbatim and `conversations/*.md` are rendered post-sanitize with no redaction. A future export of a synthesis/chat session could leak `C:\Users\<name>\…` into the PUBLIC examples repo. Docstring overstates ("strips author identity"). Shipped sync_fifo bundle is verified clean. Fix: redact events + transcript too, or narrow docstring + rely on curator review. Matters for the flagship p1 export. |
| F17 | LOW-MED (invariant 7) | FIXED (8e90f1b) | Provenance chip blanks after renaming/moving a forked session: `patch_session` (api.py:1275) builds SessionResponse WITHOUT source_template (→null), and store `renameSession`/`moveSession` overwrite currentSession with it → chip disappears until next loadSessions (SWR "populated data never blanks" violation). Fix: include source_template in patch_session response (like list/get). |

## Decisions for the owner (surfaced, not guessed)

- **D1 — `.agents/` is gitignored** ("Local agent customizations and skills",
  .gitignore:220-221). Tonight's skills (gcp_logs verified-working, ui_navigation)
  and the pre-existing gcp_deployment skill live there → functional for local/future
  agent runs on this machine, but NOT in the repo/PR and lost if the dir is cleared.
  The "mature repository for future agents" goal may want them tracked. I HONORED the
  gitignore (did not override an explicit, commented convention). If you want them in
  the repo, say so and I'll move skills to a tracked path (e.g. `docs/agent-skills/`).

## D2 — Flagship GDS showcase bundle: path decision

The strongest showcase would be a full spec→GDS session (ASU p1) as a forkable
bundle. But: the p1 GDS session that exists (`asu_p1_mcp_20260706`) lives in the
HOSTED deployment (GCS, test account), while Wave 11's export utility targets
LOCAL self-host workspaces (A5). So making it a bundle needs one of:
  (a) a fresh LOCAL self-host spec→GDS run (needs local ORFS/OpenROAD docker
      image + a CPU that survives LEC — heavy, not attempted tonight to avoid a
      rabbit hole), then `export_session_bundle`; OR
  (b) a hosted-session→bundle export path (net-new; Wave 11 is self-host only).
Meanwhile `examples/sync_fifo` (sim-only, real trajectory) already ships as a
working example. RECOMMENDATION: ship sync_fifo now; do a deliberate local
GDS authoring run for the flagship as a follow-up (or when you point me at a
keyed local run). Not blocking the landing.

## Deploy status (hosted, us-central1)

- backend **rev 00060** LIVE = F1 tenancy fix + F9 LEC_CHECK=0. (frontend rev
  00049 unchanged.) Both verified /api/health 200.
- PENDING deploys — **strategy simplified now that Wave 11 is adversarially
  reviewed (SAFE) + F16/F17 fixed.** The minimal-overlay dance was only needed
  while Wave 11 was unreviewed. Now the whole branch is reviewed/gated, so the
  end-of-night deploy is: run the FULL gate suite on final HEAD (backend pytest
  vs the 9-known baseline; frontend tsc/vitest/build/playwright), and if green,
  deploy **backend HEAD** (F1+F9+F2+Wave11+F16/F17) and **frontend HEAD**
  (landing + gallery) together from the reviewed tip. Live-verify: landing
  renders, gallery lists, GDS still works, tenancy still scoped.
- Timing: deploy when NO MCP-driven agent is mid-run (every backend deploy breaks
  the claude.ai MCP connector until manual reconnect, F15) — and after the
  landing lands + is adversarially reviewed.

## D3 — Hosted showcase vs self-host-only fork (real tension for the owner)

Wave 11 A5 HARD-GATES fork to self-host (hosted fork returns 400 — the GCS-copy
path is deferred). But your showcase goal is that visitors on the DEPLOYED app can
fork examples to "see the files, see how the agent ran." So on hosted, the gallery
will LIST + PREVIEW examples but the "Fork this example" action will 400.
- Mitigation that may already satisfy the goal: TemplatePreview shows the file
  list + conversation transcript names + "what's inside" WITHOUT forking — so a
  hosted visitor can still SEE the agent's work via preview; only creating their
  own editable copy is self-host-only. (Verify what preview renders on hosted.)
- Options for you: (a) ship hosted gallery as browse/preview-only with fork
  disabled + an honest "fork available in self-host" message (Level-1 honest);
  (b) build the hosted-fork GCS-copy path (deferred Level-3 work, non-trivial);
  (c) make preview rich enough (files + trajectory + transcript inline) that
  "fork" is optional for the showcase. RECOMMEND (a)+(c) for now; (b) later.
- FOLLOW-UP (not landing-impl's job — ExampleCard/TemplatePreview are off-limits
  to it): verify how the gallery's "Fork" action behaves on hosted today — does it
  show a graceful "available in self-host" message, or a raw 400 error? If raw,
  a small Wave-11 gallery fix should present it honestly per deployment mode. To
  do after the landing lands.

## Notes

- Discovered during setup (2026-07-07 ~04:30 UTC) before the run proper.
- Every exploration agent appends new rows here via its report; the
  orchestrator merges and triages.
