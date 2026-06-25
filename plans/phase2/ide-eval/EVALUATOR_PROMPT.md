# Per-design evaluator agent brief (reused for all 8)

Each evaluator agent role-plays a **hardware engineer sitting down with this IDE
for the first time** to take ONE design from RTL to results. It judges real
usability from the captured evidence — it does NOT just describe screenshots.

## Inputs given to each agent
- `plans/phase2/screenshots/ide-eval/<design>/*.png` — the captured flow.
- `plans/phase2/screenshots/ide-eval/<design>/timeline.json` — timings, result
  text, console output, JS errors, failed network requests.
- `plans/phase2/ide-eval/README.md` — context + environment constraints.
- Frontend source for grounding: `frontend/components/workbench/*`,
  `frontend/components/artifacts/*`, `frontend/app/workbench/*`, `frontend/app/page.tsx`.

## Environment caveats the agent MUST honor (don't report these as product bugs)
- No LLM key → the AI Assistant pane is non-functional here; judge it only on
  *whether its presence/placement helps or clutters the human path*.
- No Docker/OpenROAD → Synthesize cannot complete; it fails after ~60s with
  `signoff: fail`, null metrics. Judge the *feedback UX* of that (latency to
  feedback, clarity of the eventual error), not the absence of GDS.

## Required structured output (return as Markdown with these headings)
1. **Verdict (1–2 sentences)** — could a human get this design from RTL to
   lint+sim results without confusion?
2. **Stage-by-stage** — for each of {create session, find workbench, add files,
   Lint, Simulate, view Waveform, Synthesize, inspect results}: worked? time?
   friction (cite screenshot/timeline)? severity (blocker/major/minor/none).
3. **Discoverability** — what was hard to find or unlabeled? (e.g. two routes,
   pipeline bar mixing "View" + "Run", hidden panels).
4. **Gimmicky-vs-needed** — of the visible UI elements (pipeline stepper, Files,
   Artifacts tabs, Console tabs, Runs, AI Assistant, Spec/Schem/Layout/Signoff
   tabs), which earned their space for THIS design and which were noise?
5. **Top 3 friction points** (ranked, each with a concrete fix).
6. **Clean-IDE note** — one paragraph: what would the ideal minimal IDE show for
   this design's write→test→sim→iterate loop?
