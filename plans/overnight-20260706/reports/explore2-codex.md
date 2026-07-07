# Explore round 2 — Codex-agent UX + latency

Evaluating how a **Codex agent** performs as a SiliconCrew user: drivability,
latency, conversation continuity, and product UX. Two legs planned: **Leg 1**
(this section) is the pre-deploy baseline against live backend **rev 00060**
(F2 unconditional whole-workspace sync still shipping). **Leg 2** (placeholder
at bottom) re-runs the same measurements after tonight's deploy to measure the
delta.

Sessions I created are named `x2_codex_*` (self-host, local machine only).

---

## Leg 1 (pre-deploy, rev 00060)

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

## Leg 2 (post-deploy)

_Placeholder — to be filled after tonight's deploy. Re-run the identical
self-host multi-turn conversation (same three prompts) and re-pull the hosted
`[CODEX-TIMING]` `elapsed_setup` + `POST /mcp` latency distribution; compare
against the leg-1 tables above. Key deltas to check: (1) hosted `/mcp` tail
latency — do post-synth read calls drop from ~168s to sub-second once F2 gates
sync to mutating tools only? (2) F3 setup — unchanged unless the warm-subprocess
follow-up shipped. (3) does the claude.ai / codex hosted MCP survive the
revision roll, or still need a manual reconnect (F15)?_
