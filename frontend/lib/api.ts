import type {
  Project,
  Session,
  ChatThread,
  Message,
  FileInfo,
  SpecData,
  CodeFile,
  WaveformData,
  ReportData,
  SynthesisRun,
  DesignManifest,
  RunSummary,
  LintResult,
  PpaDiff,
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

  create: (name: string, model: string = "gemini-3.1-flash", projectId?: string | null) =>
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

// Chat thread API — many conversations per workspace (session).
export const threadsApi = {
  list: (sessionId: string) =>
    apiFetch<ChatThread[]>(`/api/sessions/${encodeSessionId(sessionId)}/threads`),

  create: (sessionId: string, title?: string, model?: string) =>
    apiFetch<ChatThread>(`/api/sessions/${encodeSessionId(sessionId)}/threads`, {
      method: "POST",
      body: JSON.stringify({ title: title ?? null, model: model ?? null }),
    }),

  getHistory: (sessionId: string, threadId: string) =>
    apiFetch<Message[]>(
      `/api/sessions/${encodeSessionId(sessionId)}/threads/${encodeURIComponent(threadId)}/history`
    ),

  patch: (sessionId: string, threadId: string, body: { title?: string; model?: string }) =>
    apiFetch<ChatThread>(
      `/api/sessions/${encodeSessionId(sessionId)}/threads/${encodeURIComponent(threadId)}`,
      { method: "PATCH", body: JSON.stringify(body) }
    ),

  delete: (sessionId: string, threadId: string) =>
    apiFetch<{ status: string }>(
      `/api/sessions/${encodeSessionId(sessionId)}/threads/${encodeURIComponent(threadId)}`,
      { method: "DELETE" }
    ),
};

// Chat API
export const chatApi = {
  // Legacy session-level history (defaults to the session's "Chat 1").
  getHistory: (sessionId: string) =>
    apiFetch<Message[]>(`/api/chat/${encodeSessionId(sessionId)}/history`),

  // Per-thread history (the general form).
  getThreadHistory: (sessionId: string, threadId: string) =>
    threadsApi.getHistory(sessionId, threadId),

  // WebSocket connection for streaming. The active chat thread rides as a query
  // param so the server keys the LangGraph checkpoint by thread while the
  // workspace stays bound from session_id.
  createConnection: (sessionId: string, threadId?: string | null): WebSocket => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = process.env.NEXT_PUBLIC_WS_URL || `${wsProtocol}//${window.location.hostname}:8000`;
    const q = threadId ? `?thread_id=${encodeURIComponent(threadId)}` : "";
    return new WebSocket(`${wsHost}/api/chat/${encodeSessionId(sessionId)}${q}`);
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

  getLayout: (sessionId: string, filename: string) =>
    apiFetch<{ svg: string; cell_name: string; cached?: boolean; error?: string; message?: string }>(
      `/api/workspace/${encodeSessionId(sessionId)}/layout/${encodeFilePath(filename)}`
    ),

  listSchematics: (sessionId: string) =>
    apiFetch<string[]>(`/api/workspace/${encodeSessionId(sessionId)}/schematics`),

  getFile: (sessionId: string, filename: string) =>
    apiFetch<{ filename: string; content: string }>(
      `/api/workspace/${encodeSessionId(sessionId)}/file/${encodeFilePath(filename)}`
    ),
};

// Workbench action layer — manifest, IDE-first buttons, unified runs.
// Every endpoint returns the uniform { ok, ... } envelope (api-contract.md).
async function actionFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || (body && body.ok === false)) {
    const err = body?.detail?.error || body?.error || { message: response.statusText };
    throw new Error(err.message || "Action failed");
  }
  return body as T;
}

const ws = (sessionId: string) => `/api/workspace/${encodeSessionId(sessionId)}`;

export const workbenchApi = {
  getManifest: (sessionId: string) =>
    actionFetch<{ ok: true; manifest: DesignManifest }>(`${ws(sessionId)}/manifest`).then((r) => r.manifest),

  updateManifest: (sessionId: string, updates: Partial<DesignManifest> | { files: { name: string; role: string }[] }) =>
    actionFetch<{ ok: true; manifest: DesignManifest }>(`${ws(sessionId)}/manifest`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }).then((r) => r.manifest),

  uploadFiles: async (sessionId: string, files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    const response = await fetch(`${API_BASE}${ws(sessionId)}/files`, { method: "POST", body: form });
    const body = await response.json().catch(() => null);
    if (!response.ok || (body && body.ok === false)) {
      throw new Error(body?.detail?.error?.message || "Upload failed");
    }
    return body as { ok: true; uploaded: string[]; manifest: DesignManifest };
  },

  saveCode: (sessionId: string, filename: string, content: string) =>
    actionFetch<{ ok: true; saved: string; manifest: DesignManifest }>(
      `${ws(sessionId)}/code/${encodeFilePath(filename)}`,
      { method: "PUT", body: JSON.stringify({ content }) }
    ),

  lint: (sessionId: string) =>
    actionFetch<LintResult & { ok: true }>(`${ws(sessionId)}/lint`, { method: "POST" }),

  simulate: (sessionId: string, body: { simTop?: string; mode?: string; runId?: string } = {}) =>
    actionFetch<{ ok: true; run: RunSummary }>(`${ws(sessionId)}/simulate`, {
      method: "POST",
      body: JSON.stringify(body),
    }).then((r) => r.run),

  synthesize: (sessionId: string, body: Record<string, unknown> = {}) =>
    actionFetch<{ ok: true; jobId: string; runId: string }>(`${ws(sessionId)}/synthesize`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listRuns: (sessionId: string, kind: "all" | "sim" | "synth" = "all") =>
    actionFetch<{ ok: true; runs: RunSummary[] }>(`${ws(sessionId)}/runs?kind=${kind}`).then((r) => r.runs),

  getRun: (sessionId: string, runId: string) =>
    actionFetch<{ ok: true; run: RunSummary }>(`${ws(sessionId)}/runs/${encodeURIComponent(runId)}`).then((r) => r.run),

  getJob: (sessionId: string, jobId: string) =>
    actionFetch<{ ok: true; job: Record<string, unknown> }>(`${ws(sessionId)}/jobs/${encodeURIComponent(jobId)}`).then((r) => r.job),

  pinRun: (sessionId: string, runId: string, pinned: boolean) =>
    actionFetch<{ ok: true; runId: string; pinned: boolean }>(`${ws(sessionId)}/runs/${encodeURIComponent(runId)}/pin`, {
      method: "POST",
      body: JSON.stringify({ pinned }),
    }),

  compareRuns: (sessionId: string, a: string, b: string) =>
    actionFetch<{ ok: true; diff: PpaDiff }>(
      `${ws(sessionId)}/runs/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`
    ).then((r) => r.diff),
};

// Health check
export const healthApi = {
  check: () =>
    apiFetch<{ status: string; version: string; sessions: number }>("/api/health"),
};
