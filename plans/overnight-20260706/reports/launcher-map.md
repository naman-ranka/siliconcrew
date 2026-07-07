# SiliconCrew Launcher — frontend code map

Evidence for the open-source landing-page redesign. Every claim carries a
`file:line` under `frontend/`. Written 2026-07-06.

## 1. The `/` route + component tree

- `app/page.tsx:11-19` — `Home()` renders `<Launcher/>` + `<SettingsModal/>`
  inside `<main className="h-screen w-screen overflow-hidden">`. No other
  landing chrome exists.
- `components/launcher/Launcher.tsx:55-589` — the entire Launcher. Layout:
  - **Header/toolbar** (`Launcher.tsx:328-389`): brand lockup
    (`330-336` — a lucide `CircuitBoard` icon in a rounded `bg-primary/15` box +
    text "SiliconCrew", `hidden md:block`), search input (`337-345`,
    placeholder "Search workspaces…"), Recent/Grouped segmented toggle
    (`347-372`), "New session" button (`373-375`), `<AccountChip/>` (`376`),
    `<ThemeToggle/>` (`377`), Settings gear (`378-387`,
    `data-testid="open-settings"`).
  - **Content states**: booting skeletons (`392-399`), error + Retry
    (`400-408`), empty state (`409` → `EmptyLauncher`), and the grid
    (`411-545`). Recent = flat 2-col card grid (`428-431`); Grouped =
    collapsible group sections with HTML5 drag-drop into groups (`432-541`).
  - **Empty state**: `EmptyLauncher` (`591-613`) — folder glyph, `<h1>No
    workspaces yet</h1>` (`601`), subtitle "Create one to start designing with
    the agent." (`602-604`), a "New session" button.
  - **Search-no-match** inline empty (`414-427`): "No workspaces match …".
  - **Overlays** (`549-586`): `ThreadDrawer`, `LauncherContextMenu`,
    `NamePrompt`, `CreateSessionModal`, delete-confirm `Dialog`.
- Sub-components under `components/launcher/`:
  - `SessionCard.tsx:31-114` — card: folder glyph, **mono** name (`78`),
    thread-count + relative "updated" (`91-101`), optional group tag (`102-110`).
  - `CreateSessionModal.tsx:38-272` — new-workspace modal: name with live
    `workspace/<slug>/` preview (`214-217`), "Start in Chat|IDE" cards
    (`219-225`), optional group tag (`227-256`).
  - `ThreadDrawer.tsx`, `NamePrompt.tsx`, `LauncherContextMenu.tsx`,
    `util.ts` (`plural`, `GROUP_SWATCH` palette `7-16`, `slugify`).

## 2. Store slices + API calls feeding it

- **Store** (`lib/store.ts`): state `sessions/projects/sessionsLoading/
  sessionsError` (`270-271`, `495-496`); `settingsOpen`/`setSettingsOpen`
  (`328-329`, `524`, `1396-1398`). Actions: `loadSessions` (`625-642`, sorts by
  `updated_at`), `loadProjects` (`575-582`), `createSession` (`644-685`),
  `deleteSession` (`687+`), `createProject`/`deleteProject`/`moveSession`/
  `renameSession`/`renameProject` (`584-622`).
- **API** (`lib/api.ts`): `projectsApi` list/create/rename/delete (`70-90`);
  `sessionsApi` list/create/get/patch/delete (`93-116`). Launcher's optimistic
  drag-move calls `sessionsApi.patch(id,{project_id})` directly
  (`Launcher.tsx:156`).
- **Auth/account state**: `useAuth()` from `lib/auth.tsx`; Launcher reads only
  `authStatus` to gate the initial load (`Launcher.tsx:71,87-91`). Account UI is
  `components/auth/AccountChip.tsx` — renders **nothing** when OAuth
  unconfigured (`AccountChip.tsx:37`); signed-out shows "Sign in with Google"
  (`39-52`); signed-in shows avatar + dropdown (`58-108`).
- **Nav**: `lib/nav.ts` — `ViewMode="agent"|"ide"` (`12`), `sessionUrl`/
  `openSession` (`22-39`); URL is `/w/{sid}?chat=&view=`.

## 3. Design tokens / theming

- **Tokens**: `app/globals.css` — HSL CSS vars on `:root` (warm dark, `10-80`)
  and `.light` ("paper", `82-141`). Brand `--primary` = Claude orange
  `14 63% 60%` (`23`); `--info` = Claude blue (`36`); surface ladder
  `--surface-0..3` (`64-67`); status colors kept separate from brand (`48-55`).
- **Theming mechanism**: `.dark` is the default on `<html className="dark">`
  (`app/layout.tsx:33`); `ThemeToggle.tsx:15-31` toggles a `.light` class on
  `<html>` and persists to `localStorage["sc-theme"]`.
- **Tailwind** (`tailwind.config.ts`): `darkMode:["class"]` (`4`); all color
  tokens mapped to the CSS vars (`12-74`); fonts (`80-83`); motion (`91-144`,
  easing `swift`); warm elevation shadows `e1/e2/e3/glow` (`145-151`);
  `tailwindcss-animate` plugin (`154`).
- **Fonts**: Inter (sans) + JetBrains Mono (mono), Google-Fonts `@import` in
  `globals.css:6-7`, wired in tailwind (`80-83`). Session names render in mono
  (`SessionCard.tsx:78`).
- **Icons**: `lucide-react` throughout (e.g. `Launcher.tsx:5-21`). There is
  **no SVG logo** — the "logo" is the lucide `CircuitBoard` glyph
  (`Launcher.tsx:331`).

## 4. Branding / identity assets + metadata

- **App name**: hardcoded text "SiliconCrew" in the header
  (`Launcher.tsx:333-335`); no logo component/svg anywhere.
- **Page metadata**: `app/layout.tsx:12-24` — `title:"SiliconCrew Architect"`,
  `description:"Autonomous RTL Design Agent - AI-powered hardware design"`,
  `icons.icon:"/favicon.ico"`, `themeColor:"#0f1419"`.
- **Assets**: **no `public/` dir and no favicon/logo/svg files exist**
  (verified — `ls public` empty; no svg/logo/favicon files outside
  node_modules). The referenced `/favicon.ico` is not actually present.
- **GitHub / external links**: **none anywhere in the frontend** (grep found
  only `CircuitBoard` icon usages, no `github.com` / external `href`). A landing
  "star on GitHub" / repo link would be net-new.

## 5. Empty state today

- `Launcher.tsx:591-613` (`EmptyLauncher`) — heading "No workspaces yet" at
  `601`. Triggered by `isEmpty` (`321`), rendered at `409-410`.

## 6. Examples / templates / gallery surface

- **None exists.** Grep for template/gallery/example hit only incidentals:
  `components/artifacts/CodeViewer.tsx:23` (`NEW_TEMPLATE` verilog stub) and
  `components/workbench/RunsPane.tsx:30` (CSS grid "column template" comment).
  No gallery, no example/template picker on the Launcher. (Session-templates are
  a *queued, unimplemented* plan — `plans/session-templates-and-forks-wave.md`.)

## 7. Hosted vs self-host detection (client-side)

- **Indirect only.** `lib/runtime-config.ts` injects backend URLs + OAuth client
  ids into `window.__SC_ENV__` at request time (`readServerEnv` `57-78`;
  injected in `layout.tsx:36-40`). The frontend infers mode purely from
  **whether an auth client id is set**: `authEnabled()` (`auth.tsx:77-79`) →
  `AccountChip` renders nothing in self-host (`AccountChip.tsx:37`). There is
  **no dedicated `/config` endpoint** exposing a `hosted` flag; BYOK's
  hosted-only nature is discovered by catching `err.status` 400/503 from
  `keysApi.list` (`api.ts:123-141`). So a landing page cannot cleanly read
  "hosted vs self-host" today beyond the auth-enabled signal.

## 8. Tests a redesign will break

- **E2E** — `frontend/e2e/workbench.smoke.spec.ts` is the binding contract.
  Asserts: `getTestId("session-card-<id>")`, `getByTitle("3 chats")`, group tag
  text `asu_hackathon`, search placeholder **"Search workspaces…"**, drawer
  testid `thread-drawer`, `New session` button, create-modal placeholder
  **"Workspace name — e.g. sync_fifo"**, live slug `untitled`/`new_block`, and
  URL `/w/{id}` (`workbench.smoke.spec.ts:95-154`); mocks at `19-93`.
- **Vitest** — `test/createSessionModal.refetchLoop.test.tsx` (guards the
  modal's mount-once effect) and `test/breadcrumb.test.tsx` (not
  Launcher-specific). No unit test snapshots the Launcher layout, so damage is
  concentrated in the two e2e tests above. Preserve the stable `data-testid`s
  and the exact placeholder strings.

## 9. README copy reusable for a hero

- **Root `README.md`**: tagline **"An autonomous LLM agent for RTL design,
  verification, and synthesis."** (`3`); badges MIT / Python / LangGraph /
  Next.js / MCP / **CVDP 68.5%** / Research (`5-11`); Overview + research
  questions (`16-30`); "Preliminary Results" table 46.7%→68.5% on CVDP
  (`34-46`); a rich **Capabilities** bullet list — spec-first, RTL gen,
  self-checking TBs, waveform debug, synth-to-GDSII, PPA, formal, XLS/HLS,
  schematic, reports (`50-62`). All strong landing copy.
- **`frontend/README.md`**: "production-quality Next.js frontend … Claude-style
  interface" (`3`); feature list + tech stack — Next 14, TS, Tailwind,
  shadcn/Radix, Zustand, Monaco (`5-27`). Somewhat stale (describes the old
  3-panel layout, not the v2 workbench/launcher).

## Notes for the redesign

- The header brand lockup (`Launcher.tsx:328-336`) and `EmptyLauncher`
  (`591-613`) are the two natural insertion points for a hero/landing section;
  both are self-contained.
- There is genuinely **no logo asset, no favicon, no `public/` dir, and no
  GitHub link** today — an open-source landing must supply all of these.
- Theme is class-based (`.light` on `<html>`, default dark); any new section
  must style via `--surface-*`/`--primary` tokens and read correctly in the
  "paper" light theme.
