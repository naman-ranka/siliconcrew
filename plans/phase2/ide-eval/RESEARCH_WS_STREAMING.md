# Research: WebSocket/SSE streaming for AI chat — standards + decision

Cited engineering brief (primary sources) guiding the chatbot streaming fixes.

## Decision (this round)
**Harden the existing WebSocket** (Option A). All 6 fixes are implemented on the
current WS transport: onclose recovery + reconnect, heartbeat, guaranteed
terminal frame + reopen reconciliation, TTFT feedback, tool durations/stage
progress. This is standard-compliant per the research (Cloud Run supports WS with
raised timeout + heartbeat + client reconnect) and is lower-risk + verifiable
here via a forced-drop repro.

**SSE migration = documented follow-up** (Option B, ideal): OpenAI/Anthropic both
ship SSE for token streaming (unidirectional, header auth, built-in resume via
Last-Event-ID). A future migration would move the token stream to an SSE endpoint
+ POST for client messages, gaining resumability for free — but it's a
transport rewrite that needs a deploy to verify, so it's deferred.

## Key findings (primary sources)
- **SSE is the industry default for token streaming.** Anthropic Messages API and
  OpenAI API both stream via SSE (unidirectional, HTTP-header auth, proxy/CDN/
  HTTP-2 friendly, EventSource auto-reconnect + `Last-Event-ID` resume).
  - platform.claude.com/docs/en/docs/build-with-claude/streaming
  - developers.openai.com/api/docs/guides/streaming-responses
- **WebSocket on Cloud Run is supported but is a long-running HTTP request** under
  the request timeout (default 5 min, max 60 min → returns 504 on timeout); must
  raise `--timeout`, keep **HTTP/2 end-to-end OFF**, and handle client reconnect.
  - docs.cloud.google.com/run/docs/triggering/websockets
  - docs.cloud.google.com/run/docs/configuring/request-timeout
- **Idle timeouts kill silent connections.** GCP ALB backend timeout defaults ~30s;
  *active* (streaming/heartbeat) traffic is fine, *idle* is not. Cloud Run TCP
  keepalive is off by default → **app-level heartbeat is the reliable lever.**
  - docs.cloud.google.com/load-balancing/docs/backend-service
  - docs.cloud.google.com/run/docs/troubleshooting
- **Heartbeat intervals:** SSE comment `:\n\n` every **15s**; WebSocket server
  **ping every 30s**, `terminate()` on missed pong (canonical `ws` pattern,
  RFC 6455 §5.5.2/5.5.3). For our 60s+ synth wait behind a ~30s idle LB, a
  heartbeat **<30s** guarantees the idle timer never fires.
  - rfc-editor.org/rfc/rfc6455.html ; github.com/websockets/ws (README heartbeat)
- **Reconnection**: exponential backoff + jitter with a cap; on reconnect,
  reconcile against server state (don't duplicate). For our per-turn WS, the
  pragmatic "resume" is to refetch the persisted thread history after a drop (the
  agent may finish server-side; Cloud Run keeps the container running after the
  request connection closes).

## Applied to our 6 fixes
- F1 hang-on-drop → onclose must exit streaming, preserve the partial, surface error.
- F2 reconnect/resume → backoff reconnect; refetch persisted history to reconcile.
- F3 heartbeat → server keepalive frame <30s during long tool waits; raise Cloud Run timeout.
- F4 terminal frame + reopen reconcile → always attempt a terminal frame; on reopen,
  reconcile a dangling tool step against the actual run status.
- F5 TTFT → optimistic placeholder + elapsed/thinking indicator within ~300ms.
- F6 durations/progress/summary → per-tool elapsed; synth stage list from poll payloads; guaranteed closing summary.
