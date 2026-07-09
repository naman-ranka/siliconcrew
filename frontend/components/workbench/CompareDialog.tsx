"use client";

import { useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { workbenchApi } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { PpaDiff } from "@/types";

interface CompareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Which delta direction is an IMPROVEMENT, by metric label (matched
// case-insensitively as a substring): +1 = bigger is better, -1 = smaller is
// better. Unknown metrics → neutral coloring.
const PER_METRIC_GOOD_DIRECTION: Record<string, 1 | -1> = {
  wns: 1,
  fmax: 1,
  area: -1,
  power: -1,
  tns: -1,
  cells: -1,
};

function goodDirection(metric: string): 1 | -1 | 0 {
  const m = metric.toLowerCase();
  for (const [key, dir] of Object.entries(PER_METRIC_GOOD_DIRECTION)) {
    if (m.includes(key)) return dir;
  }
  return 0;
}

function deltaClass(metric: string, deltaPct: number | null | undefined): string {
  if (deltaPct == null) return "text-muted-foreground";
  const dir = goodDirection(metric);
  if (dir === 0 || deltaPct === 0) return "text-muted-foreground";
  return (deltaPct > 0) === (dir === 1) ? "text-status-pass" : "text-status-fail";
}

function fmt(v: number | null): string {
  return v == null ? "—" : String(v);
}

/**
 * PPA comparison between two synth runs (BottomDock "Compare" button):
 * A/B selects over synth runs that carry PPA metrics, delta table with
 * good/bad coloring per metric direction.
 */
export function CompareDialog({ open, onOpenChange }: CompareDialogProps) {
  const currentSession = useStore((s) => s.currentSession);
  const runs = useStore((s) => s.runs);
  const sid = currentSession?.id ?? null;

  // Candidates: synth runs with PPA, newest-first (runs[] already is).
  const candidates = useMemo(
    () => runs.filter((r) => r.kind === "synth" && r.ppa),
    [runs]
  );

  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  const [diff, setDiff] = useState<PpaDiff | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Default to the two most recent comparable runs whenever the dialog opens
  // with stale/empty picks.
  useEffect(() => {
    if (!open) return;
    const ids = candidates.map((r) => r.id);
    setA((cur) => (cur && ids.includes(cur) ? cur : ids[0] ?? ""));
    setB((cur) => (cur && ids.includes(cur) ? cur : ids[1] ?? ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, candidates]);

  useEffect(() => {
    if (!open || !sid || !a || !b) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    workbenchApi
      .compareRuns(sid, a, b)
      .then((d) => {
        if (!cancelled) setDiff(d);
      })
      .catch((e) => {
        if (!cancelled) {
          setDiff(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, sid, a, b, attempt]);

  const picker = (
    label: string,
    value: string,
    onChange: (v: string) => void
  ) => (
    <div className="flex min-w-0 flex-1 flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <Select value={value || undefined} onValueChange={onChange}>
        <SelectTrigger className="h-8 font-mono text-xs" aria-label={`Run ${label}`}>
          <SelectValue placeholder="Pick a run…" />
        </SelectTrigger>
        <SelectContent>
          {candidates.map((r) => (
            <SelectItem key={r.id} value={r.id} className="font-mono text-xs">
              {r.id}
              {r.top ? ` · ${r.top}` : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-sm">Compare runs</DialogTitle>
          <DialogDescription className="text-xs">
            PPA delta between two synthesis runs (Δ% is B relative to A).
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-end gap-2">
          {picker("A", a, setA)}
          {picker("B", b, setB)}
        </div>

        {error ? (
          <div className="flex items-center justify-between gap-2 rounded border border-status-fail/40 bg-status-fail/10 px-2 py-1.5 text-[11px] text-status-fail">
            <span className="min-w-0 truncate">Compare failed: {error}</span>
            <button
              type="button"
              onClick={() => setAttempt((n) => n + 1)}
              className="shrink-0 rounded border border-status-fail/40 px-1.5 py-0.5 outline-none hover:bg-status-fail/20 focus-visible:ring-1 focus-visible:ring-status-fail/60"
            >
              Retry
            </button>
          </div>
        ) : loading ? (
          <div className="space-y-1.5" aria-hidden="true">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="grid grid-cols-[1.2fr_1fr_1fr_0.8fr] gap-2">
                <Skeleton className="h-3.5 w-16" />
                <Skeleton className="h-3.5 w-12" />
                <Skeleton className="h-3.5 w-12" />
                <Skeleton className="h-3.5 w-10" />
              </div>
            ))}
          </div>
        ) : diff ? (
          <div className="font-mono text-[11px]">
            <div className="grid grid-cols-[1.2fr_1fr_1fr_0.8fr] gap-2 border-b border-border pb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              <span>Metric</span>
              <span className="truncate" title={diff.a}>
                A · {diff.a}
              </span>
              <span className="truncate" title={diff.b}>
                B · {diff.b}
              </span>
              <span>Δ%</span>
            </div>
            {diff.rows.map((row) => (
              <div
                key={row.metric}
                className="grid grid-cols-[1.2fr_1fr_1fr_0.8fr] gap-2 border-b border-border/50 py-1"
              >
                <span className="text-muted-foreground">{row.metric}</span>
                <span>{fmt(row.a)}</span>
                <span>{fmt(row.b)}</span>
                <span className={cn(deltaClass(row.metric, row.deltaPct))}>
                  {row.deltaPct != null
                    ? `${row.deltaPct > 0 ? "+" : ""}${row.deltaPct}%`
                    : "—"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-2 text-center text-[11px] text-muted-foreground">
            {candidates.length < 2
              ? "Need at least two synth runs with PPA metrics to compare."
              : "Pick two runs to compare."}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
