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

// Model registry (the picker). `available` is per-request: false when the
// provider has no usable key (env in self-host, BYOK/hosted otherwise).
export interface ModelInfo {
  id: string;
  label: string;
  provider: "anthropic" | "openai" | "gemini";
  tier: "fast" | "balanced" | "capable";
  hint?: string;
  pricing?: { input: number; output: number };
  available: boolean;
}

// Chat thread types — a chat = a LangGraph thread_id; many per workspace.
// Threads share the LIVE workspace (files/runs); only the conversation differs.
export interface ChatThread {
  id: string;
  session_id: string;
  title: string | null;
  model: string | null;
  created_at: string | null;
  last_active: string | null;
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
  scope?: string;
  width?: number;
  isBus?: boolean;
  times: number[];
  values: number[];
  valuesStr?: string[];
  xFlags?: boolean[];
}

export interface WaveformData {
  filename: string;
  endtime: number;
  timescale?: string | null;
  unitSeconds?: number | null; // seconds per VCD tick (for ns→tick cursor mapping)
  signalCount?: number;
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

// Transient toast notifications (unified, replaces ad-hoc banners).
export interface Toast {
  id: string;
  kind: "success" | "error" | "info" | "running";
  title: string;
  detail?: string;
}

// Live synthesis (ORFS) job status — drives the stage-progress UI while a
// remote synth runs. Mirrors the backend job-status payload (snake_case).
export type SynthStageId =
  | "constraints"
  | "synth"
  | "floorplan"
  | "place"
  | "cts"
  | "grt"
  | "route"
  | "finish";
export type SynthStageStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export interface SynthJobStatus {
  jobId: string;
  runId: string;
  status: string; // queued | running | completed | failed
  currentStage?: SynthStageId | string | null;
  stages?: Partial<Record<SynthStageId, { status: SynthStageStatus; artifacts?: Record<string, unknown> }>>;
  elapsedSec?: number | null;
  backend?: string | null;
  remote?: boolean | null;
  executionLabel?: string | null;
}

// --- Workbench v2 data layer (SWR slices, activity feed, file tree) ---------

// Lifecycle of a cached data slice. The SWR iron rule: a populated slice NEVER
// goes back to "loading" — a refetch is "revalidating" (old data stays visible)
// and a failed revalidate keeps the data and sets the error.
export type SliceStatus = "empty" | "loading" | "ready" | "revalidating" | "error";

export interface Slice<T> {
  data: T | null;
  status: SliceStatus;
  error: string | null;
}

// One tool invocation in the unified per-session activity feed
// (GET /api/workspace/{sid}/activity — agent WS, user REST, and MCP sources).
export interface ActivityEvent {
  id: string;
  ts: string;
  source: "agent" | "user" | "mcp";
  tool: string;
  args: Record<string, unknown>;
  status: "ok" | "error" | "running";
  resultSummary: string;
  durationMs: number | null;
  runId: string | null;
  threadId: string | null;
}

// One entry of the lazy directory listing (GET /api/workspace/{sid}/dir).
export interface DirEntry {
  name: string;
  path: string;
  kind: "dir" | "file";
  size?: number;
  modified?: string;
}

// Honest file payload (GET /api/workspace/{sid}/file/{path}) — content is null
// (never lossy garbage) for binary or oversized files; `?raw=1` downloads.
export interface SmartFile {
  filename: string;
  content: string | null;
  size: number;
  binary: boolean;
  tooLarge: boolean;
}

// Artifact tab/key kinds for the v2 workbench (see lib/artifactKeys.ts for the
// `kind:ref` string-key helpers).
export type ArtifactKind = "code" | "spec" | "wave" | "report" | "layout" | "schematic";

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
