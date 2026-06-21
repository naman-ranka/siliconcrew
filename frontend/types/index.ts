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

// --- Design manifest (mirrors plans/phase0/data-model.md) -------------------
export type FileRole = "rtl" | "tb" | "sdc" | "include" | "other";

export interface DesignFile {
  name: string;
  role: FileRole;
  path: string;
}

export interface DesignManifest {
  sessionId: string;
  files: DesignFile[];
  synthTop: string;
  simTop: string;
  clockPeriodNs: number;
  platform: string;
}

// --- Unified run model ------------------------------------------------------
export type RunKind = "sim" | "synth";
export type RunStatus = "running" | "passed" | "failed";

export interface RunProvenance {
  repoCommit?: string | null;
  iverilogVersion?: string | null;
  orfsImageDigest?: string | null;
  pdk?: string | null;
  numCores?: number | null;
}

export interface RunSummary {
  id: string;
  kind: RunKind;
  status: RunStatus;
  createdAt: string | null;
  top: string | null;
  pinned: boolean;
  parentRunId?: string | null;
  provenance?: RunProvenance;
  // sim
  mode?: "rtl" | "post_synth";
  vcdPath?: string;
  passMarkerFound?: boolean;
  failure?: { type?: string; firstFailureLine?: string | null; timeNs?: number | null } | null;
  compileCommand?: string;
  simCommand?: string;
  stdoutTail?: string;
  stderrTail?: string;
  // synth
  platform?: string | null;
  ppa?: PpaMetrics | null;
  reportAvailable?: boolean;
}

export interface PpaMetrics {
  areaUm2?: number | null;
  cells?: number | null;
  wnsNs?: number | null;
  tnsNs?: number | null;
  fmaxMhz?: number | null;
  powerMw?: number | null;
}

export interface LintDiag {
  file?: string;
  line: number | null;
  severity: "error" | "warning";
  message: string;
}

export interface LintResult {
  status: "passed" | "failed";
  warnings: LintDiag[];
  errors: LintDiag[];
  byFile: Record<string, LintDiag[]>;
  command: string;
  files: string[];
}

export interface PpaDiff {
  a: string;
  b: string;
  rows: { metric: string; a: number | null; b: number | null; deltaPct?: number | null }[];
}

// Console entries surfaced under the artifact viewers (lint/sim/synth).
export type ConsoleChannel = "lint" | "sim" | "synth";
export interface ConsoleEntry {
  channel: ConsoleChannel;
  status: "running" | "passed" | "failed" | "info";
  command?: string;
  summary: string;
  detail?: string;
  runId?: string;
  ts: string;
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
