# Explore: account-valid Codex model ids (backlog #1)

**Status:** RESOLVED (live, authoritative). The Codex SDK exposes a
`model/list` call, and it was run against a real ChatGPT **account**-auth
(`auth_mode="chatgpt"`) session. This is a stronger source of truth than the
deployed UI (which, as noted below, can't currently prove model-passing).

---

## (a) How `model_name` flows: account vs key auth

`src/agents/codex/codex_engine.py`:

- `CodexTurn.model_name` (:89) is the picked id. It reaches the SDK only via
  `_thread_kwargs` (:379):
  ```py
  # :380-381
  # Account auth: omit model (an unknown name silently returns 0 tokens).
  effective_model = turn.model_name if turn.api_key else None
  ```
  The dict is then filtered to drop `None` values (:383-386), so under
  account auth (`turn.api_key is None`) **no `model` kwarg is passed** to
  `thread_start` / `thread_resume` (:366-370) — Codex uses the account
  default. Under BYOK (`turn.api_key` set), the picked id passes through
  verbatim.
- `service_tier`, `sandbox`, `approval_mode` also flow as thread_start
  PARAMS (not config.toml) — see `_config_overrides` docstring (:502-507).
- Auth itself: BYOK calls `codex.login_api_key(turn.api_key)` (:348-349);
  account auth relies on `CODEX_HOME/auth.json` (synced per-turn, :500) or
  `CODEX_ACCESS_TOKEN` env (:607-608). No model is implied by either.
- The picker id is curated in `src/model_catalog.py`:
  `CODEX_DEFAULT_MODEL = "gpt-5.3-codex"`; `CODEX_CATALOG` =
  `gpt-5.3-codex`, `gpt-5.5`, `gpt-5.4-mini` (:81-90).

**Net:** the `CodexModelPicker` is decorative under account auth today —
exactly the invariant-4 dishonesty #1 flags.

## (b) Account-valid model ids — how verified

The SDK ships a models-list RPC:
`openai_codex.Codex().models(include_hidden=...)` →
`client.model_list` → JSON-RPC `model/list` (SDK
`client.py:494`, `api.py:282`, `async_client.py:222`). The `Model` schema
(`generated/v2_all.py:6030`) has `id`, `model`, `is_default`, `hidden`,
`supported_reasoning_efforts`.

Ran it locally against the connected account
(`CODEX_HOME=~/.codex`, `auth_mode="chatgpt"`, no `OPENAI_API_KEY` — i.e.
the account-auth path, refreshed 2026-07-08):

| id            | default | hidden | account-valid |
|---------------|---------|--------|---------------|
| `gpt-5.5`     | yes     | no     | ✅ (this account's default) |
| `gpt-5.4`     | no      | no     | ✅            |
| `gpt-5.4-mini`| no      | no     | ✅            |
| `codex-auto-review` | no | **yes** | internal only — not user-selectable |

**Verification method = the SDK's own `model/list` (what Codex itself uses
to enumerate usable models), not docs or guesswork.**

Cross-check vs `CODEX_CATALOG`:
- `gpt-5.5` — ✅ account-valid.
- `gpt-5.4-mini` — ✅ account-valid.
- **`gpt-5.3-codex` — ❌ NOT in the account list** (not visible, not
  hidden). And it is `CODEX_DEFAULT_MODEL`. Under account auth this id would
  hit the "unknown name → 0 tokens" trap the code guards against. So a naive
  "pass it if it's in CODEX_CATALOG" rule would REINTRODUCE the bug for the
  default pick.
- `gpt-5.4` is account-valid but absent from CODEX_CATALOG.

## Honest limits

- The live account tested is `nyeshwan@asu.edu`, `chatgpt_plan_type =
  "education"` — a genuine chatgpt-mode account, but **not necessarily the
  same account** as the deployed staging test user
  (rockstarme.the5@gmail.com). The *exact id set can differ per
  account/plan tier*; the **method** (query `model/list`) is what
  generalizes. I did not drive the deployed Codex tab because, as the task
  notes, the current code won't pass a picked id under account auth, so the
  UI can't prove "id X works" — the SDK call is the authoritative source
  and made the browser path unnecessary.
- I listed models but did NOT run a full account-auth turn with a
  non-default model, so I have not empirically produced a nonzero token
  count for, say, `gpt-5.4-mini`. `model/list` membership is strong
  evidence a model is usable, but the end-to-end token proof needs the
  code-change-then-deploy cycle in (c).

## (c) Recommendation for implementing #1

**Gate on `model/list`, not on `CODEX_CATALOG` membership.** This is the
fundamental, account-honest, self-healing fix and it avoids the trap that
the naive catalog-intersection rule falls into (`gpt-5.3-codex`).

1. In `_thread_kwargs` (or once at worker bring-up, cached), under account
   auth call `codex.models()` and build the set of non-hidden ids. Pass
   `turn.model_name` only if it is in that set; otherwise omit (keep today's
   safe "account default" behavior). Under BYOK, keep passing verbatim.
   - Cache the list per worker/account (it's stable within a session) so
     it's not re-fetched every turn; the call is lightweight (`Codex()` with
     just `CODEX_HOME`, no MCP config needed).
2. Optionally reconcile the picker: `CODEX_CATALOG`'s default
   `gpt-5.3-codex` is not account-valid on at least the education plan —
   consider surfacing `model/list` (intersected with pricing-known ids) in
   the Codex picker so account users don't see ids their account rejects,
   and pick a default that exists (`gpt-5.5`). Out of strict scope for #1
   but directly implied by the finding.

**Minimal live proof still owed (needs code change + deploy):** wire the
gate from step 1, deploy, then in the deployed Codex tab pick a non-default
account-valid id (e.g. `gpt-5.4-mini`) and confirm the turn returns nonzero
usage tokens and the transcript attributes the picked model. That single
turn is the only thing not determinable without a code-change-then-deploy
cycle; everything else (the valid-id set + the safe gate) is settled here.
