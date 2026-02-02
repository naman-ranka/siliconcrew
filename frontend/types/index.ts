// Session types
export interface Session {
  id: string;
  model_name: string | null;
  created_at: string | null;
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
  status: "success" | "error";
  content: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCall[];
  tool_results?: ToolResult[];
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
