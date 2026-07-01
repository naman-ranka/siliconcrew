# Chatbot evaluation — P1 (seq_detector_0011), claude-sonnet-4-6

A subagent acted as a user of the in-app **chatbot** (AI Assistant panel), gave it
the `0011` sequence-detector spec, and watched Claude Sonnet 4.6 run the full
flow, capturing a WS-frame-timed journey + a UX critique vs the Claude/Codex bar.

Harness note: the sandbox headless browser can't open a WSS to Cloud Run (agent
proxy doesn't tunnel WS → 1006). Fixed with a local relay (browser → ws://localhost
→ deployed). The deployed chat backend itself is healthy (direct node: open 428ms,
first token 688ms, done 3.2s).

## The AI/agent did well (this is real)
- Produced a correct, well-commented **5-state Moore FSM** for overlapping "0011",
  ports exactly per spec.
- **Lint passed.**
- **Sim failed first, then the agent self-debugged** (rewrote the testbench to fix
  an output-sampling off-by-one) and **passed 8/8** (reference stream, reset-mid-
  sequence, back-to-back, pulse-width).
- Started synthesis on remote ORFS. (Run ended `failed` server-side — same remote-
  ORFS flakiness seen earlier; a sequence detector shouldn't fail synth, so the
  **remote ORFS service is worth investigating** separately.)

All artifacts persisted to the session workspace (verified via REST):
`seq_detector_0011.v` (rtl), `_tb.v` (tb), `constraints.sdc`, `dump.vcd`,
`synth_0001: failed`.

## Journey trace (WS frames, t = seconds from Send)
| t | event |
|---|---|
| +0.6 | WS open (via relay) |
| +1.9 | `start`; input disabled, Stop button shown |
| **+14.4** | first `text` — **time-to-first-token ~14s** |
| +14–20 | write_spec / read_spec |
| +74–82 | write_file ×2, lint → PASS |
| +87–90 | sim → **FAILED** (per-cycle diagnostics) |
| +174–234 | self-debug: reread, rewrite TB, re-lint, re-sim → **PASS 8/8** |
| +240 | start_synthesis (job queued→running on ORFS) |
| +300 | synth poll returns (still mid-pipeline) |
| **+304.5** | **WS close (1005), no `done` frame** |
| +305…+515 | **UI frozen**: "Starting Synthesis" spinner forever, input disabled, no error |

## Real product findings (ranked)
1. **No WS close/error handling → UI hangs forever on a dropped stream (worst).**
   When the socket closed mid-synth-poll, the UI stayed wedged in "streaming"
   (spinner, disabled input, no error, no reconnect) — only escape is a reload.
   This is a real client defect independent of *why* the socket dropped. Fix:
   `onclose`/`onerror` → exit streaming, show "connection lost", auto-reconnect and
   **resume** the in-flight run (the run survives server-side; reattach by run_id).
   *(The drop itself, at +304s during the 60s+ ORFS poll, is transport/infra —
   possibly a Cloud Run/relay WS idle timeout on the long poll; worth a heartbeat.)*
2. **Slow time-to-first-token (~14s) with weak feedback** — a static "Thinking"
   spinner and no elapsed timer; reads as "is it stuck?". Stream sooner + show
   elapsed.
3. **Tool chips lack durations + live progress for long jobs.** The chips are good
   (clear labels, expand to full code/JSON), but you can't tell a 60s synth from a
   0.2s lint, and the ORFS stage data in the poll payload isn't rendered as a live
   stage list/progress.
4. **Chunky streaming + no closing summary.** Text arrives in bursts at reasoning
   boundaries; and because the stream never terminated, no final summary rendered.
5. **Workbench panels didn't reflect the run live** — NOTE: not an architecture
   silo (the files/runs ARE in the session, verified). The panels simply didn't
   refresh (the page was wedged by #1, and/or the reactivity revalidate didn't
   fire on the frozen page). Under normal operation the focus-revalidate/active-run
   poll should surface them; worth confirming once #1 is fixed.

## Positives (already near Codex bar)
Input disabled while streaming; **Stop/cancel** present; multiline; live token
(24.6k) + cost ($0.0074) meter; expandable tool chips with syntax-highlighted,
line-numbered code and full JSON tool results.

## Top fixes to reach Claude/Codex grade
1. Handle WS close/error: exit streaming, surface error, auto-reconnect + resume by run_id.
2. Heartbeat/keepalive (or resumable server stream) so long ORFS synth doesn't drop the socket.
3. Always emit a terminal frame (even on backend error/timeout) so the UI resets.
4. Cut + instrument time-to-first-token (stream thinking early, elapsed timer).
5. Tool durations + live ORFS stage progress from the poll payloads.
6. Guarantee a closing summary; smoother token cadence.

*Screenshots: `plans/phase2/screenshots/chatbot-p1/` (01-sent … 10-stuck-final; 09-code-expanded shows the correct FSM). The 02/03-ws-error files are from the pre-relay failed attempt.*
