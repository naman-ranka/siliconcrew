"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Loader2,
  FileText,
  FileCode,
  Edit3,
  FolderOpen,
  AlertTriangle,
  PlayCircle,
  Activity,
  Cpu,
  BarChart3,
  FileOutput,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolCall, ToolResult } from "@/types";

interface ToolCallCardProps {
  toolCall: ToolCall;
  result?: ToolResult;
  isRunning?: boolean;
}

const toolIconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  write_spec: FileText,
  read_spec: FileText,
  write_file: FileCode,
  read_file: FileCode,
  edit_file_tool: Edit3,
  list_files_tool: FolderOpen,
  linter_tool: AlertTriangle,
  simulation_tool: PlayCircle,
  waveform_tool: Activity,
  synthesis_tool: Cpu,
  ppa_tool: BarChart3,
  generate_report_tool: FileOutput,
};

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

  const ToolIcon = toolIconMap[toolCall.name] || Wrench;
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
    <div
      className={cn(
        "tool-card rounded-lg overflow-hidden border transition-all",
        isError
          ? "border-destructive/30 bg-destructive/5"
          : isSuccess
          ? "border-success/30 bg-success/5"
          : "border-border bg-surface-1"
      )}
    >
      {/* Header */}
      <button
        className={cn(
          "w-full flex items-center gap-3 p-3 transition-colors text-left",
          isError
            ? "hover:bg-destructive/10"
            : isSuccess
            ? "hover:bg-success/10"
            : "hover:bg-surface-2"
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {/* Status/Tool icon */}
          <div
            className={cn(
              "flex items-center justify-center w-7 h-7 rounded-md shrink-0",
              isRunning
                ? "bg-primary/15 text-primary"
                : isError
                ? "bg-destructive/15 text-destructive"
                : isSuccess
                ? "bg-success/15 text-success"
                : "bg-surface-3 text-muted-foreground"
            )}
          >
            {isRunning ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isSuccess ? (
              <Check className="h-4 w-4" />
            ) : isError ? (
              <X className="h-4 w-4" />
            ) : (
              <ToolIcon className="h-4 w-4" />
            )}
          </div>

          {/* Tool name and summary */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm text-foreground">
                {isRunning ? toolLabel : toolCall.name}
              </span>
              {isRunning && (
                <span className="text-xs text-primary animate-pulse">Running...</span>
              )}
            </div>
            {summary && (
              <code className="text-xs text-muted-foreground font-mono truncate block mt-0.5">
                {summary}
              </code>
            )}
          </div>
        </div>

        {/* Expand/collapse indicator */}
        <div className="shrink-0">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t border-border/50">
          {/* Arguments */}
          <div className="p-3 border-b border-border/50">
            <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">
              Arguments
            </p>
            <pre className="text-xs bg-surface-0 p-3 rounded-md overflow-x-auto max-h-[200px] font-mono text-foreground/80 border border-border/50">
              {JSON.stringify(toolCall.args, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {result && (
            <div className="p-3">
              <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">
                Result
              </p>
              <pre
                className={cn(
                  "text-xs p-3 rounded-md overflow-x-auto max-h-[300px] whitespace-pre-wrap font-mono border",
                  isError
                    ? "bg-destructive/10 text-destructive border-destructive/20"
                    : "bg-surface-0 text-foreground/80 border-border/50"
                )}
              >
                {result.content}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
