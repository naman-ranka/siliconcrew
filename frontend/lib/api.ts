import type {
  Project,
  Session,
  Message,
  FileInfo,
  SpecData,
  CodeFile,
  WaveformData,
  ReportData,
  SynthesisRun,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const encodeSessionId = (sessionId: string): string => encodeURIComponent(sessionId);
const encodeFilePath = (filename: string): string => encodeURIComponent(filename);

// Generic fetch wrapper with error handling
async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "API request failed");
  }

  return response.json();
}

// Project API
export const projectsApi = {
  list: () => apiFetch<Project[]>("/api/projects"),

  create: (name: string) =>
    apiFetch<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  delete: (projectId: string) =>
    apiFetch<{ status: string }>(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
    }),
};

// Session API
export const sessionsApi = {
  list: () => apiFetch<Session[]>("/api/sessions"),

  create: (name: string, model: string = "gemini-3-flash-preview", projectId?: string | null) =>
    apiFetch<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ name, model, project_id: projectId ?? null }),
    }),

  get: (sessionId: string) => apiFetch<Session>(`/api/sessions/${encodeSessionId(sessionId)}`),

  patch: (sessionId: string, projectId: string | null) =>
    apiFetch<Session>(`/api/sessions/${encodeSessionId(sessionId)}`, {
      method: "PATCH",
      body: JSON.stringify({ project_id: projectId }),
    }),

  delete: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${encodeSessionId(sessionId)}`, {
      method: "DELETE",
    }),
};

// Chat API
export const chatApi = {
  getHistory: (sessionId: string) =>
    apiFetch<Message[]>(`/api/chat/${encodeSessionId(sessionId)}/history`),

  // WebSocket connection for streaming
  createConnection: (sessionId: string): WebSocket => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = process.env.NEXT_PUBLIC_WS_URL || `${wsProtocol}//${window.location.hostname}:8000`;
    return new WebSocket(`${wsHost}/api/chat/${encodeSessionId(sessionId)}`);
  },
};

// Workspace API
export const workspaceApi = {
  listFiles: (sessionId: string) =>
    apiFetch<FileInfo[]>(`/api/workspace/${encodeSessionId(sessionId)}/files`),

  getSpec: (sessionId: string) =>
    apiFetch<SpecData>(`/api/workspace/${encodeSessionId(sessionId)}/spec`),

  getCodeFiles: (sessionId: string) =>
    apiFetch<CodeFile[]>(`/api/workspace/${encodeSessionId(sessionId)}/code`),

  getCodeFile: (sessionId: string, filename: string) =>
    apiFetch<CodeFile>(`/api/workspace/${encodeSessionId(sessionId)}/code/${encodeFilePath(filename)}`),

  listWaveforms: (sessionId: string) =>
    apiFetch<string[]>(`/api/workspace/${encodeSessionId(sessionId)}/waveforms`),

  getWaveform: (sessionId: string, filename: string) =>
    apiFetch<WaveformData>(`/api/workspace/${encodeSessionId(sessionId)}/waveform/${encodeFilePath(filename)}`),

  listSynthesisRuns: (sessionId: string) =>
    apiFetch<SynthesisRun[]>(`/api/workspace/${encodeSessionId(sessionId)}/synthesis-runs`),

  getReport: (sessionId: string, runId?: string | null) =>
    apiFetch<ReportData>(
      `/api/workspace/${encodeSessionId(sessionId)}/report${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`
    ),

  generateReport: (sessionId: string, runId?: string | null) =>
    apiFetch<ReportData>(
      `/api/workspace/${encodeSessionId(sessionId)}/report/generate${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`,
      { method: "POST" }
    ),

  listLayouts: (sessionId: string) =>
    apiFetch<string[]>(`/api/workspace/${encodeSessionId(sessionId)}/layouts`),

  listSchematics: (sessionId: string) =>
    apiFetch<string[]>(`/api/workspace/${encodeSessionId(sessionId)}/schematics`),

  getFile: (sessionId: string, filename: string) =>
    apiFetch<{ filename: string; content: string }>(
      `/api/workspace/${encodeSessionId(sessionId)}/file/${encodeFilePath(filename)}`
    ),
};

// Health check
export const healthApi = {
  check: () =>
    apiFetch<{ status: string; version: string; sessions: number }>("/api/health"),
};
