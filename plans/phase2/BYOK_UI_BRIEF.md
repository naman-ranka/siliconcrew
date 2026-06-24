# Build brief — BYOK / API-keys settings UI

Work on `claude/integration-p1p2`. Honor `plans/phase0/ui-design-language.md`
(warm palette; status colors kept separate from the orange brand) and the a11y
bar used by the other workbench briefs.

## Goal
A polished, **mode-adaptive** Settings → **API Keys** panel so a user can manage
which LLM provider keys power the agent. Two contexts, one panel:

- **Local / self-host (not deployed):** the server uses **environment** keys
  (`GOOGLE_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`). Per-user storage is
  intentionally disabled here. The panel is **status + guidance**, not entry.
- **Deployed / hosted (signed-in user):** per-user **BYOK** against the existing
  envelope-encrypted vault — add / replace / remove a key per provider — plus the
  capped **hosted Gemini free tier** for users with no key of their own.

The backend already exists. This is a frontend panel + a thin API client + wiring
the model picker's availability to refresh. **Do not rebuild backend endpoints.**

---

## Backend — already built (verified contract; do NOT change for the UI)

Endpoints (all in `api.py`):
- `GET /api/keys` → `{ "providers": [<providers the caller has a stored key for>] }`.
  Requires sign-in. **Returns 400** (`"BYOK is only available in hosted mode."`) in
  self-host; **503** if the vault isn't configured on the server.
- `PUT /api/keys/{provider}` body `{ "api_key": "<secret>" }` → stores it
  envelope-encrypted. 400 on unknown provider or empty key.
- `DELETE /api/keys/{provider}` → removes the caller's key for that provider.
- `GET /api/models` → `{ "models": [{id,label,provider,tier,pricing?,available}], "default": "<id>" }`.
  `available` **already** reflects per-request usable providers: env keys in
  self-host; the user's BYOK keys + container fallback env + the capped hosted
  Gemini tier in hosted. (`api.py::_usable_providers`.)

Facts: `VALID_PROVIDERS = {gemini, openai, anthropic}`; provider→env key mapping
is `_PROVIDER_ENV` in `api.py`. Mode flags live in `src/platform_engines/settings.py`
(`hosted`, `llm_key_engine` = `env|byok`, `hosted_gemini_key`). The vault
(`src/platform_engines/llm_keys.py`) stores only wrapped-DEK + ciphertext (KMS in
prod, local master key self-host) and **never returns plaintext** — `GET /api/keys`
returns provider names only.

### The one dependency to flag — do not silently assume it
`create_llm(..., api_key=...)` already accepts a request-scoped key, **but the chat
path does not pass one yet**: `api.py::chat_websocket → create_architect_agent(model_name=…)
→ create_llm()` still resolves keys from the environment (no `LlmKeyProvider` on
that path). So today a stored BYOK key changes **model availability** but is **not
yet consumed by the running agent**. The UI ships against the existing endpoints
and is useful as-is, but call this out in the PR: "stored key not yet used by the
agent — chat-path wiring is a separate slice." If you choose to also do that
wiring, keep it in its **own commit with its own tests** (resolve via
`LlmKeyProvider`, thread `user_id` from the WS identity → `create_architect_agent`
→ `create_llm(api_key=…)`); do not entangle it with the UI commit.

### How the frontend detects the mode
Primary signal: `useAuth().enabled` (true when `GOOGLE_CLIENT_ID` is configured =
hosted/auth build) and `status === "signed_in"`. Secondary: treat `GET /api/keys`
**400** as "self-host / env mode" and **503** as "vault unconfigured" — render the
matching state gracefully rather than erroring.

---

## Frontend

**Entry point.** Wire the already-stubbed **"Settings"** button in the sidebar
footer (`frontend/components/sidebar/Sidebar.tsx`, ~line 769) to open a Dialog.
Build `frontend/components/settings/SettingsModal.tsx` with an **API Keys**
section, structured so future sections (Usage, Preferences) can slot in.

**Reuse the design system — no new primitives.** `Dialog*` (`components/ui/dialog.tsx`),
`Button`, `Input` (`type="password"`), `Tooltip`, `Separator`, and the toast via
`useStore().pushToast`. Surfaces `bg-surface-1` (modal) / `bg-surface-2` (inputs),
text `text-foreground` / `text-muted-foreground`. Mirror the form/error/loading
pattern of `CreateSessionDialog` in `Sidebar.tsx`.

**API client.** Add `keysApi` to `frontend/lib/api.ts` against the REAL contract:
`list(): GET /api/keys`, `save(provider, api_key): PUT /api/keys/{provider}` with
body `{ api_key }`, `remove(provider): DELETE /api/keys/{provider}`. Reuse the
existing `apiFetch` (Bearer attached; 401 → `notifyAuthExpired`).

**Mode-adaptive content (the heart of this brief):**

- **Hosted + signed in** — one row per provider (Anthropic / OpenAI / Google):
  configured vs not (from `GET /api/keys`), a masked "key set" indicator, a
  password input to **set/replace** (PUT), a **Remove** action (DELETE, with a
  confirm), a help tooltip + link to that provider's key console ("where to get a
  key"). On save: optimistic, `pushToast` success/error, then call
  `useStore.getState().loadModels()` so the picker's availability refreshes. Show a
  note that **Gemini works without a key** on the free hosted tier when
  `hosted_gemini_key` is active (reflected by gemini models being `available`).
- **Hosted + signed out** — a sign-in prompt (reuse `AccountChip` / `signIn()`):
  "Sign in to manage your API keys."
- **Local / self-host** — read-only: "This instance uses environment keys." Per
  provider show **configured / missing** (derive from `GET /api/models`
  availability, since `GET /api/keys` 400s here) with copy-paste guidance: set
  `GOOGLE_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` in `.env` (or
  `.env.docker` for Docker Compose), link to `.env.example`, note a restart is
  required. **No entry fields** (the backend would reject them).
- **Hosted, vault unconfigured (503)** — graceful: "Key storage isn't configured
  on this server" while still showing model availability.

**Think-of-all-aspects (required, not optional):**
- Secrets never leave the server in `GET`; never render a stored key. Input is
  `type="password"`, `autoComplete="off"`, cleared on save; never put the key in
  the Zustand store or `localStorage`; never log it.
- Confirm before delete. Disabled/loading states on every async action. Non-empty
  validation + a light format hint per provider.
- Full a11y: focus-visible, labelled inputs, `aria` on status, Escape /
  click-outside to close (Radix gives most of this). Empty / error / loading
  states all designed, not afterthoughts.
- Picker tie-in polish: from a disabled ("needs key") model row or the picker
  footer, offer a **"Manage keys"** shortcut that opens this modal at the API Keys
  section.

---

## Process — iterate against the LIVE UI with subagents (explicit requirement)
Do not ship this blind. Build → run → look → refine:
1. Run the stack locally (backend `api.py` + `frontend` dev server). Use the
   **Playwright MCP** to open the app and drive the real panel.
2. Exercise **both modes** by toggling env: local = `SILICONCREW_HOSTED` unset (no
   `GOOGLE_CLIENT_ID`); hosted = `SILICONCREW_HOSTED=1` + `GOOGLE_CLIENT_ID` set +
   `SILICONCREW_MASTER_KEY` set (so `build_key_vault` returns a local-master vault
   and PUT/GET/DELETE work without GCP KMS). For a signed-in identity without real
   Google OAuth, use the **static test bearer → fixed identity** seam (staging-only,
   added on this branch) so you can hit `/api/keys` end-to-end.
3. Spawn subagents for independent passes and fold their findings back in:
   - a **design critique** as a first-time *hosted* user and a first-time *local*
     user (is the mode obvious? is "where do I get a key?" answered?);
   - an **a11y / contrast** pass against `ui-design-language.md`;
   - a **flow check** that model availability flips after save and that the local
     panel never offers a dead entry field.
   Iterate until it's genuinely polished, not just functional.

---

## Guardrails
- No backend endpoint changes for the UI (the contract exists). Any chat-path
  wiring is a separate, independently-tested slice.
- No changes to the auth/tenancy seam, the one write path, or the action API.
- Keep all tests green (frontend vitest + backend pytest).

## Verify
- **Vitest** (`frontend/test/`): `keysApi` hits the right method/body/path;
  `SettingsModal` renders the correct state per mode (hosted-signed-in shows entry
  rows; local shows env-status + guidance, no inputs; signed-out shows sign-in;
  503 shows the unconfigured message); save → `pushToast` + `loadModels()` called;
  delete is confirm-gated. Mock `keysApi` + `useAuth`.
- **Playwright (live), both modes**, screenshots under
  `plans/phase2/screenshots/byok/`:
  - Hosted: open Settings → add a key → toast → the model flips from "needs key"
    to available in the picker → replace → delete (confirm) → signed-out prompt.
  - Local: open Settings → "uses environment keys" + per-provider configured/missing
    + guidance, no entry fields.

## Deliver
Commit per slice, push to `claude/integration-p1p2`. In the summary: the modal
entry point, the mode-adaptive behavior, the `keysApi` contract used, the
model-availability refresh, and — explicitly — the **chat-path consumption
dependency** (stored key not yet used by the agent) as a tracked follow-up.
