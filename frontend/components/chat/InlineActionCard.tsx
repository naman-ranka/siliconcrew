"use client";

import { useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  Plug,
  User,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { artifactKeyForActivity } from "@/lib/toolArtifacts";
import { OpenArtifactButton } from "./ToolCallCard";
import type { ActivityEvent } from "@/types";

// Inline manual-action card (agent shell, S5-2): the SAME fact the IDE shows
// as an Activity dock row, worn as a conversation card — "You ran a command"
// (IDE/right-click) or "From your AI (MCP)". Body mirrors ToolCallCard's
// compact tool-line + expandable args/result, fed from the activity event.

function XMark({ className }: { className?: string }) {
  // Tiny local ✕ to avoid clashing with lucide's X import in consumers.
  return <span className={cn("font-mono leading-none", className)}>✕</span>;
}

export function InlineActionCard({ event }: { event: ActivityEvent }) {
  const [expanded, setExpanded] = useState(false);
  const isMcp = event.source === "mcp";
  const openKey = artifactKeyForActivity(event);
  const secs =
    event.durationMs != null ? Math.round(event.durationMs / 100) / 10 : null;

  return (
    <div
      className="flex items-start gap-2 animate-fade-in"
      data-testid="inline-action-card"
      data-source={event.source}
    >
      <div className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-info/10">
        {isMcp ? (
          <Plug className="h-3.5 w-3.5 text-info" aria-hidden />
        ) : (
          <User className="h-3.5 w-3.5 text-info" aria-hidden />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <span className="font-medium text-info/80">
            {isMcp ? "From your AI (MCP)" : "You ran a command"}
          </span>
        </div>

        <div className="rounded-md border border-border/50 bg-surface-1/60 px-2 py-1.5 text-xs">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="group flex w-full items-center gap-1.5 text-left text-muted-foreground/80 transition-colors hover:text-foreground"
          >
            <span className="shrink-0">
              {event.status === "running" ? (
                <Loader2 className="h-3 w-3 animate-spin text-primary/70" aria-hidden />
              ) : event.status === "error" ? (
                <XMark className="text-[11px] text-destructive/70" />
              ) : (
                <Check className="h-3 w-3 text-success/70" aria-hidden />
              )}
            </span>
            <span className="font-mono text-foreground/85">{event.tool}</span>
            {event.resultSummary && (
              <>
                <span className="text-muted-foreground/30">·</span>
                <span className="max-w-[220px] truncate font-mono text-muted-foreground/50">
                  {event.resultSummary}
                </span>
              </>
            )}
            {event.runId && (
              <span className="shrink-0 font-mono text-primary/70">· {event.runId}</span>
            )}
            {secs != null && secs > 0 && (
              <span className="shrink-0 tabular-nums text-muted-foreground/40">· {secs}s</span>
            )}
            <span className="ml-auto shrink-0 opacity-0 transition-opacity group-hover:opacity-100">
              {expanded ? (
                <ChevronDown className="h-3 w-3" aria-hidden />
              ) : (
                <ChevronRight className="h-3 w-3" aria-hidden />
              )}
            </span>
          </button>

          {expanded && (
            <div className="ml-4 mt-1.5 space-y-1.5">
              <pre className="max-h-[180px] overflow-x-auto rounded border border-border/40 bg-surface-0 p-1.5 font-mono text-[10.5px] text-foreground/70">
                {JSON.stringify(event.args, null, 2)}
              </pre>
              {event.resultSummary && (
                <pre
                  className={cn(
                    "max-h-[180px] overflow-x-auto whitespace-pre-wrap rounded border p-1.5 font-mono text-[10.5px]",
                    event.status === "error"
                      ? "border-destructive/20 bg-destructive/5 text-destructive/80"
                      : "border-border/40 bg-surface-0 text-foreground/70"
                  )}
                >
                  {event.resultSummary}
                </pre>
              )}
            </div>
          )}
        </div>

        {openKey && <OpenArtifactButton artifactKey={openKey} />}
      </div>
    </div>
  );
}
