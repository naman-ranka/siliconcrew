"use client";

import { useEffect, useState } from "react";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Check, Loader2, Server, Cpu } from "lucide-react";
import type { SynthStageId, SynthStageStatus } from "@/types";

// Coarse, human-readable breakdown of the ORFS flow (constraints is folded into
// "synth" for a cleaner six-step read: Synth → Floorplan → Place → CTS → Route
// → Finish).
const STAGES: { id: SynthStageId; label: string }[] = [
  { id: "synth", label: "Synth" },
  { id: "floorplan", label: "Floorplan" },
  { id: "place", label: "Place" },
  { id: "cts", label: "CTS" },
  { id: "grt", label: "Route" }, // grt+route → one "Route" step
  { id: "finish", label: "Finish" },
];

function fmtElapsed(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m > 0 ? `${m}m ${String(r).padStart(2, "0")}s` : `${r}s`;
}

/**
 * Live ORFS stage breakdown shown while a synth runs (so remote synth isn't a
 * featureless spinner): a coarse stepper synced to the job's per-stage status,
 * an elapsed timer, and the "Running on remote VM" label. Renders nothing when
 * no synth job is in flight.
 */
export function SynthStageProgress({ compact = false }: { compact?: boolean }) {
  const synthJob = useStore((s) => s.synthJob);

  // Tick a local clock so the elapsed timer advances between polls. Seeded from
  // the job's server-reported elapsed_sec at each update.
  const [baseElapsed, setBaseElapsed] = useState(0);
  const [baseAt, setBaseAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!synthJob) return;
    setBaseElapsed(synthJob.elapsedSec ?? 0);
    setBaseAt(Date.now());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [synthJob?.elapsedSec, synthJob?.jobId]);

  useEffect(() => {
    if (!synthJob) return;
    // Respect reduced-motion: tick less often if the user prefers reduced motion.
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const id = setInterval(() => setNow(Date.now()), reduce ? 2000 : 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [synthJob?.jobId]);

  if (!synthJob) return null;

  const elapsed = baseElapsed + (now - baseAt) / 1000;
  const stageMap = synthJob.stages ?? {};
  const current = synthJob.currentStage;

  const statusOf = (id: SynthStageId): SynthStageStatus => {
    // Map grt→route for the merged "Route" step: running/failed if either is.
    if (id === "grt") {
      const grt = stageMap.grt?.status;
      const route = stageMap.route?.status;
      if (grt === "failed" || route === "failed") return "failed";
      if (route === "completed") return "completed";
      if (grt === "running" || route === "running") return "running";
      if (grt === "completed") return "running"; // grt done, route in flight
      return grt ?? "pending";
    }
    return stageMap[id]?.status ?? "pending";
  };

  const label = synthJob.executionLabel || (synthJob.remote ? "remote VM" : "local");

  return (
    <div
      data-testid="synth-stage-progress"
      className={cn(
        "border-b border-border bg-surface-1 animate-fade-in motion-reduce:animate-none",
        compact ? "px-3 py-2" : "p-3"
      )}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <Cpu className="h-3.5 w-3.5 text-primary" />
          Synthesizing {synthJob.runId}
        </span>
        <span className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground">
          <Server className="h-3 w-3" />
          Running on {label}
        </span>
        <span className="text-[11px] font-mono tabular-nums text-muted-foreground">{fmtElapsed(elapsed)}</span>
      </div>

      <div className="flex items-center gap-1">
        {STAGES.map((stage, i) => {
          const st = statusOf(stage.id);
          const isCurrent = stage.id === current || (stage.id === "grt" && (current === "route" || current === "grt"));
          const done = st === "completed";
          const running = st === "running" || (isCurrent && st !== "completed" && st !== "failed");
          const failed = st === "failed";
          return (
            <div key={stage.id} className="flex items-center flex-1 min-w-0">
              <div className="flex items-center gap-1.5 min-w-0">
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] transition-colors duration-base ease-swift",
                    done
                      ? "bg-status-pass/15 text-status-pass"
                      : failed
                      ? "bg-status-fail/15 text-status-fail"
                      : running
                      ? "bg-primary/15 text-primary"
                      : "bg-surface-2 text-muted-foreground/60"
                  )}
                >
                  {done ? (
                    <Check className="h-3 w-3" />
                  ) : running ? (
                    <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" />
                  ) : (
                    i + 1
                  )}
                </span>
                <span
                  className={cn(
                    "truncate text-[11px] transition-colors duration-base ease-swift",
                    done
                      ? "text-foreground/70"
                      : running
                      ? "text-foreground font-medium"
                      : failed
                      ? "text-status-fail"
                      : "text-muted-foreground/60"
                  )}
                >
                  {stage.label}
                </span>
              </div>
              {i < STAGES.length - 1 && (
                <span
                  aria-hidden
                  className={cn(
                    "mx-1 h-px flex-1 min-w-2 transition-colors duration-base ease-swift",
                    done ? "bg-status-pass/40" : "bg-border"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
