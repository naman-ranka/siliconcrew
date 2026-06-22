"use client";

import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { statusDotClass, latestOfKind } from "./runStatus";
import type { RunStatus } from "@/types";
import { FileText, Code2, CheckCircle2, Waves, Cpu, BadgeCheck, Loader2 } from "lucide-react";

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
}

/**
 * The pipeline IS the spine: Spec→RTL→Lint→Sim→Synth→Signoff with live status.
 * It doubles as the run actions — Lint/Sim/Synth trigger the action endpoints,
 * the rest jump to the relevant artifact. Status is carried by a colored dot
 * (meaning), the brand orange marks the active/primary stage.
 */
export function PipelineStepper() {
  const {
    manifest,
    runs,
    lintResult,
    report,
    actionPending,
    currentSession,
    activeArtifactTab,
    setArtifactTab,
    runLint,
    runSim,
    runSynth,
  } = useStore();

  const hasRtl = !!manifest?.files.some((f) => f.role === "rtl");
  const hasTb = !!manifest?.files.some((f) => f.role === "tb");
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
      onClick: () => setArtifactTab("spec"),
    },
    {
      id: "rtl",
      name: "RTL",
      icon: <Code2 className="h-4 w-4" />,
      status: hasRtl ? "passed" : undefined,
      statusText: hasRtl ? `${manifest!.files.filter((f) => f.role === "rtl").length} file(s)` : "none",
      desc: "Your Verilog/SystemVerilog source files.",
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
      onClick: () => void runSynth(),
    },
    {
      id: "signoff",
      name: "Signoff",
      icon: <BadgeCheck className="h-4 w-4" />,
      status: latestSynth?.status === "passed" ? "passed" : undefined,
      statusText: report || latestSynth?.reportAvailable ? "report" : "—",
      desc: "Final timing/area/power report for the synthesized design.",
      onClick: () => setArtifactTab("report"),
    },
  ];

  const activeId: StageId =
    activeArtifactTab === "spec"
      ? "spec"
      : activeArtifactTab === "code"
      ? "rtl"
      : activeArtifactTab === "waveform"
      ? "sim"
      : activeArtifactTab === "report" || activeArtifactTab === "layout"
      ? "synth"
      : "lint";

  return (
    <div className="flex items-stretch gap-1 px-3 py-2 border-b border-border bg-surface-1 overflow-x-auto">
      {stages.map((stage, i) => {
        const isActive = stage.id === activeId;
        return (
          <div key={stage.id} className="flex items-center">
            <button
              type="button"
              disabled={disabled || (stage.isAction && stage.pending)}
              onClick={stage.onClick}
              data-stage={stage.id}
              data-status={stage.status ?? "none"}
              title={`${stage.isAction ? `Run ${stage.name}` : `View ${stage.name}`} — ${stage.desc}`}
              aria-label={`${stage.isAction ? `Run ${stage.name}` : `View ${stage.name}`} — ${stage.desc}`}
              aria-pressed={isActive}
              aria-busy={stage.pending || undefined}
              className={cn(
                "group flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-left transition-all min-w-[112px]",
                "border outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                isActive
                  ? "border-primary/60 bg-primary/10"
                  : "border-transparent hover:bg-surface-2",
                (disabled || (stage.isAction && stage.pending)) && "opacity-50 cursor-not-allowed"
              )}
            >
              <span className={cn("shrink-0", isActive ? "text-primary" : "text-muted-foreground")}>
                {stage.pending ? <Loader2 className="h-4 w-4 animate-spin" /> : stage.icon}
              </span>
              <span className="flex flex-col leading-tight">
                <span className={cn("text-xs font-medium flex items-center gap-1.5", isActive && "text-foreground")}>
                  {stage.name}
                  {stage.isAction && (
                    <span className="text-[9px] uppercase tracking-wide text-primary/70 group-hover:text-primary">
                      run
                    </span>
                  )}
                </span>
                <span className="flex items-center gap-1.5">
                  {stage.status && <span className={cn("h-1.5 w-1.5 rounded-full", statusDotClass(stage.status))} />}
                  <span className="text-[10px] text-muted-foreground font-mono truncate max-w-[88px]">
                    {stage.statusText}
                  </span>
                </span>
              </span>
            </button>
            {i < stages.length - 1 && <span className="text-muted-foreground/40 px-0.5 select-none">→</span>}
          </div>
        );
      })}
    </div>
  );
}
