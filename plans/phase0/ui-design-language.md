# UI Design Language (Phase 1 guidance)

High-level direction for the workbench. Be a senior product designer: these are
principles + tokens + curated references, **not** pixel specs. Decide the
details, but stay inside this language. The non-functional target is
`mockups/workbench.html`; this doc supersedes its *colors* (the mockup used a
cold slate theme — move to the warm Claude-inspired palette below).

## Inspiration (study these, then translate to hardware)

The workbench should feel like the best 2026 agentic dev tools, adapted to the
hardware-design domain. Fetch and study:

- **Claude / Anthropic design language** — warmth, calm, rounded, approachable.
  - https://www.anthropic.com/news/claude-design-anthropic-labs
  - https://mobbin.com/colors/brand/claude  (brand palette)
  - https://github.com/ComposioHQ/awesome-claude-skills/blob/master/brand-guidelines/SKILL.md
- **OpenAI Codex app** — "the UI is the product": multi-agent threads by
  project, worktrees, inline diff review + comment, git ops tucked away.
  - https://openai.com/index/introducing-the-codex-app/
- **Google Antigravity** — Agent Manager as a *peer* to the editor; Artifacts
  (plans, task lists, screenshots, recordings) as verifiable deliverables; a
  review pane you comment on like a Google Doc.
  - https://antigravity.google/docs/artifacts
  - https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/
- **Agentic UX patterns** — ReAct transparency, no "black-box launch,"
  explainability-on-demand, status/override/error-recovery.
  - https://agentic-design.ai/patterns/ui-ux-patterns
  - https://fuselabcreative.com/ui-design-for-ai-agents/

## Color — Claude-inspired, warm (not cold slate)

Primary = **warm grey + Claude orange**; secondary accent = a **proper blue**.
Seed values from Anthropic's brand (adapt for a dense, mostly-dark tool UI):

| Token | Value (seed) | Use |
|---|---|---|
| Brand / primary action | **`#d97757`** (Claude orange; strong: `#C15F3C`) | primary buttons, active flow stage, brand, focus/selection emphasis |
| Accent / info | **`#6a9bcc`** (Claude blue) | links, info, "viewing X" banner, secondary selection |
| Neutral dark base | `#141413` → warm panels `#1e1c19`, `#262320` | backgrounds, panels (warm greys, **not** blue-slate) |
| Neutral light | `#faf9f5` / warm greys | text, light theme "paper" option |

**Semantic colors are separate from brand — and must not collide with the
orange.** This is the key senior call: in EDA, amber usually means "warning,"
but orange is now the *brand/primary*. So:

| Meaning | Color | Note |
|---|---|---|
| pass / timing met | green `#788c5d` (Claude green) or brighter `#3fb950` | |
| fail / violated | a clear red (`#cc5b49`, warm to match palette) | Claude has no brand red; pick a warm one |
| warning | a distinct **yellow** amber `#d6a221` | keep it visibly *yellower* than the orange brand, or pair with an icon, so warnings ≠ primary |
| running | blue `#6a9bcc` or a violet | never reuse orange for status |

Reserve the warm orange for **brand + primary/interactive**; carry **status**
in green/red/yellow + icons. Default to a **warm dark** theme; optionally offer
a light "Claude paper" theme. Tailwind already drives the app — express these as
CSS variables / Tailwind theme tokens, not hard-coded hexes.

## Typography

Claude brand uses Poppins (headings) + Lora (serif body) — that's marketing.
For a **dense tool UI**, prefer a clean UI sans (Inter or system-ui) + a real
mono (JetBrains Mono / Berkeley Mono / system mono) for code, signals, and PPA
values. You may use a rounded sans for headings to nod to Claude's warmth.
Carry the brand feel through **color + rounded corners + spacing**, not serifs.

## Patterns to adopt (from the inspirations → our domain)

- **Artifacts are first-class.** Our six viewers (spec/code/wave/schematic/
  layout/report) *are* Antigravity-style Artifacts. The agent should emit
  plans / task-lists, and tool-calls render as inline artifact cards.
- **Tool-call transparency, never a black box.** Show what the agent runs (the
  tools already return the exact `iverilog`/`vvp`/ORFS commands). ReAct-style
  thought → action → observation, visible.
- **Approve-before-apply.** Agent proposes fixes; the user approves (Claude
  Code's permission model). Never silent mutation.
- **Runs = threads.** Codex organizes work as reviewable threads; our runs
  timeline is the equivalent — selectable, comparable, with lineage.
- **Calm, not busy.** Claude's restraint: generous spacing, few accents, status
  carried by small dots/badges, the agent collapsed until invited.

## Guardrails

- One accent of warm orange per view as the primary; don't rainbow.
- Status color is meaning, never decoration.
- Match the existing shadcn/ui + Tailwind system; theme via tokens.
- Accessibility: check contrast on the warm dark theme (orange-on-dark and
  text-on-warm-grey both need AA).
