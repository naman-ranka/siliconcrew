# Codex Runtime as a Removable Extension

Status: proposed (Phase 0 complete — worktree + this plan). Branch: `claude/codex-extension`, based on `claude/siliconc-workbench-v2-ilsd83` @ `43b751e`.

## Goal

Add OpenAI **Codex** as a second agent runtime that sits *adjacent* to the existing
LangChain/LangGraph agent — an "extension," not a rewrite. The LangChain path stays
**exactly as is**. Codex only reaches shared primitives (the tool server, the DB, the
chat-bubble renderer); nothing in the shared/LangChain path ever depends on Codex.
If we ever want Codex gone, we delete its files, drop its table, flip a flag off — and
the app is byte-identical to today.

## The mental model: host + extensions (not one agent with a runtime knob)

Like two VS Code extensions sharing an editor: they share the *workspace* (files, tools),
not each other's chat state, auth, or model config. The reference branch
(`codex/codex-runtime-adapter`) got the mechanics working but coupled the two runtimes
through a shared execution abstraction (`ChatRuntimeAdapter` protocol, a unified
`chat_threads.runtime` column, a filtered shared `ModelPicker`). We keep its *mechanics*
as reference and **re-cut the seams** so the two runtimes are independent and Codex is removable.

### Why separation fits the grain of the tech

The two runtimes have different *physics*, so a shared abstraction is a leaky pretense:

- **LangChain** binds tools **in-process** — Python callables wired into the graph; the
  framework owns the tool loop.
- **Codex** is a **separate process** we don't control; it reaches SiliconCrew tools only
  over **MCP** (a wire). It's "external" by construction — and that's fine: the win is a
  strong pre-built agent we don't maintain, in exchange for indirection + less control of
  its loop.

So at the tool layer they share only the tool *implementations*, exposed two ways:
natively to LangChain, and over MCP (bound-session) to Codex. They share no tool-calling *path*.

## The contract (what is shared vs separate)

| Concern | LangChain surface | Codex surface |
|---|---|---|
| Entry | default occupant of the agent panel | mounts when switched to (flag-gated) |
| Turn protocol | existing path, untouched | own path (subprocess Codex SDK) |
| Threads / history | existing store | own store (`codex_threads` table) |
| Model selection | own picker | own picker (account vs BYOK) |
| Auth | existing | own (device-auth OAuth + BYOK) |
| Settings | existing | own (Codex Account section) |
| Persistence | LangGraph checkpointer (SQLite/Postgres, already landed) | Codex server-side thread (`external_thread_id`) — **no checkpointer** |
| Tool calling | native, in-framework | via MCP bound-session |
| **Message / tool-call rendering** | **shared components** | **shared components, Codex theme scope** |

### Shared (the host)
- The **MCP tool implementations** + bound-session launch mode (the one primitive Codex consumes).
- The **workbench chrome** (file explorer, artifact center, app shell).
- The **chat transcript renderer** — bubble + tool-call components — via a **thin
  presentation contract**: a rendered turn is `{role, ordered content blocks, tool_calls}`.
  A *rendering format both emit*, NOT an execution protocol both implement.

### Separate (the Codex extension owns its own)
Turn protocol, thread storage, model surface, auth, settings, entry gesture.

## UX: one agent panel, one agent at a time

- The layout has **one agent-panel slot**. Exactly one runtime is mounted in it at a time.
- **Not** a persistent VS-Code-style tab strip with both surfaces visible. Switching
  **replaces** the whole shell (model picker, history, input); the previous surface is gone
  from view, not backgrounded.
- The switcher is a **single lightweight control** (e.g. a "current agent" affordance in the
  panel header) — not a tab bar. Exact form settled in Phase 4.
- **Subtle theme accent** signals "you're in Codex" — a theme scope wrapping the shared
  components. Rule: **vary theme tokens, never fork the component.** Forking the bubble/
  tool-call components would lose the one thing we agreed to share.
- Backend reports one active runtime session in the panel → dispatch is unambiguous, no
  interleaving, no concurrent-runtime state to reconcile.

## Enforced discipline (removability)

1. **Dependency rule:** shared/LangChain code **never** imports `src/agents/codex/`.
   Arrows point one way: Codex → shared primitives. Enforced by an **import-graph test** in CI.
2. **Codex-only state** lives in its own tables (`codex_threads`), confined to a Codex-owned
   migration unit — droppable without migrating LangChain data.
3. **Gated:** `CODEX_ENABLED` flag + `openai-codex` as an **optional** (lazy-imported)
   dependency. Off → the app is byte-identical to today.
4. **Acceptance test for the whole effort:** delete the Codex files, drop its table, flip
   the flag off → app compiles and runs exactly as it does now.

## Relationship to the Postgres-durability track — RESOLVED

The Postgres checkpointer (`src/platform_engines/checkpointer.py`, `plans/hosted-chat-durability.md`)
**already landed on the base branch** (`43b751e`). Codex persists its own thread state
server-side and never touches `open_checkpointer`, so the two tracks do not collide.
This plan assumes Codex is built without touching the checkpointer, and we do **not** carry
over the reference branch's uncommitted SQLite-on-FUSE band-aids.

## Phases

### Phase 0 — Setup (DONE)
Pull latest base, create `claude/codex-extension` worktree/branch off `43b751e`, commit this plan.

### Phase 1 — The seam (shell side), with a stub runtime
- Runtime **registry / contribution point** in the shared layer: a runtime registers
  `{id, display, thread-source, turn-handler, capability-flag}`. The chat handler dispatches
  through it. LangChain is the default; when Codex is unregistered, dispatch only ever
  reaches the **existing, untouched** LangChain path.
- Define the thin **presentation contract** (rendered-turn event shape) both runtimes emit.
- Ship a **stub runtime** to prove dispatch + removability with zero risk to LangChain,
  *before* any real Codex wiring.
- LangChain path: **zero changes** beyond being reached via registry dispatch. Verified by
  existing tests passing unchanged.

### Phase 2 — The Codex extension (self-contained), under `src/agents/codex/`
- `codex_runtime.py` — subprocess Codex SDK app-server, per-thread isolated `CODEX_HOME`,
  generated `config.toml` registering the bound MCP server, SDK-event → presentation-contract
  translation. (Reference: branch `runtime_adapters.py` `CodexRuntimeAdapter`, re-implemented
  standalone — no shared protocol.)
- `codex_auth.py` — device-auth OAuth + BYOK. (Reference: `codex_account_auth.py`, ~as-is.)
- `codex_threads.py` — own thread store (`codex_threads` table), mapping to Codex's
  `external_thread_id`; additive migration in both Sqlite + Postgres metadata stores,
  confined to a Codex-owned unit.
- `register.py` — `register_codex_runtime()`, called only when `CODEX_ENABLED`.
- Codex-specific API endpoints (`/api/codex/...`) registered under the flag; existing
  endpoints untouched.

### Phase 3 — Shared MCP bound-session mode
Keep the branch's `mcp_server.py` bound-session mode (scoped to one session, hides
session-management tools, blocks path traversal). Additive launch mode — no change to
existing MCP behavior for other clients. This is the honest "external tools" boundary.

### Phase 4 — Frontend: Codex as a single-panel surface
- Shared transcript renderer stays runtime-agnostic (no Codex branching in core components).
- One agent panel; switcher (not tabs) swaps the mounted surface.
- Codex surface: own entry gesture, own model surface (account vs BYOK), own settings
  (device-auth), Codex theme scope over shared bubbles.
- All Codex UI behind a `codexEnabled` capability from the backend. Disabled → none renders.
- Codex-specific types isolated; shared types stay minimal.

### Phase 5 — Tests, gating, deployment
- Re-implement the *behaviors* the branch's tests lock in: per-thread isolation, env-key
  scrubbing, no-persist-on-failed-turn, bound MCP can't escape the session, device-auth parsing.
- **Removability CI checks:** (a) import-graph test — no shared/LangChain module imports
  `src/agents/codex/`; (b) flag-off smoke test — app behaves identically.
- LangChain regression: existing tests pass unchanged.
- `openai-codex` optional (extras group / `requirements-codex.txt`), in the hosted Docker
  image, not required for local/OSS — consistent with "local stays first-class."

## Known risks / to validate on real infra (not assume)

- **Live Codex SDK** can't be fully exercised in the dev sandbox (needs OpenAI creds +
  network + subprocess app-server). Build + unit-test against a faked SDK; a real end-to-end
  Codex turn needs a driven verification pass with creds. Won't be claimed working until run.
- **Cloud Run subprocess footprint / cleanup** — each Codex thread spawns a subprocess +
  MCP server. Resource + concurrency + cleanup behavior needs deploy-time validation.
- **Codex credential durability** — `auth.json` on ephemeral container disk has the same
  durability problem we just fixed for chat. Decide durable storage (or per-session
  device-auth) deliberately; do NOT quietly reintroduce the data-loss bug.

## Working style

Vertical slices with checkpoints, not one big drop. Phase 1 (registry + stub) proves the
seam and removability first; then the real Codex engine; then UI.
