import type { Session, Message, FileInfo, SpecData, CodeFile, WaveformData } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

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

// Session API
export const sessionsApi = {
  list: () => apiFetch<Session[]>("/api/sessions"),

  create: (name: string, model: string = "gemini-2.5-flash") =>
    apiFetch<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ name, model }),
    }),

  get: (sessionId: string) => apiFetch<Session>(`/api/sessions/${sessionId}`),

  delete: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${sessionId}`, {
      method: "DELETE",
    }),
};

// Chat API
export const chatApi = {
  getHistory: (sessionId: string) =>
    apiFetch<Message[]>(`/api/chat/${sessionId}/history`),

  // WebSocket connection for streaming
  createConnection: (sessionId: string, apiKeys?: Record<string, string>): WebSocket => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = process.env.NEXT_PUBLIC_WS_URL || `${wsProtocol}//${window.location.hostname}:8000`;

    const params = new URLSearchParams();
    if (apiKeys?.openai) params.append("openai_api_key", apiKeys.openai);
    if (apiKeys?.anthropic) params.append("anthropic_api_key", apiKeys.anthropic);
    if (apiKeys?.gemini) params.append("google_api_key", apiKeys.gemini);

    const queryString = params.toString() ? `?${params.toString()}` : "";
    return new WebSocket(`${wsHost}/api/chat/${sessionId}${queryString}`);
  },
};

// Workspace API
export const workspaceApi = {
  listFiles: (sessionId: string) =>
    apiFetch<FileInfo[]>(`/api/workspace/${sessionId}/files`),

  getSpec: (sessionId: string) =>
    apiFetch<SpecData>(`/api/workspace/${sessionId}/spec`),

  getCodeFiles: (sessionId: string) =>
    apiFetch<CodeFile[]>(`/api/workspace/${sessionId}/code`),

  getCodeFile: (sessionId: string, filename: string) =>
    apiFetch<CodeFile>(`/api/workspace/${sessionId}/code/${filename}`),

  listWaveforms: (sessionId: string) =>
    apiFetch<string[]>(`/api/workspace/${sessionId}/waveforms`),

  getWaveform: (sessionId: string, filename: string) =>
    apiFetch<WaveformData>(`/api/workspace/${sessionId}/waveform/${filename}`),

  getReport: (sessionId: string) =>
    apiFetch<{ filename: string; content: string }>(`/api/workspace/${sessionId}/report`),

  generateReport: (sessionId: string) =>
    apiFetch<{ filename: string; content: string }>(
      `/api/workspace/${sessionId}/report/generate`,
      { method: "POST" }
    ),

  listLayouts: (sessionId: string) =>
    apiFetch<string[]>(`/api/workspace/${sessionId}/layouts`),

  listSchematics: (sessionId: string) =>
    apiFetch<string[]>(`/api/workspace/${sessionId}/schematics`),

  getFile: (sessionId: string, filename: string) =>
    apiFetch<{ filename: string; content: string }>(
      `/api/workspace/${sessionId}/file/${encodeURIComponent(filename)}`
    ),
};

// Health check
export const healthApi = {
  check: () =>
    apiFetch<{ status: string; version: string; sessions: number }>("/api/health"),
};
