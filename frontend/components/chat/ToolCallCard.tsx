"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  ChevronDown,
  ChevronRight,
  Check,
  CircuitBoard,
  Code2,
  FileText,
  Image as ImageIcon,
  Layers,
  MonitorPlay,
  Table2,
  Type,
  X,
  Loader2,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { useElapsedSeconds } from "@/lib/useElapsed";
import { parseArtifactKey } from "@/lib/artifactKeys";
import { openArtifact } from "@/lib/openArtifact";
import { prettifyToolName } from "@/lib/commandSurface";
import { artifactKeyForToolCall } from "@/lib/toolArtifacts";
import type { ArtifactKind, ToolCall, ToolResult } from "@/types";

interface ToolCallCardProps {
  toolCall: ToolCall;
  result?: ToolResult;
  isRunning?: boolean;
}

const KIND_ICON: Record<ArtifactKind, React.ComponentType<{ className?: string }>> = {
  code: Code2,
  spec: FileText,
  wave: Activity,
  wavefile: Activity,
  report: BarChart3,
  layout: Layers,
  schematic: CircuitBoard,
  image: ImageIcon,
  data: Table2,
  text: Type,
  interactive: MonitorPlay,
};

const KIND_OPEN_LABEL: Record<ArtifactKind, string> = {
  code: "file",
  spec: "spec",
  wave: "waveform",
  wavefile: "waveform",
  report: "report",
  layout: "layout",
  schematic: "schematic",
  image: "image",
  data: "data",
  text: "text",
  interactive: "interactive sim",
};

/** "Open <kind> →" — a tool call whose result maps to an artifact gets a
 *  one-click route into the SINGLE open-artifact model (both shells): the
 *  IDE opens a center tab; the agent shell's panel wrapper auto-expands. */
export function OpenArtifactButton({ artifactKey }: { artifactKey: string }) {
  const sessionId = useStore((s) => s.currentSession?.id ?? null);
  const parsed = parseArtifactKey(artifactKey);
  if (!parsed || !sessionId) return null;
  const Icon = KIND_ICON[parsed.kind];
  return (
    <button
      type="button"
      data-testid="tool-open-artifact"
      onClick={() => openArtifact(sessionId, artifactKey)}
      className="mt-1.5 ml-5 inline-flex h-6 items-center gap-1.5 rounded bg-surface-2 px-2 text-[11px] text-foreground/80 transition-colors hover:bg-surface-3"
    >
      <Icon className="h-3 w-3 text-primary" aria-hidden />
      Open {KIND_OPEN_LABEL[parsed.kind]}
      <ArrowRight className="h-3 w-3 text-muted-foreground/50" aria-hidden />
    </button>
  );
}

export function ToolCallCard({ toolCall, result, isRunning }: ToolCallCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Live elapsed while the tool runs, frozen once it returns — so a 60s synth
  // reads differently from a 0.2s lint. Times only from mount, so a reopened
  // (already-complete) card shows no bogus duration. (Shared clock — W5/A21.)
  const elapsed = useElapsedSeconds(!result);

  // Derived from the tool's own name (the same prettifier the Command Surface
  // uses), not a hand-kept prose map: sixteen gerunds ("Running Simulation")
  // covered a third of the registry and quietly reverted every other tool —
  // and every renamed one — to the raw name.
  const toolLabel = prettifyToolName(toolCall.name);
  const normalizedStatus = result?.status?.toLowerCase() ?? "";

  const getToolSummary = () => {
    const args = toolCall.args as Record<string, unknown>;
    if (args.filename) return args.filename as string;
    if (args.target_file) return args.target_file as string;
    if (args.design_file) return args.design_file as string;
    if (args.module_name) return args.module_name as string;
    if (args.verilog_files) {
      const files = args.verilog_files;
      if (Array.isArray(files)) return files.join(", ");
      if (typeof files === "string") return files;
      return JSON.stringify(files);
    }
    return null;
  };

  const summary = getToolSummary();
  // Artifact routing (S5): only a FINISHED call maps — the result often
  // carries the run id, and "Open" mid-run would open a half-truth.
  const openKey = useMemo(
    () =>
      result ? artifactKeyForToolCall(toolCall.name, toolCall.args, result.content) : null,
    [toolCall, result]
  );
  const isSuccess = ["success", "passed", "test_passed"].includes(normalizedStatus);
  const isError =
    normalizedStatus.includes("fail") ||
    normalizedStatus.includes("error") ||
    normalizedStatus === "compile_failed" ||
    normalizedStatus === "sim_failed";

  return (
    <div className="text-xs">
      {/* Compact single-line trigger */}
      <button
        className="flex items-center gap-1.5 text-muted-foreground/70 hover:text-foreground transition-colors w-full text-left group"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {/* Status indicator */}
        <span className="shrink-0">
          {isRunning ? (
            <Loader2 className="h-3 w-3 animate-spin text-primary/70" />
          ) : isSuccess ? (
            <Check className="h-3 w-3 text-success/70" />
          ) : isError ? (
            <X className="h-3 w-3 text-destructive/70" />
          ) : (
            <Wrench className="h-3 w-3" />
          )}
        </span>

        <span className={cn("font-mono", isRunning && "text-foreground/80")}>
          {toolLabel}
        </span>

        {summary && (
          <>
            <span className="text-muted-foreground/30">·</span>
            <span className="font-mono truncate max-w-[200px] text-muted-foreground/50">
              {summary}
            </span>
          </>
        )}

        {elapsed > 0 && (
          <span className="text-muted-foreground/40 tabular-nums shrink-0">· {elapsed}s</span>
        )}

        <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          {isExpanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </span>
      </button>

      {/* Expanded details */}
      {isExpanded && (
        <div className="mt-2 ml-5 space-y-2">
          <pre className="text-xs bg-surface-1 border border-border/40 p-2 rounded overflow-x-auto max-h-[180px] font-mono text-foreground/70">
            {JSON.stringify(toolCall.args, null, 2)}
          </pre>
          {result && (
            <pre
              className={cn(
                "text-xs border p-2 rounded overflow-x-auto max-h-[260px] whitespace-pre-wrap font-mono",
                isError
                  ? "bg-destructive/5 border-destructive/20 text-destructive/80"
                  : "bg-surface-1 border-border/40 text-foreground/70"
              )}
            >
              {result.content}
            </pre>
          )}
        </div>
      )}

      {openKey && <OpenArtifactButton artifactKey={openKey} />}
    </div>
  );
}
