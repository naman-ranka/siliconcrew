"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Loader2,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolCall, ToolResult } from "@/types";

interface ToolCallCardProps {
  toolCall: ToolCall;
  result?: ToolResult;
  isRunning?: boolean;
}

const toolLabelMap: Record<string, string> = {
  write_spec: "Writing Specification",
  read_spec: "Reading Specification",
  write_file: "Writing File",
  read_file: "Reading File",
  edit_file_tool: "Editing File",
  list_files_tool: "Listing Files",
  linter_tool: "Running Linter",
  simulation_tool: "Running Simulation",
  waveform_tool: "Generating Waveform",
  synthesis_tool: "Running Synthesis",
  ppa_tool: "Analyzing PPA",
  generate_report_tool: "Generating Report",
};

export function ToolCallCard({ toolCall, result, isRunning }: ToolCallCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toolLabel = toolLabelMap[toolCall.name] || toolCall.name;

  const getToolSummary = () => {
    const args = toolCall.args;
    if (args.filename) return args.filename as string;
    if (args.target_file) return args.target_file as string;
    if (args.design_file) return args.design_file as string;
    if (args.module_name) return args.module_name as string;
    if (args.verilog_files) return (args.verilog_files as string[]).join(", ");
    return null;
  };

  const summary = getToolSummary();
  const isError = result?.status === "error";
  const isSuccess = result?.status === "success";

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
    </div>
  );
}
