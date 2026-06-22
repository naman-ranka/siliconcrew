# Build brief — chat threads (many conversations per workspace)

Work on `claude/integration-p1p2` (the trunk); commit + push there.

## Goal
Decouple "AI chat" from "SiliconCrew session (workspace)". One workspace
(session) should host **many chat conversations** the user can start fresh and
switch between — the right rail gets a "New chat" + a list of past chats. The
LangGraph-idiomatic model: a chat = a `thread_id`; the workspace = `session_id`.

## THE ONE RULE (do not violate)
**Threads share the LIVE workspace.** A chat thread is *conversation history
only*. All chats for a session see the same files/runs/manifest as they exist
*now* — going back to an old chat restores its messages, NOT a past workspace
state. Do **not** snapshot or version the workspace per thread (that's a separate
future git feature). Deleting a thread never touches files/runs.

## The fusion point to change
`api.py` currently keys the conversation to the workspace:
- line ~586 and ~697: `config = {"configurable": {"thread_id": session_id}}`.
Change `thread_id` to the **chat thread id** (client-supplied), while the
workspace stays bound from `session_id` via the existing SessionContext. That is
the core change; everything else supports it.

## Data model
Add a `chat_threads` table in `metadata_store` (sqlite + postgres, same pattern
as sessions), tenant-scoped:
`{ id, session_id, user_id, title, created_at, last_active }`
- Tenant isolation: every query filters by `user_id` (None in self-host), same
  as sessions. A thread inherits its session's owner.

### Back-compat migration trick (zero data migration)
Existing conversations are checkpointed under `thread_id = session_id`. So make
**each session's default/first thread use `id = session_id`**. Then existing
histories map in unchanged as "Chat 1"; only *new* chats get fresh UUID ids.
On first load of a session with no rows in `chat_threads`, insert one row
`{id: session_id, title: "Chat 1"}`.

## Backend endpoints (under the session, owner-checked, tenant-scoped)
Reuse the existing auth deps (`get_identity`/`require_signed_in`/`_require_owned`)
exactly like the session endpoints.
- `POST   /api/sessions/{session_id}/threads`            → create; returns {threadId, title}
- `GET    /api/sessions/{session_id}/threads`            → list (newest last_active first)
- `GET    /api/sessions/{session_id}/threads/{tid}/history` → that thread's messages
- `PATCH  /api/sessions/{session_id}/threads/{tid}`      → rename (title)
- `DELETE /api/sessions/{session_id}/threads/{tid}`      → delete conversation only
- **WebSocket** `/api/chat/{session_id}`: accept a `thread_id` (query param or in
  the first client message). Use it as the LangGraph `thread_id`; keep the
  workspace bound from `session_id`. If `thread_id` is omitted, default to the
  session's "Chat 1" (`id = session_id`) for back-compat.
- The existing `/api/chat/{session_id}/history` keeps working (defaults to Chat 1);
  the new per-thread history endpoint is the general form (reuse the same
  checkpoint-reading logic, keyed by the chosen `thread_id`).

Update `last_active` and (if untitled) auto-title on the first user message.

## Auto-title
Title a new thread from its first user message (truncated), else "Chat N".

## Frontend (right rail)
- A compact header above the chat: **＋ New chat** + a switcher (dropdown or list)
  of this session's threads with titles + relative time.
- Selecting a thread loads its history into the message list and reconnects the
  WebSocket with that `thread_id`. **The left rail + center (files, runs,
  artifacts) do NOT change** — same workspace.
- New chat → POST threads → switch to it (empty history).
- Store (`lib/store.ts`): add `threads`, `activeThreadId`, `loadThreads`,
  `newThread`, `selectThread`, `deleteThread`; the WS client (`lib/api.ts`) sends
  `thread_id`. Keep the existing chat message handling; only the thread key +
  history source change.

## Agent / tools — unchanged
The agent graph and all tools are identical. They resolve the workspace from
`session_id` via SessionContext (already wired). Only the checkpoint key
(`thread_id`) varies per chat. The system prompt is injected per new thread.

## Auth / concurrency
- Thread endpoints owner-checked + tenant-scoped (mirror session endpoints).
- Two chats on one workspace = last-write-wins on files (the `file_ops`
  chokepoint) — acceptable; note it, don't add locking.

## Verification
- Unit: threads CRUD; tenant red-team (user A can't list/read/delete user B's
  threads); back-compat (a session with legacy history exposes it as Chat 1).
- WS: a turn on thread T checkpoints under T; a turn on a new thread starts empty;
  both act on the same workspace (run a tool in each, confirm same files).
- Playwright (live, integration branch): new chat → send a message → switch back
  to the first chat → its history is intact and the workspace (files/runs) is
  unchanged across chats. Screenshot the switcher.
- Keep all existing tests green (134 backend / Vitest / e2e). Frontend + the
  thread endpoints only; do not change the action API, auth, or the one write path.

## Deliverable
Commit per slice, push to `claude/integration-p1p2`, and summarize: the schema,
the endpoints, the WS thread_id change, the switcher, and the back-compat result.
