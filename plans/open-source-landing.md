# Open-source landing page — plan (GROUNDED, ready to implement)

Status: READY. Grounded in `reports/launcher-map.md` (file:line). Sequence AFTER
the Wave 11 adversarial review is triaged (the landing edits Launcher.tsx, which
Wave 11 also touched — serialize to avoid contention) and integrates the gallery
Wave 11 already shipped.

## Grounding (from launcher-map.md — verified in code)

- `/` route: `app/page.tsx:11-19` → `components/launcher/Launcher.tsx:55-589`
  (self-contained). **Insertion points:** the header brand lockup
  (`Launcher.tsx:328-336` — a lucide `CircuitBoard` glyph + text "SiliconCrew",
  NO svg logo) and `EmptyLauncher` (`591-613`, "No workspaces yet").
- **Net-new for OSS (none exist today, verified):** no `public/` dir, no favicon
  (`/favicon.ico` referenced in `layout.tsx:84` but ABSENT), no logo asset, and
  **zero GitHub/external links anywhere in the frontend**. The landing must
  supply all of these.
- **Wave 11 ALREADY shipped the gallery** (impl-templates): `Launcher` Examples
  section + `ExampleCard` + `TemplatePreview` + `templatesApi` + store
  `loadTemplates`/`forkTemplate`. The landing INTEGRATES/places this, does not
  rebuild it. (launcher-map predates it and says "none" — reconcile against the
  live Wave 11 components.)
- **Design tokens:** `app/globals.css` HSL CSS vars; `--primary` = Claude orange
  `14 63% 60%`; surface ladder `--surface-0..3`; `.dark` default on `<html>`
  (`layout.tsx:33`), `.light` "paper" via `ThemeToggle`. Fonts Inter + JetBrains
  Mono (`globals.css:6-7`). Icons `lucide-react`. New sections MUST style via
  `--surface-*`/`--primary` tokens and read correctly in BOTH themes.
- **Metadata:** `layout.tsx:12-24` title "SiliconCrew Architect", description
  "Autonomous RTL Design Agent…". Update for OSS + add a real favicon.
- **Hosted vs self-host:** only indirect — `authEnabled()` (`auth.tsx:77-79`);
  no `/config` hosted flag. A landing can use the auth-enabled signal only.
- **README copy (reuse for hero):** root `README.md:3` tagline "An autonomous
  LLM agent for RTL design, verification, and synthesis."; badges incl. MIT +
  **CVDP 68.5%**; a strong Capabilities list (spec-first, RTL gen, self-checking
  TBs, waveform debug, synth-to-GDSII, PPA, formal, XLS/HLS) — all real, usable.
- **DO-NOT-BREAK (e2e contract, `workbench.smoke.spec.ts:95-154`):** preserve
  testids `session-card-<id>`, `thread-drawer`, `open-settings`; and the EXACT
  strings "Search workspaces…" and "Workspace name — e.g. sync_fifo". Only two
  e2e tests bind the Launcher; no unit test snapshots its layout.

## The ask (owner, verbatim in spirit)

The first page must make it unmistakable that SiliconCrew is a serious
**open-source hardware-design project** — GitHub, issues, the things a credible
OSS project has — with the **examples/templates gallery** as a first-class
showcase (fork → see the files, the agent's tool trajectory, the transcripts).
The **session picker becomes ONE element, not the whole page.** This is the
top-priority end state of the night.

## Principles (from CLAUDE.md — a landing page is not exempt)

- **Honest, hardware-designers-first, no demo theater.** No fake stars/among
  metrics, no "trusted by" fabrication, no simulated liveness (invariant 4).
  Every number shown is real or absent.
- **Fundamental & simple over clever.** A boring, durable, tasteful landing that
  loads fast and says true things — not a marketing splash.
- **Signed-in vs signed-out are different jobs.** Signed-out: "what is this,
  why should I care, how do I look inside" (identity + gallery + GitHub/issues).
  Signed-in: their workspaces come first (the picker), with the OSS identity as
  persistent chrome, not a wall between them and their work.
- **URL is the source of truth**; the store follows the URL (invariant 7). No new
  client-side polling; reuse existing data paths.

## Proposed structure (single `/` route, posture by auth state)

A vertical composition on `/` (Launcher), top to bottom:

1. **Identity header / hero (new, compact).** Logo + "SiliconCrew" + a one-line
   honest tagline (e.g. "Open-source AI-assisted RTL-to-GDS with open EDA
   tools"). Primary actions: **GitHub** (repo), **Issues** (new-issue/issues
   list), **New session**, account/theme/settings (existing). Keep it one row on
   desktop, collapsing gracefully — this is where "open source" reads instantly.
   - Links point to the real repo: `github.com/naman-ranka/siliconcrew` (verify
     the canonical public URL before shipping; may differ if a public mirror is
     the intended OSS home).
2. **What it is (signed-out emphasis).** A short, honest "spec → RTL → lint →
   sim → synthesis/PnR → GDS, driven by an agent, on OpenROAD + iverilog/
   verilator" strip — 3-5 plain capability bullets pulled from README, no
   invented benchmarks. Collapses/reduces for signed-in users (they know).
3. **Examples gallery (the showcase; NEW — depends on Wave 11 templates).**
   The curated bundles (7-seg seconds, ASU p1 seq_detector, ASU p9 FIR, traffic
   light, LFSR, Simon) as cards: name, one-line pitch, real highlight bullets
   from `template.json`, file/run counts. Card → preview (files + transcript
   names + "what's inside") → **Fork this example**. Reuses SessionCard visual
   language; NO status-dot verdicts (revision 1). This section is what turns a
   visitor into someone who has *seen the agent work*.
   - Hard dependency: the Wave 11 templates backend + `templatesApi` +
     gallery/preview components (task #10). If Wave 11 isn't landed, ship the
     landing with the gallery behind a real "examples coming" state that is
     honest (not a fake gallery), OR sequence landing after Wave 11. Prefer
     sequencing after Wave 11 so the gallery is real on first paint.
4. **Your workspaces (the session picker — now ONE section, not the page).**
   The existing Recent/Grouped session list, search, create — unchanged
   behavior, reframed as a section beneath the identity + gallery for
   signed-out/empty users, and floated to the TOP for signed-in users with
   existing sessions (their work is the priority once they're in).
   - Empty state ("No workspaces yet") stays honest but now sits below a page
     that already explained the project and showed forkable examples — so an
     empty account is no longer a dead end.
5. **Footer (new, small).** GitHub, Issues, License, docs/README link, version/
   commit (honest build stamp if cheap). Standard OSS footer.

## Posture logic

- **Signed-out / empty account:** hero + what-it-is + gallery first; picker/empty
  state last. The page sells the project and invites a fork.
- **Signed-in with sessions:** picker floats up (their workspaces first); hero
  compresses to the header row; gallery remains available lower or via a tab.
- Implement as ordering/emphasis on ONE page (like the IDE/agent postures are
  "layout emphasis only, same stores") — not two separate routes.

## Explicitly NOT doing (fences)

- No new backend endpoints solely for the landing if existing ones suffice
  (settings/auth flags, sessions list, templates list). Verify what exists.
- No fabricated social proof, no animated marketing, no telemetry-driven
  "N designs taped out" unless that number is real and cheap to compute.
- No change to session-picker behavior/data flow — only its placement/framing.
- No status dots at session level (invariant 4).

## Open questions for the owner (morning)

- Canonical public GitHub URL for the OSS home (the working remote is
  `naman-ranka/siliconcrew` — is that the public face, or a mirror?).
- Tagline wording + whether to name the open EDA tools explicitly (OpenROAD,
  Yosys, iverilog, Verilator, sky130) — good for credibility with designers.
- Sequencing: land Wave 11 templates FIRST so the gallery is real on first
  paint (recommended), vs. ship landing with an honest "examples coming" state.

## Net-new assets to create

- A simple, tasteful **SVG logo** (inline component or `public/logo.svg`) —
  circuit/silicon motif consistent with the `CircuitBoard` glyph already used;
  themeable via `currentColor`/tokens.
- A real **favicon** (`public/favicon.ico` or `app/icon.svg`) — the referenced
  one is missing; a 404 today.
- Create the `public/` dir (none exists).

## Test list

- vitest: hero/identity renders with GitHub+Issues links (real hrefs); gallery
  section renders cards + honest empty state; picker still renders + creates;
  posture ordering (signed-in picker-first vs signed-out gallery-first).
- e2e: signed-out `/` shows project identity + GitHub/Issues + gallery; fork
  from a card lands in `/w/{id}`; signed-in `/` shows workspaces first.
- Gates: tsc · vitest · Playwright · next build.
