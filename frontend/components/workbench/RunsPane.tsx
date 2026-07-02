"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  CornerDownRight,
  Cpu,
  Layers,
  Pin,
  Waves,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { useSessionUi } from "@/lib/workbenchUiStore";
import { openArtifact } from "@/lib/openArtifact";
import { groupRuns } from "@/lib/runsGrouping";
import { relativeTime, statusDotClass, statusTextClass } from "./runStatus";
import { Skeleton } from "@/components/ui/skeleton";
import type { RunSummary } from "@/types";

const KIND_FILTERS: { id: "all" | "sim" | "synth"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "sim", label: "Sim" },
  { id: "synth", label: "Synth" },
];

// Shared column template: Run | Top | Result | Age | Artifacts | Pin
const GRID = "grid grid-cols-[minmax(0,1.4fr)_minmax(0,0.9fr)_minmax(0,1.3fr)_60px_72px_28px] items-center gap-2 px-2";

function primaryArtifactKey(r: RunSummary): string {
  return r.kind === "sim" ? `wave:${r.id}` : `report:${r.id}`;
}

/**
 * The Runs table (BottomDock "Runs" tab): sim + synth in one lineage-grouped
 * table — retries indent under their root — with unread markers, artifact
 * glyphs and pinning.
 */
export function RunsPane() {
  const currentSession = useStore((s) => s.currentSession);
  const runs = useStore((s) => s.runs);
  const runsLoading = useStore((s) => s.runsLoading);
  const pinRun = useStore((s) => s.pinRun);
  const synthJob = useStore((s) => s.synthJob);
  const sid = currentSession?.id ?? null;
  const { unreadRunIds, clearUnread } = useSessionUi(sid);

  const [kind, setKind] = useState<"all" | "sim" | "synth">("all");

  const groups = useMemo(() => {
    const filtered = kind === "all" ? runs : runs.filter((r) => r.kind === kind);
    return groupRuns(filtered);
  }, [runs, kind]);

  const open = (r: RunSummary) => {
    if (!sid) return;
    openArtifact(sid, primaryArtifactKey(r));
    clearUnread(r.id);
  };

  const renderRow = (r: RunSummary, isChild: boolean) => {
    const unread = unreadRunIds.includes(r.id);
    return (
      <div
        key={r.id}
        role="button"
        tabIndex={0}
        onClick={() => open(r)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            open(r);
          }
        }}
        aria-label={`Open run ${r.id}`}
        className={cn(
          GRID,
          "h-8 cursor-pointer border-b border-border/50 outline-none hover:bg-surface-2 focus-visible:ring-1 focus-visible:ring-primary/60"
        )}
        data-run-id={r.id}
        data-run-kind={r.kind}
      >
        {/* Run */}
        <span className={cn("flex min-w-0 items-center gap-1.5", isChild && "pl-4")}>
          {isChild ? (
            <CornerDownRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          ) : null}
          <span className={cn("h-2 w-2 shrink-0 rounded-full", statusDotClass(r.status))} />
          <span className="shrink-0 text-muted-foreground">
            {r.kind === "sim" ? <Waves className="h-3 w-3" /> : <Cpu className="h-3 w-3" />}
          </span>
          <span className="truncate font-mono text-xs">{r.id}</span>
          {unread ? (
            <span
              title="new"
              className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary animate-pulse-subtle"
            />
          ) : null}
        </span>

        {/* Top */}
        <span className="truncate font-mono text-[11px] text-muted-foreground">
          {r.top ?? "—"}
        </span>

        {/* Result */}
        <span className="flex min-w-0 items-center gap-1.5 text-[11px]">
          <span className={cn("truncate", statusTextClass(r.status))}>
            {r.status}
            {r.kind === "sim" && r.status === "failed" && r.failure?.timeNs != null
              ? ` @ ${r.failure.timeNs}ns`
              : ""}
          </span>
          {r.kind === "synth" &&
          r.status === "running" &&
          r.id === synthJob?.runId &&
          synthJob.currentStage ? (
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
              · {synthJob.currentStage}
            </span>
          ) : null}
          {r.kind === "synth" && r.status === "passed" && r.ppa?.wnsNs != null ? (
            <span
              title="Worst negative slack"
              className={cn(
                "shrink-0 rounded px-1 font-mono text-[10px]",
                r.ppa.wnsNs >= 0
                  ? "bg-status-pass/10 text-status-pass"
                  : "bg-status-fail/10 text-status-fail"
              )}
            >
              {r.ppa.wnsNs >= 0 ? "+" : ""}
              {r.ppa.wnsNs}ns
            </span>
          ) : null}
        </span>

        {/* Age */}
        <span className="text-[10px] text-muted-foreground">{relativeTime(r.createdAt)}</span>

        {/* Artifacts */}
        <span className="flex items-center justify-end gap-1">
          {r.kind === "sim" ? (
            <button
              type="button"
              title="Open waveform"
              aria-label={`Open waveform of ${r.id}`}
              onClick={(e) => {
                e.stopPropagation();
                if (!sid) return;
                openArtifact(sid, `wave:${r.id}`);
                clearUnread(r.id);
              }}
              className="rounded p-0.5 text-muted-foreground outline-none hover:bg-surface-3 hover:text-foreground focus-visible:ring-1 focus-visible:ring-primary/60"
            >
              <Activity className="h-3 w-3" />
            </button>
          ) : (
            <>
              <button
                type="button"
                title="Open report"
                aria-label={`Open report of ${r.id}`}
                onClick={(e) => {
                  e.stopPropagation();
                  if (!sid) return;
                  openArtifact(sid, `report:${r.id}`);
                  clearUnread(r.id);
                }}
                className="rounded p-0.5 text-muted-foreground outline-none hover:bg-surface-3 hover:text-foreground focus-visible:ring-1 focus-visible:ring-primary/60"
              >
                <BarChart3 className="h-3 w-3" />
              </button>
              <button
                type="button"
                title="Open layout"
                aria-label={`Open layout of ${r.id}`}
                onClick={(e) => {
                  e.stopPropagation();
                  if (!sid) return;
                  openArtifact(sid, `layout:${r.id}`);
                  clearUnread(r.id);
                }}
                className="rounded p-0.5 text-muted-foreground outline-none hover:bg-surface-3 hover:text-foreground focus-visible:ring-1 focus-visible:ring-primary/60"
              >
                <Layers className="h-3 w-3" />
              </button>
            </>
          )}
        </span>

        {/* Pin */}
        <span className="flex items-center justify-end">
          <button
            type="button"
            title={r.pinned ? "Unpin" : "Pin (protect from prune)"}
            aria-label={r.pinned ? `Unpin ${r.id}` : `Pin ${r.id}`}
            aria-pressed={r.pinned}
            onClick={(e) => {
              e.stopPropagation();
              void pinRun(r.id, !r.pinned);
            }}
            className={cn(
              "rounded p-0.5 outline-none focus-visible:ring-1 focus-visible:ring-primary/60",
              r.pinned
                ? "text-primary"
                : "text-muted-foreground hover:bg-surface-3 hover:text-foreground"
            )}
          >
            <Pin className={cn("h-3 w-3", r.pinned && "fill-current")} />
          </button>
        </span>
      </div>
    );
  };

  return (
    <div className="flex flex-col">
      {/* Kind filter */}
      <div className="flex h-7 shrink-0 items-center gap-1 border-b border-border px-2">
        {KIND_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setKind(f.id)}
            aria-pressed={kind === f.id}
            className={cn(
              "rounded-full border px-1.5 py-px text-[10px] outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
              kind === f.id
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:bg-surface-2"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Table header */}
      <div
        className={cn(
          GRID,
          "h-6 shrink-0 border-b border-border text-[10px] uppercase tracking-wide text-muted-foreground"
        )}
      >
        <span>Run</span>
        <span>Top</span>
        <span>Result</span>
        <span>Age</span>
        <span className="text-right">Artifacts</span>
        <span />
      </div>

      {runsLoading && runs.length === 0 ? (
        <div aria-hidden="true">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className={cn(GRID, "h-8 border-b border-border/50")}>
              <span className="flex items-center gap-1.5">
                <Skeleton className="h-2 w-2 rounded-full" />
                <Skeleton className="h-3 w-3 rounded" />
                <Skeleton className="h-3 w-20" />
              </span>
              <Skeleton className="h-3 w-14" />
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-10" />
              <Skeleton className="ml-auto h-3 w-8" />
              <span />
            </div>
          ))}
        </div>
      ) : runs.length === 0 ? (
        <div className="px-3 py-6 text-center text-xs text-muted-foreground">
          No runs yet — lint, simulate or synthesize from ⌘K.
        </div>
      ) : (
        <div>
          {groups.map((g) => (
            <div key={g.root.id}>
              {renderRow(g.root, false)}
              {g.children.map((c) => renderRow(c, true))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
