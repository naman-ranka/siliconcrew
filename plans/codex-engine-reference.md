# Codex Engine — Reference Implementation Capture

A faithful, line-level capture of the **working** Codex integration on branch
`codex/codex-runtime-adapter` (commit `f6f3f50` + its uncommitted WIP), read
end-to-end. Phase 2b reimplements this against our removable-extension design
(plans/codex-runtime-extension.md) — this doc is the written contract so we build
against a spec, not memory.

**Status of confidence:** every mechanic below was line-read and is understood.
The ONE part that cannot be verified without live OpenAI creds + network is the
`openai_codex` SDK event/object surface (§3) — the SDK is beta (`0.1.0b3`), so
those names are taken on the reference author's authority and must be confirmed
in a live Phase 2b bring-up.

---

## 1. Execution model (how a Codex turn actually runs)

A Codex thread is driven by the **OpenAI Codex SDK** running as a subprocess
"app-server", NOT by our LangGraph agent. It reaches SiliconCrew's tools only
over **MCP** — our own `mcp_server.py` launched in a locked-down "bound-session"
mode. So: different brain, same workspace, tools over a wire.

Per-turn flow (`CodexRuntimeAdapter.stream_turn`):

1. `check_available()` — gated by `enabled` (env `ENABLE_CODEX_RUNTIME=1`) + lazy
   `import openai_codex`. Either failure → `RuntimeUnavailable` (a structured,
   actionable error, never a 500).
2. `prepare_paths(turn)`:
   - Per-thread `CODEX_HOME` at `<state_dir>/users/<uid>/sessions/<sid>/threads/<tid>`
     (each component sanitized, dir chmod 0700).
   - A **separate** `CODEX_SQLITE_HOME` under a *local, non-FUSE* dir
     (`/app/codex-sqlite/...`) — Codex's SQLite uses WAL/mmap which breaks on
     FUSE/VirtioFS mounts. **(WIP band-aid — see §7; we supersede it.)**
   - Writes `config.toml` (§2); if `codex_account_home` is set, copies its
     `auth.json` into `CODEX_HOME` (chmod 0600).
3. `_sdk_config()` — builds `openai_codex.CodexConfig(cwd, env, client_name=
   "siliconcrew_workbench", ...)`. **Env-key scrubbing (security):** `ANTHROPIC_API_KEY`,
   `GOOGLE_API_KEY`, `OPENAI_API_KEY` are set to `""` in the subprocess env unless
   a BYOK key is supplied — the external Codex agent must never see the server's
   other credentials. `CODEX_HOME`, `CODEX_SQLITE_HOME`, `RTL_WORKSPACE`,
   `RTL_DATA_DIR` are passed through.
4. `async with sdk_factory(config=config) as codex:` — `sdk_factory` defaults to
   `openai_codex.AsyncCodex` and is **injectable for tests** (the fake-SDK seam).
   - If `turn.api_key` → `await codex.login_api_key(api_key)`.
   - `thread_start(base_instructions=system_prompt, config=..., **kwargs)` OR, if
     `turn.external_thread_id` present, `thread_resume(external_thread_id, **kwargs)`
     **with a fallback to `thread_start`** on any resume exception.
   - kwargs (None-filtered): `model`, `cwd=workspace`, `sandbox`, `approval_mode`,
     `service_tier=tier`.
   - Emit `RuntimeEvent(type="start", external_thread_id=<thread.id>)`.
   - `turn_handle = await thread.turn(message, **turn_kwargs)`, then stream
     (§3) → yield events.
5. Any exception (except `RuntimeUnavailable`) is wrapped as
   `RuntimeUnavailable("codex", ...)` so the WS layer renders it cleanly.

### Account-vs-BYOK model rule (real footgun)
`effective_model = turn.model_name if turn.api_key else None`. With ChatGPT
**account** auth (no API key), the model name is omitted so Codex uses the
account's subscribed default — **passing an unrecognized model name silently
returns zero tokens.** Likewise a BYOK key set alongside account auth silently
zeroes tokens, so when account auth is present the api layer forces `api_key=None`.

---

## 2. `config.toml` (generated per thread) — the MCP wiring

`_write_config` writes a TOML registering our MCP server as the Codex agent's
tool source:

```toml
cli_auth_credentials_store = "file"
[features]
enable_mcp_apps = true
[mcp_servers.siliconcrew]
command = "<python_exe>"
args = ["<repo>/mcp_server.py", "--transport", "stdio", "--codex-tools",
        "--bound-session", "<session_id>"]
cwd = "<repo_root>"
enabled = true
required = true
startup_timeout_sec = 20
tool_timeout_sec = 300
disabled_tools = ["create_session_tool", "list_sessions_tool",
                  "set_active_session", "delete_session_tool"]
default_tools_approval_mode = "approve"
[mcp_servers.siliconcrew.env]
RTL_WORKSPACE = "<workspace_base>"
RTL_DATA_DIR  = "<data_dir>"
SILICONCREW_MCP_TOKEN = "<token>"   # if present
```

`config.toml` is chmod 0600. The MCP bearer token flows from `turn.mcp_token`
(or `CODEX_MCP_BEARER_TOKEN` / `SILICONCREW_MCP_TOKEN` env).

---

## 3. SDK event surface → `RuntimeEvent` (THE unverifiable contract)

`_stream_sdk_events(turn_handle)` iterates `turn_handle.stream()`; each event has
`.method` and a payload (`.payload` or `.params`). Mapping:

| SDK `method`                    | Extract                                            | Emit |
|---|---|---|
| contains `"error"`              | `payload.error.message` / `payload.message`        | raise `RuntimeUnavailable` |
| `item/agentMessage/delta`       | `payload.delta` (stringified)                      | `text` (delta; sets `emitted_text_delta`) |
| `thread/tokenUsage/updated`     | `token_usage.last.{input,output}_tokens`           | `usage` |
| `item/started`                  | item type ∈ {mcptoolcall, dynamictoolcall, commandexecution} → `{id,name,args}` | `tool_call` |
| `item/completed` (agentMessage) | `item.text`                                        | (collected as fallback text) |
| `item/completed` (tool item)    | `{tool_call_id, status, content}`                  | `tool_result` |
| `turn/completed`                | if no deltas were emitted, flush last collected text | `text` then `done` (with usage) |

Item-type helpers:
- `_tool_from_item`: `commandexecution` → name `"command"`, args `{"command": ...}`;
  else name = `item.tool`, args = `item.arguments` (dict).
- `_tool_result_from_item`: `commandexecution` status from `exit_code` (0/None→success),
  content from `aggregated_output`; else from `item.result.content` / `item.error.message`,
  status normalized (`completed/success`→`success`, `failed`/error→`error`).
- `_usage_from_payload`: `token_usage.last` with snake_case + camelCase fallbacks.

**Object shapes here (methods, item types, field names) are the beta-SDK surface
and the only thing not verifiable without a live run.** Everything else is
deterministic and unit-testable by feeding a fake `turn_handle.stream()`.

### `RuntimeEvent` / `RuntimeTurn` (reference dataclasses)
- `RuntimeEvent(type, content, tool, tool_call_id, status, usage:RuntimeUsage,
  external_thread_id)` — type ∈ start/text/tool_call/tool_result/ping/usage/done.
- `RuntimeTurn(session_id, thread_id, message, workspace, user_id, model_name,
  api_key, external_thread_id, system_prompt, tier, codex_home,
  codex_account_home, sandbox, mcp_config_path, mcp_token)`.

> Note: our Phase 1 presentation contract uses `text_delta` for streaming +
> `text` for the authoritative segment; the reference collapses both to `text`
> with cumulative content. When we reimplement, translate the SDK's `delta` into
> our `text_delta` and the final into `text` to match our shared renderer.

---

## 4. Account auth (`codex_account_auth.py`)

`CodexAccountAuthManager(state_dir)`:
- `start_device_auth(user_id)` — spawns `codex login --device-auth` (command from
  `CODEX_LOGIN_COMMAND`, default `codex`) as a subprocess with `CODEX_HOME` /
  `CODEX_SQLITE_HOME` = per-user auth home (`<state_dir>/codex-account-auth/users/<uid>`);
  **scrubs `OPENAI/ANTHROPIC/GOOGLE_API_KEY` + `CODEX_ACCESS_TOKEN` from its env**.
  A daemon thread reads stdout; `_parse_line` extracts login URL + user code from
  JSON (`verification_uri_complete`/`user_code`/…) or regex.
- `status(user_id)` → `{connected, in_progress, login_url, user_code, message, …}`.
  `connected` ⇔ `auth.json` exists and is non-empty.
- `cancel` (terminate process), `disconnect` (cancel + `rmtree` the auth home).

---

## 5. Bound-session MCP (`mcp_server.py`)

`RTLDesignMCPServer(codex_tools=bool, bound_session=str|None)`. When
`bound_session` is set (CLI `--codex-tools --bound-session <sid>`):
- On init, **verifies the identity owns the bound session** (else refuses to
  start); forces `current_session = bound_session`.
- **Session-management tools blocked**: `create/list/delete_session`,
  `set_active_session` return "disabled; bound to '<sid>'".
- **Cross-session access refused**: any tool given a `session_id != bound_session`
  is rejected (path-traversal / escape prevention); listings scope to the bound
  session only. Tool-visibility count adjusts (2 vs 6 session tools).

This is defense-in-depth: `config.toml` also lists these in `disabled_tools`, but
the server enforces isolation itself regardless of client config.

---

## 6. api glue (endpoints, dispatch, persistence)

- Globals: `_CODEX_AUTH_MANAGER = CodexAccountAuthManager(_DATA_DIR)`.
- Endpoints: `GET /api/codex/auth` (status), `POST /api/codex/auth/device/start`,
  `POST /api/codex/auth/device/cancel`, `DELETE /api/codex/auth` (disconnect) —
  all `require_signed_in`; responses include `runtime_enabled` from
  `ENABLE_CODEX_RUNTIME`.
- Helpers: `_codex_model_for_thread`, `_codex_account_auth_allowed`,
  `_codex_account_home_for_user` (with a host-mounted `~/.codex` read-only
  fallback — a hosted convenience, not core).
- Thread create/patch accept `runtime` + `external_thread_id`
  (`set_thread_runtime_metadata`).
- **WS dispatch** (`thread_row["runtime"] == "codex"`):
  1. `append_message(thread_id, "user", message)` **before** dispatch.
  2. Build `CodexRuntimeAdapter(enabled=ENABLE_CODEX_RUNTIME,
     state_dir="/app/codex-state", local_sqlite_dir="/app/codex-sqlite")`.
  3. Resolve model + key: BYOK via `_LLM_KEY_PROVIDER.resolve` OR account auth
     (`_codex_account_auth_allowed`); if account home present → `api_key=None`.
     No usable key/auth → structured error.
  4. `async for event in adapter.stream_turn(RuntimeTurn(...))`:
     - `start` → capture `pending_external_thread_id`, send `{"type":"start"}`.
     - `text` → accumulate `assistant_content`, send cumulative `{"type":"text",content}`.
     - `tool_call` → track pending, `log_tool_call(source="codex_ws")`, send frame.
     - `tool_result` → `log_tool_result`, send frame.
     - `usage`/`done` → accumulate tokens; `done` sets `codex_turn_completed`.
  5. **Persist once** after the loop: `append_message("assistant",
     assistant_content, tool_metadata={tool_calls, tool_results})`.
  6. **Persist `external_thread_id` only if the turn completed AND it changed** —
     a failed turn never corrupts resume state.
- History reads: for codex threads, `list_messages` (normalized) replaces the
  checkpointer-based history read.

---

## 7. What we deliberately change / do NOT copy

- **No shared `ChatRuntimeAdapter` protocol / `runtime` column entanglement.** We
  use the Phase 1 registry + the shell-level `runtime` marker (Phase 2a) and keep
  Codex in its own removable module.
- **Transcript store is codex-owned** (`codex_messages` + a tiny `codex_threads`
  map for `external_thread_id`), FK to `chat_threads`; cleanup on thread delete
  via a registry `notify_thread_deleted` hook (FK cascade won't fire — shared
  SQLite runs `foreign_keys` OFF), NOT via codex-specific DELETEs in shared code.
- **Persistence is dual-engine** (sqlite self-host / Postgres hosted) so Codex
  history is durable in hosted mode — same reason the langchain checkpointer moved
  to Postgres. This **replaces** the WIP FUSE/`journal_mode=DELETE` SQLite band-aid.
- **Drop WIP debug leftovers**: `/tmp/mcp_server_exec.log`, stderr-to-file redirect.
- **Event mapping** targets our presentation contract (`text_delta` + `text`),
  not the reference's cumulative-`text`-only shape.
- **Flag name**: reference uses `ENABLE_CODEX_RUNTIME`; we align to a
  `CODEX_ENABLED` setting in settings.py (final name TBD, one source of truth).

---

## 8. The irreducible unknown (Phase 2b live bring-up)

Only §3 (the beta `openai_codex` SDK event/object surface) and the real
subprocess/bound-MCP/device-auth round trips need live OpenAI creds + network to
confirm. Build everything against a fake `sdk_factory` + fake `turn_handle.stream()`;
schedule one credentialed verification pass to confirm the SDK surface and the
end-to-end subprocess path before claiming it works.
