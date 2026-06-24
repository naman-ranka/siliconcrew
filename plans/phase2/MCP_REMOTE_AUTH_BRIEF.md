# Build brief — remote MCP auth for the deployed app (WorkOS)

Work on `claude/integration-p1p2`. Honor `plans/phase0/ui-design-language.md` for
any UI, and the tenancy/security posture of the other Phase-2 work.

## Why we're doing this (plain language)
We want a user to connect **deployed SiliconCrew** to their own AI client (the
Claude app, Codex, etc.) as a remote MCP connector, sign in once with Google, and
from then on **create / list / continue SiliconCrew sessions and run the EDA tools
from inside their own AI client** — on their own SiliconCrew account.

The point of MCP here: the user's **own AI subscription is the brain** (it does the
reasoning and decides which tools to call); **SiliconCrew provides the tools, the
session/workspace state, and the synthesis compute.** This is separate from BYOK —
BYOK is about keys for *our own* web agent; MCP is "bring your own AI client."

## The outcome we want
- A user opens Claude → adds SiliconCrew's MCP URL → a browser window asks them to
  **"Sign in with Google"** → they approve → Claude is now connected to **their**
  SiliconCrew account.
- Inside Claude they can list their sessions, start a new one, continue an existing
  one, and drive lint/sim/synth — all scoped to their account.
- Because it's the **same Google identity** they use on the SiliconCrew website,
  sessions started in Claude appear on the website and vice-versa (one account, one
  set of data).
- We do **not** build an OAuth login system ourselves. A trusted provider
  (**WorkOS**) runs the login screens, the connect handshake, and token
  issue/refresh/revoke. We just check the token and act as that user.

## The hard rule — local must not change
Everything in this brief is gated by the existing `settings.hosted` flag.
**Local / self-host stays exactly as it is today: no login, no WorkOS, no tokens**
— stdio MCP with the trusted `LOCAL_IDENTITY`, env keys, "No authentication
required." If any auth code runs when `hosted` is false, that's a bug. Add a test
that asserts the local path is unchanged and authless.

## What already exists (don't rebuild)
- **Remote transport**: `mcp_server.py` already serves `--transport http`
  (Streamable HTTP, `/mcp`) and `sse` as plain **Starlette** apps.
- **Tenant-scoped tools**: every tool already scopes to `self._scoped_user_id()`
  and checks `owns_session(...)`; tool dispatch already binds a per-call
  `SessionContext` (`set_current_session` / `session_scope`) with `user_id` + tier
  — the same tenancy seam the web uses. So MCP-created sessions already land in the
  shared store.
- **An identity seam**: `_resolve_identity()` maps a token → `Identity`, with
  capability gating (`authorize(... SYNTHESIZE/SAVE)`).

**The one gap:** identity is resolved **once per process** from a single
`SILICONCREW_MCP_TOKEN` env var (one user per server). For a shared deployed
endpoint, identity must be resolved **per request** from the inbound
`Authorization: Bearer …` header and bound into that request's tool calls.

## What WorkOS does vs. what we build
- **WorkOS (the "front desk"):** hosts the login UI, "Sign in with Google" (Google
  configured as the upstream connection), the connect/registration handshake AI
  clients use, and token issue / refresh / **revoke**. We own none of this.
- **SiliconCrew (us):** validate the token on each request, figure out which user
  it is, and run as that user. Plus a tiny "where to sign in" info document the AI
  client looks for. That's the whole job.

---

## Slice 1 — Per-request identity in the HTTP/SSE transport (the real work)
In `mcp_server.py`, add a **Starlette middleware** in front of the `/mcp` (and
`/sse`) routes that runs **only when `settings.hosted`**:
1. Read `Authorization: Bearer <token>`.
2. **Validate it against WorkOS** (verify the token signature via WorkOS's public
   keys / JWKS, and check issuer, audience, and expiry). Use the WorkOS SDK or a
   standard JWT-verify library — do not hand-roll crypto.
3. Map the verified claims (`sub` / email) → a SiliconCrew `Identity` / `user_id`.
4. Stash that identity on the request and make the per-call `SessionContext` use it
   (replace the single process-wide `self.identity` for hosted requests), so every
   tool runs as the calling user and tenancy/quota gating sees the right user.
5. If the token is missing or invalid, return **HTTP 401** with a
   `WWW-Authenticate` header that points to the metadata document from Slice 2
   (this is how the AI client knows where to send the user to log in).

When `settings.hosted` is false: skip all of the above — keep today's
`LOCAL_IDENTITY` and the "no auth" path verbatim.

## Slice 2 — The "where to sign in" document + reject-unauth
- Serve the standard **protected-resource metadata** document (RFC 9728, at
  `/.well-known/oauth-protected-resource`) that names WorkOS as the place to get a
  token. This is a tiny static JSON built from config; the AI client reads it after
  the 401 to start the login flow.
- In hosted mode, **reject every unauthenticated MCP call** (no anonymous-degrade).
  This also closes the security finding that the deployed MCP was wide open.

## Slice 3 — One account across web + MCP (identity unification)
For "sessions show up in both places" to be automatic, the token WorkOS issues must
resolve to the **same `user_id` the website uses**. The clean, standard way: route
the **deployed website's sign-in through WorkOS too** (WorkOS with Google upstream),
so web and MCP share one identity source and one `user_id`.

**Honest note / cost:** today the deployed web app signs in with Google directly
(Google Identity Services). Unifying means the *deployed* web sign-in moves to
WorkOS-with-Google. The user-facing experience is unchanged ("Sign in with
Google"); `user_id` becomes the WorkOS subject; BYOK keys (keyed by `user_id`)
keep working as long as we migrate the id mapping cleanly. Local is unaffected
(still no sign-in at all). If we decide not to unify now, the fallback is matching
MCP ↔ web by verified email — messier; prefer unification.

## Slice 4 — Keep the existing guards on over MCP
The per-user **synthesis quota** and capability gating (`authorize`) already exist —
keep enforcing them on the MCP path (each synth burns our hosted compute). No new
quota system needed; just make sure the per-request identity flows into it.

---

## Config / secrets (hosted only)
Behind `hosted`, via GitHub repo Variables/Secrets → Cloud Run env (same pattern as
the rest of deploy): WorkOS **client id**, **API key/secret**, the **issuer / JWKS
URL**, and the expected **audience** (our MCP resource identifier). One-time setup,
documented in `deploy/` like the Google OAuth and WIF setup. None of these exist or
are read in local mode.

## A decision to make (flagged, not assumed)
**Tool surface over MCP:** expose the *full* tool set, or a *curated* set first?
Recommendation: start curated — **sessions (list / create / continue), reads, and
synthesis** — since each synth costs us compute; widen later. Confirm before
building the tool filter.

## Guardrails
- **Local stays authless and unchanged** — gated by `hosted`; covered by a test.
- Do **not** build an OAuth authorization server; WorkOS is the front desk, we are
  only the token-checker + tool provider.
- No changes to the one write path, the action API, or the web tenancy seam beyond
  the identity-source swap in Slice 3.
- Reuse the existing `Identity` / `authorize` / `SessionContext` seams — don't fork
  a parallel auth model for MCP.
- Keep all tests green (backend pytest + frontend vitest).

## Verify
- **Backend pytest** (use the in-memory fakes + the staging static test bearer
  already on this branch):
  - A valid token → resolves to the right `Identity`/`user_id`; tools run as that
    user.
  - Missing/invalid token in hosted → **401** with the `WWW-Authenticate` pointer.
  - Two different users' tokens → strict tenant isolation (user A can't see/continue
    user B's sessions over MCP).
  - **Local mode unchanged**: `hosted` false → no auth required, `LOCAL_IDENTITY`,
    tools work exactly as before.
  - The metadata document is served and names the WorkOS issuer.
- **Live (the real flow):** from the Claude app, add the deployed MCP URL, complete
  the Google sign-in through WorkOS, then list/create/continue a session and confirm
  it also appears in the web UI. Capture screenshots under
  `plans/phase2/screenshots/mcp-auth/`.

## Deliver
Commit per slice on `claude/integration-p1p2`. Summary: per-request identity in the
MCP transport (gated by `hosted`), WorkOS token validation + the metadata document,
the web+MCP identity unification (and its migration note), quota still enforced, and
— explicitly — that **local is untouched and authless**.

## Notes — why WorkOS, why this shape
- **Why WorkOS:** handling login for AI apps / MCP connectors is one of its core,
  advertised jobs; it's free up to ~1M monthly users, runs the login + consent
  screens for us, supports "Sign in with Google" upstream (so the experience matches
  today), and is a trusted, standard choice — the same "set it up once, then trust
  it" deal we had with Google sign-in. We are the **only** host of the deployed
  version, so depending on a managed provider here is fine — there's no third-party
  self-hoster to burden.
- **Open source = local only.** The free, self-contained, no-login SiliconCrew is
  the local build; that's what stays open and untouched. The deployed multi-tenant
  service is ours to operate, and WorkOS lives only there.
- **Whose AI?** Over MCP the user's own AI client is the brain; SiliconCrew is the
  tools + state + synthesis. BYOK keys are not involved in the MCP path.
