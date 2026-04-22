// Project types
export interface Project {
  id: string;
  name: string;
  created_at: string | null;
}

// Session types
export interface Session {
  id: string;
  name: string | null;
  model_name: string | null;
  project_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  total_tokens: number;
  total_cost: number;
}

// Message types
export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface ToolResult {
  tool_call_id: string;
  status: string;
  content: string;
}

export type ContentBlock =
  | { type: "text"; content: string }
  | { type: "tool"; toolCall: ToolCall; result?: ToolResult };

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCall[];
  tool_results?: ToolResult[];
  blocks: ContentBlock[];
  timestamp?: string;
}

// Workspace types
export interface FileInfo {
  name: string;
  path: string;
  type: "verilog" | "spec" | "waveform" | "layout" | "schematic" | "report" | "yaml" | "unknown";
  size: number;
  modified: string;
}

export interface SpecData {
  filename: string;
  content: string;
  parsed: Record<string, unknown> | null;
}

export interface CodeFile {
  filename: string;
  content: string;
  language: string;
}

export interface WaveformSignal {
  name: string;
  full_name: string;
  times: number[];
  values: number[];
}

export interface WaveformData {
  filename: string;
  endtime: number;
  signals: WaveformSignal[];
}

export interface SynthesisRun {
  run_id: string;
  status: string;
  updated_at: string | null;
  created_at: string | null;
  finished_at: string | null;
  top_module: string | null;
  platform: string | null;
  elapsed_sec: number | null;
  summary_metrics: Record<string, unknown> | null;
  auto_checks: Record<string, unknown> | null;
  report_available: boolean;
  report_filename: string | null;
}

export interface ReportData {
  filename: string;
  content: string;
  run_id: string | null;
}

// WebSocket message types
export type WSMessageType =
  | { type: "start" }
  | { type: "text"; content: string }
  | { type: "tool_call"; tool: ToolCall }
  | { type: "tool_result"; tool_call_id: string; status: string; content: string }
  | { type: "done"; tokens: { input: number; output: number } }
  | { type: "error"; error: string };

// UI State types
export type ArtifactTab = "spec" | "code" | "waveform" | "schematic" | "layout" | "report";
