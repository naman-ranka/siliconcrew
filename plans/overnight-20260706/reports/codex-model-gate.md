# Implement #1 — honest Codex model picker under account auth

**Status:** DONE (code + tests + gates). One live post-deploy verification
remains (below). Builds on the exploration in
`codex-account-models.md` (RESOLVED), which established the fix must gate on
the SDK's live `model/list`, NOT on `CODEX_CATALOG` membership.

## The bug

`src/agents/codex/codex_engine.py` `_thread_kwargs`:

```py
effective_model = turn.model_name if turn.api_key else None
```

Under **account** auth (`turn.api_key is None`) the model was always omitted,
so the `CodexModelPicker` was decorative — every pick fell back to the account
default. It couldn't naively pass the id either: an id the account rejects
returns 0 tokens silently. And the backlog's original "pass it if it's in
`CODEX_CATALOG`" idea is WRONG — `CODEX_DEFAULT_MODEL` (`gpt-5.3-codex`) is not
account-valid on the tested plan, so catalog-gating reintroduces the 0-token
bug for the default pick.

## The fix

Gate the picked id on the account's own live model list.

- New `CodexEngine._fetch_allowed_models(codex, turn)`
  (`src/agents/codex/codex_engine.py`): under **account** auth only, calls the
  SDK's `models()` (the `model/list` RPC) and returns the frozenset of
  non-hidden ids. Returns `None` for BYOK (nothing to gate) and on ANY error
  or empty result (honest degradation → caller omits). Defensive parsing:
  accepts a bare list or an object/dict wrapping `.models`/`.data`; skips
  `hidden` items; reads `id` (falls back to `model`).
- New `CodexEngine._effective_model(turn, allowed_models)`: BYOK → picked id
  verbatim; account auth → picked id only if in `allowed_models`, else `None`
  (omit → account default). `_thread_kwargs` now delegates to it.
- **Cached per worker.** `_fetch_allowed_models` runs once in `spawn_worker`
  (right after login) and the result is stored on
  `WarmWorker.allowed_models` (`src/agents/codex/codex_warm.py`). `stream_turn`
  passes `worker.allowed_models` to `_thread_kwargs` on every turn, so the RPC
  is not repeated per turn. The account is fixed per worker (auth material is
  already in the worker key + fingerprint), so per-worker caching is the
  natural, correctly-scoped cache. The one extra RPC lands at cold spawn only,
  amortized across the whole warm session.

One sentence: *under account auth we pass the picked model only when the
account's own `model/list` says it's valid, caching that list per worker;
otherwise we omit it and let Codex use the account default.*

## Tests — `tests/test_codex_model_gate.py` (fake SDK, no live creds)

Fake SDK whose `models()` returns `{gpt-5.5, gpt-5.4, gpt-5.4-mini}` (the
exploration's live set; note `gpt-5.3-codex` is absent). Asserts the model
kwarg actually reaching `thread.turn` / `thread_start`:

- (a) `test_account_auth_passes_valid_picked_id` — `gpt-5.4` passes under
  account auth. **Proven to FAIL on pre-fix code** (see below).
- (b) `test_account_auth_omits_invalid_picked_id` — `gpt-5.3-codex` (the
  default, not account-valid) is omitted; turn still completes.
- (b') `test_account_auth_omits_hidden_model` — a `hidden=True` id is omitted.
- (c) `test_account_auth_models_failure_omits_safely` — `models()` raising
  omits and the turn still reaches `done` (never 0-token / never breaks).
- (c') `test_account_auth_empty_model_list_omits` — empty list omits.
- (d) `test_byok_passes_model_unchanged` — BYOK passes `gpt-5.3-codex`
  verbatim and never calls `models()` (`models_calls == 0`).
- (e) `test_model_list_cached_across_turns` — with the warm pool, one spawn,
  `models_calls == 1` across two turns, and both turns pass `gpt-5.4`.

### Pre-fix proof

Stashed the two source edits and ran the headline tests against the old
engine:

```
FAILED tests/test_codex_model_gate.py::test_account_auth_passes_valid_picked_id
FAILED tests/test_codex_model_gate.py::test_model_list_cached_across_turns
  assert 0 == 1  (models_calls)   # old code never queried model/list
```

Old code left `model` out of `turn_kwargs` under account auth and never called
`models()` — exactly the decorative-picker bug. Both pass on the fix.

## Gates

- `python -m pytest tests/ -q --ignore=tests/test_identity_migration.py
  --ignore=tests/test_mcp.py --ignore=tests/test_mcp_remote_auth.py`:
  **11 failed, 815 passed** with the fix vs **11 failed, 808 passed** on the
  clean tree (same 11 env-gap failures: congestion_summary, lint_engines,
  llm_factory, orfs_job_entrypoint, perf_read_no_sync, sby_engine,
  workspace_incremental_sync ×2, xls_engine ×2 — all Windows/dep gaps
  unrelated to Codex). **Zero new failures**; the +7 are the new tests.
- `tests/test_codex_*.py` explicitly: 48 passed.
- Fixtures restored (`git checkout -- tests/fixtures/ test_sby_output.txt`).

## Remaining verification (owner / live, one turn)

The explorer listed the account's models via `model/list` but did NOT run a
full account-auth turn on a non-default id, and the fake-SDK tests can't
exercise the real beta `model/list` surface. So the one thing not provable
here: after deploy, in the deployed Codex tab under a connected ChatGPT
account, pick a non-default account-valid id (e.g. `gpt-5.4-mini`) and confirm
the turn returns **nonzero** usage tokens and the transcript attributes the
picked model. That single live turn is the only open item; the valid-id set,
the safe gate, and the caching are all settled here.

## Notes / out of scope

- Reconciling the picker itself (surfacing `model/list` in `CODEX_CATALOG`,
  changing the default off the non-account-valid `gpt-5.3-codex`) lives in
  `src/model_catalog.py` and was explicitly fenced out of this task — left
  as-is. The runtime gate makes the current picker honest regardless.
- BYOK behavior is byte-for-byte unchanged.
