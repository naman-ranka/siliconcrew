# Build brief — BYOK end to end (key storage UI **and** agent consumption)

Work on `claude/integration-p1p2`. Honor `plans/phase0/ui-design-language.md`
(warm palette; status colors kept separate from the orange brand) and the a11y
bar used by the other workbench briefs.

## Goal
Ship BYOK as **one complete, working feature**: a user can supply their own LLM
provider key (hosted) or rely on environment keys (local), **and the running
agent actually uses the right key for every request**, with a capped hosted Gemini
fallback. Two contexts, one feature:

- **Local / self-host (not deployed):** the server uses **environment** keys
  (`GOOGLE_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`). Per-user storage is
  intentionally disabled; the panel is **status + guidance**, not entry.
- **Deployed / hosted (signed-in):** per-user **BYOK** against the encrypted vault
  — add / replace / remove per provider — plus the capped **hosted Gemini free
  tier** for users with no key of their own; the agent resolves and uses that key.

This is intentionally a single deliverable: the UI is meaningless if a saved key
isn't consumed, and the consumption is untestable without the UI.

---

## What already exists (verified — do NOT rebuild)

**Key-management endpoints** (`api.py`):
- `GET /api/keys` → `{ "providers": [...] }` (sign-in required; **400** in
  self-host: `"BYOK is only available in hosted mode."`; **503** if vault off).
- `PUT /api/keys/{provider}` body `{ "api_key": "<secret>" }` → envelope-encrypt + store.
- `DELETE /api/keys/{provider}`.
- `GET /api/models` → `{ models:[{id,label,provider,tier,pricing?,available}], default }`,
  `available` already per-request (`api.py::_usable_providers`).

**Vault + resolver layer** (`src/platform_engines/llm_keys.py`) — *fully built*:
- `EnvelopeKeyVault` (`store_key`/`get_key`/`has_key`/`delete_key`), KMS or local
  master-key KEK, persisted only as wrapped-DEK + ciphertext.
- `LlmKeyProvider` protocol: **`resolve(user_id, model_name) -> LlmKey`**
  (`LlmKey = {provider, api_key, source: "byok"|"hosted"|"env", model?}`).
- `EnvLlmKeyProvider` (self-host: env keys) and `ByokHostedLlmKeyProvider`
  (hosted: BYOK → container-env fallback → capped hosted Gemini → raise).
- Factory **`build_llm_key_provider(settings, vault)`** picks the right one.
- `HostedTierExhausted` (has `.code`, `.message`) + `HostedTierLimiter`
  (`.check(user_id)` / `.record(user_id, tokens, cost)`).

**The LLM factory is ready:** `create_llm(model_name, temperature=0.0, api_key=None)`
already accepts a request-scoped key; when `None` it falls back to env.

**The ONLY gap:** `api.py` never builds the provider or calls `.resolve()`, so the
chat path (`chat_websocket → create_architect_agent(model_name=…) → create_llm()`)
still reads env keys regardless of what the user stored. Closing that gap +
building the UI is the whole job.

---

## Slice 1 — Backend: make the agent use the resolved key

1. **Build the provider once** in `api.py` (next to `_KEY_VAULT`):
   `_LLM_KEY_PROVIDER = build_llm_key_provider(get_settings(), _KEY_VAULT)`.
2. **Thread the key through agent construction.** In `src/agents/architect.py`,
   add `api_key: str | None = None` to `create_architect_agent(...)` and pass it:
   `create_llm(model_name=model_name, temperature=0.0, api_key=api_key)`.
3. **Resolve per request in `chat_websocket`.** After the active model is known
   (and using the connection's `uid`/identity), call
   `llm_key = _LLM_KEY_PROVIDER.resolve(uid, model_name)`; if `llm_key.model` is
   set (hosted tier pins a model), use it as the effective model. Pass
   `api_key=llm_key.api_key` into `create_architect_agent`.
4. **Handle the "no usable key" paths** as clean WebSocket errors, not 500s:
   wrap resolution in `try/except (HostedTierExhausted, ValueError)` and emit
   `{"type":"error","code": <"hosted_tier_exhausted"|"no_key">, "error": <message>}`
   so the UI can show a CTA to open the keys panel. (`ByokHostedLlmKeyProvider`
   raises `ValueError("No key available for provider …")` and `HostedTierExhausted`
   with a ready user-facing message.)
5. **Read-only agent construction must not require a live key.** `_read_thread_history`
   (and any state-only `aget_state` path) builds an agent but never calls the LLM.
   Resolve best-effort and tolerate failure (e.g. pass `api_key=None` / skip), so
   viewing history never 500s when a user has no key yet.
6. **Cap the hosted tier (recommended).** When `llm_key.source == "hosted"`,
   after a turn completes record usage via the limiter
   (`_LLM_KEY_PROVIDER.limiter.record(uid, tokens, cost)`) using the token/cost
   the WS loop already computes — otherwise the daily/global caps never bite.

No new endpoints, no schema changes — this is wiring an existing resolver into the
existing agent constructor.

## Slice 2 — Frontend: the mode-adaptive API Keys panel

**Entry point.** Wire the stubbed **"Settings"** button in the sidebar footer
(`frontend/components/sidebar/Sidebar.tsx`, ~line 769) to open a Dialog. Build
`frontend/components/settings/SettingsModal.tsx` with an **API Keys** section,
structured so future sections (Usage, Preferences) slot in.

**Reuse the design system — no new primitives.** `Dialog*`, `Button`, `Input`
(`type="password"`), `Tooltip`, `Separator`, toast via `useStore().pushToast`.
Surfaces `bg-surface-1`/`bg-surface-2`, text `text-foreground`/`text-muted-foreground`.
Mirror `CreateSessionDialog`'s form/error/loading pattern.

**API client.** Add `keysApi` to `frontend/lib/api.ts` against the REAL contract:
`list(): GET /api/keys`, `save(provider, api_key): PUT /api/keys/{provider}` (body
`{ api_key }`), `remove(provider): DELETE /api/keys/{provider}`. Reuse `apiFetch`.

**Mode-adaptive content** (detect via `useAuth().enabled` + `status`; treat `400`
→ self-host and `503` → vault-off as graceful states):
- **Hosted + signed in:** one row per provider (Anthropic / OpenAI / Google):
  configured-or-not (from `GET /api/keys`), a password input to set/replace (PUT),
  a confirm-gated **Remove** (DELETE), a help tooltip + link to the provider's key
  console. On save/delete: `pushToast` + `useStore.getState().loadModels()` so the
  picker's availability refreshes. Note that **Gemini works without a key** on the
  free hosted tier when available.
- **Hosted + signed out:** sign-in prompt (reuse `AccountChip`/`signIn()`).
- **Local / self-host:** read-only "This instance uses environment keys" with
  per-provider configured/missing (derive from `GET /api/models`, since
  `GET /api/keys` 400s here) + copy guidance to set the env vars in `.env` (or
  `.env.docker`), link `.env.example`, note restart required. **No entry fields.**
- **Hosted, vault unconfigured (503):** graceful "key storage isn't configured."

## Slice 3 — Close the loop in chat

When the WS emits the Slice-1 `no_key` / `hosted_tier_exhausted` error, render it
in the chat as a clear message with a **"Add an API key"** CTA that opens the
SettingsModal at the API Keys section. This is what makes BYOK feel finished: a
model that needs a key tells you so and takes you straight to fixing it.

---

## Mode matrix (both required)
| Situation | `resolve()` picks | Panel behavior |
|---|---|---|
| Local (`SILICONCREW_HOSTED` unset) | `EnvLlmKeyProvider` → env key | status + guidance, no entry |
| Hosted, user has BYOK | `byok` (decrypted) | per-provider CRUD |
| Hosted, no BYOK, Gemini | capped `hosted` key | CRUD + "free tier" note |
| Hosted, no BYOK, non-Gemini | raises → `no_key` error | CRUD; chat CTA to add a key |
| Hosted tier exhausted | `HostedTierExhausted` | chat CTA to add own key |

## Think-of-all-aspects (required)
- Secrets: `GET` never returns a key; never render one. Input `type="password"`,
  `autoComplete="off"`, cleared on save; never store the key in Zustand/localStorage;
  never log it (server already keeps it request-scoped).
- Confirm before delete; disabled/loading on every async action; non-empty +
  light per-provider format hint.
- a11y: focus-visible, labelled inputs, aria on status, Escape/click-outside.
  Empty/error/loading states designed, not afterthoughts.
- `apiFetch` already maps 401 → `notifyAuthExpired`; keep that path.

## Process — iterate against the LIVE UI with subagents (explicit requirement)
1. Run the stack locally (backend `api.py` + `frontend` dev server); drive the
   real panel + chat with the **Playwright MCP**.
2. Exercise **both modes**: local = `SILICONCREW_HOSTED` unset / no `GOOGLE_CLIENT_ID`;
   hosted = `SILICONCREW_HOSTED=1` + `GOOGLE_CLIENT_ID` + `SILICONCREW_MASTER_KEY`
   (so `build_key_vault` returns a local-master vault and PUT/GET/DELETE work
   without GCP KMS). For a signed-in identity without real OAuth, use the
   **static test bearer → fixed identity** seam (staging-only, on this branch).
   Verify the full loop: save a key → model flips to available → send a message →
   the agent uses that key; remove the key → the chat shows the `no_key` CTA.
3. Spawn subagents for independent passes and fold findings back: a **design
   critique** (first-time hosted user *and* first-time local user — is the mode
   obvious? is "where do I get a key?" answered?), an **a11y/contrast** pass, and a
   **flow check** (availability flips after save; local panel never shows a dead
   entry field; hosted-tier-exhausted message is reachable). Iterate to genuinely
   polished, not just functional.

## Guardrails
- No new endpoints or schema changes — Slice 1 wires the existing resolver into the
  existing agent constructor; Slice 2/3 are frontend + the WS error shape.
- No changes to the auth/tenancy seam, the one write path, or the action API.
- Keep all tests green (backend pytest + frontend vitest).

## Verify
- **Backend pytest:** `chat_websocket` resolves and passes `api_key` (assert
  `create_architect_agent`/`create_llm` receives the BYOK key for a user with a
  stored key; the hosted Gemini fallback for one without; `no_key` for a non-Gemini
  provider with no key); `HostedTierExhausted` → structured WS error; history read
  works with no key configured. Use the in-memory vault + fakes already used by the
  llm_keys tests.
- **Frontend vitest:** `keysApi` method/body/path; `SettingsModal` renders the
  right state per mode; save → `pushToast` + `loadModels()`; delete confirm-gated;
  the chat `no_key` error renders the "Add an API key" CTA.
- **Playwright (live), both modes**, screenshots under
  `plans/phase2/screenshots/byok/`: hosted add→use→remove loop + the chat CTA;
  local status/guidance panel.

## Deliver
Commit per slice on `claude/integration-p1p2` (Slice 1 backend, Slice 2 UI, Slice 3
chat loop). Summary: the resolver-into-agent wiring, the `keysApi` contract, the
mode-adaptive panel, the model-availability refresh, the hosted-tier cap behavior,
and the chat "add a key" CTA — i.e. a BYOK key a user saves is actually used by the
agent, end to end, in both local and deployed modes.
