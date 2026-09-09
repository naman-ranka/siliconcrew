import type {
  Project,
  Session,
  ChatThread,
  ModelInfo,
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
  ActivityEvent,
  DirEntry,
  SmartFile,
  ToolCatalogEntry,
  TemplateSummary,
  TemplateDetail,
  SkillsIndex,
  SkillDetail,
} from "@/types";
import { authHeader, getAuthToken, recoverAuthExpired } from "./authToken";

import { getApiBase, getWsBase } from "@/lib/runtime-config";

const encodeSessionId = (sessionId: string): string => encodeURIComponent(sessionId);
const encodeFilePath = (filename: string): string => encodeURIComponent(filename);

async function fetchWithAuthRecovery(makeRequest: () => Promise<Response>): Promise<Response> {
  const sentToken = getAuthToken();
  let response = await makeRequest();
  if (response.status !== 401) return response;

  await recoverAuthExpired();
  const recoveredToken = getAuthToken();
  if (recoveredToken && recoveredToken !== sentToken) {
    response = await makeRequest();
  }
  return response;
}

/**
 * One extractor for every error body the backend can produce, so no path ever
 * renders "[object Object]". Shapes seen in the wild:
 *   - detail: "plain string"                      (most HTTPExceptions)
 *   - detail: { code, message }                   (auth deps, api.py:613-631)
 *   - detail: { error: { message } }              (envelope-in-HTTPException)
 *   - detail: [{ loc, msg, ... }]                 (pydantic 422)
 *   - { error: { message } } / { message }        (top-level envelopes)
 */
export function extractErrorMessage(body: unknown, fallback: string): string {
  if (typeof body === "string" && body) return body;
  if (!body || typeof body !== "object") return fallback;
  const b = body as Record<string, unknown>;

  const detail = b.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" ? (d as { msg?: unknown }).msg : null))
      .filter((m): m is string => typeof m === "string" && m.length > 0);
    if (msgs.length) return msgs.join("; ");
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: unknown; error?: { message?: unknown } };
    if (typeof d.message === "string" && d.message) return d.message;
    if (typeof d.error?.message === "string" && d.error.message) return d.error.message;
  }

  const err = b.error;
  if (typeof err === "string" && err) return err;
  if (err && typeof err === "object") {
    const m = (err as { message?: unknown }).message;
    if (typeof m === "string" && m) return m;
  }
  if (typeof b.message === "string" && b.message) return b.message;
  return fallback;
}

/**
 * The machine-readable error CODE across every backend error shape — the
 * exact twin of extractErrorMessage above (W4/A17, FA8):
 *   - detail: { code, message }              (auth deps — core twins' 403)
 *   - detail: { error: { code, message } }   (_err envelope-in-HTTPException —
 *                                             /invoke's 401 signin_required)
 *   - { error: { code } }                    (top-level { ok:false } envelope)
 * Callers branch on THIS (e.g. "signin_required" → sign-in CTA), never on
 * message strings.
 */
export function extractErrorCode(body: unknown): string | undefined {
  if (!body || typeof body !== "object") return undefined;
  const b = body as Record<string, unknown>;
  const detail = b.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as { code?: unknown; error?: { code?: unknown } };
    if (typeof d.code === "string" && d.code) return d.code;
    if (typeof d.error?.code === "string" && d.error.code) return d.error.code;
  }
  const err = b.error;
  if (err && typeof err === "object") {
    const c = (err as { code?: unknown }).code;
    if (typeof c === "string" && c) return c;
  }
  return undefined;
}

/** The `_err` envelope's structured `details` (e.g. `{ fields: [...] }` on a
 *  400 invalid_arguments), from either the envelope-in-HTTPException or the
 *  top-level shape; undefined when the body carries none. */
export function extractErrorDetails(body: unknown): Record<string, unknown> | undefined {
  if (!body || typeof body !== "object") return undefined;
  const b = body as { detail?: unknown; error?: unknown };
  const candidates = [
    (b.detail as { error?: { details?: unknown } } | undefined)?.error?.details,
    (b.error as { details?: unknown } | undefined)?.details,
  ];
  for (const d of candidates) {
    if (d && typeof d === "object" && !Array.isArray(d)) return d as Record<string, unknown>;
  }
  return undefined;
}

/** Errors thrown by apiFetch/actionFetch carry the HTTP status, the backend's
 *  error code and its structured details when the body supplied them. */
export type ApiError = Error & {
  status?: number;
  code?: string;
  details?: Record<string, unknown>;
};

/** True iff the error is the hosted-anonymous "sign in to run this" rejection
 *  (401 from /invoke's envelope, 403 from the core twins' auth dep) —
 *  detected by CODE, never by message text. */
export function isSignInRequired(e: unknown): boolean {
  return (e as ApiError | null)?.code === "signin_required";
}

/** Build the thrown error for a failed response: message + status + code +
 *  details, normalized at this ONE boundary for both fetchers. */
function apiError(body: unknown, status: number, fallback: string): ApiError {
  const err = new Error(extractErrorMessage(body, fallback)) as ApiError;
  err.status = status;
  const code = extractErrorCode(body);
  if (code) err.code = code;
  const details = extractErrorDetails(body);
  if (details) err.details = details;
  return err;
}

// Generic fetch wrapper with error handling
async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetchWithAuthRecovery(() => fetch(`${getApiBase()}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...options?.headers,
    },
  }));

  if (!response.ok) {
    // Expired/invalid token → let the auth layer drop to anonymous + re-prompt.
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    // Attach the HTTP status + backend error code so callers can branch on
    // graceful states (e.g. BYOK: 400 self-host, 503 vault-off; W4:
    // signin_required → CTA) without parsing the message string.
    throw apiError(error, response.status, "API request failed");
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

  // S0: rename a project (UI calls these "groups" — pure relabel, same entity).
  rename: (projectId: string, name: string) =>
    apiFetch<Project>(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "PATCH",
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

  create: (name: string, model: string = "gemini-3.1-flash-lite", projectId?: string | null) =>
    apiFetch<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ name, model, project_id: projectId ?? null }),
    }),

  get: (sessionId: string, init?: RequestInit) =>
    apiFetch<Session>(`/api/sessions/${encodeSessionId(sessionId)}`, init),

  // S0: PATCH accepts `name` (display-only rename — the workspace dir/id never
  // changes) and/or `project_id` (explicit null removes from the group).
  patch: (sessionId: string, body: { name?: string; project_id?: string | null }) =>
    apiFetch<Session>(`/api/sessions/${encodeSessionId(sessionId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  delete: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${encodeSessionId(sessionId)}`, {
      method: "DELETE",
    }),
};

// Templates API (Wave 11) — repo-owned example bundles you can FORK into a
// session. list/get are PUBLIC (no sign-in); fork requires a signed-in/self-host
// identity (it owns the resulting session).
export const templatesApi = {
  list: () => apiFetch<{ templates: TemplateSummary[] }>("/api/templates").then((r) => r.templates),

  get: (templateId: string) =>
    apiFetch<TemplateDetail>(`/api/templates/${encodeURIComponent(templateId)}`),

  fork: (templateId: string) =>
    apiFetch<{ sessionId: string }>(`/api/templates/${encodeURIComponent(templateId)}/fork`, {
      method: "POST",
    }),
};

// Models API — the registry for the pickers (availability per request).
// `models`/`default` feed the native picker; `codex_models`/`codex_default`
// feed the separately curated Codex picker.
export const modelsApi = {
  list: () =>
    apiFetch<{
      models: ModelInfo[];
      default: string;
      codex_models?: ModelInfo[];
      codex_default?: string;
    }>("/api/models"),
};

// BYOK API keys (hosted, signed-in). The server NEVER returns a stored key —
// only which providers have one. In self-host `list` 400s ("BYOK is only
// available in hosted mode."); when the vault is unconfigured it 503s. Callers
// branch on `err.status` (see apiFetch) for those graceful states.
export const keysApi = {
  list: () => apiFetch<{ providers: string[] }>("/api/keys"),

  save: (provider: string, api_key: string) =>
    apiFetch<{ ok: true; provider: string; stored: boolean }>(
      `/api/keys/${encodeURIComponent(provider)}`,
      { method: "PUT", body: JSON.stringify({ api_key }) }
    ),

  remove: (provider: string) =>
    apiFetch<{ ok: true; provider: string; deleted: boolean }>(
      `/api/keys/${encodeURIComponent(provider)}`,
      { method: "DELETE" }
    ),
};

/**
 * Skills — the built-in pack and the caller's own layer over it.
 *
 * The backend owns the four merge rules; this is a transport, and it must stay
 * one. Nothing here decides which layer wins, and nothing caches a list: a
 * skill index is owner-scoped state, and a stale copy in the browser is the
 * same class of lie as a stale copy on the server.
 */
export const skillsApi = {
  list: () => apiFetch<SkillsIndex>("/api/skills"),

  read: (name: string) => apiFetch<SkillDetail>(`/api/skills/${encodeURIComponent(name)}`),

  save: (name: string, text: string) =>
    apiFetch<{ ok: true; name: string }>(`/api/skills/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),

  /** Drop the caller's copy. Over a built-in that IS "reset to shipped". */
  remove: (name: string) =>
    apiFetch<{ ok: true; name: string }>(`/api/skills/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  setEnabled: (name: string, enabled: boolean) =>
    apiFetch<{ ok: true; name: string; enabled: boolean }>(
      `/api/skills/${encodeURIComponent(name)}/enabled`,
      { method: "PUT", body: JSON.stringify({ enabled }) }
    ),
};

// Chat thread API — many conversations per workspace (session).
export const threadsApi = {
  list: (sessionId: string) =>
    apiFetch<ChatThread[]>(`/api/sessions/${encodeSessionId(sessionId)}/threads`),

  create: (sessionId: string, title?: string, model?: string, runtime?: string) =>
    apiFetch<ChatThread>(`/api/sessions/${encodeSessionId(sessionId)}/threads`, {
      method: "POST",
      body: JSON.stringify({ title: title ?? null, model: model ?? null, runtime: runtime ?? null }),
    }),

  getHistory: (sessionId: string, threadId: string) =>
    apiFetch<Message[]>(
      `/api/sessions/${encodeSessionId(sessionId)}/threads/${encodeURIComponent(threadId)}/history`
    ),

  patch: (sessionId: string, threadId: string, body: { title?: string; model?: string; reasoning_effort?: string }) =>
    apiFetch<ChatThread>(
      `/api/sessions/${encodeSessionId(sessionId)}/threads/${encodeURIComponent(threadId)}`,
      { method: "PATCH", body: JSON.stringify(body) }
    ),

  delete: (sessionId: string, threadId: string) =>
    apiFetch<{ status: string }>(
      `/api/sessions/${encodeSessionId(sessionId)}/threads/${encodeURIComponent(threadId)}`,
      { method: "DELETE" }
    ),

  // TTFT (Codex warm-keep): start the thread's runtime worker before the first
  // message, and read its HONEST readiness. States: ready | starting | cold |
  // unavailable ("unavailable" = the runtime has no warm capability — show
  // nothing). See plans/codex-ttft-remediation.md 3B/3C.
  prewarmRuntime: (sessionId: string, threadId: string) =>
    apiFetch<{ state: string }>(
      `/api/sessions/${encodeSessionId(sessionId)}/threads/${encodeURIComponent(threadId)}/runtime/prewarm`,
      { method: "POST" }
    ),
  runtimeStatus: (sessionId: string, threadId: string) =>
    apiFetch<{ state: string }>(
      `/api/sessions/${encodeSessionId(sessionId)}/threads/${encodeURIComponent(threadId)}/runtime/status`
    ),
};

// Codex runtime capability + account-auth (ChatGPT device-code login) status.
// runtime_enabled reflects the CODEX_ENABLED server flag; connected reflects a
// completed device-auth login; while in_progress the login_url + user_code are
// what the user opens/enters to sign in.
export interface CodexAuthStatus {
  connected: boolean;
  runtime_enabled: boolean;
  in_progress?: boolean;
  login_url?: string | null;
  user_code?: string | null;
  message?: string;
}

export const codexApi = {
  status: () => apiFetch<CodexAuthStatus>("/api/codex/auth"),
  startDeviceAuth: () => apiFetch<CodexAuthStatus>("/api/codex/auth/device/start", { method: "POST" }),
  cancelDeviceAuth: () => apiFetch<CodexAuthStatus>("/api/codex/auth/device/cancel", { method: "POST" }),
  disconnect: () => apiFetch<CodexAuthStatus>("/api/codex/auth", { method: "DELETE" }),
  models: () => apiFetch<{ models: ModelInfo[]; default: string; source: string }>("/api/codex/models"),
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
    // First-message auth handshake (naman-ranka/siliconcrew-dev#59): the token
    // must NEVER ride the URL — Cloud Run logs query strings verbatim, which
    // put bearer JWTs in request logs. Browsers can't set headers on
    // `new WebSocket`, so the very first frame on the socket is
    // {"type":"auth","token":...} (token null in self-host / signed-out; the
    // backend authenticates it exactly like the old query param). Registered
    // via addEventListener so the store's later `onopen` assignment (which
    // sends the first chat message) fires AFTER it — auth is always frame one,
    // on fresh connects and reconnects alike.
    const params = new URLSearchParams();
    if (threadId) params.set("thread_id", threadId);
    const qs = params.toString();
    const ws = new WebSocket(`${getWsBase()}/api/chat/${encodeSessionId(sessionId)}${qs ? `?${qs}` : ""}`);
    ws.addEventListener("open", () => {
      // Read the token at open time so reconnects pick up a refreshed token.
      ws.send(JSON.stringify({ type: "auth", token: getAuthToken() ?? null }));
    });
    return ws;
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
    apiFetch<{ layouts: string[]; missing_binaries: string[] }>(
      `/api/workspace/${encodeSessionId(sessionId)}/layouts`
    ),

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

  // --- Workbench v2: lazy file tree + honest file payloads -------------------

  // Immediate children of one directory ("" = workspace root). Dirs first,
  // dotfiles/__pycache__ excluded; 404 on missing/traversal. { ok } envelope.
  getDir: (sessionId: string, path: string = "") =>
    actionFetch<{ ok: true; path: string; entries: DirEntry[] }>(
      `/api/workspace/${encodeSessionId(sessionId)}/dir${path ? `?path=${encodeURIComponent(path)}` : ""}`
    ),

  // Flat recursive file-path index for quick-open (⌘P).
  getDirPaths: (sessionId: string) =>
    actionFetch<{ ok: true; paths: string[]; truncated: boolean }>(
      `/api/workspace/${encodeSessionId(sessionId)}/dir?recursive=paths`
    ),

  // Honest file payload — content is null for binary/oversized files (plain
  // endpoint, NOT the { ok } envelope).
  getFileSmart: (sessionId: string, path: string) =>
    apiFetch<SmartFile>(
      `/api/workspace/${encodeSessionId(sessionId)}/file/${encodeFilePath(path)}`
    ),

  // Raw-bytes escape hatch (?raw=1): fetch with the auth header, then trigger a
  // programmatic download. Browser-only (no-op during SSR).
  downloadRawFile: async (sessionId: string, path: string): Promise<void> => {
    if (typeof window === "undefined") return;
    const response = await fetchWithAuthRecovery(() =>
      fetch(
        `${getApiBase()}/api/workspace/${encodeSessionId(sessionId)}/file/${encodeFilePath(path)}?raw=1`,
        { headers: { ...authHeader() } }
      )
    );
    if (!response.ok) throw new Error(`Download failed (HTTP ${response.status})`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = path.split("/").pop() || path;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // Raw bytes as an in-app object URL (for <img> rendering). `/file?raw=1`
  // requires a Bearer HEADER, so a bare `<img src=…?raw=1>` would 401 and the
  // download helper above force-downloads — neither is renderable. Fetch with
  // the auth header → blob → object URL. The CALLER owns the URL and MUST
  // `URL.revokeObjectURL` it on unmount/path change.
  fetchRawObjectUrl: async (sessionId: string, path: string): Promise<string> => {
    const response = await fetchWithAuthRecovery(() =>
      fetch(
        `${getApiBase()}/api/workspace/${encodeSessionId(sessionId)}/file/${encodeFilePath(path)}?raw=1`,
        { headers: { ...authHeader() } }
      )
    );
    if (!response.ok) throw new Error(`Load failed (HTTP ${response.status})`);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  },

  // Raw bytes as an ArrayBuffer — for content-hash provenance checks and the
  // websim netlist (which can exceed the smart-file reader's inline cap).
  fetchRawBytes: async (sessionId: string, path: string): Promise<ArrayBuffer> => {
    const response = await fetchWithAuthRecovery(() =>
      fetch(
        `${getApiBase()}/api/workspace/${encodeSessionId(sessionId)}/file/${encodeFilePath(path)}?raw=1`,
        { headers: { ...authHeader() } }
      )
    );
    if (!response.ok) throw new Error(`Load failed (HTTP ${response.status})`);
    return response.arrayBuffer();
  },
};

// Workbench action layer — manifest, IDE-first buttons, unified runs.
// Every endpoint returns the uniform { ok, ... } envelope (api-contract.md).
async function actionFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetchWithAuthRecovery(() => fetch(`${getApiBase()}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...authHeader(), ...options?.headers },
  }));
  const body = await response.json().catch(() => null);
  if (!response.ok || (body && body.ok === false)) {
    // Same status/code/details attachment as apiFetch (W4/A17, FA8): the
    // Command Surface detects signin_required by CODE across the 403-detail
    // (core twins) and 401-envelope (/invoke) shapes, and reads the
    // invalid_arguments `details.fields` for field-level errors.
    throw apiError(body, response.status, response.statusText || "Action failed");
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

  uploadFiles: async (sessionId: string, files: File[], dir = "") => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    // Workspace-relative target directory; omitted (not sent empty) so the
    // endpoint's default keeps root uploads byte-identical to before.
    if (dir) form.append("dir", dir);
    // FormData sets its own multipart Content-Type (with boundary) — only add
    // Authorization here, never Content-Type.
    const response = await fetchWithAuthRecovery(() => fetch(`${getApiBase()}${ws(sessionId)}/files`, {
      method: "POST",
      body: form,
      headers: { ...authHeader() },
    }));
    const body = await response.json().catch(() => null);
    if (!response.ok || (body && body.ok === false)) {
      throw new Error(extractErrorMessage(body, "Upload failed"));
    }
    return body as { ok: true; uploaded: string[]; manifest: DesignManifest };
  },

  saveCode: (sessionId: string, filename: string, content: string) =>
    actionFetch<{ ok: true; saved: string; manifest: DesignManifest }>(
      `${ws(sessionId)}/code/${encodeFilePath(filename)}`,
      { method: "PUT", body: JSON.stringify({ content }) }
    ),

  // `files` (L1): optional override of the manifest-resolved compile set —
  // absent/empty keeps today's manifest-driven behavior exactly.
  lint: (sessionId: string, body?: { engine?: string; files?: string[] }) =>
    actionFetch<LintResult & { ok: true }>(`${ws(sessionId)}/lint`, {
      method: "POST",
      // Body is optional on the backend too — omit it entirely for the
      // no-arg call so legacy servers keep working.
      ...(body ? { body: JSON.stringify(body) } : {}),
    }),

  // Returns the run PLUS any duplicate-module collision warnings the backend
  // attached to the dispatch (sc#66: `manifestWarnings` — advisory only, they
  // never alter the run result). `files` (L1): optional compile-set override;
  // absent = files_for_stage(manifest) as today.
  simulate: (
    sessionId: string,
    body: { simTop?: string; mode?: string; runId?: string; files?: string[] } = {}
  ) =>
    actionFetch<{ ok: true; run: RunSummary; manifestWarnings?: string[] }>(
      `${ws(sessionId)}/simulate`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ).then((r) => ({ run: r.run, manifestWarnings: r.manifestWarnings ?? [] })),

  // Dispatch-only: returns the durable run key immediately (no job_id), plus
  // the same advisory manifestWarnings as /simulate.
  synthesize: (sessionId: string, body: Record<string, unknown> = {}) =>
    actionFetch<{ ok: true; runId: string; pollAfterSec?: number; manifestWarnings?: string[] }>(
      `${ws(sessionId)}/synthesize`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ),

  listRuns: (sessionId: string, kind: "all" | "sim" | "synth" = "all") =>
    actionFetch<{ ok: true; runs: RunSummary[] }>(`${ws(sessionId)}/runs?kind=${kind}`).then((r) => r.runs),

  // F4: one hydration returning the whole workbench (manifest+runs+files+spec+
  // code+report), replacing the ~18-call fan-out on initial load.
  getWorkbench: (sessionId: string) =>
    actionFetch<{
      ok: true;
      manifest: DesignManifest;
      runs: RunSummary[];
      files: FileInfo[];
      spec: SpecData | null;
      code: CodeFile[];
      report: ReportData | null;
      synthesisRuns: SynthesisRun[];
      // v2 additions (same shapes as GET /activity and GET /dir) so the first
      // paint of the Activity dock + file tree costs no extra round trips.
      activity?: ActivityEvent[];
      rootDir?: DirEntry[];
    }>(`${ws(sessionId)}/workbench`),

  // Newest-first page of the unified tool-event log (agent WS, user REST, MCP).
  // `before` = last event id of the previous page; nextBefore is null at the end.
  getActivity: (sessionId: string, opts: { limit?: number; before?: string | null } = {}) => {
    const params = new URLSearchParams();
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.before) params.set("before", opts.before);
    const qs = params.toString();
    return actionFetch<{ ok: true; events: ActivityEvent[]; nextBefore: string | null }>(
      `${ws(sessionId)}/activity${qs ? `?${qs}` : ""}`
    );
  },

  getRun: (sessionId: string, runId: string) =>
    actionFetch<{ ok: true; run: RunSummary }>(`${ws(sessionId)}/runs/${encodeURIComponent(runId)}`).then((r) => r.run),

  // Self-healing run-status read (GET /runs/{run_id}/status). The UI never
  // calls this on its own cadence — it exists for actor-style reads; the
  // user-gesture Refresh goes through invokeTool("get_synthesis_status")
  // instead so the gesture lands in the activity log.
  getRunStatus: (sessionId: string, runId: string) =>
    actionFetch<{ ok: true; job: Record<string, unknown> }>(
      `${ws(sessionId)}/runs/${encodeURIComponent(runId)}/status`
    ).then((r) => r.job),

  // Introspected tool catalog — every UI-invocable tool with its real JSON
  // Schema + policy flags, straight from the agent's @tool registry.
  getToolCatalog: (sessionId: string) =>
    actionFetch<{ ok: true; tools: ToolCatalogEntry[] }>(`${ws(sessionId)}/tools`).then(
      (r) => r.tools
    ),

  invokeTool: (sessionId: string, tool: string, args: Record<string, unknown>) =>
    actionFetch<{ ok: true; tool: string; result: unknown }>(`${ws(sessionId)}/invoke`, {
      method: "POST",
      body: JSON.stringify({ tool, arguments: args }),
    }),

  retryRun: (
    sessionId: string,
    runId: string,
    body: { fromStage: string; maxStage?: string; overrides?: Record<string, unknown> }
  ) =>
    actionFetch<{ ok: true; runId: string; pollAfterSec?: number }>(
      `${ws(sessionId)}/runs/${encodeURIComponent(runId)}/retry`,
      { method: "POST", body: JSON.stringify(body) }
    ),

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
