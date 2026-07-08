# Live-verify #1 — honest Codex model gate under account auth (staging rev 00068)

**Verdict: PASS** for backlog #1 end-to-end. A non-default, account-picked
Codex model drove a real turn with **NONZERO** usage tokens and no 0-token
silent failure. Backlog #2 (visible prose before a tool call) also **PASS**.

- Staging: frontend `https://siliconcrew-frontend-psp2dkllmq-uc.a.run.app`,
  backend revision **siliconcrew-backend-00068-jfm** (ready 2026-07-08
  23:31 UTC, confirmed in the Cloud Run audit log).
- Account: signed in as `rockstarme.the5@gmail.com` (WorkOS test user, "Claude
  test"). Codex tab shows **"ChatGPT connected"** — account auth, not BYOK.
- Session created for the test: `verify_codex_model_live`, Agent posture,
  Codex tab. Owner authorized use of their connected ChatGPT account.

## What the CodexModelPicker offers (honesty check)

Opened the picker in the Codex tab. It offers three genuine Codex/GPT models,
footer **"Using your ChatGPT account."** — screenshot `img5/01-codex-picker-open.png`:

| Label | subtitle | price |
|---|---|---|
| **GPT-5.3 Codex** (marked *Codex default*) | Code-tuned Codex default — best for RTL work | $2/$12 per Mtok |
| GPT-5.5 | OpenAI flagship; strongest general reasoning | $5/$30 per Mtok |
| GPT-5.4 mini | Fast and inexpensive for light edits | $0.3/$2.5 per Mtok |

The **options themselves are honest** (no "Gemini" in the list). The default
marked in the menu is GPT-5.3 Codex.

**One honesty gap worth flagging (NOT a #1 regression):** before any Codex
pick, the picker BUTTON label read **"gemini-3.5-flash"** — the session's
stored `model_name` (verified via `GET /api/sessions/verify_codex_model_live`
→ `"model_name":"gemini-3.5-flash"`, the *native* LangGraph chat model) leaks
into the Codex tab's initial selected-label. Selecting a real Codex model
fixes the label immediately ("GPT-5.4 mini"). This is exactly the picker
reconciliation that `codex-model-gate.md` explicitly fenced OUT of #1's scope
(default off the shared/native `model_name`), so it is a known-deferred
cosmetic item, not a break of the runtime gate. The X2C-6 "Gemini 3.5 Flash"
symptom is therefore still visible in the *initial label* until a Codex model
is picked; the picker's real options and the runtime gate are honest.

## The key test — non-default model, real turn, nonzero tokens

Picked the **non-default GPT-5.4 mini** (default is GPT-5.3 Codex). Ran three
account-auth turns; captured the raw Codex WebSocket `done` frames
(instrumented `window.WebSocket` in-page, since Codex usage is transient and
not persisted to REST or logs):

| turn | prompt | assistant output | usage tokens (`done` frame) |
|---|---|---|---|
| chat c30619 | "Say hello in one sentence." | `Hello!` | (WS opened before capture; completed, see logs) |
| chat c30619 | "Reply with just the word: pong" | `pong` | (reused WS; completed) |
| chat 32f509 | "Say hello in exactly one short sentence." | `Hello!` | **input 26115, output 24** |
| chat 32f509 | "…tell me what you'll do, then create note.txt…" | prose + `write_file` + "Done." | **input 26418, output 6** |

The captured `done` frame — the definitive nonzero-token proof:

```json
{"type":"done","tokens":{"input":26115,"output":24},"turn_id":"751a872a-…"}
{"type":"done","tokens":{"input":26418,"output":6},"turn_id":"a1cd3825-…"}
```

A 0-token silent failure (the bug #1 fixes) would produce empty output and/or
`{input:0,output:0}`. Instead every turn returned correct, instruction-
following text and nonzero usage. The tool-call turn even executed the tool:
`write_file(note.txt, "hello")` → `"Successfully wrote to note.txt"`.

Screenshots: `img5/02-turn-complete.png` (hello), `img5/03-prose-before-toolcall.png`.

## Log evidence (Cloud Run, backend rev 00068)

Per-turn `[CODEX-TIMING]` for the captured turn (warm-pool hit, completed):

```
[CODEX-TIMING] thread=32f509dc… event=warm_worker_spawned elapsed=5.14s pool_size=2
[CODEX-TIMING] thread=32f509dc… turn=751a872a… event=turn_start
[CODEX-TIMING] thread=32f509dc… event=sdk_thread_ready elapsed_setup=0.00s warm=hit
[CODEX-TIMING] thread=32f509dc… event=sdk_turn_issued elapsed=0.00s
[CODEX-TIMING] thread=32f509dc… turn=751a872a… event=turn_end status=completed elapsed=4.83s
```

**Honest limit on model attribution:** the codebase logs **no**
model-attribution line — `sdk_turn_issued` does not print the effective model,
and `_effective_model` / `_fetch_allowed_models`
(`src/agents/codex/codex_engine.py`) only log on *failure*
(`"[CODEX] model/list failed … omitting picked model"`). That failure line
was **absent**, so `model/list` was fetched without error; but the logs do
**not** expose the returned allowed-set, so I cannot prove from logs alone
whether `gpt-5.4-mini` was *applied* (in the account's set → passed) versus
*omitted → account default*. Per the task's own criteria both are a PASS —
the only FAIL is a 0-token silent failure, which did **not** occur. The gate's
guarantee (never break the turn to 0 tokens when a non-default id is picked
under account auth) held end-to-end.

## Backlog #2 spot-check — prose before a tool call (PASS)

The tool-calling turn rendered the assistant's genuine explanation as
**visible prose**, not a collapsed "Thinking" toggle:

> I'm going to create note.txt with just hello.
> [ Writing File · note.txt ]  [ Open file ]
> Done.

Visible preamble prose → tool-call card → closing prose. Screenshot
`img5/03-prose-before-toolcall.png`. #2 confirmed on staging.

## Verdicts

- **#1 (honest Codex model gate under account auth): PASS.** Non-default
  GPT-5.4 mini picked under a connected ChatGPT account; turn completed with
  nonzero usage (input 26115 / output 24) and correct output. No 0-token
  silent failure — the decorative-picker bug is gone at runtime. Model-vs-
  default attribution is not determinable from logs (no such log line), but is
  not required for the PASS.
- **#2 (visible prose before tool call): PASS.**
- **Deferred/cosmetic (not a #1 regression):** the Codex picker's *initial
  button label* inherits the session's native `model_name`
  (`gemini-3.5-flash`) until a Codex model is picked — the picker-
  reconciliation item `codex-model-gate.md` fenced out of #1.
