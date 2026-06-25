export const meta = {
  name: "ide-usability-eval",
  description: "Per-design IDE usability critiques + synthesized clean-IDE report",
  phases: [
    { title: "Evaluate", detail: "8 agents, one per design, judge the captured live-UI flow" },
    { title: "Synthesize", detail: "aggregate into FINDINGS.md + clean-IDE redesign" },
  ],
};

const DESIGNS = [
  { dir: "01_mux2", label: "2:1 mux (combinational baseline)" },
  { dir: "02_adder4", label: "4-bit adder (multi-bit combinational)" },
  { dir: "03_dff", label: "D flip-flop (first clocked element)" },
  { dir: "04_counter8", label: "8-bit counter (sequential)" },
  { dir: "05_shiftreg", label: "8-bit shift register (sequential)" },
  { dir: "06_seqdet", label: "1011 sequence detector (FSM)" },
  { dir: "07_alu4", label: "4-bit ALU (datapath)" },
  { dir: "08_fifo", label: "depth-4 FIFO (hardest)" },
];

const ROOT = "/home/user/siliconcrew";
const SHOTS = `${ROOT}/plans/phase2/screenshots/ide-eval`;

const FINDING_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["design", "verdict", "stages", "discoverability", "gimmicky_vs_needed", "top_friction", "clean_ide_note"],
  properties: {
    design: { type: "string" },
    verdict: { type: "string", description: "1-2 sentences: could a human get this design to lint+sim results without confusion?" },
    stages: {
      type: "array",
      description: "one entry per stage actually observed",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["stage", "worked", "severity", "note"],
        properties: {
          stage: { type: "string" },
          worked: { type: "string", enum: ["yes", "partial", "no", "n/a"] },
          severity: { type: "string", enum: ["blocker", "major", "minor", "none"] },
          note: { type: "string", description: "cite screenshot/timeline evidence" },
        },
      },
    },
    discoverability: { type: "array", items: { type: "string" } },
    gimmicky_vs_needed: {
      type: "object",
      additionalProperties: false,
      required: ["earned", "noise"],
      properties: {
        earned: { type: "array", items: { type: "string" }, description: "UI elements that earned their space for THIS design" },
        noise: { type: "array", items: { type: "string" }, description: "UI elements that were clutter/noise for THIS design" },
      },
    },
    top_friction: { type: "array", items: { type: "object", additionalProperties: false, required: ["issue", "fix"], properties: { issue: { type: "string" }, fix: { type: "string" } } } },
    clean_ide_note: { type: "string" },
  },
};

phase("Evaluate");
const findings = await parallel(
  DESIGNS.map((d) => () =>
    agent(
      `You are a hardware engineer using the SiliconCrew IDE for the FIRST time to take ONE design — ${d.label} — from RTL to results. Judge REAL usability from captured evidence; do not merely describe screenshots.

Read the captured live-UI flow for this design:
- Screenshots (Read each PNG): ${SHOTS}/${d.dir}/01-workbench-empty.png, 02-files-uploaded.png, 03-lint.png, 04-sim.png, 05-wave.png, 06-synth.png, 07-view-rtl.png, 08-view-spec.png, 09-view-signoff.png, 10-chat-route.png
- Timeline (timings, console output, JS errors, failed network requests): ${SHOTS}/${d.dir}/timeline.json

Context + the hard environment constraints you MUST honor (do NOT report these as product bugs):
- Read ${ROOT}/plans/phase2/ide-eval/README.md and ${ROOT}/plans/phase2/ide-eval/EVALUATOR_PROMPT.md
- No LLM key here -> the AI Assistant pane is inert; judge only its placement/clutter on the human path.
- No Docker/OpenROAD -> Synthesize cannot finish; it shows a long "running...no output" interim then fails ~60s later with signoff:fail. Judge the FEEDBACK UX (latency, clarity), not the missing GDS.

Ground your UI judgments in the source where useful:
- ${ROOT}/frontend/components/workbench/  (PipelineStepper, FileTree, Console, etc.)
- ${ROOT}/frontend/components/artifacts/  (the viewers)
- ${ROOT}/frontend/app/workbench/page.tsx and ${ROOT}/frontend/app/page.tsx (the two routes)

Be specific and cite evidence (which screenshot / timeline entry). Focus on: discoverability, whether the staged pipeline is necessary or gimmicky, error/empty-state handling, and whether the write->test->sim->iterate loop is smooth.`,
      { label: `eval:${d.dir}`, phase: "Evaluate", schema: FINDING_SCHEMA }
    ).then((f) => ({ ...(f || {}), design: d.dir, label: d.label }))
  )
);

const ok = findings.filter(Boolean);
log(`collected ${ok.length}/${DESIGNS.length} design critiques`);

phase("Synthesize");
const summary = await agent(
  `You are a senior product designer + RTL tools engineer. Synthesize 8 first-person usability critiques of the SiliconCrew IDE into ONE decisive report, then WRITE it to ${ROOT}/plans/phase2/ide-eval/FINDINGS.md.

The 8 structured critiques (JSON):
${JSON.stringify(ok, null, 2)}

Also read these cross-cutting references yourself before writing:
- ${ROOT}/plans/phase2/ide-eval/README.md (method + environment ceiling)
- A few screenshots to see the layout firsthand, e.g. ${SHOTS}/01_mux2/04-sim.png, ${SHOTS}/06_seqdet/05-wave.png, ${SHOTS}/08_fifo/06-synth.png
- ${ROOT}/frontend/app/workbench/page.tsx and ${ROOT}/frontend/components/workbench/PipelineStepper.tsx

The user's brief, verbatim intent: the current UI feels "very gimmicky — all these stages and I don't know if it's required." They want a CLEAN IDE where a human can, by himself: write code, test it, run simulation, run synthesis, check output, and iterate. Answer that head-on.

FINDINGS.md must contain, in this order:
1. **Executive summary** — can a human do write->lint->sim->iterate today? (with the honest environment caveats stated once).
2. **Verdict: are the stages gimmicky or needed?** — a direct, evidence-backed ruling on the pipeline stepper and each major panel (Files, Artifacts tabs Spec/Code/Wave/Schem/Layout/Report, Console Lint/Sim/Synth, Runs, AI Assistant, the two routes). State which elements earned their space across designs and which were consistently noise.
3. **Cross-cutting friction (ranked)** — the issues that recurred across designs, each with severity + a concrete fix. Pull the strongest recurring items from the critiques (e.g. two-route split, View-vs-Run conflation in the pipeline bar, empty Wave on passing sim w/o $dumpvars, silent/slow synth failure, JS 404s).
4. **Per-design table** — design x {lint, sim, wave, synth} status + 1 friction headline each.
5. **Proposed clean IDE** — a concrete redesign: the minimal layout (describe panels/regions), what to MERGE, what to CUT, what to DEFER behind progressive disclosure, and how the write->test->sim->iterate loop should feel. Include a simple ASCII wireframe of the proposed layout.
6. **Quick wins vs bigger bets** — a short prioritized list.

Be specific and opinionated; this is decision-support, not a survey. After writing the file, return a 6-8 line summary of the headline conclusions and the single most important redesign recommendation.`,
  { label: "synthesize", phase: "Synthesize" }
);

return { evaluated: ok.length, findingsFile: `${ROOT}/plans/phase2/ide-eval/FINDINGS.md`, summary };
