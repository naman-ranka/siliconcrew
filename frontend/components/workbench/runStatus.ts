import { workbenchApi } from "@/lib/api";
import { useStore } from "@/lib/store";
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

/** Parse a tool's JSON result defensively — /invoke returns the tool's raw
 *  result, which may arrive as a JSON string or an already-parsed object. */
export function parseToolJsonResult(result: unknown): Record<string, unknown> | null {
  if (result && typeof result === "object" && !Array.isArray(result)) {
    return result as Record<string, unknown>;
  }
  if (typeof result === "string") {
    try {
      const parsed = JSON.parse(result);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      /* not JSON — nothing to apply */
    }
  }
  return null;
}

/**
 * User-gesture run Refresh: calls get_synthesis_status THROUGH /invoke — the
 * same primitive every actor uses, so the gesture is logged as a source:"ui"
 * activity event — then applies the payload to the run row + last-known
 * status via the store's applyRunStatus.
 */
export async function refreshRunStatus(sessionId: string, runId: string): Promise<void> {
  const res = await workbenchApi.invokeTool(sessionId, "get_synthesis_status", { run_id: runId });
  const parsed = parseToolJsonResult(res.result);
  if (parsed) useStore.getState().applyRunStatus(parsed);
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
