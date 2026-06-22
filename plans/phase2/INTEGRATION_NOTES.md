# Phase 2 → Phase 1 Integration Notes

Captured by the Phase 2 (deployed backend) agent for the merge with the parallel
Phase 1 (frontend + action-API) branch. Precise and factual. Read this before
reconciling.

Branch: `claude/focused-brahmagupta-utoxla`. Local/self-host behavior is
**bit-for-bit unchanged**: every cloud engine activates only via config, and the
tenancy seam is unscoped (`user_id=None`) unless `SILICONCREW_HOSTED=1`.

---

## 1. Shared files I changed (what + why)

These are the files Phase 1 most likely also touched. Conflicts to expect:

### `api.py` (REST + WebSocket) — **high conflict risk**
- **Imports added:** `Header, Depends` (from fastapi); `get_workspace_provider`;
  `Action, AuthError, Identity`; `auth as auth_engine`; `build_key_vault,
  VALID_PROVIDERS`; `get_settings`.
- **Module init added:** `_KEY_VAULT = build_key_vault(get_settings(), db_path=…/byok.db)`.
- **Auth dependencies added** (after CORS middleware): `get_identity`,
  `require_signed_in`, `_uid`, `_require_owned`, `verify_session_access`.
- **Every session/project endpoint** now takes `identity: Identity = Depends(...)`
  and passes `user_id=_uid(identity)` into `session_manager`. Mutating endpoints
  (`POST /api/sessions`, projects, delete/patch) use `Depends(require_signed_in)`.
- **New endpoints:** `POST /api/trial-session` (anonymous lint/sim path),
  `GET/PUT/DELETE /api/keys/{provider}` (BYOK).
- **All `/api/workspace/{session_id}/*` read endpoints** gained
  `_acl: Optional[str] = Depends(verify_session_access)` — ownership 404 guard.
  No body changes; only the signature gained the dependency.
- **WS handler `chat_websocket`:** authenticates via `?token=` query param →
  `auth_engine.authenticate(...)`; checks `session_manager.owns_session`; binds
  `SessionContext(session_id, workspace, user_id=uid, tier=identity.tier)`;
  resolves workspace via `get_workspace_provider().workspace_for(...)` and calls
  `provider.sync(...)` after each turn. `get_session_metadata` /
  `update_session_stats` inside the loop pass `user_id=uid`.
- **Lifespan startup** calls `apply_platform_wiring()` (the single wiring point).

> Phase 1's action endpoints (`POST /lint|simulate|synthesize`, etc.) are NOT in
> my diff — I only added auth/tenancy/BYOK. When merging, Phase 1's action
> handlers must adopt the same two-line pattern: take `identity = Depends(get_identity)`
> and run their tool call inside the request scope (see §3).

### `mcp_server.py` — medium conflict risk
- Imports `run_in_session`, `auth as auth_engine`, `Action/AuthError/authorize`.
- `__init__`: adds `self.identity = self._resolve_identity()`, calls
  `apply_platform_wiring()`, defines `_PROTECTED_TOOLS`, `_scoped_user_id()`.
- **Removed every `os.environ["RTL_WORKSPACE"] = …` mutation** (6 sites).
- Session-mgmt tools set `self.current_session` only; `create_session` /
  `ensure_session` pass `user_id=self._scoped_user_id()`; `set_active_session` /
  `inject_architect_prompt` use `owns_session(...)` instead of `os.path.exists`.
- Regular tool execution: `await run_in_session(active_session, tool_func.invoke,
  arguments, user_id=uid, tier=self.identity.tier)` — replaces the bare
  `run_in_executor(lambda: tool_func.invoke(...))` + env mutation. Protected
  tools gated via `authorize(self.identity, …)`.

### `src/utils/session_context.py` — low risk (additive)
- `SessionContext` gained two optional fields: `user_id: Optional[str] = None`
  (already existed as reserved), `tier: Optional[str] = None`. Frozen dataclass;
  positional `(session_id, workspace)` unchanged → backward compatible.

### `src/utils/session_manager.py` — medium risk (additive params)
- Every public method gained an **optional** `user_id=None`:
  `create_session`, `ensure_session`, `get_all_sessions`, `get_session_metadata`,
  `move_session_to_project`, `update_session_stats`, `delete_session`,
  `create_project`, `get_all_projects`, `get_project`, `delete_project`.
- New: `owns_session(session_id, user_id) -> bool`.
- `delete_session` raises `PermissionError` if `user_id` set and not owner.
- All delegate to `MetadataStore` (sqlite default, Postgres in hosted). With
  `user_id=None` the SQL is unscoped → identical to before.

### `src/tools/synthesis_manager.py` — medium risk (additive seams)
- `_EXECUTOR` default unchanged. Added `set_job_executor`/`_job_executor`,
  `set_quota_manager`/`_quota_identity`/`_reserve_synth_quota`/`_submit_with_quota_release`.
- `start_synthesis_job` + `retry_pd_job`: reserve quota first (return error
  envelope on cap hit), submit via `_submit_with_quota_release` (releases on
  completion). Both no-op when no quota manager installed (self-host).
- `config.mk` writers pin `NUM_CORES`; `run_meta` stamped with `provenance`.
- ORFS execution routed through `get_orfs_runner()` (was direct `run_docker`).

### `src/tools/wrappers.py` — low risk
- `get_workspace_path()` moved to `src/utils/workspace.py` (dependency-light);
  re-exported from wrappers. Behavior identical (context → `RTL_WORKSPACE` → default).

### `src/platform_engines/settings.py` — **the single wiring point** (coordinate)
- `PlatformSettings` + `get_settings()` (cached) + `reset_settings_cache()`.
- `apply_platform_wiring(force=False)` / `reset_wiring()`: installs the per-user
  job queue + shared quota manager in hosted mode; no-op in self-host. Call it
  once at startup. **Both branches must funnel engine wiring through here.**

---

## 2. `platform_engines` public surface + settings flags

### Public functions/classes Phase 1 may call
- `settings.get_settings() -> PlatformSettings`, `apply_platform_wiring()`,
  `reset_settings_cache()`, `reset_wiring()`.
- `auth.authenticate(token, *, settings=None, verifier=None, session_hint=None) -> Identity`,
  `auth.parse_bearer(header)`, `auth.scoped_user_id(identity, settings=None)`,
  `auth.require_action(identity, action)`, `auth.ensure_signed_in(identity)`,
  `auth.build_verifier(settings)`, `auth.LOCAL_IDENTITY`.
- `identity.Identity`, `identity.Action{LINT,SIMULATE,SYNTHESIZE,SAVE,MCP}`,
  `identity.authorize`, `identity.new_anonymous`, `identity.AuthError`,
  `identity.GoogleOAuthVerifier`.
- `request_scope.session_request_scope(...)`, `request_scope.run_in_session(...)` (§3).
- `workspace_provider.get_workspace_provider()` / `set_workspace_provider()`.
- `orfs_runner.get_orfs_runner()` / `set_orfs_runner()`; `OrfsRequest`,
  `OrfsResult`, `OrfsRunner`, `LocalDockerOrfsRunner`, `CloudJobOrfsRunner`,
  `RemoteOrfsRunner`, `JobExecution` (§4).
- `quotas.QuotaManager`, `build_quota_manager(settings)`, `QuotaExceeded`,
  `InMemoryQuotaStore`, `PostgresQuotaStore`.
- `llm_keys.build_key_vault(settings, db_path)`, `build_llm_key_provider(settings, vault)`,
  `EnvelopeKeyVault`, `VALID_PROVIDERS`, `LlmKey`.
- `metadata_store.build_metadata_store(db_path)`, `SqliteMetadataStore`,
  `PostgresMetadataStore`.
- `gcp_clients.GcpCloudRunJobClient`.
- `orfs_service.OrfsService`, `orfs_service.create_app(service, token)`.

### Settings flags (env vars) and what each switches
| Env var | Default | Switches |
|---|---|---|
| `SILICONCREW_HOSTED` | `0` | Master switch. Flips every engine default to cloud; enables auth scoping + quota wiring in `apply_platform_wiring`. |
| `ORFS_ENGINE` | `local_docker` (hosted: `cloud_job`) | `local_docker` \| `cloud_job` \| `remote` — where ORFS executes. |
| `WORKSPACE_ENGINE` | `local` (hosted: `cloud`) | `local` dir vs `cloud` (GCS staged to scratch). |
| `PERSISTENCE_ENGINE` | `sqlite` (hosted: `postgres`) | session/quota/BYOK metadata backend. |
| `LLM_KEY_ENGINE` | `env` (hosted: `byok`) | env keys vs BYOK+hosted-Gemini. |
| `GOOGLE_OAUTH_CLIENT_ID` | "" | OAuth audience; empty → no token verification (hosted token rejected as `auth_unconfigured`). |
| `DATABASE_URL` | "" | Cloud SQL DSN (Postgres engines). |
| `WORKSPACE_BUCKET`, `WORKSPACE_SCRATCH_DIR` | "", `/tmp/siliconcrew-scratch` | GCS bucket + local stage dir. |
| `ORFS_IMAGE`, `ORFS_CLOUD_RUN_JOB`, `GCP_PROJECT`, `GCP_REGION` | image `openroad/orfs:latest`, job `siliconcrew-orfs`, region `us-central1` | Cloud Run Job execution. |
| `ORFS_SERVICE_URL`, `ORFS_SERVICE_TOKEN` | "" | `RemoteOrfsRunner` target + bearer (with `ORFS_ENGINE=remote`). |
| `KMS_KEY_URI` | "" | Cloud KMS KEK for BYOK envelope encryption. |
| `SILICONCREW_MASTER_KEY` | "" | Self-host BYOK KEK when no KMS (sha256→32-byte key). |
| `HOSTED_GEMINI_KEY`, `HOSTED_GEMINI_MODEL` | "", `gemini-3-flash-preview` | Capped hosted free tier. |
| `ORFS_NUM_CORES` | `4` | Pinned `NUM_CORES` (P&R determinism). |
| `SILICONCREW_MCP_TOKEN` | "" | Bearer for remote MCP identity. |
| `RTL_WORKSPACE`, `RTL_DATA_DIR` | (pre-existing) | self-host workspace/db roots; read-only override (never mutated per request now). |

---

## 3. Request scoping — the most likely conflict with Phase 1's `run_scoped`

### What I built (richer; keep mine as the single mechanism)

`src/platform_engines/request_scope.py`:

```python
@contextmanager
def session_request_scope(session_id, user_id=None, provider=None, tier=None) -> Iterator[str]:
    # 1. provider = provider or get_workspace_provider()
    # 2. workspace = provider.workspace_for(session_id)        # local dir OR GCS->scratch
    # 3. with session_scope(SessionContext(session_id, workspace, user_id, tier)):
    #        yield workspace
    #    finally: provider.sync(session_id) if provider has sync()  # cloud writeback; local no-op

async def run_in_session(session_id, fn, *args, user_id=None, tier=None, provider=None, **kwargs):
    # enters session_request_scope INSIDE the worker thread (run_in_executor),
    # so the contextvar propagates across the thread boundary, then fn(*args).
```

Key properties (these are why mine should win):
1. **Binds the full identity** into the task-local `SessionContext`:
   `user_id` (tenant) **and** `tier` ("user"/"anonymous"). Synthesis quota
   enforcement reads `tier` from the context (`_quota_identity()`), so dropping
   it silently disables anonymous-synth blocking.
2. **Materializes the workspace via `WorkspaceProvider`** (not just a path):
   local = same `workspace/<id>` dir; cloud = downloads the session tarball into
   scratch and returns the POSIX path.
3. **Calls `provider.sync()` on exit** — persists the workspace back to object
   storage in hosted mode. A scope that forgets this loses all writes in cloud.
4. **`run_in_session` enters the scope inside the executor thread.** A bare
   `loop.run_in_executor(None, lambda: tool.invoke())` does NOT copy the
   contextvar; entering the scope in the worker is the correct fix. (Note:
   `asyncio.to_thread` and `langchain_core.runnables.config.run_in_executor` DO
   copy context — so wrapping the outer scope works there; bare executors do not.)

### Reconciliation recommendation

**Adopt `session_request_scope` / `run_in_session` as the one mechanism.** If
Phase 1 wrote a `run_scoped`/`with_session` that only sets the workspace
contextvar, replace its body with a call to `session_request_scope`. Phase 1
**must keep**, when wrapping action handlers:
- pass `user_id` (from `auth.scoped_user_id(identity)`) and `tier`
  (`identity.tier`) — not just `session_id`;
- let the provider resolve the workspace (don't hardcode `workspace/<id>`);
- preserve the `provider.sync()` on exit.

Sync handler pattern Phase 1 should use for REST action endpoints:
```python
@app.post("/api/workspace/{session_id}/lint")
async def lint(session_id, body, identity: Identity = Depends(get_identity)):
    uid = _require_owned(session_id, identity)          # 404 if not owner
    with session_request_scope(session_id, user_id=uid, tier=identity.tier):
        return run_linter_tool(...)                     # tools resolve workspace task-locally
```
(`get_identity`, `_require_owned`, `require_signed_in` already exist in `api.py`.)

For synth specifically, **do not** add a second quota gate in the handler — it's
already enforced inside `synthesis_manager.start_synthesis_job` / `retry_pd_job`
(reads tier/user from the context bound by the scope). The handler just needs the
scope + `require_signed_in`.

---

## 4. Shareable surface for Phase 1 (drive a real synth without this backend)

Phase 1 can run a real synth against a deployed ORFS service via the **remote
client**, importing only stdlib-dependent code.

**To import (today):** from `src/platform_engines/orfs_runner.py`
- `OrfsRequest(run_dir, command, volumes=[], timeout=3600, image=None, cwd=…, workspace_mount=…)`
- `OrfsResult(success, stdout, stderr, command, exit_code=None, backend=…)`
- `OrfsRunner` (Protocol: `.run(OrfsRequest) -> OrfsResult`)
- `RemoteOrfsRunner(service_url, token="", http=None, poll_initial, poll_max, clock, sleep)`

**Wire contract:** `deploy/ORFS_SERVICE.md` (POST `/v1/jobs` with a base64 gzip
tar of the run dir + `volumes`/`command`/`timeout`; GET `/v1/jobs/{id}`; GET
`/v1/jobs/{id}/artifacts`). An external client can speak it with stdlib `urllib`
+ `tarfile` — a no-import snippet is in that doc.

**Server side:** `orfs_service.OrfsService(runner, scratch_dir, object_store=None)`
+ `create_app(service, token)` (Starlette). The service wraps any `OrfsRunner`.

**Where it should live for both branches:** the interface + dataclasses +
`RemoteOrfsRunner` are stdlib-only and self-contained. Recommend extracting them
into a tiny shared package — proposal: `src/orfs_client/` (or a publishable
`siliconcrew-orfs-client`) exporting `OrfsRequest/OrfsResult/OrfsRunner/RemoteOrfsRunner`
and the tar helpers, which `platform_engines.orfs_runner` then re-exports for
backward compat. Until then, Phase 1 imports from `platform_engines.orfs_runner`.
(See §6 — I packaged a merge-safe `src/orfs_client/` in my own modules.)

---

## 5. Tested-with-fakes vs deploy-time-only

**Tested in CI now (stdlib + fakes, no cloud/Docker):**
- Tenant isolation (red-team), auth resolution + gating, MCP per-call isolation,
  quota enforcement + multi-instance semantics (shared store + PG `FOR UPDATE`
  SQL shape), BYOK envelope round-trip + persistence, `GcpCloudRunJobClient`
  poll/backoff/terminal/timeout (fake operation), `RemoteOrfsRunner` ↔
  `OrfsService` end-to-end (loopback, mock ORFS exec), provider parity,
  determinism/provenance, sqlite persistence contract.

**Deploy-time only (owner runs; code + IaC + runbook provided, no auto-spend):**
- Real Cloud Run Job execution (`RUN_REAL_CLOUD_RUN=1`), real ORFS run
  (`RUN_REAL_ORFS=1`), GCS workspace round-trip, Cloud SQL, Cloud KMS, live
  Google OAuth token verification, deploying the ORFS HTTP service.
- **Known follow-up:** hosted **read** endpoints (`/api/workspace/{id}/*`) serve
  from local disk; ownership is enforced, but staging the object-storage
  workspace to scratch for reads is not wired (writes/agent path are, via the WS
  handler's `provider.workspace_for` + `sync`). Phase 1's read endpoints inherit
  this — fine for self-host; for hosted reads, wrap them in `session_request_scope`
  too so the provider stages the workspace in.

---

## 6. Merge-safe hardening done in my own modules (this pass)
- `OrfsService`: in-memory job map now has TTL + cleanup (bounded growth) — see
  `orfs_service.py` (`job_ttl_seconds`, `_gc()`); behavior otherwise unchanged.
- Packaged the shareable client as `src/orfs_client/` (stdlib-only);
  `platform_engines.orfs_runner` re-exports from it for backward compatibility,
  so existing imports and Phase 1 both work.
