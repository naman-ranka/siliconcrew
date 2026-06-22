"use client";

import { useState } from "react";
import { useStore } from "@/lib/store";
import { workbenchApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { statusDotClass, statusTextClass, relativeTime } from "./runStatus";
import { Pin, PinOff, GitBranch, Waves, Cpu, GitCompare, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PpaDiff, RunSummary } from "@/types";

const FILTERS: { id: "all" | "sim" | "synth"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "sim", label: "Sim" },
  { id: "synth", label: "Synth" },
];

/**
 * The unified runs timeline — sim + synth in one list, newest first, with
 * lineage (staged retries indent under their parent), pin, and compare. It is
 * the spine of provenance: selecting a run drives the viewers + the banner.
 */
export function RunsTimeline() {
  const {
    runs,
    selectedRunId,
    runKindFilter,
    setRunKindFilter,
    selectRun,
    pinRun,
    loadRuns,
    currentSession,
  } = useStore();

  const [compareMode, setCompareMode] = useState(false);
  const [compareSel, setCompareSel] = useState<string[]>([]);
  const [diff, setDiff] = useState<PpaDiff | null>(null);
  const [simDiff, setSimDiff] = useState<{
    a: RunSummary;
    b: RunSummary;
    rows: { metric: string; a: string; b: string }[];
  } | null>(null);

  const childrenByParent = new Map<string, RunSummary[]>();
  for (const r of runs) {
    if (r.parentRunId) {
      const arr = childrenByParent.get(r.parentRunId) ?? [];
      arr.push(r);
      childrenByParent.set(r.parentRunId, arr);
    }
  }
  const roots = runs.filter((r) => !r.parentRunId || !runs.some((x) => x.id === r.parentRunId));

  const toggleCompare = async (id: string) => {
    const next = compareSel.includes(id)
      ? compareSel.filter((x) => x !== id)
      : [...compareSel, id].slice(-2);
    setCompareSel(next);
    setDiff(null);
    setSimDiff(null);
    if (next.length !== 2 || !currentSession) return;
    const [ra, rb] = next.map((id) => runs.find((r) => r.id === id));
    // Sim runs have no PPA — a synth PPA table would be all dashes. Build a
    // sim-aware diff locally (status / failure time / pass marker) instead.
    if (ra?.kind === "sim" && rb?.kind === "sim") {
      setSimDiff({
        a: ra,
        b: rb,
        rows: [
          { metric: "Status", a: ra.status, b: rb.status },
          { metric: "Top", a: ra.top ?? "—", b: rb.top ?? "—" },
          {
            metric: "Failure @",
            a: ra.failure?.timeNs != null ? `${ra.failure.timeNs}ns` : "—",
            b: rb.failure?.timeNs != null ? `${rb.failure.timeNs}ns` : "—",
          },
          { metric: "Pass marker", a: ra.passMarkerFound ? "yes" : "no", b: rb.passMarkerFound ? "yes" : "no" },
        ],
      });
      return;
    }
    try {
      setDiff(await workbenchApi.compareRuns(currentSession.id, next[0], next[1]));
    } catch {
      setDiff(null);
    }
  };

  const renderRow = (r: RunSummary, depth: number) => {
    const selected = r.id === selectedRunId;
    const inCompare = compareSel.includes(r.id);
    return (
      <div key={r.id}>
        <div
          className={cn(
            "group flex items-center gap-2 px-2 py-1.5 mx-1 rounded-md cursor-pointer outline-none",
            "focus-visible:ring-2 focus-visible:ring-primary/60",
            selected ? "bg-primary/10 border border-primary/40" : "border border-transparent hover:bg-surface-2",
            inCompare && "ring-1 ring-info/60"
          )}
          style={{ paddingLeft: 8 + depth * 14 }}
          role="button"
          tabIndex={0}
          aria-pressed={selected}
          aria-label={`${compareMode ? "Compare" : "View"} run ${r.id} — ${r.status}`}
          onClick={() => (compareMode ? void toggleCompare(r.id) : void selectRun(r.id))}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              compareMode ? void toggleCompare(r.id) : void selectRun(r.id);
            }
          }}
          data-run-id={r.id}
          data-run-kind={r.kind}
        >
          {depth > 0 && <GitBranch className="h-3 w-3 text-muted-foreground/60 shrink-0" />}
          <span className={cn("h-2 w-2 rounded-full shrink-0", statusDotClass(r.status))} />
          <span className="shrink-0 text-muted-foreground">
            {r.kind === "sim" ? <Waves className="h-3.5 w-3.5" /> : <Cpu className="h-3.5 w-3.5" />}
          </span>
          <div className="flex flex-col min-w-0 flex-1 leading-tight">
            <span className="text-xs font-mono truncate">
              {r.id}
              {r.top ? <span className="text-muted-foreground"> · {r.top}</span> : null}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {r.status}
              {r.kind === "sim" && r.failure?.timeNs != null ? ` @ ${r.failure.timeNs}ns` : ""}
              {r.createdAt ? ` · ${relativeTime(r.createdAt)}` : ""}
            </span>
          </div>
          <button
            type="button"
            className={cn(
              "shrink-0 text-muted-foreground hover:text-primary transition-opacity outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-primary/60 rounded",
              r.pinned ? "opacity-100 text-primary" : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
            )}
            title={r.pinned ? "Unpin" : "Pin (protect from prune)"}
            aria-label={r.pinned ? `Unpin ${r.id}` : `Pin ${r.id}`}
            aria-pressed={r.pinned}
            onClick={(e) => {
              e.stopPropagation();
              void pinRun(r.id, !r.pinned);
            }}
          >
            {r.pinned ? <Pin className="h-3.5 w-3.5" /> : <PinOff className="h-3.5 w-3.5" />}
          </button>
        </div>
        {(childrenByParent.get(r.id) ?? []).map((c) => renderRow(c, depth + 1))}
      </div>
    );
  };

  return (
    <div className="flex flex-col min-h-0 border-t border-border">
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Runs</span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className={cn("h-6 w-6", compareMode && "text-info")}
            title="Compare two runs"
            aria-label="Compare two runs"
            aria-pressed={compareMode}
            onClick={() => {
              setCompareMode((v) => !v);
              setCompareSel([]);
              setDiff(null);
              setSimDiff(null);
            }}
          >
            <GitCompare className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" title="Refresh runs" aria-label="Refresh runs" onClick={() => void loadRuns()}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex gap-1 px-3 pb-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setRunKindFilter(f.id)}
            className={cn(
              "text-[10px] px-2 py-0.5 rounded-full border",
              runKindFilter === f.id
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:bg-surface-2"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {compareMode && (
        <div className="px-3 pb-2 text-[10px] text-info">
          {compareSel.length < 2 ? `Select ${2 - compareSel.length} more run(s) to compare` : "Comparing"}
        </div>
      )}

      <div className="flex-1 overflow-y-auto thin-scrollbar pb-1 max-h-[40vh]">
        {runs.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-muted-foreground">
            No runs yet. Use the pipeline to Lint / Simulate / Synthesize.
          </div>
        ) : (
          roots.map((r) => renderRow(r, 0))
        )}
      </div>

      {simDiff && (
        <div className="border-t border-border p-2 text-[10px] font-mono">
          <div className="text-info mb-1">
            {simDiff.a.id} → {simDiff.b.id}
          </div>
          {simDiff.rows.map((row) => (
            <div key={row.metric} className="flex justify-between gap-2">
              <span className="text-muted-foreground">{row.metric}</span>
              <span className="text-right">
                <span className={row.metric === "Status" ? statusTextClass(simDiff.a.status) : ""}>{row.a}</span>
                <span className="text-muted-foreground"> → </span>
                <span className={row.metric === "Status" ? statusTextClass(simDiff.b.status) : ""}>{row.b}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {diff && (
        <div className="border-t border-border p-2 text-[10px] font-mono">
          <div className="text-info mb-1">
            {diff.a} → {diff.b}
          </div>
          {diff.rows.map((row) => (
            <div key={row.metric} className="flex justify-between">
              <span className="text-muted-foreground">{row.metric}</span>
              <span>
                {row.a ?? "—"} → {row.b ?? "—"}
                {row.deltaPct != null && (
                  <span className={row.deltaPct <= 0 ? "text-status-pass ml-1" : "text-status-fail ml-1"}>
                    ({row.deltaPct > 0 ? "+" : ""}
                    {row.deltaPct}%)
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
