# Explore round 2 — Codex-agent UX + latency

Evaluating the **Codex agent experience for a user of the deployed web app**:
switch the agent panel to the **Codex** tab and run a multi-turn design
conversation, judging drivability, latency, continuity, and UX. Two legs
planned: **Leg 1** (this section) is the pre-deploy baseline against live
backend **rev 00060** (F2 unconditional whole-workspace sync still shipping).
**Leg 2** (placeholder at bottom) re-runs the same conversation after tonight's
deploy to measure the delta.

**Method (per owner course-correction): drive the deployed frontend UI**, not
the local CLI. The UI route is the deliverable; the CLI measurements are kept
as **Appendix A**. UI session: `x2_codex_ui_20260707` (hosted, test account).

---

## Leg 1b — Codex via the deployed UI (DELIVERABLE — the primary result)

Frontend `https://siliconcrew-frontend-psp2dkllmq-uc.a.run.app/`, signed in as
`rockstarme.the5@gmail.com` (already authenticated — no AuthKit step needed).
Created `x2_codex_ui_20260707` in **Agent** posture, switched the agent panel's
**Workbench | Codex** toggle to **Codex**. This is SiliconCrew's server-side
Codex brain (the `[CODEX-TIMING]` path, hosted mode → F2/F3 apply), driven from
the user's seat.

### Wiring & first impressions (UI)

- Switching to **Codex** shows a **"Codex — ChatGPT connected"** account chip
  and opens a fresh Codex chat thread. **No auth/link step was required** — the
  ChatGPT account is already connected on the test account, so the "does the
  Codex tab need a link step" risk did not materialize here (a first-time user
  without a connected account would see the connect affordance — untested).
- **UX bug — stale model label:** the composer's model picker still reads
  **"Gemini 3.5 Flash"** while the Codex tab is active, even though Codex runs
  on the connected ChatGPT account (a gpt-5.x brain), not Gemini. Misleading:
  the user can't tell which model is actually answering on the Codex tab
  (X2C-6).

### Turn 1 — "design a 4-bit Gray-code counter + self-checking TB, lint,
simulate" (UI)

Thread `6287…bb44`, turn `5f76…047`, sent 08:03:23 UTC. **First visible
activity ("Thinking · 7s") ~7s after Send.** The Codex agent's work rendered as
**legible inline cards** — each a friendly name + duration + a contextual action
button — in this order: `get_current_session` → `Listing Files · 1s` → `Writing
Specification · gray4` *(Open spec)* → `Reading Specification` *(Open spec)* →
`Writing File · gray4.v` *(Open file)* → `Writing File · gray4_tb.v` *(Open
file)* → `update_manifest` → `Running Linter · gray4.v` → `Running Linter ·
gray4.v, gray4_tb.v` → `run_isolated_simulation` *(Open waveform)* → `Starting
Synthesis · gray4.v` *(Open report)* → `Waiting for Synthesis · 60s / 106s / …`.
The Artifacts Index populated live (`synth_0001` gray4, `sim_0001` gray4_tb).

**Server-side latency for this turn (`[CODEX-TIMING]`, authoritative):**

| bucket | value | note |
|---|---|---|
| `elapsed_setup` (F3 cold-start) | **10.17s** | fresh MCP subprocess bring-up before first token |
| `sdk_turn_issued` | 0.05s | issuing the turn is cheap |
| get_current_session | 0.05s | |
| list_files_tool | 0.54s | |
| write_spec / read_spec | 0.15s / 0.16s | |
| write_file ×2 | 0.18s / 0.22s | |
| update_manifest | 0.17s | |
| linter_tool ×2 | 0.88s / 0.20s | |
| run_isolated_simulation | 0.24s | |
| start_synthesis | 0.52s | |
| **wait_for_synthesis** | **60.17s, then 121.73s** | bounded blocker; 2nd call slightly **exceeded** the ≤120s ceiling |

Two headline facts: (1) **F3 is real and live** — 10.17s of cold-start setup
before the agent could act (consistent with the 6–15s seen in older hosted
turns). (2) **F2 grows with the workspace, live on this turn.** Pre-synthesis,
every read/write tool returned **sub-second** (tiny workspace: spec + 2 `.v`).
**Post-synthesis, the same class of read tools jumped to ~14–16s each** on the
grown workspace (ODBs + reports + GDS):

| post-synth read tool | elapsed |
|---|---|
| get_synthesis_metrics | 13.98s |
| get_route_drc_summary | 15.73s |
| get_cts_summary | 14.60s |
| get_congestion_summary | 13.92s |

That ~14s-per-read is F2 (whole-workspace tar+GCS-upload on every call) biting
once the workspace has synthesis artifacts — the exact cost the batched F2 fix
targets. It is smaller than the 168–186s seen on the multi-run FIR workspace
(Appendix A hosted baseline) because this is a single-synth 8k-cell design, but it is the same
mechanism and clearly visible from the user's seat (each metric the agent reads
to write its summary costs ~14s). Notably these four PD-summary tools **all
succeeded** here — the X2M-2 "-32602 on every PD-summary tool" symptom did **not
reproduce** on this run. The felt latency between cards (~10–29s gaps) pre-synth
is Codex **model reasoning**, same as the CLI. The `wait_for_synthesis` ceiling
of 121.73s is a minor invariant-6 overrun to note (bound is "≤120s").

**Design outcome:** the agent's synthesis persistence paid off — `synth_0001`
did not produce GDS, but **`synth_0002` completed successfully** (ORFS job
`siliconcrew-orfs-whbk6`, exit 0, GDS uploaded to
`orfs-runs/x2_codex_ui_20260707/synth_0002/`). So turn 1 reached **routed GDS**
by hand of the Codex agent, unattended — real capability, at the cost of a very
long turn (F9 CTS coin-flip: 1st synth failed, 2nd passed — consistent with the
known heterogeneous-CPU flake).

**Two behavioral findings from turn 1:**
- **X2C-7 — the Codex agent over-reaches the ask.** I requested only lint +
  simulate; the agent proactively ran `start_synthesis` + `wait_for_synthesis`
  and, when `synth_0001` did not cleanly produce GDS, investigated
  (`search_logs_tool`, `read_stage_report`) and **re-ran synthesis** — turning a
  ~1-minute design+sim request into a 6+ minute GDS saga. Good initiative, but a
  user who asked for a quick sim gets a long synthesis they didn't request.
- **X2C-5 (HIGH) — long Codex turns lose their live progress in the UI, the
  composer falsely goes idle, and there is no way to see or stop the running
  turn.** Observed twice on this one turn:
  1. **Mid-turn blank:** the **entire assistant response block vanished from the
     transcript** (only the user message remained) and the composer **reset to
     idle** (default placeholder, Send disabled) — while the turn was **still
     running server-side** (`[CODEX-TIMING]` showed tools firing for another
     ~10 minutes). Zero console errors.
  2. **No reconnect after reload:** reloading the page (and re-selecting the
     Codex tab / the codex chat by URL) still showed **only the user message** —
     the UI does **not** reattach to the in-flight Codex turn's stream. No tool
     cards, no text, **no Stop button** → the user cannot see progress *or
     cancel a runaway turn* from the chat; only the Artifacts Index reveals that
     work is happening (runs appearing).
  Likely cause: the Codex runtime persists the assistant message only at **turn
  end** (`codex_runtime.py` appends the assistant turn after the stream
  completes), so any transcript (re)fetch mid-turn — SWR revalidate,
  window-focus (invariant 6), or a full reload — renders the **empty persisted
  state**, and there is no live-stream reattach for an already-running Codex
  turn. A real user hits this simply by tabbing away, refreshing, or running a
  long synthesis turn. The work is not lost (workspace + runs persist, see
  below), but the chat looks **done-and-empty while Codex churns for minutes**,
  with no cancel affordance. (Distinct from the native/Gemini agent, whose
  LangGraph checkpointer persists incrementally — this is specific to the Codex
  persist-at-turn-end model.)
  - **Mitigation exists and is honest (not a lie):** once the turn ends, a
    reload shows the **full persisted tool-card transcript**, ending with an
    honest advisory — *"The connection was lost during this step — it may still
    be running. Check the Runs / Signoff panel for live status, or send a
    message to continue."* So the platform does NOT fake completion; it points
    the user to the authoritative Runs panel (invariant 5). **But** the turn's
    **final written summary/verdict is missing** — the 698s turn that reached
    GDS never delivered its textual conclusion in-chat (lost with the dropped
    stream); the user must reconstruct the outcome from the Runs/Signoff panel.
    Net: honest but poor legibility — the fix is a live-stream **reattach** for
    an in-flight Codex turn (and/or incremental assistant-message persistence so
    a refetch shows progress instead of blank). **This is the most important UI
    finding of the leg.**
- **Workspace durability is fine (the chat is the only casualty):** across the
  mid-turn blank and a full reload, the **Artifacts Index stayed correct** —
  `sim_0001`, `synth_0001`, `synth_0002`, `sim_0002` runs and the `gray4.v` /
  `gray4_tb.v` / `constraints.sdc` files all persisted, with a `gray4`
  top-module chip. So the run directory (invariant 5) is durable; only the live
  Codex chat transcript is not recoverable until the turn ends.
- **Continuity nit — reload resets the agent sub-tab.** After reload, the agent
  group reverted to **Workbench + Chat 1** even though the URL carried the Codex
  chat id (`?chat=6287…`) — the Codex/Workbench sub-tab and active chat are not
  fully driven by the URL (minor invariant-7 "URL is source of truth" gap;
  X2C-8).

**Turn 1 total: `turn_end status=completed elapsed=698.03s` (11.6 min).** The
length is F2 (14–16s post-synth reads) + the `wait_for_synthesis` polls + the
synth retry + a very thorough metric/DRC/congestion/re-sim sweep the agent did
on its own.

### Turn 2 — "add an enable input, re-verify (no synthesis)" — continuity (UI)

Sent in the **same Codex chat** (thread `6287…bb44`, new turn `72ce…9912`),
08:18:01 UTC. **Continuity confirmed:** the turn opened by `read_file gray4.v` →
`read_file gray4_tb.v` → `get_manifest` — it saw and re-read **turn 1's own
files**, then re-wrote the spec and proceeded to edit. The transcript correctly
stacks turn 1 (ending in the honest advisory) above turn 2.

**But turn 2 is where F2 is unmistakable.** `[CODEX-TIMING]`:

| turn-2 tool | elapsed |
|---|---|
| `elapsed_setup` (F3) | **3.83s** (F3 varies 3.8–14.6s across turns) |
| read_file gray4.v | 14.23s |
| read_file gray4_tb.v | 13.81s |
| get_manifest | 13.78s |
| write_spec | 14.05s |
| read_spec | 14.13s |

**On the post-synth workspace, EVERY tool call costs ~14s** — reads and writes
alike — because F2 tars+uploads the whole workspace (now ODBs + GDS + reports)
on each call. A routine "add a port and re-verify" turn therefore drags into
minutes purely on sync overhead. **This is the single clearest, most damning F2
signal of the leg**, and the exact cost the batched F2 fix removes (leg 2 should
show these drop to sub-second).

**Turn 2 outcome — continuity + correctness + honesty all pass.** It **read
turn 1's files, edited them**, respected the no-synthesis instruction, and
delivered a **complete, honest final summary** in-chat (this shorter 4-min turn
did not lose its stream): *"Done — no synthesis run was started. Changed files:
gray4.v, gray4_tb.v, gray4_spec.yaml, constraints.sdc … Lint: PASS …
Simulation: Run sim_0003, Status PASS, Pass marker found: TEST PASSED … verifies
reset, en=0 hold, en=1 advancement, exactly one Gray-code bit change."* So the
lost-final-summary symptom is specific to **long turns whose stream drops**
(turn 1, 11.6 min + a reload), not every turn. `turn_end status=completed
elapsed=247.66s` (4.1 min, all F2 + reasoning, no synth).

### Turn 3 — "what's in my workspace?" — continuity (UI)

Sent in the same Codex chat, 08:23:51 UTC. New turn: `elapsed_setup=3.64s`,
`list_files_tool` 14.73s (F2 again), then `get_manifest`, then a short
inventory. It correctly enumerated the workspace and manifest roles — continuity
held a third time, and (being short, ~54s) it delivered its full answer in-chat:
*"gray4.v — rtl, gray4_tb.v — tb, constraints.sdc — sdc; RTL/synthesis top:
gray4, Testbench top: gray4_tb; other files: gray4_spec.yaml, manifest.json,
sim_runs/…, synth_runs/…, attempt_log.json, attempt_events.jsonl."*
`turn_end status=completed elapsed=53.99s` (2 tools, each ~14s from F2, + setup
3.64s + reasoning).

### UI per-turn wall-clock summary

| Turn (UI) | server `elapsed` | F3 setup | tools | dominant cost | outcome |
|---|---|---|---|---|---|
| 1 — design gray4 + TB + lint + sim (agent also synthesized) | **698.03s** (11.6 min) | 10.17s | ~30 (incl. synth retry) | synth waits + F2 post-synth reads + model | routed **GDS** (synth_0002); final summary lost to dropped stream (X2C-5) |
| 2 — add enable, re-verify (no synth) | **247.66s** (4.1 min) | 3.83s | ~12 | **F2 ~14s/call** + model | lint PASS, **sim_0003 PASS**; full summary delivered; continuity ✓ |
| 3 — workspace inventory | **53.99s** | 3.64s | 2 | F2 ~14s/call + model | correct inventory; continuity ✓ |

### Continuity verdict (UI)

**Strong within a chat.** All three turns ran in one Codex chat (thread
`6287…bb44`); turn 2 re-read and edited **turn 1's own files**, turn 3
inventoried them — the Codex `external_thread_id` resume + the session binding
carried context across turns, and the workspace/runs are durable (survive
reloads and the mid-turn blank). Two caveats: (1) **X2C-5** — a *live* turn's
progress is not recoverable in-chat until it ends (blank on refetch, no
reattach), and a long turn can lose its final summary; (2) **X2C-8** — a reload
resets the agent sub-tab to Workbench/Chat 1 while the URL still points at the
Codex chat (URL-source-of-truth nit). Neither loses data.

### UX verdict (from the web-app user's seat)

**The Codex agent is genuinely capable and its work is beautifully legible —
but the hosted latency (F2/F3) and the live-turn UI gaps make it feel heavy, and
its over-eagerness can run away.** Concretely:

- **Legibility — excellent.** Every tool is a friendly-named inline card
  (*Writing Specification*, *Running Linter*, *Waiting for Synthesis*, *Reading
  File · gray4.v · 14s*) with a duration and a contextual action (*Open spec /
  file / waveform / report*). A designer can follow exactly what the agent did.
  Final summaries (when delivered) are honest and specific (real run ids, pass
  markers, VCD paths).
- **Honesty — good.** Lint/sim verdicts are real; when the stream drops the UI
  shows an honest "connection lost — check the Runs panel" advisory rather than
  faking completion; the Artifacts Index is always authoritative.
- **Latency — the weak point.** F3 cold-start is 3.6–14.6s **before every turn's
  first token**; and once a workspace has synthesis artifacts, **F2 makes every
  tool call ~14s**, so multi-tool turns take minutes. A designer would tolerate
  the ~1-min self-host-class turns, but **not** a post-synth turn where each of
  a dozen tool calls costs 14s.
- **Behavior — over-reach + no cancel.** The agent volunteered a full
  synthesis→GDS run on a "design + simulate" ask and, on a failed first synth,
  looped through diagnosis + a second synth (11.6-min turn) — impressive
  autonomy, but a user who wanted a quick sim can't easily stop it (no Stop
  control once the live view blanks, X2C-5).

**Single change that would most improve the Codex web experience: ship the
batched F2 sync-gating fix** (`f095fcb`). It turns the ~14s-per-call post-synth
tax into sub-second reads — the difference between a 4-minute and a ~40-second
"add a port and re-verify" turn. Second: **fix X2C-5** (live-stream reattach /
incremental persistence) so a long Codex turn stays visible and cancelable.

### Findings (UI leg — NEW only)

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| X2C-5 | HIGH (UX/legibility) | OPEN | A live Codex turn's progress is not recoverable in the UI until it ends: mid-turn the assistant block **blanks to just the user message** and the composer **goes idle** (no Stop) on any transcript refetch (SWR/focus/reload), because the Codex runtime persists the assistant message only at turn-end and the UI does **not** reattach to the running stream. Honest mitigation exists (post-turn reload shows the full cards + a "connection lost — check Runs panel" advisory), but a long turn (turn 1, 698s) **lost its final written summary** and could not be cancelled from chat. Fix: live-stream reattach and/or incremental assistant-message persistence. Most important UI finding. |
| X2C-6 | LOW (UX/honesty) | OPEN | The composer **model picker still reads "Gemini 3.5 Flash" while the Codex tab is active** — Codex runs on the connected ChatGPT account (a gpt-5.x brain), not Gemini. The user can't tell which model is answering on the Codex tab. Fix: reflect the Codex/account model in the picker when the Codex sub-tab is selected. |
| X2C-7 | LOW-MED (behavior) | OPEN | The Codex agent **over-reaches the ask** — given "design + lint + simulate," it also ran `start_synthesis` + `wait_for_synthesis`, and on a failed first synth looped through log/stage-report diagnosis + a second synth, turning a ~1-min request into an 11.6-min GDS saga. Good initiative, but should be scoped to the request (or the runaway should be cancelable — see X2C-5). Adding "do NOT run synthesis" to turn 2 correctly suppressed it, so it is steerable. |
| X2C-8 | LOW (invariant 7) | OPEN | A page reload **resets the agent sub-tab to Workbench + Chat 1** even though the URL carries the Codex chat id (`?chat=…`) — the Codex/Workbench sub-tab and active chat are not fully URL-driven. No data loss; a source-of-truth nit. |

**Not reproduced this leg (worth noting):** X2M-2 (the "-32602 on every
PD-summary tool" symptom) — here `get_synthesis_metrics`, `get_route_drc_summary`,
`get_cts_summary`, `get_congestion_summary` **all succeeded** (just slow, ~14s
each from F2). `wait_for_synthesis` returned at 60.17s and 121.73s — one call
**slightly over** the "≤120s" bound (minor invariant-6 note).

---

## Appendix A — CLI route (self-host, superseded by UI route above)

_Kept for the honest measurements gathered before the course-correction. The
CLI drives the **local self-host** `rtl-codex` server, which does not exercise
F2/F3 (those are hosted, server-side-brain only) — so these numbers characterize
the self-host CLI experience, not the hosted product._

### How Codex is wired on this machine (verified)

There are **two distinct "Codex" integrations**; the latency findings F2/F3/F4
(reports/codex-latency.md) belong to the *second*, and the two must not be
conflated:

1. **Codex CLI as an external MCP client** (`codex-cli 0.139.0`, model
   `gpt-5.5`, `model_reasoning_effort="xhigh"`). `~/.codex/config.toml`
   registers SiliconCrew twice:
   - `rtl-codex` — a **local stdio** server:
     `RTL_AGENT\.venv\Scripts\python.exe mcp_server.py --codex-tools`, running
     in **self-host** mode (the local `RTL_AGENT\.env` has no
     `SILICONCREW_HOSTED`; sqlite `state.db` + local `workspace/`). **No GCS,
     so F2 does not apply on this path.**
   - `siliconcrew-hosted` — the remote hosted backend URL
     (`https://siliconcrew-backend-psp2dkllmq-uc.a.run.app/mcp`), **no bearer
     token configured**.
   This is the integration the task named ("codex CLI with the rtl-codex MCP
   config"). It is **drivable non-interactively** via `codex exec`.

2. **SiliconCrew's own server-side Codex brain** (`src/agents/codex/
   codex_runtime.py` + `codex_engine.py`) — when a SiliconCrew user picks the
   `codex` runtime in the agent posture, the SiliconCrew *server* runs the
   OpenAI Codex SDK as the brain and connects it to its own tools by
   **spawning `mcp_server.py --transport stdio --codex-tools --bound-session
   <sid>` per turn**. **This** is what emits `[CODEX-TIMING]` to Cloud Run,
   and **this** is the path the F2/F3/F4 anatomy describes (hosted mode, so the
   per-tool whole-workspace sync fires). Driving it requires the hosted app UI
   with the codex model selected + an OpenAI key on the account — not the CLI.

**Consequence for leg 1:** the CLI path I can drive (rtl-codex, self-host) does
**not** exercise F2; and the hosted backend that *does* run F2 is **not
reachable from the Codex CLI** (see X2C-1). So I measured leg 1 in two honest
parts: (a) a real multi-turn Codex-CLI conversation on the self-host path
(drivability, continuity, UX, and where its latency actually goes), and (b) the
**hosted** F2/F3 "before" numbers pulled from Cloud Run logs (`[CODEX-TIMING]`
+ `/mcp` request latencies) produced by the server-side Codex brain / hosted
MCP earlier today.

### Hosted "before" baseline from Cloud Run (rev 00060)

**F3 — per-turn cold-start setup** (`[CODEX-TIMING] event=sdk_thread_ready
elapsed_setup`), the seconds before the first token, from three real
server-side Codex turns today:

| Turn (thread) | elapsed_setup | turn total | setup share |
|---|---|---|---|
| 06:27 (8502…) | **14.59s** | 27.01s | **54%** |
| 04:30 (a546…) | 6.32s | 17.95s | 35% |
| (2026-07-06) 05:25 (8502…) | 9.72s | — | — |

Cold-spawn setup is **6–15s per turn** and up to **half the whole turn** — a
direct confirmation of F3 (fresh MCP subprocess: heavy import + `init_schema`
DDL + JWKS) on the deployed rev. (`sdk_turn_issued` was ~0.05s — issuing the
turn is cheap; the cost is bring-up.) No per-tool `[CODEX-TIMING]` lines were
in retention, so F2 is sized from request latencies instead:

**F2 — per-tool hosted `/mcp` latency** (Cloud Run request logs, `POST /mcp
200`, 12h window, n=26):

| bucket | count |
|---|---|
| <0.05s | 18 |
| 0.5–2s | 4 |
| **168–186s** | **4** (168, 168, 169, 186) |

Bimodal and brutal: most calls are the sub-50ms JSON-RPC handshake/notification
traffic, but **four tool calls took 168–186 seconds** against the post-synth
FIR workspace (`x2_fir_mcp_20260707`: many ODBs + GDS). That is the
whole-workspace tar+GCS-upload-per-call pathology (F2) and/or a blocking read
stalled behind it (X2M-4) — a design loop on a large hosted workspace is
unusable at these latencies. This is the number leg 2 must move.

### Conversation transcript summary (self-host, Codex CLI)

Drove a real 3-turn design conversation with `codex exec` (+ `resume --last`)
against the local `rtl-codex` server. Autonomy config (after hitting X2C-2):
`--dangerously-bypass-approvals-and-sandbox -c shell_tool=false -c
apply_patch_tool=false` — i.e. approvals off but shell/apply_patch disabled so
Codex could act **only** through SiliconCrew MCP tools, mirroring the
server-side brain's tool policy.

- **Turn 1 — "design a 4-bit Gray-code counter + self-checking TB, lint,
  simulate."** Codex called `create_session_tool` → `write_file`×2 (`gray4.v`,
  `gray4_tb.v`) → `update_manifest` → `linter_tool` → `simulation_tool`. Lint
  clean (`Syntax OK.`), sim **passed** (`TEST PASSED` found). The RTL is
  genuine and correct — a binary counter with `gray <= (bin_next>>1)^bin_next`
  (verified on disk at `RTL_AGENT\workspace_new\x2_codex_gray4\gray4.v`).
- **Turn 2 — "add an enable input `en`, re-verify" (`resume --last`).** Codex
  re-established the session (`create_session_tool` + `set_active_session` — see
  X2C-3), `read_file`×2 the existing sources, `write_file`×2 the updated
  versions, `linter_tool`, `simulation_tool`. Lint clean, sim **passed**. The
  enable semantics and TB hold/advance checks were implemented correctly.
- **Turn 3 — "what's in my workspace?" (`resume --last`).** `list_files_tool`
  → `set_active_session` → `list_files_tool` → `get_manifest`. Returned a
  correct inventory: `gray4.v`, `gray4_tb.v`, `gray4_tb.out` (sim output),
  `manifest.json` (+ `attempt_events.jsonl`/`attempt_log.json`), with manifest
  roles RTL top `gray4`, TB top `gray4_tb` — all accurate. Continuity held a
  third time (same re-bind pattern).

The Codex agent completed the entire spec→lint→sim loop unaided across three
turns, produced correct RTL + a self-checking TB, and self-recovered its
session on each resume. Task completion: **strong**.

### Latency table (self-host, Codex CLI)

Client wall-clock + per-tool durations from the timestamped `--json` stream
(each turn = one `codex exec` process; model = gpt-5.5, reasoning `xhigh`):

| Turn | wall | SiliconCrew tool calls | Σ tool time | model/overhead | prompt→1st tool | input tokens |
|---|---|---|---|---|---|---|
| smoke (`list_sessions`) | 141s | 1 | ~0.0s | ~100% | — | 52,530 |
| 1 (design gray4) | **81s** | 6 | **0.32s (0.4%)** | 99.6% | 24.2s | 128,294 |
| 2 (add enable, resume) | **139s** | 10 | **0.61s (0.4%)** | 99.6% | ~25s | 374,128 |
| 3 (inventory, resume) | **35s** | 4 | **0.06s (0.2%)** | 99.8% | 13s | 495,062 |

**Headline: on self-host the SiliconCrew tools are not the bottleneck — the
model is.** Every SiliconCrew tool call returned in 0.01–0.34s (local sqlite +
local workspace, no GCS). Tool execution is **0.4% of a turn**; the other
~99.6% is Codex model time — gpt-5.5 at `xhigh` reasoning plus a very large
context: the fixed MCP tool-catalog (~52k input tokens before any work) that
then **balloons with the conversation** (128k → 374k → 495k input tokens across
the three turns, mostly cached but still processed). Time-to-first-tool was a
flat ~13–25s of pre-thinking every turn. This is the exact inverse of the hosted path, where F2
makes the tools the bottleneck (168–186s per call above).

### Continuity verdict

**Conversation + workspace continuity: YES. Server-side session binding: NO
(self-recovered).** `resume --last` correctly carried Codex's memory of the
session name and what it built, and the durable on-disk workspace persisted
(turn 2 `read_file` returned turn-1's exact sources; turn 1's files were intact
after a re-issued `create_session_tool`). But each turn spawns a **fresh MCP
subprocess with an empty active session**, so continuity is carried entirely by
(a) Codex's transcript and (b) the durable workspace — **not** by the MCP
server. On resume Codex had to re-bind by calling `create_session_tool` +
`set_active_session` before it could read files. It recovered cleanly and
nothing was lost, but leaning on `create_session_tool` being create-or-attach
(non-destructive) for continuity is fragile (X2C-3).

### UX verdict

From the Codex user's seat: **the SiliconCrew work is legible and honest, and a
designer would tolerate the self-host latency for correctness — but the hosted
latency would be intolerable, and two rough edges block a smooth headless
experience.**

- **Legible & honest:** tool calls, arguments, and results stream clearly in
  `--json`; lint/sim verdicts came back as real strings (`Syntax OK.`, `TEST
  PASSED` found / `status=test_passed`). No fabricated success.
- **Errors reach the user honestly — mostly.** The one dishonest signal is
  X2C-2: blocked tool calls are surfaced as *"user cancelled MCP tool call"*
  when the user cancelled nothing (it's the non-interactive approval policy).
  That message sent Codex down a dead end in the first turn-1 attempt.
- **Latency tolerance:** ~1–2 min per turn on self-host is acceptable for a
  correct spec→sim loop (and it's model latency, not SiliconCrew's). The hosted
  path's 168–186s **per tool call** on a real workspace (F2) is not — a
  multi-call design loop there would take tens of minutes.

**Single change that would most improve the Codex experience** — it differs by
path: (1) **Hosted (where F2/F3 live): ship the F2 sync-gating fix** (f095fcb,
batched for tonight) — that alone removes the 168–186s tool calls, the dominant
pain. (2) **Self-host CLI: run Codex with a lean, RTL-only MCP profile** (just
`rtl-codex`, dropping playwright/node_repl/trezzit and the dead
`siliconcrew-hosted` entry) — the fixed tool-catalog context is the largest
controllable driver of per-turn model latency and cost, and the dead hosted
entry adds an auth-failure stall + error spam to every invocation (X2C-1).

### Findings (NEW only)

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| X2C-1 | MEDIUM (integration gap) | OPEN | The hosted SiliconCrew MCP is **not reachable from the Codex CLI** on this machine. `~/.codex/config.toml`'s `siliconcrew-hosted` entry has no bearer token, and the backend serves no OAuth discovery for it: every startup the codex rmcp worker fatal-quits with `AuthRequired { missing_token }`, and Cloud Run shows `POST /mcp 401` + `GET /.well-known/oauth-authorization-server 404` (confirmed from my runs, 07:54Z). So "a Codex agent as a **hosted** SiliconCrew user" is not wired — the only working Codex→SiliconCrew path here is the **local self-host** `rtl-codex` server. Corollary: F2/F3/F4 cannot be exercised from the CLI at all; they belong to SiliconCrew's server-side Codex brain (the `[CODEX-TIMING]` path). Fix options: give the hosted entry a bearer token / working OAuth, or drop it from the codex config so it stops stalling+spamming every turn. |
| X2C-2 | MEDIUM (headless UX + honesty) | OPEN | `codex exec` with `approval_policy="never"` **silently cancels every MCP tool not in the config's pre-approved allowlist**, surfaced to the agent as `"user cancelled MCP tool call"`. Turn 1's first attempt was fully blocked — `create_session_tool`×3 + `get_manifest` all "cancelled" at 0.00s — even though no human cancelled anything and the tools are harmless. Only pre-listed tools (`list_sessions_tool`, `get_current_session`, `write_spec`) ran. Worked only after switching to `--dangerously-bypass-approvals-and-sandbox` + disabling shell/apply_patch. A headless Codex user gets a misleading dead-end. This is a Codex-CLI/config behavior (not SiliconCrew code), but it blocks the intended integration; the fix is a documented codex profile that pre-approves the SiliconCrew tool set (or bypass+shell-off, as used here). |
| X2C-3 | LOW-MED (continuity) | OPEN | **Server-side active-session state does not survive across Codex CLI turns.** Each `codex exec [resume]` spawns a fresh `mcp_server --codex-tools` subprocess with an empty active session, so on `resume --last` Codex had to re-issue `create_session_tool` + `set_active_session` to re-enter `x2_codex_gray4` before it could read its own earlier files. It self-recovered and nothing was lost (create-or-attach was non-destructive; the workspace is durable), but relying on `create_session_tool` idempotency for continuity is fragile — a stricter create (reject-if-exists) would break resume. Consider having the codex-tools server honor a bound/last-active session, or document `set_active_session` as the resume entry point. |
| X2C-4 | LOW (observation, not a SiliconCrew bug) | NOTED | Self-host Codex latency is **~99.6% model-side**: 6–10 SiliconCrew tool calls total 0.3–0.6s of 81–139s turns; the rest is gpt-5.5 `xhigh` reasoning + a large, growing MCP-tool-catalog/conversation context (input tokens 52k→128k→374k across the run). SiliconCrew is not the bottleneck on self-host. The controllable lever is the loaded MCP surface (see the single-change recommendation), which is a codex-config choice, not SiliconCrew code. |

---

## Leg 2 (post-deploy) — F2 fix CONFIRMED

**Deploy:** backend **rev 00063** (digest `dddabfd3`), shipping the F2
sync-gating fix (`f095fcb`) + F9c stateless. Frontend also updated (landing +
14-example gallery live). Method: same UI route — fresh session
**`x2_codex_ui_leg2_20260707`** in Agent posture → Codex tab (still
"ChatGPT connected", no link step) → same design-gray4 prompt (asked it to run
synthesis so the workspace reaches the post-synth state where F2 bit in leg 1).
Thread `9059…04de`, turn `de71…bf38`, sent 08:46:04 UTC.

### F2 before/after — the headline (authoritative `[CODEX-TIMING]`)

Same tools, same design, same UI path — **rev 00060 (leg 1) vs rev 00063
(leg 2)**, on a workspace that already has synthesis artifacts:

| tool (post-synth call) | rev 00060 (before) | rev 00063 (after) | speedup |
|---|---|---|---|
| `get_synthesis_metrics` | 13.98s | **0.00s** | ~1000×+ |
| `get_route_drc_summary` | 15.73s | **0.00s** | ~1000×+ |
| `get_manifest` | 13.78s | **0.04s** | ~340× |
| `read_file` | 14.2s | **0.05s** | ~280× |
| `get_synthesis_status` | (F2-slow class) | **0.04s** | — |
| `search_logs_tool` | 2.75s | **0.04–0.06s → 0.00s** | ~50×+ |

(`get_synthesis_metrics` and `get_route_drc_summary` are the *same* tools that
read 13.98s and 15.73s in leg 1 — an exact apples-to-apples pair. `0.00s` is the
`[CODEX-TIMING]` rounding of a sub-5ms call. `get_cts_summary`/
`get_congestion_summary` weren't individually re-triggered this run but are the
identical read-only class.)

**The F2 fix works, decisively.** The post-synthesis reads that cost ~14–16s
each on rev 00060 now return in **single-digit milliseconds** on rev 00063 — the
whole-workspace tar+GCS-upload no longer fires on read-only tools. This is the
definitive before/after the owner asked about: a post-synth design loop that
dragged into minutes of pure sync overhead is now essentially free on reads. The
design also reached routed **GDS** (ORFS job `siliconcrew-orfs-s8khq` completed
successfully) after the usual F9 CTS retry.

### Other leg-2 observations

- **F3 setup: unchanged** — `elapsed_setup=10.96s` this turn (still in the
  3.6–14.6s band). Expected: only F2 shipped; the warm-subprocess follow-up did
  not, so cold-start is untouched.
- **Pre-synth tools: sub-second on both revs** (write_spec 0.82s, write_file
  0.15–0.17s, read_spec 0.04s, linter 0.22–0.99s) — confirms F2 was always cheap
  on a small workspace; the fix's value is entirely on the grown/post-synth
  workspace.
- **In-app Codex path survived the revision swap** — I drove the Codex tab live
  on the freshly-rolled rev 00063 with no reconnect/relink step (the F15 "manual
  reconnect after deploy" issue is about the external claude.ai MCP connector, a
  different surface; the in-app server-side Codex brain came up clean on the new
  revision).
- **X2C-6 still present** — the composer model picker still reads "Gemini 3.5
  Flash" on the Codex tab post-deploy (the F2 deploy didn't touch it).
- **F9 CTS coin-flip still occurs** — `synth_0001` failed (ORFS exec
  `siliconcrew-orfs-5998d`, 0/1 tasks) and the agent retried; the LEC_CHECK=0
  fix prevents the SIGILL class but a per-run PnR flake remains (known, out of
  scope for this leg).
- **X2C-5 still present (unchanged post-deploy)** — rechecked by reloading
  mid-turn: after reload + re-selecting the Codex tab, the still-running turn
  again showed **only the user message** (no cards, no Stop, no reattach) while
  `[CODEX-TIMING]` confirmed tools firing server-side. Expected — the deploy
  shipped F2 + F9c, not a fix for the Codex streaming/persistence model; X2C-5
  remains the top follow-up. **X2C-8** (reload resets sub-tab to Workbench/Chat 1
  despite the URL) also still reproduces.

### Leg-2 verdict

**The headline the owner asked about is answered: the F2 fix is live and
decisive** — post-synth Codex tool calls dropped from ~14s to single-digit
milliseconds (get_synthesis_metrics 13.98s→0.00s, get_route_drc_summary
15.73s→0.00s, get_manifest 13.78s→0.04s). A hosted Codex design loop on a
post-synth workspace is now fast. What did **not** change (and shouldn't have,
given what shipped): F3 cold-start (~11s), X2C-5 (live-turn blank / no
reattach), X2C-6 (Gemini model label on the Codex tab), X2C-8, and the F9 CTS
per-run flake. Those are the remaining follow-ups; X2C-5 is the most
user-visible.
