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

export function ToolCallCard({ toolCall, result, isRunning }: ToolCallCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const getToolIcon = (name: string) => {
    const iconMap: Record<string, string> = {
      write_spec: "write",
      read_spec: "read",
      write_file: "write",
      read_file: "read",
      edit_file_tool: "edit",
      list_files_tool: "list",
      linter_tool: "lint",
      simulation_tool: "sim",
      waveform_tool: "wave",
      synthesis_tool: "synth",
      ppa_tool: "ppa",
      generate_report_tool: "report",
    };
    return iconMap[name] || "tool";
  };

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

  return (
    <div
      className={cn(
        "border rounded-lg overflow-hidden",
        result?.status === "error"
          ? "border-destructive/50 bg-destructive/5"
          : "border-border bg-muted/30"
      )}
    >
      {/* Header */}
      <button
        className="w-full flex items-center gap-3 p-3 hover:bg-muted/50 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <div
            className={cn(
              "flex items-center justify-center w-6 h-6 rounded",
              result?.status === "error"
                ? "bg-destructive/20 text-destructive"
                : result?.status === "success"
                ? "bg-green-500/20 text-green-500"
                : "bg-primary/20 text-primary"
            )}
          >
            {isRunning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : result?.status === "success" ? (
              <Check className="h-3.5 w-3.5" />
            ) : result?.status === "error" ? (
              <X className="h-3.5 w-3.5" />
            ) : (
              <Wrench className="h-3.5 w-3.5" />
            )}
          </div>

          <span className="font-medium text-sm">{toolCall.name}</span>

          {summary && (
            <code className="text-xs bg-muted px-1.5 py-0.5 rounded truncate max-w-[200px]">
              {summary}
            </code>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isRunning && (
            <span className="text-xs text-muted-foreground">Running...</span>
          )}
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t border-border">
          {/* Args */}
          <div className="p-3 border-b border-border">
            <p className="text-xs font-medium text-muted-foreground mb-2">
              Arguments
            </p>
            <pre className="text-xs bg-background p-2 rounded overflow-x-auto max-h-[200px]">
              {JSON.stringify(toolCall.args, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {result && (
            <div className="p-3">
              <p className="text-xs font-medium text-muted-foreground mb-2">
                Result
              </p>
              <pre
                className={cn(
                  "text-xs p-2 rounded overflow-x-auto max-h-[300px] whitespace-pre-wrap",
                  result.status === "error"
                    ? "bg-destructive/10 text-destructive"
                    : "bg-background"
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
