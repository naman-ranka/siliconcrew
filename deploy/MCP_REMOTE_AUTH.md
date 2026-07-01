# Remote MCP auth + web/MCP identity unification (WorkOS)

> Hosted (deployed) only. Local / self-host is unaffected — no login, no WorkOS,
> no tokens. None of the variables below exist or are read when
> `SILICONCREW_HOSTED` is false. See `plans/phase2/MCP_REMOTE_AUTH_BRIEF.md`.

This document covers operating the deployed app's remote MCP connector and the
one-account-across-web+MCP unification:

1. What WorkOS is (the "front desk") and what we run.
2. The hosted config (backend env / secrets).
3. The MCP connector flow (what an AI client sees).
4. The web sign-in swap (Google-direct → WorkOS-with-Google).
5. The one-time identity migration (`google_<sub>` → `workos_<sub>`).

---

## 1. Roles

- **WorkOS AuthKit** is the OAuth authorization server for remote MCP. It hosts
  authorization-server metadata, Dynamic Client Registration / CIMD, consent,
  token issue / refresh / revoke, and the JWKS.
- **SiliconCrew** is the MCP resource server. It validates WorkOS tokens on each
  MCP request (RS256 against the published JWKS, checking issuer / audience /
  expiry — standard PyJWT, no hand-rolled crypto), maps the verified subject to
  a `workos_<sub>` user_id, and runs as that user.
- **Optional Standalone Connect**: if you want the browser to pass through the
  SiliconCrew frontend for the user-auth step, set the WorkOS Login URI to
  `https://<frontend>/mcp/connect`. The frontend signs the user in with the
  existing web AuthKit path, calls `POST /api/mcp/oauth/complete`, and WorkOS
  resumes the OAuth flow back to the AI client.

## 2. Hosted config (backend)

Set these (GitHub repo Variables/Secrets → Cloud Run env, same pattern as the
Google OAuth / WIF setup). They are read **only** when `SILICONCREW_HOSTED=true`.

| Env var | Meaning |
| --- | --- |
| `WORKOS_CLIENT_ID` | WorkOS user-management client id for the web SPA. The web issuer/JWKS are derived from it (`https://api.workos.com/user_management/<client_id>` and `https://api.workos.com/sso/jwks/<client_id>`). |
| `WORKOS_AUTHKIT_DOMAIN` | **Recommended for MCP.** AuthKit OAuth issuer/domain, e.g. `https://premier-plant-48-staging.authkit.app`. When set, MCP metadata advertises this OAuth server and the MCP verifier uses `<domain>/oauth2/jwks`. |
| `WORKOS_API_KEY` | **Only for Standalone Connect.** Server-side key used by `POST /api/mcp/oauth/complete` to call WorkOS's completion API. Leave empty if you let AuthKit host the full login UI. |
| `WORKOS_AUDIENCE` | **MCP service only.** Expected `aud` = the MCP resource identifier (your `/mcp` URL). Leave **empty** on the web service. |
| `MCP_RESOURCE_URL` | **MCP service only.** Public MCP resource URL advertised in the metadata document (usually the same `/mcp` URL). |
| `MCP_AUTHORIZATION_SERVER` / `MCP_ISSUER` / `MCP_JWKS_URL` | Optional MCP-specific overrides. Normally `WORKOS_AUTHKIT_DOMAIN` is enough. |
| `MCP_SCOPES_SUPPORTED` | Optional comma/space-separated scopes advertised to MCP clients. Defaults to `openid,email,profile,offline_access` when `WORKOS_AUTHKIT_DOMAIN` is set; otherwise `mcp` for the legacy direct path. |
| `WORKOS_ISSUER` / `WORKOS_JWKS_URL` | Optional web-token overrides — set only for a custom WorkOS user-management token profile. |

Web validation is active when `settings.workos_configured` is true. MCP
validation is active when `settings.mcp_auth_configured` is true. If hosted MCP
is reachable but its issuer/JWKS are unconfigured, every MCP call fail-closes
with `401`.

Web AuthKit JS access tokens use
`iss=https://api.workos.com/user_management/<client_id>`. MCP OAuth tokens from
the AuthKit domain use `iss=<WORKOS_AUTHKIT_DOMAIN>`. Keep those verifier
profiles separate; the code does this via `workos_*` settings for web and
`mcp_*` settings for remote MCP.

### Web vs MCP differ on audience (important)

WorkOS issues two token profiles, and the backend runs as two separate Cloud Run
services (web API `api.py`, MCP `mcp_server.py`) with separate env:

- **Web API service** — AuthKit access tokens carry **no `aud`** claim. Set
  `WORKOS_CLIENT_ID` and **leave `WORKOS_AUDIENCE` empty**. The verifier checks
  issuer + signature + expiry only. (If you set an audience here, every web token
  is rejected.)
- **MCP service** — the AI client's token **is** audience-bound to your resource.
  Set `WORKOS_AUDIENCE` = `MCP_RESOURCE_URL` = your `/mcp` URL **and register that
  exact URL as a resource indicator in the WorkOS dashboard** (AuthKit → MCP /
  resources). Without the registration WorkOS falls back to a default
  environment-scoped audience and validation 401s.

Staging shortcut (CI / automated agents): `SILICONCREW_TEST_BEARER_TOKEN` still
works on the MCP path — a request whose bearer equals that secret authenticates
as the fixed `test-bot` identity (constant-time compare). **Never set it in
production.**

## 3. The MCP connector flow

- The deployed server runs `mcp_server.py --transport http` (Streamable HTTP at
  `/mcp`) or `--transport sse`. In hosted mode a per-request auth middleware sits
  in front (inside CORS).
- An unauthenticated MCP call returns **`401`** with a `WWW-Authenticate: Bearer
  resource_metadata="https://<host>/.well-known/oauth-protected-resource"` header.
- That well-known route serves the RFC 9728 **protected-resource metadata** (a
  small JSON built from config) naming the AuthKit OAuth domain as the
  authorization server. The AI client discovers AuthKit's OAuth metadata,
  registers dynamically when supported, walks the user through auth/consent, and
  retries with `Authorization: Bearer <token>`.
- For Standalone Connect, configure the WorkOS Login URI to
  `https://<frontend>/mcp/connect`. The page stores WorkOS's `external_auth_id`,
  signs the user in if needed, then calls the backend completion endpoint. The
  backend calls `https://api.workos.com/authkit/oauth2/complete` with
  `WORKOS_API_KEY` and returns WorkOS's `redirect_uri` to the browser.
- Every authenticated tool call then runs as the calling user — sessions,
  reads, synthesis, etc. — scoped to their `workos_<sub>` tenant, with the
  existing per-user synthesis quota and capability gating enforced.

Quick check after deploy:

```bash
curl -s https://<host>/.well-known/oauth-protected-resource | jq .
curl -i  https://<host>/mcp           # expect 401 + WWW-Authenticate (hosted)
```

## 4. Web sign-in swap (unification)

For a user's sessions to appear in **both** the website and their AI client, the
website must resolve to the **same** `user_id` WorkOS issues. The backend already
does this: `auth.build_verifier` **prefers WorkOS** whenever `WORKOS_*` is
configured, so the deployed web API validates the same WorkOS token the MCP path
does → one `workos_<sub>` id. Until `WORKOS_*` is set, the backend keeps
verifying Google tokens (`google_<sub>`) — **nothing changes until you flip it
on.**

Frontend: the web app now ships a **WorkOS AuthKit** sign-in path
(`@workos-inc/authkit-js`) alongside the existing Google one. It activates when a
WorkOS client id is configured and **takes precedence** over Google; with neither
configured there is no auth UI at all (self-host unchanged). The user-facing
button stays "Sign in with Google" (configured as the WorkOS upstream); the token
the SPA holds and sends as `Authorization: Bearer` becomes the WorkOS access
token, which the SDK refreshes automatically.

Frontend runtime env (read per-request by the server layout, like the Google
vars — no rebuild needed):

| Env var | Meaning |
| --- | --- |
| `WORKOS_CLIENT_ID` (or `NEXT_PUBLIC_WORKOS_CLIENT_ID`) | AuthKit client id; presence flips the web app to the WorkOS path |
| `WORKOS_REDIRECT_URI` (or `NEXT_PUBLIC_WORKOS_REDIRECT_URI`) | OAuth callback; defaults to the app origin (`https://<app>/`) if unset |

In the **WorkOS dashboard**: add `WORKOS_REDIRECT_URI` as an allowed redirect URI,
and configure **Google** as the AuthKit connection so the upstream button matches
today. The `@workos-inc/authkit-js` dependency is already in
`frontend/package.json` — a normal `npm ci` / image build picks it up.

> The live browser flow (add the MCP URL in the Claude app → Sign in with Google
> through WorkOS → list/create/continue a session → confirm it also shows on the
> website) is verified at deploy time — there are no WorkOS credentials in CI.
> Capture screenshots under `plans/phase2/screenshots/mcp-auth/`.

## 5. One-time identity migration (`google_<sub>` → `workos_<sub>`)

Existing deployed users signed in with Google, so their data is keyed by
`google_<google_sub>`. After the swap their id becomes `workos_<workos_sub>`. A
one-time, **operator-run, idempotent** re-key moves their data so nothing
disappears. It is **email-linked**: WorkOS knows each user's verified email and
new subject; Google knew the same email and old subject — you build the pairing
out-of-band and feed it in. No shipped data is ever auto-mutated.

1. Build a mapping file `migration.json` (one entry per user; `email` is for the
   audit log only):

   ```json
   [
     {"old_user_id": "google_1078...", "new_user_id": "workos_01HX...", "email": "user@example.com"}
   ]
   ```

2. Dry-run (validates the file, mutates nothing):

   ```bash
   python -m src.platform_engines.identity_migration migration.json --dry-run
   ```

3. Apply (re-keys projects, sessions, chat threads, and BYOK keys). It is safe to
   re-run — a completed migration moves zero rows:

   ```bash
   python -m src.platform_engines.identity_migration migration.json
   ```

What moves: `projects`, `session_metadata`, `chat_threads`, and `byok_keys` rows
owned by the old id. BYOK keys need **no** rewrap — the wrapped DEK is independent
of the owner id, so the keys keep working under the new id. Each user's run is
isolated; one bad pair never aborts the batch. The exit code is non-zero if any
user failed.

Run it once, immediately after enabling `WORKOS_*` and the AuthKit frontend, so a
user's first WorkOS sign-in lands them on their migrated data.
