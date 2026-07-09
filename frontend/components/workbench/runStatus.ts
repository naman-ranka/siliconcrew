import type { RunStatus, RunSummary } from "@/types";

/** Tailwind text color for a run/stage status (status = meaning, never brand). */
export function statusTextClass(status: RunStatus | "info" | undefined): string {
  switch (status) {
    case "passed":
      return "text-status-pass";
    case "failed":
      return "text-status-fail";
    case "running":
      return "text-status-running";
    default:
      return "text-muted-foreground";
  }
}

export function statusDotClass(status: RunStatus | "info" | undefined): string {
  switch (status) {
    case "passed":
      return "bg-status-pass";
    case "failed":
      return "bg-status-fail";
    case "running":
      return "bg-status-running animate-pulse-subtle";
    default:
      return "bg-muted-foreground";
  }
}

export function latestOfKind(runs: RunSummary[], kind: "sim" | "synth"): RunSummary | undefined {
  return runs.find((r) => r.kind === kind);
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
