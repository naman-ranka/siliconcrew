"use client";

import { Clock, CircuitBoard, Boxes, Zap, Gauge, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RunSummary, PpaMetrics } from "@/types";

/**
 * Pure selector: given the unified runs and a target synth runId, return the
 * run's PPA and the previous synth run to compare against. Exported for tests.
 */
export function selectPpaView(runs: RunSummary[], runId: string | null | undefined) {
  const synths = runs.filter((r) => r.kind === "synth");
  const current = (runId ? synths.find((r) => r.id === runId) : undefined) ?? synths[0];
  if (!current) return null;
  // "previous" = the next-older synth run by position (runs are newest-first).
  const idx = synths.findIndex((r) => r.id === current.id);
  const previous = idx >= 0 ? synths[idx + 1] : undefined;
  return { current, previous };
}

function fmt(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(digits);
}

function delta(cur: number | null | undefined, prev: number | null | undefined): { pct: number; better: boolean } | null {
  if (cur == null || prev == null || prev === 0) return null;
  const pct = ((cur - prev) / Math.abs(prev)) * 100;
  return { pct, better: cur <= prev }; // for area/cells/power lower is better
}

interface MetricCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
  d?: { pct: number; better: boolean } | null;
  lowerIsBetter?: boolean;
}

function MetricCard({ icon, label, value, unit, d, lowerIsBetter = true }: MetricCardProps) {
  return (
    <div className="rounded-lg border border-border bg-surface-1 p-3 flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground uppercase tracking-wide">
        {icon}
        {label}
      </div>
      <div className="text-lg font-semibold font-mono">
        {value}
        {unit && <span className="text-xs text-muted-foreground ml-1">{unit}</span>}
      </div>
      {d && (
        <div
          className={cn(
            "text-[10px] font-mono",
            (lowerIsBetter ? d.better : !d.better) ? "text-status-pass" : "text-status-fail"
          )}
        >
          {d.pct > 0 ? "+" : ""}
          {d.pct.toFixed(1)}% vs prev
        </div>
      )}
    </div>
  );
}

/**
 * Timing-hero + PPA + compare-vs-previous header for the Report.
 * Timing (WNS) is the star: met = green, violated = red. Status is meaning,
 * never the orange brand.
 */
export function PpaHero({ runs, runId }: { runs: RunSummary[]; runId: string | null | undefined }) {
  const view = selectPpaView(runs, runId);
  if (!view) return null;
  const { current, previous } = view;
  const ppa: PpaMetrics | undefined = current.ppa ?? undefined;
  if (!ppa) return null;

  const prev = previous?.ppa;
  const wns = ppa.wnsNs;
  const violated = wns != null && wns < 0;
  const timingKnown = wns != null;

  return (
    <div className="border-b border-border bg-surface-0 p-4">
      {/* Timing hero */}
      <div
        className={cn(
          "rounded-xl border p-4 mb-3 flex items-center gap-4",
          violated ? "border-status-fail/40 bg-status-fail/5" : "border-status-pass/40 bg-status-pass/5"
        )}
      >
        <div className={cn("h-10 w-10 rounded-lg flex items-center justify-center", violated ? "bg-status-fail/15" : "bg-status-pass/15")}>
          <Clock className={cn("h-5 w-5", violated ? "text-status-fail" : "text-status-pass")} />
        </div>
        <div className="flex flex-col">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Worst Negative Slack</span>
          <span className={cn("text-2xl font-bold font-mono", violated ? "text-status-fail" : "text-status-pass")}>
            {timingKnown ? `${fmt(wns)} ns` : "—"}
          </span>
        </div>
        <div className="ml-auto text-right">
          <span
            className={cn(
              "text-sm font-semibold px-2 py-1 rounded",
              violated ? "bg-status-fail/15 text-status-fail" : "bg-status-pass/15 text-status-pass"
            )}
          >
            {!timingKnown ? "unknown" : violated ? "TIMING VIOLATED" : "TIMING MET"}
          </span>
          {ppa.tnsNs != null && (
            <div className="text-[11px] text-muted-foreground font-mono mt-1">TNS {fmt(ppa.tnsNs)} ns</div>
          )}
        </div>
      </div>

      {/* PPA cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <MetricCard icon={<CircuitBoard className="h-3 w-3" />} label="Area" value={fmt(ppa.areaUm2)} unit="µm²" d={delta(ppa.areaUm2, prev?.areaUm2)} />
        <MetricCard icon={<Boxes className="h-3 w-3" />} label="Cells" value={fmt(ppa.cells)} d={delta(ppa.cells, prev?.cells)} />
        <MetricCard icon={<Gauge className="h-3 w-3" />} label="Fmax" value={fmt(ppa.fmaxMhz)} unit="MHz" d={delta(ppa.fmaxMhz, prev?.fmaxMhz)} lowerIsBetter={false} />
        <MetricCard icon={<Zap className="h-3 w-3" />} label="Power" value={fmt(ppa.powerMw)} unit="mW" d={delta(ppa.powerMw, prev?.powerMw)} />
      </div>

      {previous && (
        <div className="mt-2 text-[11px] text-muted-foreground flex items-center gap-1 font-mono">
          comparing <span className="text-info">{previous.id}</span>
          <ArrowRight className="h-3 w-3" />
          <span className="text-foreground">{current.id}</span>
        </div>
      )}
    </div>
  );
}
