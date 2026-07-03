# Wave 8 — Agent Shell v2 (slide-over) + IDE breadcrumb trim + review fixes

Status: DRAFT (pending 2nd-agent review)
Prototype: `651657f9-workbenchslideover.html` (user-approved direction)

## User decisions (locked)

1. IDE top bar loses the chat crumb — thread ownership lives in the right-rail
   chat panel only.
2. Agent shell drops the strict three sections. Resting state = **header +
   conversation**. Left nav is a **collapsible overlay rail** (closed by
   default); the right artifact panel is a **docked split that animates its
   width open/closed** (chat recenters; no overlay/occlusion, no pin state —
   simpler than slide-over+pin).
3. Runs + Files move from the old fixed sidebar INTO the artifact panel as its
   **Index home tab** — they are an index into artifacts, so they live with
   the artifacts.
4. Agent posture stays **prompt + view only**: no ⌘K/commands in the agent
   shell (prototype's composer ⌘K affordance is NOT adopted).
5. **No session-level status dots** (rail rows, header) — revision-1 rule
   stands. Per-RUN dots in the Index are fine (one run = one verdict).
6. Composer context strip shows **real data only**: manifest facts (synth top ·
   clock · platform). Session token/cost totals may also appear — they are
   REAL (`session.total_tokens/total_cost`, shown in the chat header today);
   no per-thread metering is built.

## Track A — Agent shell restructure

### A1. UI store additions (`lib/workbenchUiStore.ts`)
- Ephemeral: `navRailOpen: boolean` + `setNavRailOpen`.
- Per-session (persisted): `artifactsWide?: boolean` + `setArtifactsWide`.
  Migration default `false` in `useSessionUi` (like `artifactsOpen`).

### A2. Shortcuts (`hooks/useWorkbenchShortcuts.ts`)
- Agent scope ⌘O now **toggles the nav rail** (the rail replaces QuickSwitch
  in the agent posture; IDE ⌘O unchanged → QuickSwitch modal).
- ⌘P unchanged (QuickOpen) in both scopes.
- **Fix F4 (reviewer P2)**: the effect closes over `enabled` but deps are
  `[scope]` — toggling enabled true→false never unregisters the listener.
  Add `enabled` to the dependency array.

### A3. ArtifactCenter home view (`components/workbench/ArtifactCenter.tsx`)
New optional prop `homeSlot?: React.ReactNode`. Prop-gated so the IDE path is
byte-for-byte unchanged (no homeSlot → current behavior, incl. empty state):
- With homeSlot, the tab strip always renders with a pinned first **Index**
  tab (Home icon). `activeTab === null` ⇒ Index view; clicking Index ⇒
  `setActiveTab(null)`. `closeTab` already falls back to null when the last
  tab closes → lands on Index naturally.
- Keep-alive body unchanged; Index renders alongside (hidden when a tab is
  active, like other panels).
- Footer "← Back to index" bar when homeSlot present && a tab is active.

### A4. `components/workbench/ArtifactIndex.tsx` (new)
The panel's home view = the old sidebar's Runs + Files, relocated:
- **Runs** (`store.runs`, honest RunSummary fields only): status dot, kind
  icon, run id, `top` module, relative time, unread pulse. Click →
  `openArtifact(sid, primaryArtifactKey(run))` + `clearUnread(runId)`.
  No lint rows (runs are sim/synth run dirs only; lint lives in activity).
- **Files** (manifest roles rtl/tb/sdc/include): name + role tag. Click →
  `openArtifact(sid, artifactKeyForFile(path))`.
- `primaryArtifactKey` moves from AgentShell to this module (exported).

### A5. AgentShell rewrite (`components/workbench/AgentShell.tsx`)
- **Header row** (h-12, replaces both the old sidebar chrome and ChatArea's
  header in this posture): ☰ rail toggle · session button (folder icon +
  name, opens rail, no status dot) · `›` · existing `ThreadSwitcher` · right:
  `ThemeToggle` · `ModeToggle` (compact) · **ArtifactsChip** (Layers icon +
  "Artifacts" + unread count pill; toggles the panel; primary-tinted while
  open).
- **Center**: `<ChatArea hideHeader tailSlot={InlineActionsTail}
  footerSlot={ContextStrip} />` — full width, self-centering (max-w-3xl).
- **Right panel**: ALWAYS MOUNTED container animating `width` (0 ↔
  `min(42%,520px)` ↔ wide `min(62%,760px)`), `overflow-hidden`, inner body
  fixed-width (min 360) so content doesn't reflow during the animation.
  Keeping it mounted at width 0 means Monaco/VCD keep-alive now survives
  close/reopen (improvement over today's conditional render).
  - Panel header: "Artifacts" + unread pill + quick-open (⌘P) + wide/narrow
    toggle + close. Esc closes the panel when open and no overlay is up
    (guard: quickOpen/quickSwitch/navRail/settings all closed).
  - Body: `<ArtifactCenter readOnly homeSlot={<ArtifactIndex/>} />`.
  - The existing auto-reveal effect (flash/activeTab change → open) stays.
- **Old fixed Sidebar deleted** (SidebarRuns/SidebarFiles → ArtifactIndex;
  session block → rail; footer → rail footer).
- Floating top-right cluster removed (ModeToggle + reopen button move into
  the header).

### A6. NavRail (`components/workbench/NavRail.tsx`, new)
Overlay rail, closed by default, agent posture only:
- Scrim + fixed left aside (w-[264px]), translate-x animation, Esc +
  click-outside close (Esc precedence: rail owns its own key handler).
- Header: brand + collapse. "New session" button → opens the existing
  `CreateSessionModal` (launcher component, self-contained).
- Body: sessions grouped by project (group swatch header, "Ungrouped" tail),
  expandable rows → nested chats. **No status dots.**
  - Data: `store.projects` + `store.sessions` (call `loadProjects` /
    `loadSessions` on first open if empty).
  - Chats per session are **lazy**: expanding a row fetches
    `threadsApi.list(sid)` once (component-level cache keyed by sid, reset on
    rail open). The CURRENT session renders `store.threads` (live). After fix
    F3 the list endpoint is read-only, so browsing never mutates.
  - Click chat: same-session → `selectThread` + `replaceThreadUrl` (like
    ThreadSwitcher); other session → `router.push(sessionUrl(sid, { chat,
    view: "agent" }))`.
- Footer: GitHub link + `ProfileMenu` (owns the MCP handoff modal), moved
  verbatim from the old sidebar footer.

### A7. ChatArea (`components/chat/ChatArea.tsx`)
- New props: `hideHeader?: boolean` (agent shell owns session/thread chrome)
  and `footerSlot?: React.ReactNode` (rendered after `ChatInput`).
- Error banners (key CTA etc.) stay inside ChatArea in both postures.
- IDE posture unchanged (no props passed).

### A8. ContextStrip (small component, agent shell)
Under the composer: `Crown` synthTop · `clk {clockPeriodNs}ns · {platform}`
(from `store.manifest`, pieces hidden when absent) · right-aligned session
totals `#tokens · $cost` when > 0 (real data; parity with the hidden header).

### A9. Workbench wiring (`components/workbench/Workbench.tsx`)
- Agent branch: stop mounting `QuickSwitch` (rail replaces it); keep
  QuickOpen/Toaster/SettingsModal. NavRail mounts inside AgentShell.

## Track B — IDE breadcrumb trim (`components/workbench/Breadcrumb.tsx`)
- Remove the chat crumb + dropdown entirely (thread ownership = ChatArea's
  ThreadSwitcher in the assistant rail). Breadcrumb = Home › block.
- Drop now-unused imports/state/handlers (threads, selectThread, newThread,
  replaceThreadUrl, popover state).

## Track C — Reviewer findings (fold in as F1–F4)

### F1 (P1): session delete leaves chat threads + their checkpoints behind
`src/platform_engines/metadata_store.py`:
- SQLite `delete_session`: collect `SELECT id FROM chat_threads WHERE
  session_id = ?` first; delete checkpoint rows for **each** thread id (plus
  the legacy `thread_id == session_id` already handled); `DELETE FROM
  chat_threads WHERE session_id = ?`; then the session row. Owner clause
  keeps applying to the session row (tenancy gate); child rows are deleted
  only if the gated session delete matched (check rowcount).
- Postgres `delete_session`: add the `chat_threads` cascade (same rowcount
  gate). Checkpoints live in the sqlite checkpoint DB even in hosted mode —
  the API delete path already goes through the store; add a best-effort
  checkpoint cleanup helper there if it doesn't exist (verify at impl time).

### F2 (P1): stale/crafted `?chat=` selects/materializes unknown threads
- Backend (authoritative): the WS turn handler currently calls
  `ensure_thread(thread_id, …)` for ANY client-supplied id. Replace with
  validation: allow the default (`thread_id == session_id`, lazily ensured —
  that's the legit "Chat 1" materialization) and otherwise require an
  existing `chat_threads` row whose `session_id` matches the connection's
  session (owner-scoped). Unknown/mismatched → WS error frame
  `{"type":"error","error":"Unknown chat thread"}`, no row created. Logic
  lives in `session_manager.resolve_ws_thread(thread_id, session_id,
  user_id) -> str | None` so it's unit-testable.
- Frontend (UX): Workbench's thread-follow effect checks the loaded
  `threads` list before `selectThread(threadId)`; unknown `?chat=` falls back
  to the default thread and cleans the URL via `replaceThreadUrl`.

### F3 (P2): browsing threads mutates session state
- `session_manager.list_threads` drops its `ensure_default_thread` call —
  GET is read-only (ThreadDrawer/QuickSwitch/NavRail browsing never writes).
- The default "Chat 1" row is created **at session creation** instead
  (create_session path), so fresh sessions honestly have their chat from
  birth. Legacy sessions without rows: the WS connect ensure (existing)
  still materializes Chat 1 on first real open. Update the
  `count_threads_by_session` docstring accordingly.

### F4 (P2): `useWorkbenchShortcuts` stale-effect — see A2.

## Tests / gates
- pytest: delete-session cascade (threads gone, checkpoints gone, other
  sessions untouched); `list_threads` is read-only (no row materialized);
  `resolve_ws_thread` accept/reject matrix (default id · known id · unknown
  id · cross-session id); session creation seeds Chat 1.
- vitest: existing suites keep passing (store/threads unaffected by F3
  client-side); any new pure helpers get specs.
- e2e (`workbench.smoke.spec.ts`, `chat-threads.spec.ts`): agent-shell test
  rewritten — no sidebar; header carries session + thread switcher; ☰ opens
  the rail (sessions + nested chats listed); Artifacts chip toggles the
  panel; Index lists runs/files; opening a run creates a tab, "Back to
  index" returns; ⌘K stays inert. Breadcrumb test: no chat crumb; simplify
  selectors that excluded `breadcrumb-chat`.
- Gates: `tsc` clean · vitest green · Playwright (PW_EXECUTABLE) · `next
  build` · pytest suite.

## Deferred (documented, not in this wave)
- Model picker relocation to the header (it stays in the composer — the
  picker logic the user liked already exists there; placement churn adds
  nothing functional now).
- Blanket unread-clear on viewing the Index (we keep per-run clear-on-open).
- Lint entries in the Runs index; per-thread token/cost metering; session
  status dots; thread previews in rail rows; checkpoint cleanup for hosted
  PG mode beyond best-effort.
