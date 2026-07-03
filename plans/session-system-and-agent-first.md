# Session System + Agent-first Shell — Implementation Plan

Status: PROPOSED (awaiting review). Branch: `claude/siliconc-workbench-v2-ilsd83`.
Prototypes: `sessionsystemv2_backup.html` (Launcher / ⌘O / breadcrumb),
`workbenchagentfirst_backup.html` (chat-primary shell + inline tool stream).

## Intent — the definitions these two prototypes settle

**A session IS a workspace IS one design block.** A hardware engineer's mental
unit is the block: `sync_fifo`, `uart_tx`, `spi_master`. One session = one
workspace directory (RTL + spec + constraints + runs) = one manifest. The
launcher card proves it by showing *design truth*, not chat fluff: latest-run
verdict ("WNS +0.42ns · 412 cells", "FAIL @320ns"), file chips, thread count.

**Chats are conversations about a block, never containers of work.** Many
chats per session; all share the live files/runs. Navigation says this out
loud: breadcrumb = `Home › <block> › <chat>`.

**Groups are tags, not folders.** "asu_hackathon", "tapeout_q3". The backend's
existing *projects* ARE groups — we relabel and finish the CRUD, we don't
build a new entity.

**Two postures, one machine.** This is the load-bearing claim:
- *Agent-first*: you DELEGATE. The conversation is the workspace narrative —
  agent prose interleaved with tool cards, artifacts opened on demand in a
  side panel. For architecture/exploration ("build me a FIFO, make it pass").
- *IDE-first* (shipped v2 workbench): you DRIVE. Files/tabs/dock center-stage,
  agent in the rail. For debug/signoff.
Same session, same manifest, same runs, same open-tab artifact model, same
command engine, same activity truth. **Posture is layout emphasis only.** Our
codebase is unusually well-positioned for this: all data lives in UI-agnostic
stores (lib/store.ts) and every v2 surface (ArtifactCenter, QuickOpen,
CommandPalette/Modal/Surface, openArtifact) is prop-less and store-driven —
they can mount in either shell unchanged.

**The agent-first stream and the IDE Activity feed are the same fact, worn
differently.** A user right-click-lints: IDE shows it as an Activity row;
agent-first shows it inline in the conversation as a "You ran a command" card.
One event log (already built — attempt_events + activity slice), two renderings.

## What exists vs what the prototypes add

| Prototype element | Codebase today |
|---|---|
| Launcher (home) with session cards, search, recent/grouped | `/` is the LEGACY chat page (old Sidebar + old fixed-tab ArtifactsPanel) |
| Groups (tag-style, DnD, CRUD) | Backend projects: create/delete/move exist; **no rename**; old Sidebar UI is folder-flavored |
| Create-session modal (slug preview, Start-in Chat/IDE, group) | Bare dialog in old Sidebar; no shell choice |
| ⌘O quick-switch | Nothing (SessionPicker dropdown only) |
| Breadcrumb Home › block › chat | SessionPicker + ThreadSwitcher, separate places |
| Session remembers last shell | Nothing |
| Deep links (open session X, chat Y, shell Z) | **No URL state at all** — selection is store-only, refresh loses context |
| Agent-first shell | Legacy `/` is a rough ancestor; not the prototype |
| Tool cards with "Open artifact →" | ToolCallCard shows args/result; no artifact routing |
| Manual actions inline in conversation | Only visible in IDE Activity dock |
| Session rename / duplicate | **No backend endpoint** (SessionPatch = project_id only) |

## Plan

### Wave S0 — backend micro-wave (small, unblocks everything)
1. `PATCH /api/sessions/{id}`: accept `name` (rename; workspace dir unchanged —
   name is display; document that) alongside `project_id`.
2. `PATCH /api/projects/{id}`: rename. (`ProjectResponse` already has label.)
3. OPTIONAL (defer unless cheap): `POST /api/sessions/{id}/duplicate` — new
   session + copy workspace files (excluding run dirs). If deferred, the
   launcher menu ships without Duplicate.
4. Session list enrichment for cards, ONE cheap endpoint concern: the launcher
   needs per-session `latestRun {kind,status,head}`, `fileCount/topFiles`,
   `threadCount`. Options: (a) extend GET /api/sessions with a `?cards=1`
   aggregate (reads each session's runs index + manifest — hosted cost: N
   hydrations! NO) — or (b) persist a tiny `card_summary` into the session
   store row updated on workspace sync / run completion (honest cache,
   cheap list). **Choose (b)**; stale-tolerant (card shows last-synced truth).
   Reviewer: check `session_manager` row shape + where sync completes.

### Wave S1 — routing foundation (the real structural change)
- URL becomes the source of truth for *where you are*:
  - `/` → Launcher
  - `/w/{sessionId}?chat={threadId}&view=agent|ide` → workbench (both shells)
  - legacy `/workbench` redirects to `/w/{last-session}` or `/`.
- Store follows URL (App Router route params → selectSession/selectThread),
  not the other way; refresh/share/back-button all just work. This deletes the
  mount-effect "select first session" heuristic in Workbench.tsx.
- Per-session `shell` preference lives in workbenchUiStore.perSession
  (client-side; honest — it's a viewing preference, not design data), used as
  the default when `view=` is absent.

### Wave S2 — Launcher (replaces the legacy `/` page)
- Card grid per prototype: glyph, mono name, status dot (from card_summary),
  thread count, updated, file chips, group tag; Recent | Grouped toggle;
  search; empty-state.
- Groups: sections with colored dots, collapse, drag-to-group, context menus
  (session: Open in Chat / Open in IDE / New chat / Rename / Move to group /
  [Duplicate] / Delete; group: new-session-here / rename / delete-keeps-
  sessions; background: new session / new group). Backed by projectsApi +
  S0 endpoints. Card ordering within group: client-side (updated desc) — the
  prototype's manual reorder is cosmetic; skip (honesty: no persistence).
- Thread drawer on card select: chats list w/ previews (threadsApi.list —
  previews need last-message text: threads store has `last_active` but no
  preview; EITHER add `preview` to ThreadResponse (backend reads last message
  of checkpoint — cost: one checkpoint read per thread; do lazily per-session
  on drawer open, not on list) OR ship drawer without previews first. Start
  without; add preview endpoint as a fast-follow if it feels dead.)
- Create-session modal: slug preview (`workspace/<slug>/`), Start in Chat|IDE,
  optional group; model comes from the real catalog default (no picker here —
  model is a per-chat choice, not a workspace property; keeps the modal
  design-first).
- DELETE the legacy chat page + its exclusive components once this lands
  (old Sidebar, old fixed-tab ArtifactsPanel wiring on `/`, hardcoded MODELS
  remnants). The store slices they alone consumed get pruned (activeArtifactTab
  / artifactsVisible / selectedCodeFile bulk-code path etc. — grep-verified list
  at implementation time).

### Wave S3 — ⌘O Quick-switch + breadcrumb (both shells)
- QuickSwitch overlay: search, grouped session list (left), detail pane
  (right: files/chats counts, Open in Chat / Open in IDE, jump-to-chat, new
  chat, "New session…"), ↑↓/Enter/Esc. Data: sessions list + card_summary +
  threads (lazy on highlight).
- Breadcrumb component in BOTH top bars: Home → Launcher; block name (status
  dot; click → ⌘O); chat dropdown (threads + "New chat — same workspace").
  In the IDE TopBar it REPLACES SessionPicker (SessionPicker retires).

### Wave S4 — Agent-first shell (`view=agent`)
- Layout per prototype: compact left sidebar (210px: session block, Runs list
  w/ status+unread dots — click opens the run's artifact; Files quick list;
  footer repo/theme/profile) · center conversation (max-w-760) · right
  collapsible artifact panel = **the existing ArtifactCenter mounted at 40%
  width** (open tabs, keep-alive, unread, ⌘P — zero new artifact code; add an
  "Artifacts" header variant w/ unread count + collapse).
- The overlays mount once as in the IDE shell: CommandPalette, CommandModal,
  CommandSurface, QuickOpen, Toaster, SettingsModal, McpModal — identical
  invocation power in both postures (⌘K works mid-conversation, exactly as the
  prototype's composer hints).
- Composer footer: manifest facts strip (synthTop · clk · platform) + session
  token/cost (already in Session).

### Wave S5 — conversation upgrades (shared by both shells)
1. **ToolCallCard → artifact routing**: cards gain "Open <artifact> →" when the
   tool result maps to one (write_file/edit → `code:<file>`; sim tools →
   `wave:<runId>`; start_synthesis/retry → `report:<runId>`; write_spec →
   `spec`; schematic → `schematic:<file>`). Pure mapping fn (tool name + args
   + result-extracted runId → ArtifactKey) in lib, unit-tested; uses the same
   run-id extraction conventions as the activity feed.
2. **Manual actions inline**: user/mcp-source activity events render as
   "You ran a command" / "Run from your AI (MCP)" cards inside the
   conversation stream. LIVE interleaving is exact (events arrive with ts as
   they happen). HISTORY interleaving is approximate: thread history messages
   carry no timestamps today — so on reload, foreign-actor events since the
   last message render as a grouped "while you were away" section rather than
   fake-precise interleaving. Backend fast-follow (flagged, not required):
   expose per-message timestamps from the LangGraph checkpoint so reload
   interleaving becomes exact.
3. Mode toggle: TopBar (IDE) + chat header (agent) get the Agent-first ↔
   IDE-first switch → routes `view=`; per-session default updated.

### Wave S6 — gates + cleanup + review
- Full suites (pytest / tsc / vitest / Playwright: launcher flows, ⌘O, deep
  links, agent-shell smoke: chat→tool card→open artifact→switch to IDE →
  same tabs). Adversarial review pass. Legacy-page deletion verified by grep
  (no orphan store slices/components).

## Hardware-designer-first checks (why this shape)
- The launcher speaks silicon: a card's headline is its latest *verdict*
  (timing met / sim fail @ns / warnings), not "last opened".
- Block-centric nav: `Home › sync_fifo › Debug overflow assert` matches how
  designers context-switch between blocks, and ⌘O is block-hopping.
- Delegate vs drive is a real workflow split (architecture exploration vs
  debug/signoff), not a marketing toggle — and switching mid-task keeps every
  artifact tab, run, and unread marker because state never lived in the shell.
- No dishonest UI: no fake reorder persistence, approximate history
  interleaving is labeled, card summaries are last-synced truth.

## Sequencing & risk
S0 → S1 → S2 → (S3 ∥ S4) → S5 → S6. Biggest risk is S1 (routing refactor
touches session-selection flow everywhere) — do it as its own reviewed commit
with both shells still functional. S2 deletes the legacy page: one-way door,
taken only after Launcher covers its jobs (session CRUD + open + settings
access). Everything else is additive.

## Open questions for the reviewer
1. S0-4: confirm the session-store row is the right home for `card_summary`
   and which code paths must refresh it (sync? run completion? both).
2. S1: App Router dynamic segment for `sessionId` containing `/` (project-
   scoped ids use slashes — catch-all segment `/w/[...sid]` needed?).
3. S5-2: cheapest correct source for per-message timestamps from LangGraph
   checkpoints, if we promote exact reload interleaving.
4. Naming: cards say "session" everywhere in copy but the path shows
   `workspace/<slug>/` — confirm this reads right, or standardize on
   "workspace" in user-facing copy with "session" kept for API/MCP.
