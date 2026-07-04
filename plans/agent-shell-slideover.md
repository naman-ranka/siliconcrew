# Wave 8 — Agent Shell v2 (slide-over) + IDE breadcrumb trim + review fixes

Status: IMPLEMENTED (plan review amendments below; post-implementation
reviews — external codex + adversarial agent — fixed: default-CLOSED panel
resting state, inert closed surfaces, thread_count on POST responses,
same-session ?chat= refresh-once, ensure_session seeds the TRUE owner's
default thread (never the caller's), delete cascade returns the deleted
thread ids for the checkpoint purge (no fragile pre-read), unified vw
panel widths (no %/vw clipping).
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

## Amendments from the 2nd-agent review

1. **F3 — the WS ensures per MESSAGE, not per connect** (api.py:1144). So a
   session opened but never messaged would show 0 chats forever once the
   list stops ensuring. Resolution: seed the default "Chat 1" row
   (`ensure_default_thread`) in BOTH `create_session` and `ensure_session`
   (the MCP materialization path). Legacy rows (pre-seeding dev DBs) still
   materialize on first WS message; additionally, thread PATCH (rename /
   model-set) may materialize the DEFAULT id only (`tid == session_id`) —
   a deliberate user action, unlike browsing. Frontend
   `setActiveThreadModel` targets `session_id` when `activeThreadId` is
   null (fixes the silent no-op; update stale comments store.ts:553/1033).
   Consequence: fresh sessions honestly report `thread_count == 1`.
2. **F1 ordering** — inside one transaction: delete the session row FIRST
   (capture rowcount, owner-gated), then `chat_threads`, then (SQLite)
   checkpoint rows for every collected thread id + the legacy session id.
   Gate children on `rowcount or user_id is None` (self-host cleanup of
   orphans). Keep the per-table try/except (checkpoint tables appear only
   after LangGraph first writes). The store-level owner gate is
   defense-in-depth — `SessionManager.delete_session` already raises
   PermissionError for non-owners.
3. **PG checkpoint cleanup lives in SessionManager.delete_session**, not
   the PG store: collect thread ids via `store.list_threads` BEFORE the
   store delete; if the store has no `_CHECKPOINT_TABLES` (PG), best-effort
   delete those ids from the local sqlite state DB (`self.db_path`).
   Cloud-instance locality accepted (documented best-effort).
4. **Esc design** (double-handling): the panel's window listener runs at
   bubble phase and ignores `e.defaultPrevented`; our popovers
   (ThreadSwitcher, ModelPicker, ProfileMenu, NavRail, CreateSessionModal)
   add `e.preventDefault()` when they consume Esc. Store-driven overlays
   (QuickOpen via cmdk closes on document-level Esc before us): the panel
   keeps a one-tick "overlay was open" ref so the same keypress never
   falls through. NavRail ignores Esc while its CreateSessionModal is open
   (rail owns that flag).
5. **CreateSessionModal** gets `defaultStartIn?: ViewMode` — the rail
   passes "agent" so creating from the agent shell doesn't bounce to IDE.
6. **`artifactsWide` uses the optional-field pattern** (`shell?:`), NOT a
   new `emptySessionUi` member (exact-shape tests + persisted-state shape).
7. **F2 frontend fallback** only fires when the thread list actually
   loaded (`threadsLoading === false && !chatError`); Workbench gains
   `useRouter` for `replaceThreadUrl`.
8. **Test updates the tracks imply** (enumerated, not "keep passing"):
   pytest `test_chat_threads.py` (legacy list-ensure test → new semantics),
   `test_session_rename_and_thread_count.py` (fresh count is now 1; list
   no longer ensures), WS fixtures `test_chat_byok.py` /
   `test_chat_heartbeat.py` (stub the new resolve path); vitest
   `agentShell.test.tsx` (rewrite for the new shell; collapsed panel is
   width-0 + `data-open`, not unmounted), `breadcrumb.test.tsx`,
   `useWorkbenchShortcuts.test.ts` (agent ⌘O → rail);
   `workbenchUiStore.test.ts` untouched thanks to (6). e2e selector
   inventory: workbench.smoke.spec.ts:632-668 agent-view block rewritten;
   chat-threads.spec.ts:110 drops the `:not([data-testid=…])` guard.
9. REST list endpoint docstring (api.py:944) updated with F3; hosted
   object-storage blob leak on delete is pre-existing and out of scope
   (F1 tests are local-mode).

## Deferred (documented, not in this wave)
- Model picker relocation to the header (it stays in the composer — the
  picker logic the user liked already exists there; placement churn adds
  nothing functional now).
- Blanket unread-clear on viewing the Index (we keep per-run clear-on-open).
- Lint entries in the Runs index; per-thread token/cost metering; session
  status dots; thread previews in rail rows; checkpoint cleanup for hosted
  PG mode beyond best-effort.
