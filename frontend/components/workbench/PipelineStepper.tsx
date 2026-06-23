"use client";

import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { statusDotClass, latestOfKind } from "./runStatus";
import type { RunStatus } from "@/types";
import { IconTooltip } from "@/components/ui/tooltip";
import { FileText, Code2, CheckCircle2, Waves, Cpu, BadgeCheck, Loader2, Play } from "lucide-react";

type StageId = "spec" | "rtl" | "lint" | "sim" | "synth" | "signoff";

interface Stage {
  id: StageId;
  name: string;
  icon: React.ReactNode;
  status?: RunStatus;
  statusText: string;
  desc: string; // plain-language explanation (newcomer tooltip)
  onClick: () => void;
  pending?: boolean;
  isAction?: boolean;
  reached?: boolean; // pipeline progress has arrived at / through this stage
}

/**
 * The pipeline IS the spine: Spec→RTL→Lint→Sim→Synth→Signoff with live status.
 * It doubles as the run actions — Lint/Sim/Synth trigger the action endpoints,
 * the rest jump to the relevant artifact. Status is carried by a colored dot
 * (meaning), the brand orange marks the active/primary stage. Connectors between
 * stages fill in as the pipeline advances, reading as a real stepper.
 */
export function PipelineStepper() {
  const {
    manifest,
    runs,
    lintResult,
    report,
    actionPending,
    currentSession,
    setArtifactTab,
    runLint,
    runSim,
    runSynth,
  } = useStore();

  const hasRtl = !!manifest?.files.some((f) => f.role === "rtl");
  const latestSim = latestOfKind(runs, "sim");
  const latestSynth = latestOfKind(runs, "synth");
  const disabled = !currentSession;

  const stages: Stage[] = [
    {
      id: "spec",
      name: "Spec",
      icon: <FileText className="h-4 w-4" />,
      statusText: manifest ? `${manifest.synthTop || "—"}` : "no spec",
      desc: "Design intent — the module, its ports, and the clock.",
      reached: !!manifest,
      onClick: () => setArtifactTab("spec"),
    },
    {
      id: "rtl",
      name: "RTL",
      icon: <Code2 className="h-4 w-4" />,
      status: hasRtl ? "passed" : undefined,
      statusText: hasRtl ? `${manifest!.files.filter((f) => f.role === "rtl").length} file(s)` : "none",
      desc: "Your Verilog/SystemVerilog source files.",
      reached: hasRtl,
      onClick: () => setArtifactTab("code"),
    },
    {
      id: "lint",
      name: "Lint",
      icon: <CheckCircle2 className="h-4 w-4" />,
      status: lintResult ? lintResult.status : undefined,
      statusText: lintResult
        ? lintResult.status === "passed"
          ? `${lintResult.warnings.length} warn`
          : `${lintResult.errors.length} err`
        : "run lint",
      desc: "Check the RTL compiles — catches syntax errors fast.",
      pending: actionPending.lint,
      isAction: true,
      reached: !!lintResult,
      onClick: () => void runLint(),
    },
    {
      id: "sim",
      name: "Simulate",
      icon: <Waves className="h-4 w-4" />,
      status: latestSim?.status,
      statusText: latestSim
        ? latestSim.status === "failed"
          ? `fail${latestSim.failure?.timeNs != null ? ` @ ${latestSim.failure.timeNs}ns` : ""}`
          : latestSim.status
        : "run sim",
      desc: "Run the testbench and check the design behaves (needs a *_tb).",
      pending: actionPending.sim,
      isAction: true,
      reached: !!latestSim,
      onClick: () => void runSim(),
    },
    {
      id: "synth",
      name: "Synthesize",
      icon: <Cpu className="h-4 w-4" />,
      status: latestSynth?.status,
      statusText: latestSynth ? latestSynth.status : "run synth",
      desc: "Map RTL to real gates + place & route (OpenROAD).",
      pending: actionPending.synth,
      isAction: true,
      reached: !!latestSynth,
      onClick: () => void runSynth(),
    },
    {
      id: "signoff",
      name: "Signoff",
      icon: <BadgeCheck className="h-4 w-4" />,
      status: latestSynth?.status === "passed" ? "passed" : undefined,
      statusText: report || latestSynth?.reportAvailable ? "report" : "—",
      desc: "Final timing/area/power report for the synthesized design.",
      reached: latestSynth?.status === "passed" || !!report,
      onClick: () => setArtifactTab("report"),
    },
  ];

  // The highlighted stage should read as "what's current". A running (or
  // just-triggered) action is the strongest signal of where the pipeline is —
  // running Sim must light up Simulate even if the center stays on the Code
  // tab. Only fall back to the artifact-tab mapping when nothing is pending.
  const pendingStage: StageId | null = actionPending.synth
    ? "synth"
    : actionPending.sim
    ? "sim"
    : actionPending.lint
    ? "lint"
    : null;

  // Idle fallback: reflect actual PIPELINE PROGRESS — the furthest stage the
  // pipeline has reached — NOT the artifact tab being viewed. (Viewing Wave must
  // not light up "Simulate" if the pipeline has since synthesized.) Synth is a
  // running action, not a passive "reached" milestone, so once it has *passed*
  // we point at Signoff; otherwise we land on the furthest reached stage.
  const progressStage: StageId = (() => {
    if (latestSynth?.status === "passed" || report) return "signoff";
    // Walk the stages newest→oldest and pick the last one marked reached.
    for (let i = stages.length - 1; i >= 0; i--) {
      if (stages[i].reached) return stages[i].id;
    }
    return "spec";
  })();

  const activeId: StageId = pendingStage ?? progressStage;

  return (
    <div className="flex items-stretch gap-0.5 px-3 py-1.5 border-b border-border bg-surface-1 overflow-x-auto">
      {stages.map((stage, i) => {
        const isActive = stage.id === activeId;
        const isBusy = !!(stage.isAction && stage.pending);
        const isDisabled = disabled || isBusy;
        const verb = stage.isAction ? `Run ${stage.name}` : `View ${stage.name}`;
        // The connector between this stage and the next "leads into" the next
        // stage — fill it once progress has reached the next stage (or this one
        // is running), so the line advances visibly as lint/sim/synth complete.
        const next = stages[i + 1];
        const connectorFilled = !!next?.reached;
        return (
          <div key={stage.id} className="flex items-center">
            <IconTooltip
              side="bottom"
              label={
                <span className="flex flex-col gap-0.5">
                  <span className="font-medium">{verb}</span>
                  <span className="text-popover-foreground/70">{stage.desc}</span>
                </span>
              }
            >
            <button
              type="button"
              disabled={isDisabled}
              onClick={stage.onClick}
              data-stage={stage.id}
              data-status={stage.status ?? "none"}
              aria-label={`${verb} — ${stage.desc}`}
              aria-pressed={isActive}
              aria-busy={stage.pending || undefined}
              className={cn(
                "group relative flex h-9 items-center gap-2 rounded-lg px-2.5 text-left min-w-[108px]",
                "border outline-none transition-all duration-base ease-swift",
                "focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-1 focus-visible:ring-offset-surface-1",
                isActive
                  ? "border-primary/60 bg-primary/10 shadow-e1"
                  : isDisabled
                  ? "border-transparent"
                  : "border-transparent hover:border-border hover:bg-surface-2 active:scale-[0.98]",
                isDisabled && "opacity-50 cursor-not-allowed"
              )}
            >
              <span
                className={cn(
                  "relative shrink-0 transition-colors duration-base ease-swift",
                  isActive
                    ? "text-primary"
                    : stage.isAction && !isDisabled
                    ? "text-foreground/70 group-hover:text-primary"
                    : "text-muted-foreground"
                )}
              >
                {isBusy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : stage.isAction && !isDisabled ? (
                  <>
                    {/* default: stage icon; hover: run glyph — clearer "click to run" affordance */}
                    <span className="block transition-opacity duration-base ease-swift group-hover:opacity-0">
                      {stage.icon}
                    </span>
                    <Play className="absolute inset-0 h-4 w-4 fill-current opacity-0 transition-opacity duration-base ease-swift group-hover:opacity-100" />
                  </>
                ) : (
                  stage.icon
                )}
              </span>
              <span className="flex min-w-0 flex-col leading-tight">
                <span
                  className={cn(
                    "flex items-center gap-1.5 text-xs font-medium transition-colors duration-base ease-swift",
                    isActive ? "text-foreground" : "text-foreground/80"
                  )}
                >
                  {stage.name}
                </span>
                <span className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      "h-1.5 w-1.5 shrink-0 rounded-full transition-all duration-base ease-swift",
                      stage.status
                        ? statusDotClass(stage.status)
                        : "scale-75 bg-muted-foreground/30"
                    )}
                  />
                  <span className="truncate max-w-[80px] font-mono text-[11px] text-muted-foreground">
                    {stage.statusText}
                  </span>
                </span>
              </span>
            </button>
            </IconTooltip>
            {i < stages.length - 1 && (
              <span aria-hidden className="flex w-4 shrink-0 items-center justify-center">
                <span
                  className={cn(
                    "h-px w-full transition-colors duration-base ease-swift",
                    connectorFilled ? "bg-primary/40" : "bg-border"
                  )}
                />
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
