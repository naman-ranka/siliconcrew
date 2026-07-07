# Open-source landing page — implementation report

Branch: `claude/overnight-showcase`. Scope: frontend only. Delivers the OSS
landing as **layout emphasis on the ONE `/` Launcher route** (no second route),
per `plans/open-source-landing.md`.

## What was built (by plan item)

1. **OSS identity.** New `frontend/components/branding/Logo.tsx` — a real,
   ownable SVG mark (stroked silicon-die motif: package + core + pins on four
   sides), all `currentColor` so it themes for free. Replaces the bare lucide
   `CircuitBoard` glyph in the header brand lockup and appears in the hero and
   footer. Favicon via the App Router file convention `frontend/app/icon.svg`
   (filled brand-orange die, legible at 16px), mirrored to
   `frontend/public/favicon.svg` (the `public/` dir did not exist). The old
   `layout.tsx` `icons.icon: "/favicon.ico"` reference 404'd — removed; Next now
   auto-wires `/icon.svg`. `layout.tsx` metadata title/description reframed for
   open source (verified live in the served HTML `<title>`/`<meta>`).

2. **GitHub + Issues.** Always-visible icon links in the header right cluster
   (lucide `Github` + `CircleDot`), plus buttons in the hero and links in the
   footer. All URLs centralized in `frontend/components/branding/links.ts`
   (`REPO_URL`, `ISSUES_URL`, `DOCS_URL`, `LICENSE_URL`) — single source, with a
   `// TODO(owner): confirm the canonical PUBLIC repo URL` fence. Currently
   `https://github.com/naman-ranka/siliconcrew`.

3. **Hero / what-it-is.** `frontend/components/branding/Hero.tsx`: the README
   tagline ("An autonomous LLM agent for RTL design, verification, and
   synthesis."), the flow line, 4 capability bullets drawn verbatim-in-spirit
   from README Capabilities, the open EDA tool names (OpenROAD, Yosys, Icarus
   Verilog, Verilator, sky130), and the ONE real sourced number — CVDP 68.5%
   (63/92), marked "preliminary" and linked to the README results. No fabricated
   stars/social-proof/telemetry (invariant 4).

4. **Examples gallery.** Reused the Wave 11 gallery as-is (`ExampleCard`,
   `TemplatePreview`, store `templates`/`loadTemplates`/`forkTemplate`). Did NOT
   rebuild it. Re-placed by posture (see below); the `examplesBlock` section and
   its SWR "populated data never blanks" contract are untouched.

5. **Session picker = one section.** Behavior/data flow of the Recent/Grouped
   list + search + create is unchanged. Only placement changed:
   - Empty / signed-out account → Hero, then gallery, then the create CTA
     (`EmptyLauncher`), then footer. An empty account is no longer a dead end.
   - Signed-in *with sessions* → their workspaces render first; the gallery
     drops below them; footer anchors the page. (Posture keys on
     `sessions.length`, which is the honest signal in both self-host and hosted
     — auth is not configured in self-host, so "has work" is the right pivot.)

6. **Footer.** `frontend/components/branding/LandingFooter.tsx` — mark + "Open
   source, MIT-licensed" + GitHub / Issues / Docs / License links. No fake build
   stamp.

## Files

- New: `components/branding/{Logo,Hero,LandingFooter}.tsx`, `links.ts`;
  `app/icon.svg`; `public/favicon.svg`; `test/landing.test.tsx`.
- Edited: `components/launcher/Launcher.tsx` (logo lockup, header repo links,
  posture reorder, hero/footer wiring), `app/layout.tsx` (metadata + favicon).
- Untouched by design: `lib/store.ts`, `lib/api.ts`, `ExampleCard.tsx`,
  `TemplatePreview.tsx`, `Breadcrumb.tsx`, all backend.

## Commits (per item)

- `feat(landing): OSS identity — SVG logo, favicon, metadata` — logo, favicon,
  links.ts, layout metadata.
- `feat(landing): open-source Launcher — hero, gallery framing, footer, repo
  links` — Launcher integration + `test/landing.test.tsx`.

Both pushed to `origin/claude/overnight-showcase`.

## Gate results

- `npx tsc --noEmit` — pass (clean).
- `npx vitest run` — 367 pass + 7 new (`test/landing.test.tsx`) = 374 pass; the
  ONLY failure is the pre-existing `test/chat.threads.store.test.ts` (a
  `threadsApi.create` signature mismatch, unrelated to this work — **verified it
  fails identically on the stashed clean tree**).
- `npx next build` — pass; `/` = 12 kB / 168 kB First Load; `/icon.svg` route
  registered.
- Playwright `workbench.smoke.spec.ts -g "launcher"` — 2/2 pass (bundled
  chromium). The preserved e2e contract holds: "Search workspaces…" /
  "Workspace name — e.g. sync_fifo" strings and `session-card-*` /
  `thread-drawer` / `open-settings` testids all intact.

## Screenshots

In `plans/overnight-20260706/reports/img/`:
- `landing-empty.png` / `landing-empty-light.png` — signed-out/empty posture,
  dark + paper light. Hero + gallery + create CTA.
- `landing-populated.png` / `landing-populated-light.png` — has-sessions
  posture: workspaces first, gallery below, footer.

Both themes verified to render correctly via the design tokens.

## Design decisions flagged for owner review

- **Repo URL**: `naman-ranka/siliconcrew` (working remote). `// TODO(owner)` in
  `links.ts` — confirm the canonical *public* repo, or point at a mirror.
- **Logo motif**: a stroked silicon-die glyph (consistent with the old
  CircuitBoard vibe). `// TODO(owner)` in `Logo.tsx` if a wafer/crew emblem is
  preferred. The favicon is a filled brand-orange variant for tab legibility.
- **CVDP claim**: shown as "68.5% CVDP no_commercial", `title`="63/92, graded in
  NVIDIA's reference container (preliminary)", linked to README. Sourced, not
  fabricated. Owner may prefer to omit a headline number entirely on the landing.
- **Hero copy**: capability bullets mirror README:50-62; `// TODO(owner)` fences
  in `Hero.tsx` for wording/trimming.
- **Posture pivot** is `sessions.length`, not auth state — because self-host has
  no auth. Worth confirming that "signed-in with sessions → picker first" is the
  intended read of the plan (it is what shipped).

## Deferred / not done

- No scroll-to-gallery anchor or "Browse examples" jump from the hero (kept
  restrained; can add if wanted).
- Playwright run used the bundled Windows chromium, not `PW_EXECUTABLE`
  (Linux-container path absent here); only the two Launcher e2e tests were run,
  not the full workbench suite.
