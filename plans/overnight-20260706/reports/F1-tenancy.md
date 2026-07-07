# F1 — MCP hosted tenancy leak (list_sessions + cross-tenant delete + shared active session)

**Status:** CONFIRMED in code. Severity: **HIGH → CRITICAL.** The reported symptom
(33 sessions leaked) is the *least* severe of three distinct defects on the same
surface. Two of them are cross-tenant **write/destroy**, not just a metadata read.

Investigated read-only against `mcp_server.py`, `src/utils/session_manager.py`,
`src/platform_engines/metadata_store.py`, `api.py`. I did **not** call any live MCP tools.

---

## Root cause 1 — `list_sessions_tool` ignores owner scope (the reported 33-session leak)

`mcp_server.py:722-723`:

```python
elif name == "list_sessions_tool":
    sessions = self.session_manager.get_all_sessions()   # <-- no user_id
```

`get_all_sessions(user_id=None)` (`session_manager.py:92-105`) →
`get_all_session_rows(user_id=None)`. Both stores treat `None` as "no tenant filter":

- Postgres: `metadata_store.py:649-652` → `SELECT * FROM session_metadata` (no WHERE).
- SQLite: `metadata_store.py:278-287` → same, WHERE omitted when `user_id is None`.

So on hosted the tool returns **every tenant's** session ids and metadata
(model, created_at, tokens) — exactly the 33 rows incl. `p1`, `asdads`,
`aes128_gds`, `Phone`, `codex_*`. The identity *is* available at this point
(`self._scoped_user_id()`), it is simply not passed.

**Proof this path is the anomaly, not the norm:** the RESOURCE surface right above
it does scope correctly. `_resource_sessions()` (`mcp_server.py:262-271`) passes
`user_id=self._scoped_user_id()` when `self._hosted`, and `read_resource`'s
`rtl://sessions` (`:358-382`) reuses it. Only the *tool* path regressed. Same bug,
lesser blast radius, in `list_sessions_tool`'s per-row `get_session_metadata(session_id)`
(`:730`, unscoped) — moot once the list itself is scoped.

The frontend Launcher shows only 2 sessions because the REST list endpoint
(`api.py`, owner-scoped via `require_signed_in` + `_owner_clause`) is a *different*
code path that is correct. This is a pure MCP-tool regression against invariant 8.

## Root cause 2 — `delete_session_tool` has NO ownership check (cross-tenant DESTRUCTION)

`mcp_server.py:771-780`:

```python
elif name == "delete_session_tool":
    session_id = arguments["session_id"]
    if session_id == self.current_session:
        return [... "Cannot delete active session ..."]
    self.session_manager.delete_session(session_id)      # <-- no user_id
```

`delete_session(user_id=None)` (`session_manager.py:211-220`) **skips its own guard**:

```python
if user_id is not None and not self.owns_session(session_id, user_id):
    raise PermissionError(...)          # user_id is None here → guard bypassed
...
shutil.rmtree(session_path)             # deletes ANY tenant's workspace dir
```

and the store delete (`metadata_store.py:688-704`) runs with an empty `_owner_clause`,
purging another tenant's `session_metadata`, `chat_threads`, and LangGraph
conversation checkpoints. The only guard (`== self.current_session`) does not apply to
a *foreign* session. Combined with root cause 1 (ids are freely enumerable), any
signed-in hosted user can **irreversibly delete any other user's session, workspace,
and chat history by id.** This is data loss, not just data exposure.

## Root cause 3 — `self.current_session` is a process global on the one shared server (cross-tenant READ/WRITE under concurrency)

`api.py:403-424` mounts **one** `RTLDesignMCPServer(codex_tools=True)` and runs a
**single** `mcp_server.server.run()` task multiplexing all hosted users
(stateless HTTP, `mcp_session_id=None`). `self.current_session` (`mcp_server.py:186`)
is one instance field. `call_tool` reads the workspace from it:

```python
active_session = self.current_session                              # :865
active_workspace = self.session_manager.get_workspace_path(active_session)  # :866
result = await run_in_session(active_session, tool_func.invoke, arguments, user_id=uid, ...)
```

Identity/auth is per-request (`_current_identity()` via request scope), but **workspace
selection is a global.** Interleaving: user A `set_active_session(A)`; user B
`set_active_session(B)` flips the shared field; A's next `write_file`/`read_file`/
`edit_file_tool` now targets **B's** workspace. So concurrent hosted users can read and
overwrite each other's files. `set_active_session` itself is ownership-checked
(`:746`), which is why A can only *set* its own — but B's set mutates the state A
reads. This is already recorded as **P0 #1 (CONFIRMED, DEFERRED)** in
`plans/phase2/REVIEW_FINDINGS.md:15-27`; F1 is the same class surfacing in the wild.

Note the `_PROTECTED_TOOLS` authz gate (`:849-853`) uses the correct per-request
identity, so quota/authz can't be dodged — but it does nothing to bind the workspace,
and plain read/write tools aren't in that set at all.

## What is NOT broken (bounds the read blast radius)

- `set_active_session` (`:742-747`) and `inject_architect_prompt` (`:815`) both call
  `owns_session(..., self._scoped_user_id())` before switching. `get_prompt`/
  `ensure_session` seed with the TRUE owner (`session_manager.py:166-168`). So there is
  **no single-request** way to point `current_session` at a foreign session; the read/
  write cross-tenant vector is the *concurrency* race (root cause 3), not a direct call.
- Resource surface (`list_resources`/`read_resource`) is correctly scoped and
  path-contained (`:391-403`).

---

## Severity assessment

| Vector | Cross-tenant effect | Severity |
|---|---|---|
| `list_sessions_tool` | Read all tenants' session ids + metadata | HIGH (confirmed, the reported symptom) |
| `delete_session_tool` | Destroy any tenant's session/workspace/chats by id | **CRITICAL** (confirmed, destructive) |
| shared `current_session` | Read/write any tenant's files under concurrency | **CRITICAL** (confirmed; already DEFERRED P0 #1) |

**Can user B read user A's files?** Yes, under concurrent load, via the shared
`current_session` race (root cause 3) — not via a single crafted call.
**Can user B destroy user A's data?** Yes, deterministically and single-request, via
`delete_session_tool` + ids enumerated from `list_sessions_tool` (root causes 1+2).

## The `first_session` mystery

No auto-seed bug. The literal `first_session` appears **nowhere** in the codebase
(repo-wide grep: zero hits in code, frontend, or config). No login/auth-callback path
seeds a session — `auth.py` has no `ensure_session`/`create_session` call; the only
implicit MCP seed is `get_prompt` → `ensure_session("mcp_session_<timestamp>")`
(`mcp_server.py:493-498`), a different name. The Launcher is owner-scoped, so a
`first_session` it shows **is owned by the test user**. Most likely explanation: it is a
pre-existing session created in earlier testing on this returning test account
(rockstarme.the5@gmail.com), surfacing on login — i.e. one of the user's real 2
sessions, not a phantom. I found no code that fabricates it. (If reproduction shows it
appearing on a genuinely fresh account, re-open — but the code has no such path.)

---

## Minimal fix proposal (per invariant 8; do NOT implement — proposal only)

Three small, independent edits in `mcp_server.py`, all "pass the uid we already have":

1. **`list_sessions_tool`** (`:722`): 
   `sessions = self.session_manager.get_all_sessions(user_id=self._scoped_user_id())`
   and pass the same `user_id` to `get_session_metadata` at `:730`. (Self-host uid is
   `None` → unchanged full list.)

2. **`delete_session_tool`** (`:777`):
   `self.session_manager.delete_session(session_id, user_id=self._scoped_user_id())`
   and translate the raised `PermissionError` into the existing "not found" text (do not
   leak existence). The guard in `session_manager.delete_session:216` already enforces
   ownership once a non-None uid is passed — no store change needed.

3. **Defense-in-depth on every session-id tool + the shared-state race** (root cause 3):
   after `if not self.current_session` (`:844`), add
   `if self._hosted and not self.session_manager.owns_session(self.current_session, self._scoped_user_id()): return ["❌ ..."]`
   so a workspace flipped underneath the caller is rejected before dispatch. This closes
   the read/write leg without the larger refactor. The *durable* fix (REVIEW_FINDINGS P0
   #1) is to request-scope the active session like identity/workspace already are
   (stop storing it on the shared instance) — recommend that as the follow-up, but the
   per-call `owns_session` gate is the minimal stopgap and is cheap.

Also fold in the already-noted `update_manifest` gate gap (REVIEW_FINDINGS P2,
`:231`/`_PROTECTED_TOOLS`) if touching this file — adjacent, one-line.

## Test plan (recording fakes / sys.modules injection; no live Postgres — patterns in `tests/test_persistence.py`, `tests/test_tenancy_redteam.py`, `tests/test_mcp_bound_session.py`)

Construct a hosted `RTLDesignMCPServer` with an injected `SessionManager` over an
in-memory/temp SqliteMetadataStore (as `test_mcp_bound_session.py:30` does), seed two
owners' sessions directly in the store, then drive `call_tool`:

1. **List scoping:** stub `_current_identity`/`_scoped_user_id` to return owner A; assert
   `call_tool("list_sessions_tool", {})` returns only A's ids, never B's. Regression: the
   test must FAIL on current code (returns both).
2. **Delete scoping:** as owner A, `call_tool("delete_session_tool", {"session_id": <B's>})`
   must NOT rmtree B's workspace nor delete B's row; assert B's dir + metadata still
   present and the response is the "not found" text. FAILS on current code (B destroyed).
3. **Shared-session race:** set A active, flip to B active (simulating B's request), then
   as A call `write_file`; assert the pre-dispatch `owns_session` gate rejects it (or, for
   the durable fix, that A's write lands in A's workspace). 
4. **Self-host parity:** with `hosted=False` / uid `None`, assert list returns all
   sessions and delete still works — the fix must not regress single-tenant behavior.
5. Reuse `tests/test_tenancy_redteam.py` style assertions
   (`get_all_session_rows(user_id=...)` disjointness) as the store-level guardrail.

## Fix size estimate

~15-25 lines across 3 handlers in `mcp_server.py` (no store/schema changes for stopgap)
+ ~1 new test module (~120 lines). Stopgap is low-risk and self-host-neutral. The durable
request-scoping of `current_session` (REVIEW_FINDINGS P0 #1) is a larger, separate change
— recommend as a fast-follow, not blocking the three one-liners above.
