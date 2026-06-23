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
  known?: boolean;
}

function isKnown(v: number | null | undefined): boolean {
  return v != null && !Number.isNaN(v);
}

function MetricCard({ icon, label, value, unit, d, lowerIsBetter = true, known = true }: MetricCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3 flex flex-col gap-1.5 shadow-e1",
        known ? "border-border bg-surface-1" : "border-dashed border-border/70 bg-surface-1/40"
      )}
    >
      <div className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
        <span className="text-muted-foreground/70">{icon}</span>
        {label}
      </div>
      {known ? (
        <div className="text-xl font-semibold font-mono tabular-nums leading-none text-foreground">
          {value}
          {unit && <span className="text-xs font-normal text-muted-foreground ml-1">{unit}</span>}
        </div>
      ) : (
        <div className="text-sm font-medium leading-none text-muted-foreground/70 italic">
          Not computed
        </div>
      )}
      {known && d && (
        <div
          className={cn(
            "text-[10px] font-mono tabular-nums",
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
  // Timing semantics: a real WNS ≥ 0 = met (green); WNS < 0 = violated (red);
  // null/unknown = NEUTRAL (never green — green means "timing met", which we
  // cannot claim for an uncomputed slack).
  const timingKnown = isKnown(wns);
  const violated = timingKnown && (wns as number) < 0;
  const met = timingKnown && (wns as number) >= 0;
  // Tone: pass (green) only when met; fail (red) when violated; otherwise
  // neutral surface colors.
  const tone = met ? "pass" : violated ? "fail" : "neutral";

  return (
    <div className="border-b border-border bg-surface-0 p-4">
      {/* Timing hero */}
      <div
        className={cn(
          "rounded-xl border p-4 mb-3 flex items-center gap-4 shadow-e1",
          tone === "fail"
            ? "border-status-fail/40 bg-status-fail/5"
            : tone === "pass"
            ? "border-status-pass/40 bg-status-pass/5"
            : "border-border bg-surface-1"
        )}
      >
        <div
          className={cn(
            "h-11 w-11 shrink-0 rounded-lg flex items-center justify-center",
            tone === "fail" ? "bg-status-fail/15" : tone === "pass" ? "bg-status-pass/15" : "bg-surface-2"
          )}
        >
          <Clock
            className={cn(
              "h-5 w-5",
              tone === "fail" ? "text-status-fail" : tone === "pass" ? "text-status-pass" : "text-muted-foreground"
            )}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Worst Negative Slack</span>
          <span
            className={cn(
              "text-2xl font-bold font-mono tabular-nums leading-none",
              tone === "fail" ? "text-status-fail" : tone === "pass" ? "text-status-pass" : "text-muted-foreground"
            )}
          >
            {timingKnown ? `${fmt(wns)} ns` : "—"}
          </span>
        </div>
        <div className="ml-auto flex flex-col items-end gap-1 text-right">
          <span
            className={cn(
              "text-xs font-semibold uppercase tracking-wide px-2 py-1 rounded-md",
              tone === "fail"
                ? "bg-status-fail/15 text-status-fail"
                : tone === "pass"
                ? "bg-status-pass/15 text-status-pass"
                : "bg-surface-2 text-muted-foreground"
            )}
          >
            {!timingKnown ? "Not computed" : violated ? "Timing violated" : "Timing met"}
          </span>
          {isKnown(ppa.tnsNs) && (
            <div className="text-[11px] text-muted-foreground font-mono tabular-nums">TNS {fmt(ppa.tnsNs)} ns</div>
          )}
        </div>
      </div>

      {/* PPA cards — null metrics render as a neutral "Not computed" state. */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <MetricCard icon={<CircuitBoard className="h-3 w-3" />} label="Area" value={fmt(ppa.areaUm2)} unit="µm²" d={delta(ppa.areaUm2, prev?.areaUm2)} known={isKnown(ppa.areaUm2)} />
        <MetricCard icon={<Boxes className="h-3 w-3" />} label="Cells" value={fmt(ppa.cells)} d={delta(ppa.cells, prev?.cells)} known={isKnown(ppa.cells)} />
        <MetricCard icon={<Gauge className="h-3 w-3" />} label="Fmax" value={fmt(ppa.fmaxMhz)} unit="MHz" d={delta(ppa.fmaxMhz, prev?.fmaxMhz)} lowerIsBetter={false} known={isKnown(ppa.fmaxMhz)} />
        <MetricCard icon={<Zap className="h-3 w-3" />} label="Power" value={fmt(ppa.powerMw)} unit="mW" d={delta(ppa.powerMw, prev?.powerMw)} known={isKnown(ppa.powerMw)} />
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
