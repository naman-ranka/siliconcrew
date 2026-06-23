# Build brief — Frontend Google sign-in (make hosted mode usable)

Work on `claude/integration-p1p2`. Commit + push there.

## The gap (why this exists)
The **backend OAuth is already complete**: `authenticate()` verifies a Google ID
token (`GoogleOAuthVerifier`) into an `Identity`, and every sensitive route in
`api.py` is guarded by `get_identity` / `require_signed_in`, with per-tenant DB
scoping via `scoped_user_id`. Anonymous callers get a **trial** (lint/sim only);
signed-in callers get full access (synth, save, BYOK keys, MCP).

The frontend has **no sign-in UI and never sends a token**. So in hosted mode
every request lands as anonymous → synth/save/keys are all 403. Your job is the
client side of the existing contract: let a user sign in with Google, hold the
token, and attach it as `Authorization: Bearer <token>` on **every** API call
(REST + WebSocket). No backend changes.

> Self-host is unaffected: when `SILICONCREW_HOSTED` is off the backend returns
> `LOCAL_IDENTITY` and ignores tokens. The UI must degrade gracefully when auth
> is **not configured** (see "Config gating" below) so contributors stay
> plug-and-play with zero setup.

## The contract you're building against
- **Send:** `Authorization: Bearer <google_id_token>` on every request the
  backend reads identity from.
- **Backend reads it** in `api.py::get_identity` via `parse_bearer` →
  `authenticate`. A valid token → real user; no token → anonymous trial; invalid
  token → 401/`AuthError`. Match these: surface a sign-in prompt on
  `signin_required` (403) and a re-auth prompt on invalid/expired (401).
- The token is a **Google ID token (JWT)**, audience = `GOOGLE_OAUTH_CLIENT_ID`.

## THE STANDARD WAY: Google Identity Services (GIS) + a tiny auth context

### 1. Library — use GIS, no heavy deps
Prefer **Google Identity Services** (the official `https://accounts.google.com/gsi/client`
script) over adding `next-auth`. Reasons: the backend already verifies the ID
token itself (we don't need a server-side session/callback route), GIS gives us
exactly an ID token, and it's one script tag + a small wrapper. Load the script
in `app/layout.tsx` (Next `<Script strategy="afterInteractive">`), or inject it
from the auth provider on mount. Do **not** add a backend OAuth callback.

### 2. Auth context (`frontend/lib/auth.tsx` — new)
A React context + provider that owns auth state:
```ts
type AuthState = {
  enabled: boolean;        // is OAuth configured? (NEXT_PUBLIC_GOOGLE_CLIENT_ID set)
  status: "loading" | "anonymous" | "signed_in";
  user: { email: string | null; name?: string; picture?: string } | null;
  token: string | null;    // the Google ID token (JWT)
  signIn: () => void;
  signOut: () => void;
};
```
- Read `NEXT_PUBLIC_GOOGLE_CLIENT_ID` from env. **If empty → `enabled = false`**:
  render nothing auth-related, never call GIS, `token` stays null. This is the
  self-host / unconfigured path and MUST be the zero-config default.
- On sign-in, GIS returns a `credential` (the ID token). Decode the JWT payload
  client-side **only for display** (email/name/picture) — never trust it for
  authz; the backend re-verifies.
- Persist the token in memory + `sessionStorage` (survives refresh, dies with
  the tab). On load, restore and check `exp`; if expired, drop to anonymous.
- **Token expiry:** Google ID tokens last ~1h. Handle it: on any API `401`,
  clear the token, set status `anonymous`, and prompt re-sign-in (toast +
  sign-in button). GIS can also be configured to refresh; a simple
  "session expired, sign in again" is acceptable for v1 — just don't leave the
  user silently 403ing.
- Mount `<AuthProvider>` in `app/layout.tsx` wrapping `TooltipProvider`.

### 3. Wire the token into the API layer (`frontend/lib/api.ts`)
There are **four** outbound paths — all must carry the token:
1. `apiFetch` (line ~24) — generic REST.
2. `actionFetch` (line ~192) — the `{ ok }` action envelope.
3. `workbenchApi.uploadFiles` (line ~217) — raw `fetch` with `FormData` (do
   **not** set `Content-Type` there; just add `Authorization`).
4. `chatApi.createConnection` (line ~131) — the **WebSocket**. Browsers can't set
   headers on `new WebSocket`, so the token rides a query param. **The backend
   already supports this** — `api.py::chat_websocket` reads
   `websocket.query_params.get("token")`, runs `authenticate(token, ...)`, and
   does the tenant ownership check. So **no backend change**: just append
   `&token=<idToken>` alongside the existing `?thread_id=` (URL-encode it).

Standard approach: a module-level `getAuthToken: () => string | null` setter the
`AuthProvider` registers on mount, so `api.ts` (not a React component) can read
the current token without prop-drilling. Then in both fetch wrappers:
```ts
const token = getAuthToken();
headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...rest }
```
Keep it conditional so the unconfigured/self-host path sends no header.

### 4. UI surface (minimal, matches the existing design language)
- A **sign-in button / account chip** in the sidebar header or top bar
  (`components/sidebar/Sidebar.tsx`). Signed-out: "Sign in with Google".
  Signed-in: avatar + email + a dropdown with "Sign out".
- Use the warm palette + existing `ui/` primitives (`Button`,
  `dropdown-menu`, `avatar` — all already in deps). Don't introduce a new style.
- **Gate the gated actions visibly:** when `enabled && status !== "signed_in"`,
  synth/save controls should show a "Sign in to synthesize" affordance (tooltip
  or inline) instead of silently 403ing. Lint/sim stay available (anonymous
  trial). When `!enabled` (self-host), show nothing — full access, no chrome.

## Config gating (the make-or-break detail)
| Env | Behavior |
|-----|----------|
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` **unset** | Auth UI hidden, no token sent, no GIS script. Self-host / dev default. |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` **set** | Sign-in button shown; token attached after sign-in; gated actions prompt sign-in. |

This must pair with the backend's `GOOGLE_OAUTH_CLIENT_ID` (same client ID).
Document both in the frontend README + the deploy runbook.

## Guardrails
- **No backend changes at all.** The REST (`get_identity`/`parse_bearer`) and WS
  (`?token=`) contracts both already exist. Do not touch `authenticate`, the
  action router, or tenancy.
- Unconfigured = zero-config, behavior bit-for-bit today's. No console errors
  when the client ID is absent.
- Never use the decoded JWT for authorization decisions — display only.
- No new heavyweight auth deps (no `next-auth`) unless justified to the maintainer.

## Verify
- **Vitest:** auth context — `enabled=false` when client ID unset (no token, no
  script); token attached to `apiFetch`/`actionFetch`/upload headers when a token
  is present; header omitted when absent; `401` clears token → `anonymous`.
- **Playwright (Tier 2):** with client ID set (use a mocked GIS/credential),
  sign-in flips the UI to the account chip and a subsequent gated request carries
  the `Authorization` header (assert via `browser_network_requests`); with client
  ID unset, no sign-in UI renders and requests carry no auth header.
- Manual: confirm `signin_required` (403) surfaces a sign-in prompt, not a raw
  error toast.

## Deliver
Commit in slices (auth context → api.ts wiring → UI surface → tests), push to
`claude/integration-p1p2`, and summarize: the GIS integration, the
`getAuthToken` seam, all four outbound paths wired (incl. the WS decision), the
config gating, and how gated actions are surfaced.
