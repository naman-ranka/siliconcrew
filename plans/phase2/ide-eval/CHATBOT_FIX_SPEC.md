# Chatbot streaming/lifecycle — fix spec (all 6)

Grounded in the P1 evaluation + code recon. Transport/resumable design (WS vs SSE,
resume tokens, heartbeat interval) is finalized from the research brief; acceptance
criteria below are transport-agnostic.

## Current behavior (recon)
Frontend `store.ts` `sendMessage` (445–598):
- `onmessage`: `text`/`tool_call`/`tool_result`/`done`/`error`.
  - `done` → commit streamingMessage → messages, `isStreaming:false`.
  - `error` → set chatError, `isStreaming:false`, **discards** streamingMessage (null).
- `onerror` (585) → chatError "WebSocket connection error", `isStreaming:false`, **discards** partial.
- `onclose` (594) → **only clears ws refs. Does NOT reset isStreaming, surface an error, or preserve the partial.** ← the perpetual hang when a drop fires `close` without `error`.
- No reconnect, no resume, no heartbeat, no TTFT feedback beyond a spinner, no per-tool durations.

Backend `api.py` `chat_websocket` (~1017–1255):
- `done` sent on success (with tokens); `error` sent on agent exception (1241) and outer exception (1250).
- On `WebSocketDisconnect`: nothing. **No heartbeat/ping. No resumability.** A drop mid-run ⇒ no terminal frame ever reaches the client.

## The 6 fixes + acceptance criteria

**F1 — Never hang on a dropped stream.**
- AC: if the socket `close`s (any code) while `isStreaming` and no terminal (`done`/`error`) frame was received, the UI must within ~1s: exit streaming, re-enable input, keep the partial assistant message (marked "interrupted", not discarded), and show a non-blocking "Connection lost" state with a **Retry**. Track a `receivedTerminal` flag to distinguish clean close from drop.
- Files: `frontend/lib/store.ts` (onclose/onerror), chat UI banner.

**F2 — Auto-reconnect + resume the in-flight run.**
- AC: on an unexpected drop, reconnect with exponential backoff+jitter (cap ~5 tries); on reconnect, resume the run (approach per research — e.g. resume token / replay from last event id / re-attach by thread) without duplicating already-shown tokens. If resume unsupported, at minimum reconnect and surface "reconnected — resend?" rather than silent death.
- Files: `store.ts`; backend resume endpoint/contract per research.

**F3 — Keep the socket alive through long tool jobs.**
- AC: heartbeat (client ping / server pong or app-level keepalive) at the research-recommended interval so a 60s+ ORFS synth poll doesn't hit an idle/proxy timeout. Dead-connection detection triggers F1/F2.
- Files: `api.py` chat_websocket loop; `store.ts`.

**F4 — Guaranteed terminal frame + reopen reconciliation.**
- AC: backend always emits a terminal frame (`done` or `error`) even on timeout/backend error before the socket goes away where possible. On reopen, a persisted trace whose last tool step is non-terminal must be reconciled against actual run state (the Runs/synthesis-runs status) so it never renders a perpetual "Waiting for Synthesis" when the run actually failed/finished.
- Files: `api.py`; `store.ts` `loadChatHistory` + `buildBlocks`.

**F5 — Cut + mask time-to-first-token.**
- AC: an optimistic assistant placeholder with a live "thinking…"/elapsed indicator appears within ~300ms of send; stream partial/thinking output as early as the backend can. No 14s of static spinner.
- Files: `store.ts` (placeholder already exists — add elapsed/indicator), chat message components.

**F6 — Tool durations + live multi-stage progress + closing summary.**
- AC: each tool chip shows elapsed time; the synthesis chip renders the ORFS stage list (constraints→synth→floorplan→place→cts→route→finish) live from poll payloads; a closing summary always renders on completion.
- Files: tool-chip component; backend already has stage data in synth poll payloads.

## Verification
- **Forced-drop repro** (verifiable here): drive the chat via the relay, kill the relay mid-stream → confirm F1 (no hang, error+retry) and F2 (reconnect). Screenshot before/after.
- `pytest` + `vitest` + `next build` green; unit tests for the new store lifecycle logic and any backend contract.
- Backend-only pieces (heartbeat, resumable endpoint) → unit-tested; full end-to-end needs a **deploy** (flagged), same as the synth reconciliation.

## Commit plan
One scoped commit per fix (F1…F6), each with its test, per the last batch's style.
