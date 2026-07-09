# Defensive review — Codex SDK auth storage vs official docs

**Scope:** read-only design review of SiliconCrew's own Codex/ChatGPT credential
handling, compared to the official OpenAI Codex SDK / `codex` CLI auth docs. No
live probing; code-reading + docs only. Branch `endgame`.

## Verdict (maturity + security)

The **at-rest** story is genuinely mature: BYOK API keys *and* the reused
ChatGPT `auth.json` are stored with real envelope encryption (per-key random DEK
wrapping the secret, DEK wrapped by a Cloud-KMS KEK), tenant-keyed by owner id,
never persisted in plaintext, never logged, and durable across
redeploy/scale — this matches the GCP-recommended pattern and is above the bar
for an early platform. The honest weaknesses are all about the **account token's
working copy and lifecycle**, not the DB blob: (1) the ChatGPT credential is a
*rotating refresh-token* that OpenAI explicitly says must **never be shared
across concurrent machines**, yet our hosted design deliberately shares one
durable blob across all instances with a last-writer-wins persist — a real
rotation-clobber race; (2) the token is staged as **plaintext `auth.json` on
instance disk** (per-user home + per-turn home), so the encryption-at-rest
benefit is bypassed for the live working set; (3) a single KEK wraps every
tenant's DEK, so KEK/master-key compromise is total. None of these are demo-grade
sloppiness — they're the next hardening wave for an otherwise sound design.

---

## (A) What we store, and where — file:line map

Two credential types share **one** envelope-encrypted vault.

### 1. BYOK API keys (OpenAI / Anthropic / Gemini)
- **Encryption:** `EnvelopeKeyVault.store_key` — fresh 32-byte DEK, Fernet-encrypt
  the api key under the DEK, wrap the DEK with the KEK, persist only
  `{wrapped_dek, ciphertext, v:1}`; plaintext is never written
  (`src/platform_engines/llm_keys.py:283-304`).
- **KEK selection:** Cloud KMS via `KmsKekProvider` when `KMS_KEY_URI` is set
  (`llm_keys.py:97-115`); else a local master key = `SHA-256(SILICONCREW_MASTER_KEY)`
  (`LocalKekProvider`, `llm_keys.py:83-94`, `459-495`). If neither is set the
  vault is `None` and `/api/keys` returns 503 (`api.py:915-918`).
- **Persistence backend:** Postgres `byok_keys` table hosted
  (`PostgresWrappedKeyStore`, `llm_keys.py:215-267`), SQLite self-host
  (`SqliteWrappedKeyStore`, `llm_keys.py:158-212`); PK `(user_id, provider)`.
- **Endpoints:** `PUT/GET/DELETE /api/keys/{provider}` (`api.py:921-949`),
  tenant-scoped through `_byok_user` which *requires* a uid and rejects self-host
  (`api.py:906-912`). Decrypted only into request scope by the chat path
  (`ByokHostedLlmKeyProvider.resolve`, `llm_keys.py:417-445`) — never to env,
  never logged (`LlmKey` docstring, `llm_keys.py:30-37`).

### 2. Codex ChatGPT account auth (`auth.json` = access + refresh + id token, account id)
- **Login:** SDK-native device-code flow, no stdout scraping —
  `codex.login_chatgpt_device_code()` on a daemon thread; `auth.json` persisted
  under a per-user `CODEX_HOME` on success (`codex_auth.py:79-143`).
- **Durable copy (hosted):** `VaultCodexCredentialStore` stores the **entire
  auth.json text** as a vault "key" under the reserved provider slot
  `codex_account` in the **same `EnvelopeKeyVault`** — so it is envelope-encrypted
  at rest, tenant-keyed by raw uid (`codex_auth.py:40-64`). Wired only when the
  vault exists; else `None` and the local file is the durable copy
  (`api.py:95-103`).
- **Local on-disk copy:** per-user `CODEX_HOME` at
  `<_DATA_DIR>/codex-account-auth/users/<safe(uid)>/auth.json`, dir `chmod 0700`,
  file `chmod 0600` (`codex_auth.py:165-169, 73-76, 205-208`).
- **Per-turn ephemeral `CODEX_HOME`:**
  `<state_dir>/users/<uid>/sessions/<sid>/threads/<tid>/auth.json`; the account
  home's auth.json is copied *in* before the turn (`_sync_auth_file`,
  `codex_engine.py:554-566, 654-662`) and copied *back out* after the turn since
  Codex may have refreshed the token (`_sync_auth_back`, `codex_engine.py:636-652`).
- **Restore/persist lifecycle:** durable store is source of truth —
  `ensure_local` restores durable → local each turn (`codex_auth.py:186-215`);
  `persist` writes local → durable **only when the content hash changed**, to avoid
  a non-refreshing turn clobbering another instance's refresh (`codex_auth.py:217-232`).
- **Turn wiring:** `account_home_for` resolves the staged home per turn; account
  auth wins over BYOK when present (`api.py:105-145`, `codex_runtime.py:226-247,
  353-355`). `cli_auth_credentials_store="file"` is hardcoded in the SDK config
  overrides (`codex_engine.py:616`).

---

## (B) Maturity + security — ranked concrete risks

**Logs:** no secret logging found — `[CODEX-TIMING]`/`[CODEX]` lines carry ids,
model, state only (`codex_runtime.py`, `codex_engine.py`). Env scrubbing is
deliberate and good: the Codex subprocess gets an allowlist of settings keys,
never provider keys (`_SETTINGS_PASSTHROUGH`, `codex_engine.py:34-43, 664-681`).

- **R1 (High) — Refresh-token rotation race across instances/warm workers.**
  `auth.json` holds a refresh token Codex rotates (~8 days, or per-use if
  rotating). Warm workers are keyed by `(session_id, thread_id, user_id)`
  (`codex_engine.py:326-327`); two Cloud Run instances can each restore the same
  durable blob, refresh independently, and persist last-writer-wins. The
  `persist` hash guard (`codex_auth.py:229`) only skips *unchanged* content — it
  does **not** serialize two *different* concurrent refreshes. OpenAI:
  *"Never share the same file across concurrent jobs or multiple machines."*
  Failure: a user's ChatGPT session silently breaks; they must reconnect.
  Fix: single-flight/lease per uid around refresh+persist.
- **R2 (High/structural) — Plaintext credential on instance disk.** The local
  home (`codex_auth.py:206`) and per-turn home (`codex_engine.py:566, 649`) hold
  **plaintext** auth.json (chmod 600, but still on disk for the turn/instance
  lifetime). Invariant 9 says nothing durable on disk; an instance compromise or
  disk snapshot leaks plaintext ChatGPT tokens for any user who had a turn there.
  BYOK api keys are *never* written to disk (decrypted into request scope only),
  so this is strictly worse for account-auth. Fix: stage on tmpfs; wipe after the
  turn.
- **R3 (Medium) — Single KEK, total blast radius.** One KMS key (or one
  SHA-256 master) wraps every tenant's DEK. A DB-only leak is inert (DEKs are
  wrapped — good), but KEK/master compromise decrypts everything. No per-tenant
  KEK, no rotation path beyond the unused `"v":1` blob field
  (`llm_keys.py:290`). The self-host master path derives a 256-bit key from an
  arbitrary-entropy string (`_derive_master_key`, `llm_keys.py:459-463`) — weak
  if the secret is weak.
- **R4 (Medium) — Account token handled slightly *less* carefully than API
  keys in one axis:** it is the only credential written to disk in plaintext, and
  the *whole* auth.json (access + refresh + id + account id) is stored vs a bare
  api key. At-rest parity is fine (same encrypted vault); the asymmetry is the
  disk staging (see R2).
- **R5 (Low) — `_safe_component(uid)` collision on the LOCAL home.** Two
  distinct raw uids that sanitize to the same string share a local `auth_home`
  path (`codex_auth.py:67-70, 165`). The durable store uses the *raw* uid so
  there is no cross-tenant DB mix, but concurrent turns from colliding uids could
  race on the local file. WorkOS ids are safe-charset so practically unreachable,
  but it is a latent invariant-8 sharp edge.
- **R6 (Low) — No proactive token-validity check.** `is_connected` checks only
  file/blob existence (`codex_auth.py:175-184`); an expired/revoked refresh token
  surfaces as a failed turn rather than a "reconnect" CTA. Honest-ish, worse UX.
- **R7 (Low) — Broad `suppress(Exception)` around load/save**
  (`codex_auth.py:200-201, 224`). A KMS outage or decrypt failure degrades
  silently to "not connected"/BYOK fallback — acceptable for availability, but a
  KMS outage looks like "logged out."
- **R8 (Low, soft-guard) — `codex_account` slot is protected only by absence
  from `VALID_PROVIDERS`.** `/api/keys` validates against that list
  (`api.py:932`, `llm_keys.py:456`), so today the account blob can't be read via
  the BYOK endpoints — but it lives in the same table keyed by the same uid; a
  future endpoint that forgets the allowlist would expose it. Consider a separate
  namespace/table.

---

## (C) Could we store it in the user's browser instead? — answer + recommendation

**No — not as a replacement, given how the SDK actually authenticates.** The
Codex SDK runs as a **server-side subprocess** we spawn (`AsyncCodex` enters a
context that starts an app-server + the bound MCP child, then `login_api_key` /
account auth from `CODEX_HOME` on disk — `codex_engine.py:337-382`). The
credential **must be present server-side at turn time**, and pre-warm spawns the
worker and logs in *before the user sends a message* (`prewarm`,
`codex_runtime.py:130-185`). A browser-held token sent per turn would:

- **Break pre-warm** (no credential at spawn → the ~8.5s TTFT rebuild the
  warm-keep work exists to eliminate returns).
- **Break headless/offline/background** runs and any finalization not driven by
  a live browser.
- **Not remove server-side exposure:** the token still has to reach the
  subprocess every turn, so it lands on our server anyway — while *adding* per-turn
  transit exposure and putting a long-lived, XSS-reachable token in the browser
  (localStorage/JS is a classic exfil target). Net security is arguably **worse**.

What browser storage *buys*: a smaller at-rest blast radius (we no longer hold
the long-lived refresh token) and user "ownership." Real but modest — and it is
exactly the refresh-token rotation semantics (R1) that break when the client
holds the credential.

**Recommendation: keep the credential server-side in the encrypted vault (as
today) — it is the correct model for a server-side-subprocess SDK.** Reduce
blast radius on the server rather than moving to the browser:
1. **Single-flight/lease per uid** around refresh+persist to kill R1.
2. **Ephemeral (tmpfs) staging** of the plaintext auth.json, wiped after the
   turn, so plaintext is not durable on disk (R2).
3. **KEK rotation** wired to the existing `"v"` blob version (R3).
The browser can hold nothing but a session cookie; the user's existing
`DELETE /api/codex/auth` disconnect (`api.py:991-995`) already gives them
control. Middle paths (short-lived server session token + client-held long-lived
credential, OS keychain) don't fit: the subprocess needs the *real* long-lived
credential on disk at spawn, and there is no per-user OS keychain on a shared
Cloud Run instance.

---

## (D) How we compare to the official docs / standard practice

- **Storage model:** we mirror the documented `CODEX_HOME/auth.json` +
  `cli_auth_credentials_store="file"` exactly (`codex_engine.py:616`) — per-user
  CODEX_HOME, file store. Standard.
- **Refresh:** we rely on Codex's automatic refresh and sync the rotated
  auth.json back (`codex_engine.py:636-652`, `persist`), which is precisely
  OpenAI's CI/CD guidance: *"Codex already knows how to refresh a ChatGPT-managed
  session… persist the updated file for subsequent runs."* Good.
- **Deviation 1 (the big one):** OpenAI says *"never share the same file across
  concurrent jobs or multiple machines."* Our hosted design **intentionally
  shares** one durable blob across all instances (the whole point of
  `VaultCodexCredentialStore`) for twelve-factor durability — a knowing tradeoff.
  The missing piece is the concurrency control OpenAI's warning implies (R1).
- **Deviation 2:** OpenAI offers `keyring` (OS credential store) as a
  more-secure alternative to the plaintext file; we hardcode `"file"`. On a
  shared server keyring is largely moot, and our vault gives at-rest encryption a
  plain CLI file wouldn't — so the *DB* copy is arguably better than the
  documented default. The on-disk *staging* is still plaintext (keyring wouldn't
  help across instances anyway) — see R2.
- **Deviation 3:** OpenAI recommends **API keys as the primary method** for
  servers/automation; account auth is "advanced." We support both and correctly
  prefer account auth when present, BYOK otherwise (`codex_runtime.py:226-247`).
  Fine and honest.
- **Envelope encryption:** our DEK/KEK split with Cloud KMS is textbook
  GCP/AWS practice — above average for the space.

**Specific improvements (priority order):**
1. Single-flight/lease per uid on refresh+persist (R1).
2. tmpfs staging + post-turn wipe of plaintext auth.json (R2).
3. KEK rotation via the existing blob version field (R3).
4. Proactive token-validity → reconnect CTA instead of fail-at-turn (R6).
5. Harden the self-host master key (require a base64 32-byte key / min entropy,
   not `SHA-256(anything)`) or document the requirement loudly (R3).
6. Give `codex_account` its own namespace/table so a future `/api/keys` bug can
   never enumerate it (R8).

---

### Sources
- Authentication — Codex (OpenAI Developers): https://developers.openai.com/codex/auth
- Maintain Codex account auth in CI/CD (advanced): https://developers.openai.com/codex/auth/ci-cd-auth
- Configuration Reference (`cli_auth_credentials_store`): https://developers.openai.com/codex/config-reference
- CLI reference (`codex login`, `--with-access-token`): https://developers.openai.com/codex/cli/reference
