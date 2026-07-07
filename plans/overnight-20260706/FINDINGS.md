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
| F5 | MEDIUM (a11y) | FIXED (31a45db hidden DialogTitle) | ⌘K/Ctrl+K command palette fires a Radix console error every open: `DialogContent requires a DialogTitle`. Missing accessible title on the palette Dialog → screen-reader + console noise. Fix: add a visually-hidden DialogTitle. |
| F6 | MEDIUM (UX/layout) | RE-DIAGNOSED + FIXED (06f4e11) | Original "pinned rail shoves tabs" cause was WRONG (NavRail is a fixed overlay + scrim since Wave 8 — cannot displace layout; X2U-4 live probe agreed). The REAL clip: artifacts panel inner body minWidth:360 inside a width:min(42vw,520px) overflow-hidden wrapper → under ~857px viewport the tab strip's right edge clips. Fixed by flooring the width presets at max(360px,…) so wrapper==inner; no new state. Unit test guards the floor; visual check at ~800px queued for endgame Playwright. | Agent posture: open pinned nav rail (264px) shoves the artifacts slide-over tab strip off the right edge on viewports <~1650px → tabs become unclickable until the rail is closed. Real usability break at common laptop widths. |
| F7 | LOW (UX) | FIXED (2b16187 — ☰ duplicated into the rail header's top-left, same corner opens and closes; top-right collapse glyph replaced) | Open nav rail overlays its own header hamburger → can only be closed via ⌘O / the rail's collapse control, not the toggle that opened it. |
| F8 | LOW (UX) | FIXED (ee5d0e6 — success toast existed; failure path now toasts the real error) | File save gives no toast/confirmation — the only signal is the Save button re-disabling. Easy to miss. |

(Also documented, not a bug: Monaco now uses the EditContext API — editable `div.native-edit-context`, no textarea/`.inputarea` — the ui_navigation skill records the reliable type recipe for future e2e.)

## Exploration findings

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F9 | HIGH (blocker) | FIXED (04365b2) — DEPLOY PENDING | Hosted spec→GDS dies at CTS with SIGILL: the OpenROAD LEC (logical-equivalence) child exec'd from cts.tcl uses ISA extensions the Cloud Run CPU pool lacks → "illegal instruction" AFTER CTS metrics compute cleanly, blocking all hosted GDS. ASU p1 met timing at place (+0.372ns) but produced no GDS. Owner-directed fix: write `export LEC_CHECK = 0` into ORFS config.mk on HOSTED only (self-host keeps the real equivalence check). Both config.mk builders in synthesis_manager.py covered; regression test tests/test_lec_check_hosted.py. Deployed-CPU root cause = out of scope (owner). DEPLOYED backend-only to **rev siliconcrew-backend-00060** (built from the F1 base ccdb6e0 + LEC-only synthesis_manager.py overlay, EXCLUDING the unreviewed Wave 11 backend; verified the deploy tree had LEC + none of Wave 11). /api/health 200. **REFINED understanding (explore-mcp):** the CTS SIGILL is a HETEROGENEOUS-CPU-POOL FLAKE — on the OLD rev (no fix) CTS passed only ~1-in-3 (synth_0001 fail, synth_0003 fail, synth_0004 PASS→real GDS by luck). So hosted GDS was a **coin-flip per run**; the LEC_CHECK=0 fix makes it **dependable by construction** (no LEC child exec'd → no SIGILL regardless of CPU). explore-mcp's asu_p1_mcp_20260706 already has a real 6_final.gds (lucky pass). **F9 FIX DEFINITIVELY CONFIRMED ✅** (gds-verify, rev 00060, via UI): read `synth_runs/synth_0005/config.mk` on a FRESH run — it contains `export LEC_CHECK = 0`. The LEC child is disabled by construction → no SIGILL possible regardless of CPU (proof-of-mechanism, not luck). Full-flow GDS run polling for final metrics. |
| F9b | HIGH | ROOT-CAUSED (code correct; blocked on ORFS JOB-IMAGE redeploy) | NOT a synthesis_manager bug: the resume path already stages 3_place.odb + emits the volume map, and deploy/orfs_job/entrypoint.sh has had stage-in since 868907e (2026-06-24). But recent rolls were BACKEND-ONLY — the separate `siliconcrew-orfs` Cloud Run job image was never rebuilt, so the live job still runs a pre-868907e entrypoint with no stage-in → ORD-0007 on the worker. Manager-side contract + honest-state locked by tests/test_retry_pd_resume_staging.py (3927e60). REMEDIATION (endgame deploy): rebuild+push the orfs job image from deploy/orfs_job/, update the Cloud Run job, then re-verify a hosted resume-from-CTS produces 4_cts.odb. Full analysis: reports/legibility-backend.md. |
| F9c | MEDIUM | ROOT-CAUSED + FIXED self-host (835c1e6); hosted one-liner PENDING (task #10) | The -32602 is not SiliconCrew code: session-less Streamable HTTP transport ran with SDK default `stateless=False`, so after a restart the reused connector session hits the SDK's "Received request before initialization" RuntimeError (server/session.py:192) which the base receive loop's broad `except` blanket-maps to -32602 (shared/session.py:385). Fix = pass `stateless=True` to match the session-less transport (as the SDK's own StreamableHTTPSessionManager does) — post-restart requests then SUCCEED instead of erroring, which also cures F15's break-on-every-deploy. Self-host `--transport http` fixed in mcp_server.py; hosted mount fixed too (cad3242). Mechanism regression: tests/test_mcp_preinit_error_mapping.py. Expected side effect: F15 (connector breaks on every deploy) should be cured for all deploys AFTER the next one ships this fix — verify on the deploy after that. |

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
| F10 | LOW (capability, not tenancy) | STALE / NOT-A-BUG — drift-guarded (ef0e1d0) | As filed, already closed: `_PROTECTED_TOOLS` aliases tool_catalog.PROTECTED_TOOLS which has contained update_manifest since c072d5c; anonymous MCP identity is refused at the gate (runtime-verified). Locked with tests/test_mcp_protected_policy.py: update_manifest gated + every MUTATING MCP tool is PROTECTED or in an explicit intentionally-open allowlist (sim tools are deliberately open for anonymous trial). Guard proven to fire on the reconstructed pre-c072d5c set. |

## UI-as-human findings (explore-ui — full spec→GDS by hand, verdict: engine capable, FAILURE-LEGIBILITY is the weak point)

Headline insight: a hardware designer CAN reach spec→GDS unaided, but a first-timer
would likely quit at an opaque "failure" — the engine is honest+capable; where it
fails the human is making failures legible. explore-ui independently hit the CTS
coin-flip a 3rd time (synth_0001 fail → synth_0002 pass → GDS).

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| F11 | HIGH (UX/legibility) | FIXED (c8ab0b0 backend passMarker + 4b9993c render; contract: reports/legibility-contract.md) | A PASSING sim is reported "failed" when the TB prints "ALL TESTS PASSED" but not the exact substring the tool greps ("TEST PASSED", run_simulation.py:11,437). The failed card shows NO reason; the truth (passMarkerFound:false, stdout says PASSED) is buried in sim_runs/.../run_meta.json. Fix: surface the expected pass-marker + stdout tail on the failed card. A first-timer gives up here. |
| F12 | HIGH (UX/legibility) | FIXED (910ecb1 stage/notes plumbing + 4b9993c row reason + report failure panel) | Synth failure is opaque in the UI: "failed" + partial metrics + a Retry button, but the real error is ~7 folders deep in orfs_logs/.../4_1_cts.log. Fix: surface the FAILING STAGE + that stage's log tail on the run card / Report. |
| F13 | LOW (editor) | OPEN | Monaco auto-close strands a `)` when a line ends in a bare `(` (U4). |
| F14 | LOW (UX) | OPEN | Top-module chips are display-only (U6) — can't act on them. |
| F15 | MEDIUM (ops) | OPEN | The claude.ai Silicon_crew MCP connector does NOT re-handshake after a Cloud Run revision swap — it returns -32602 indefinitely until a MANUAL reconnect on the claude.ai side. So every backend deploy breaks the hosted MCP integration until someone reconnects it. Compounds F9c (backend-unavailable mis-mapped to -32602). Ops implication: MCP-driven verification can't survive a mid-run deploy; the UI/Playwright path can. |

(Confirmed dups: U5 = F8 no-save-toast; U7 = F5 ⌘K Radix a11y; U2 = F9 CTS SIGILL.)
Positives to NOT regress (explore-ui): manifest auto-population; /invoke tags UI gestures as "You" in Activity (inv.3); honest per-run status + retained failures (inv.4); dispatch→poll(Refresh)→read behaved as documented; good waveform / GDS-layout / report viewers.

## Explore round 2 — UI-as-human (reports/explore2-ui.md, session x2_debounce_ui_20260707)

Headline: first-timer reached routed GDS BY HAND on the FIRST synth attempt (F9
fix live-confirmed again); F11 confirmed+strengthened with a real injected bug
(fix already landed tonight: 4b9993c renders exactly the fields the report asks
for); F8 correction — the "Saved" toast already existed on deployed (X2U-3);
F5/F7/F13 confirmed (F5 fixed tonight; F13 trigger pinned: line ending in bare
`(`).

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| X2U-1 | LOW (ops) | EXPECTED-RESOLVED by landing deploy | favicon.ico 404 on every page load — pre-landing frontend rev has no favicon. Verify gone at endgame live-check. |
| X2U-2 | LOW (honesty) | FIXED (e3f3844) | Report scanned workspace ROOT for .out/simulation.log (isolated sim runs never write there) → always "Not Run"; spec detection matched only *_spec.yaml. Now reads list_sim_runs (latest verdict + "latest of N"), recognizes spec.md/*_spec.md/spec.{yaml,yml,txt}; legacy fallbacks kept. 6 regression tests, 4 proven failing pre-fix. |
| X2U-3 | POSITIVE | — | Save already toasts "Saved · <file>" on deployed; tonight's ee5d0e6 adds the missing FAILURE toast. F8 fully closed. |
| X2U-4 | correction | — | F6 not reproducible live; see F6 row. |

## Explore round 2 — hosted MCP / FIR (reports/explore2-mcp.md, session x2_fir_mcp_20260707)

Engine verdict: capable + honest end-to-end (clean-room FIR → real GDS; honest
failing timing WNS -6.36ns for a deliberately unpipelined MAC; F9 re-confirmed
via auto_checks.equiv=skip). All weak points are hosted plumbing/legibility.
Triage of X2M findings:

| ID | Severity | Triage |
|----|----------|--------|
| X2M-1 (post-synth degradation: hangs + -32602 flapping) | HIGH | EXPECTED-RESOLVED by tonight's deploy: live rev 00060 still runs the unconditional whole-workspace sync (F2 fix f095fcb undeployed) — a post-synth workspace (20 ODBs, 2 GDS) makes every call tar+PUT the tree; the -32602 flapping is the F9c pre-init mapping after instance recycle (stateless fix undeployed). POST-DEPLOY VERIFY: on the existing x2_fir_mcp_20260707 session, read-only MCP calls (read_spec, list_files, get_synthesis_status) must return fast and repeatedly. |
| X2M-2 (all 5 PD-summary tools -32602 on a completed run, incl. no-arg get_cts_summary, while status/search/report worked same-minute) | HIGH | ASSIGNED (small-fixes lane): family-wide pattern suggests a REAL schema/validation rejection specific to these wrappers, not load. Investigate signatures vs working tools; add an every-tool schema-validation guard test. |
| X2M-3 (-32602 lie across ~8 tools) | MED | F9c CONFIRMED with broad evidence; fix ships tonight. |
| X2M-4 (wait_for_synthesis >300s despite max_wait_sec=120; status read hung) | MED | Largely F2-coupled (sync stall inside the read path) → expected-resolved; post-deploy verify. If a status read can EVER exceed its ceiling post-F2, that's a real invariant-5/6 hole to fix then. |
| X2M-5 (schematic_tool leaks raw docker-socket error on hosted) | MED | ASSIGNED (small-fixes lane): honest hosted message via settings.hosted gate; hosted schematic support = owner decision, deferred. |
| X2M-6 (waveform: raw binary values, undocumented VCD-native time units) | LOW-MED | DEFERRED, documented — good first fix for a future wave (radix + unit hints). |
| X2M-7 (apply_patch rejects context-only diffs) | LOW | DEFERRED — document line-numbered-hunk requirement or accept context hunks. |
| X2M-8 (14-min synth stage with empty last_log_lines) | LOW | DEFERRED — feeds the known "stream synth-stage logs" idea (F12 family). |
| X2M-9 (256 mW total power for 8k-cell sky130 design, no sanity flag) | LOW | DEFERRED — units/parse sanity check on power metrics; unconfirmed concern. |
| X2M-10 (stage_history ended_at batch-stamped identical; manifest sessionId "") | LOW | Known-deferred hosted per-stage timings; sessionId note logged. |

Ops decision: the CODEX explorer is RESEQUENCED to AFTER the deploy — pre-deploy
it would re-document known-fixed bugs (F2 sync latency, -32602); post-deploy it
doubles as live verification of F2/F9c/X2M-1/X2M-4 resolution and of the
connector surviving the roll (F15/stateless).

## Explore round 2 — agent/delegate posture (reports/explore2-agent.md, session x2_uart_agent_20260707)

Delegated a UART TX (8N1, self-checking TB) to the in-app agent (Gemini 3.5 Flash on
hosted). Verdict: platform honest-state machinery + synth engine strong; the delegating
MODEL is the weak point and produced a dishonest ending. Contract honored (⌘K no palette,
read-only file viewer, no file-creation UI, Runs/Files Index home tab, "Artifacts · 1 new"
unread marker, expandable cards with real result JSON incl. F11/F12 timeout detail).

**Backend root-cause (code-verified — answers the owner's "the turn kept going in the
backend"):** (1) synthesis is a DETACHED job — `start_synthesis` dispatches an independent
ORFS/Cloud Run job (run dir = DB, dispatch→poll→read); turn 2 launched it, then died on
recursion_limit, and the job finished in the background → the real synth_0001+GDS exist
though no turn "watched" them. (2) A dropped socket does NOT stop the chat turn — server
keeps the graph running headless to completion (api.py:1636-1639, 1771-1776); the
"connection lost — may still be running" card (store.ts:859-873) is literally true.
(3) The steer prompt DID land as turn 3 (post-reload isStreaming=false → sent immediately,
store.ts:890-899); the model simply IGNORED it (never edited the TB) — a model-obedience
failure, not delivery. Per-turn budget is only `recursion_limit: 50` (api.py:1596) — a
hanging-TB fix loop exhausts it, so turns die mid-work with raw "Sorry, need more steps".

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| X2A-1 | HIGH (honesty, model layer) | OPEN | Delegate's final prose fabricated "successfully verified … RTL Simulation: Passed, 8/8 tests, TEST PASSED" — no sim ever passed (all timed out); TB still had no clk init. Cards told the truth; the model's summary lied. Argues for a Claude default in the hosted delegate. |
| X2A-2 | MED-HIGH (honesty, platform artifact) | OPEN | `generate_report_tool`'s design_report.md "Verification Results" table marks **Simulation: ✅ Pass** when no sim passed (likely inferred from a partial dump.vcd / default). Persisted, authoritative-looking. Fix: gate the report's sim verdict on the last sim's pass_marker_found/status. Synth PPA in the same report IS real. |
| X2A-3 | MED (model capability) | OPEN | For a moderately complex bit-period-sampling TB, the delegate wrote a broken TB (clk never initialized → sim hangs to 60s ceiling), looped ~6× across two TBs, and never diagnosed it even when handed the exact fix. |
| X2A-4 | MED (legibility, inv.6) | OPEN | Artifacts Index home tab doesn't update live during a run — Files/Runs showed 0 through the whole turn (and after synth_0001 was created); only a full reload populated them. Inline cards DO stream live → two divergent views during a live turn. |
| X2A-5 | LOW-MED (legibility) | OPEN | "Connection lost" card says "Check the Runs / Signoff panel," but agent sims are ephemeral (run_isolated_simulation in /tmp scratch, no run record) → that panel is empty for sims. Hint is correct only for synthesis. |
| X2A-6 | LOW (robustness/UX) | OPEN | recursion_limit=50 exhausted by a normal fix loop → raw LangGraph error shown verbatim ("…set the recursion_limit config key… docs.langchain.com/…GRAPH_RECURSION_LIMIT") + "Sorry, need more steps"; no Continue/Resume affordance (user must know to type "continue"). |

Cross-ref re-observed: **F5 CONFIRMED still live on deployed frontend rev 00049** (DialogContent-requires-DialogTitle fired from the New Session dialog, not just ⌘K; + companion missing-aria-describedby warning); favicon 404 (X2U-1); F11/F12 legibility fix present in the agent shell (POSITIVE); F9 GDS dependable (POSITIVE).

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

## Landing page status (landing-impl) — CODE DONE + HONEST; content is the gap

Verified myself (not on faith): the gallery is purely store-driven (`templates.map`
from real `/api/templates`, gated `templates.length>0`, no hardcoded/fabricated
cards — the 4 example names in the screenshots appear NOWHERE in the repo); gates
green (tsc, vitest 374 pass + the 1 known-pre-existing failure, next build,
Launcher e2e 2/2 with preserved testids/strings); both themes render; posture
(sessions.length pivot) correct: empty→hero+gallery+CTA, populated→workspaces
first. Well-built OSS identity (logo/favicon/metadata), GitHub+Issues, honest hero
(README tagline + the ONE sourced CVDP 68.5% number, no fake social proof), footer.

**F18 (transparency) — the report's screenshots are MOCKED.** Both the sessions
(sync_fifo/uart_tx) AND the 4 GDS-laden example cards (seven_seg_seconds,
asu_p1_seq_detector, asu_p9_fir, lfsr8) are Playwright fixture data, not real. The
REAL deployed gallery today shows only `examples/sync_fifo` (1 bundle, sim-only, no
GDS, no chat transcript). The screenshots oversell current state — landing-impl
didn't disclose the mock. Not a product bug (code is honest), but the SHOWCASE
CONTENT is thin. **Action: author real bundles (below) before the landing deploy so
the gallery is genuinely rich, not a 1-item list.**

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

## D3 follow-up — RESOLVED (session 2, code-path verified)

Hosted Fork is already presented honestly: `fork_from_template` raises
`TemplatesUnavailable("Templates are available in self-host today; the hosted
gallery is a later wave.")` (src/utils/templates.py:338), the route maps it to
HTTP 400 with that string as `detail` (api.py:813-814), `apiFetch` throws
`Error(detail)` (frontend/lib/api.ts:60-65), and `TemplatePreview` renders it
as a `role="alert"` line above the Fork button (TemplatePreview.tsx:201-205).
No raw 400 reaches the user. Final visual confirmation at endgame live-verify.

## Session 2 baseline (HEAD 608864e, 2026-07-06 ~23:40 MST)

- Backend pytest: **9 failed, 679 passed, 8 skipped** — identical to the known
  9-failure machine baseline (congestion x2, lint norm_file, llm_factory,
  orfs_job stage_in, perf_read_no_sync, sby_engine, xls x2). Zero new.
- Frontend: tsc clean; vitest **1 known pre-existing failure**
  (chat.threads.store.test.ts, from af0124b) + 367 pass; next build green.

## Notes

- Discovered during setup (2026-07-07 ~04:30 UTC) before the run proper.
- Every exploration agent appends new rows here via its report; the
  orchestrator merges and triages.
