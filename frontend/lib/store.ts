import { create } from "zustand";
import type {
  Project,
  Session,
  ChatThread,
  ModelInfo,
  Message,
  ToolCall,
  ToolResult,
  ContentBlock,
  ArtifactTab,
  SpecData,
  CodeFile,
  WaveformData,
  FileInfo,
  ReportData,
  SynthesisRun,
  DesignManifest,
  RunSummary,
  LintResult,
  FileRole,
  SynthJobStatus,
  Toast,
  SliceStatus,
  ActivityEvent,
  DirEntry,
  SmartFile,
} from "@/types";
import { projectsApi, sessionsApi, threadsApi, modelsApi, chatApi, workspaceApi, workbenchApi } from "./api";
import { generateId } from "./utils";
import { makeArtifactKey, type ArtifactKey } from "./artifactKeys";
import { isDuplicateOfServer, mergeActivity, upsertActivityEvent } from "./activityMerge";

// F4/F5: store-level single-flight for the workspace hydrate + workbench load,
// keyed by session id. Every trigger — mount, selectSession, chat-complete,
// upload, the active-run poll, manual refresh — shares one in-flight promise, so
// the heavy hydration runs ONCE even when several fire together (the double-open
// and the two polling loops overlapping during a synth). Cleared on settle.
const _inflight = new Map<string, Promise<unknown>>();
function singleFlight<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const existing = _inflight.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const p = fn().finally(() => {
    if (_inflight.get(key) === p) _inflight.delete(key);
  });
  _inflight.set(key, p);
  return p;
}

// Which artifact tab a file type maps to (initial-load tab selection).
const _fileTypeToTab: Record<string, ArtifactTab | undefined> = {
  spec: "spec",
  verilog: "code",
  waveform: "waveform",
  schematic: "schematic",
  report: "report",
};
function newestArtifactTab(files: FileInfo[]): ArtifactTab | null {
  let best: { tab: ArtifactTab; ts: number } | null = null;
  for (const f of files) {
    const tab = _fileTypeToTab[f.type];
    if (!tab) continue;
    const ts = f.modified ? new Date(f.modified).getTime() : 0;
    if (!best || ts > best.ts) best = { tab, ts };
  }
  return best?.tab ?? null;
}

// --- Workbench v2 SWR slices -------------------------------------------------
// The iron rule for every slice below: a populated slice NEVER goes back to
// "loading" — a refetch is "revalidating" (old data stays visible) and a failed
// revalidate keeps the data and sets the error.

export interface DirSlice {
  status: SliceStatus;
  entries: DirEntry[];
  error: string | null;
}

export interface FileSlice {
  status: SliceStatus;
  file: SmartFile | null;
  modified: string | null;
  error: string | null;
  // LRU bookkeeping (monotonic access stamp; see lruTick()).
  lastAccess: number;
}

export interface ArtifactSlice {
  status: SliceStatus;
  data: unknown;
  // terminal artifacts (from passed/failed runs) can never change → cached
  // forever, never refetched.
  terminal: boolean;
  error: string | null;
  lastAccess: number;
}

export interface ActivitySlice {
  // Durable log pages from GET /activity (newest-first).
  serverEvents: ActivityEvent[];
  // Synthetic live events from WS tool frames (id "ws:<tool_call_id>").
  // Merged/deduped at read time via selectActivity().
  localEvents: ActivityEvent[];
  status: SliceStatus;
  nextBefore: string | null;
  error: string | null;
}

const FILE_CACHE_CAP = 30;
const ARTIFACT_CACHE_CAP = 12;

// Monotonic access stamp for LRU eviction — strictly increasing (Date.now()
// ties within a millisecond would make eviction order nondeterministic).
let _lruCounter = 0;
function lruTick(): number {
  return ++_lruCounter;
}

// Evict least-recently-used entries beyond `cap` (in-flight entries are safe).
function evictLru<T extends { lastAccess: number; status: SliceStatus }>(
  cache: Record<string, T>,
  cap: number
): Record<string, T> {
  const keys = Object.keys(cache);
  if (keys.length <= cap) return cache;
  const next = { ...cache };
  const evictable = keys
    .filter((k) => next[k].status !== "loading" && next[k].status !== "revalidating")
    .sort((a, b) => next[a].lastAccess - next[b].lastAccess);
  let excess = keys.length - cap;
  for (const k of evictable) {
    if (excess <= 0) break;
    delete next[k];
    excess -= 1;
  }
  return next;
}

const emptyActivity = (): ActivitySlice => ({
  serverEvents: [],
  localEvents: [],
  status: "empty",
  nextBefore: null,
  error: null,
});

// Local start clocks for WS tool calls → durationMs on the synthetic events.
const _wsToolStart = new Map<string, number>();

// Which dirCache prefixes a completed WS tool invalidates ("" = root only).
const TOOL_DIR_INVALIDATION: Record<string, string[]> = {
  write_spec: [""],
  write_file: [""],
  edit_file_tool: [""],
  apply_patch_tool: [""],
  generate_report_tool: [""],
  simulation_tool: ["", "sim_runs"],
  run_isolated_simulation: ["", "sim_runs"],
  start_synthesis: ["", "synth_runs"],
  retry_pd: ["", "synth_runs"],
};

// Debounced activity refresh after WS tool results — a burst of tool frames
// coalesces into ONE GET /activity (limit 50).
let _activityRefreshTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleActivityRefresh(get: () => AppState): void {
  if (_activityRefreshTimer) return;
  _activityRefreshTimer = setTimeout(() => {
    _activityRefreshTimer = null;
    void get().loadActivity();
  }, 1200);
}

interface AppState {
  // Project state
  projects: Project[];
  loadProjects: () => Promise<void>;
  createProject: (name: string) => Promise<Project>;
  deleteProject: (projectId: string) => Promise<void>;
  moveSession: (sessionId: string, projectId: string | null) => Promise<void>;

  // Session state
  sessions: Session[];
  currentSession: Session | null;
  sessionsLoading: boolean;
  sessionsError: string | null;

  // Chat state
  messages: Message[];
  isStreaming: boolean;
  streamingMessage: Message | null;
  chatError: string | null;
  // Machine-readable code from a WS error frame (e.g. "no_key",
  // "hosted_tier_exhausted") so the chat can render an actionable CTA.
  chatErrorCode: string | null;

  // Chat threads (many conversations per workspace). The active thread keys the
  // LangGraph checkpoint; all threads share the live workspace.
  threads: ChatThread[];
  activeThreadId: string | null;
  threadsLoading: boolean;

  // Model registry (the picker). The active thread's model is what the WS uses.
  models: ModelInfo[];
  modelsLoaded: boolean;

  // WebSocket
  ws: WebSocket | null;
  wsSessionId: string | null;
  wsThreadId: string | null;

  // Sidebar state
  sidebarCollapsed: boolean;

  // Artifacts panel state
  artifactsVisible: boolean;
  activeArtifactTab: ArtifactTab;

  // Settings modal (BYOK API Keys). Opened from the sidebar Settings button and
  // from the chat "Add an API key" CTA — shared state so either surface can open it.
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;

  // Workspace data
  files: FileInfo[];
  // Set when the session's workspace failed to load (e.g. a transient backend
  // error / a cold hosted instance that hasn't rehydrated). Distinguishes
  // "couldn't load" from a genuinely empty new session so the UI surfaces it
  // instead of silently showing the empty onboarding.
  workspaceError: string | null;
  spec: SpecData | null;
  codeFiles: CodeFile[];
  selectedCodeFile: string | null;
  waveformFiles: string[];
  selectedWaveform: string | null;
  waveformData: WaveformData | null;
  synthesisRuns: SynthesisRun[];
  selectedSynthesisRunId: string | null;
  report: ReportData | null;
  layoutFiles: string[];
  selectedLayout: string | null;
  schematicFiles: string[];

  // Actions
  loadSessions: () => Promise<void>;
  createSession: (name: string, model: string, projectId?: string | null) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  selectSession: (session: Session | null) => Promise<void>;

  loadChatHistory: () => Promise<void>;
  sendMessage: (content: string) => void;
  stopStreaming: () => void;

  // Chat thread actions
  loadThreads: () => Promise<void>;
  newThread: () => Promise<void>;
  selectThread: (threadId: string) => Promise<void>;
  deleteThread: (threadId: string) => Promise<void>;
  renameThread: (threadId: string, title: string) => Promise<void>;

  // Model actions
  loadModels: () => Promise<void>;
  setActiveThreadModel: (modelId: string) => Promise<void>;

  toggleSidebar: () => void;
  toggleArtifacts: () => void;
  setArtifactTab: (tab: ArtifactTab) => void;

  refreshWorkspace: () => Promise<void>;
  loadSpec: () => Promise<void>;
  loadCodeFiles: () => Promise<void>;
  selectCodeFile: (filename: string) => void;
  saveCodeFile: (filename: string, content: string) => Promise<void>;
  loadWaveforms: () => Promise<void>;
  selectWaveform: (filename: string) => Promise<void>;
  loadSynthesisRuns: () => Promise<void>;
  selectSynthesisRun: (runId: string | null) => Promise<void>;
  loadReport: (runId?: string | null) => Promise<void>;
  generateReport: (runId?: string | null) => Promise<void>;
  selectLayout: (filename: string) => void;

  // --- Workbench (Phase 1) ---
  manifest: DesignManifest | null;
  runs: RunSummary[];
  selectedRunId: string | null;
  runKindFilter: "all" | "sim" | "synth";
  lintResult: LintResult | null;
  // Live ORFS synth job status (stages, elapsed, remote label) while a synth
  // runs; null when no synth is in flight. Drives the stage-progress UI
  // (RunsPane's live stage cell; published by lib/commands' job poll).
  synthJob: SynthJobStatus | null;
  // Section-load flags drive skeleton loaders so a section shows shimmer rows
  // instead of flashing an empty/"No …" state before content lands.
  runsLoading: boolean;
  manifestLoading: boolean;
  reportLoading: boolean;
  codeLoading: boolean;
  uploadNotice: string | null;
  toasts: Toast[];
  pushToast: (t: Omit<Toast, "id">, ttlMs?: number) => void;
  dismissToast: (id: string) => void;

  loadWorkbench: () => Promise<void>;
  loadManifest: () => Promise<void>;
  setFileRole: (name: string, role: FileRole) => Promise<void>;
  uploadFiles: (files: File[]) => Promise<{ uploaded: string[]; notShown: string[] }>;
  loadRuns: () => Promise<void>;
  selectRun: (runId: string | null, opts?: { keepTab?: boolean }) => Promise<void>;
  pinRun: (runId: string, pinned: boolean) => Promise<void>;
  setRunKindFilter: (kind: "all" | "sim" | "synth") => void;
  refreshSynthArtifacts: (runId?: string | null) => Promise<void>;

  // --- Workbench v2 data layer (SWR slices) ---
  // Lazy directory tree: key "" = workspace root. Single-flight per path.
  dirCache: Record<string, DirSlice>;
  loadDir: (path: string, opts?: { revalidate?: boolean }) => Promise<void>;
  // Refetch every cached dir whose path matches a prefix ("" matches root
  // only), keeping old entries visible (status "revalidating").
  invalidateDirs: (prefixes: string[]) => void;

  // Smart file cache (LRU cap 30). Cache hit iff the caller's `modified` stamp
  // matches the cached one and both are non-null (null = always stale).
  fileCache: Record<string, FileSlice>;
  loadFile: (path: string, opts?: { modified?: string | null }) => Promise<void>;

  // Generic artifact cache (LRU cap 12), keyed by lib/artifactKeys.ts keys.
  // terminal+ready → cached forever; non-terminal → revalidate on each call.
  artifactCache: Record<ArtifactKey, ArtifactSlice>;
  loadArtifact: (
    key: ArtifactKey,
    loader: () => Promise<unknown>,
    opts: { terminal: boolean }
  ) => Promise<void>;
  loadWaveformArtifact: (runId: string, vcdPath: string) => Promise<void>;
  loadReportArtifact: (runId: string) => Promise<void>;

  // Unified activity feed (server pages + live WS events; see selectActivity).
  activity: ActivitySlice;
  loadActivity: (opts?: { more?: boolean }) => Promise<void>;
  appendLocalActivity: (event: ActivityEvent) => void;
}

function buildBlocks(
  content: string,
  toolCalls?: ToolCall[],
  toolResults?: ToolResult[]
): ContentBlock[] {
  const blocks: ContentBlock[] = [];
  if (content) blocks.push({ type: "text", content });
  for (const tc of toolCalls ?? []) {
    blocks.push({
      type: "tool",
      toolCall: tc,
      result: toolResults?.find((r) => r.tool_call_id === tc.id),
    });
  }
  return blocks;
}

export const useStore = create<AppState>((set, get) => ({
  // Initial state
  projects: [],
  sessions: [],
  currentSession: null,
  sessionsLoading: false,
  sessionsError: null,

  messages: [],
  isStreaming: false,
  streamingMessage: null,
  chatError: null,
  chatErrorCode: null,

  threads: [],
  activeThreadId: null,
  threadsLoading: false,

  models: [],
  modelsLoaded: false,

  ws: null,
  wsSessionId: null,
  wsThreadId: null,

  sidebarCollapsed: false,

  artifactsVisible: false,
  activeArtifactTab: "spec",
  settingsOpen: false,

  files: [],
  workspaceError: null,
  spec: null,
  codeFiles: [],
  selectedCodeFile: null,
  waveformFiles: [],
  selectedWaveform: null,
  waveformData: null,
  synthesisRuns: [],
  selectedSynthesisRunId: null,
  report: null,
  layoutFiles: [],
  selectedLayout: null,
  schematicFiles: [],

  // Workbench state
  manifest: null,
  runs: [],
  selectedRunId: null,
  runKindFilter: "all",
  lintResult: null,
  synthJob: null,
  runsLoading: false,
  manifestLoading: false,
  reportLoading: false,
  codeLoading: false,
  uploadNotice: null,
  toasts: [],

  // Workbench v2 data-layer state
  dirCache: {},
  fileCache: {},
  artifactCache: {},
  activity: emptyActivity(),

  pushToast: (t, ttlMs = 5000) => {
    const id = generateId();
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    if (ttlMs > 0) {
      setTimeout(() => {
        useStore.setState((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
      }, ttlMs);
    }
  },

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),

  // Project actions
  loadProjects: async () => {
    try {
      const projects = await projectsApi.list();
      set({ projects });
    } catch {
      // non-fatal — sidebar still works without projects
    }
  },

  createProject: async (name: string) => {
    const project = await projectsApi.create(name);
    set((state) => ({ projects: [...state.projects, project] }));
    return project;
  },

  deleteProject: async (projectId: string) => {
    await projectsApi.delete(projectId);
    set((state) => ({
      projects: state.projects.filter((p) => p.id !== projectId),
      // Unassign sessions that belonged to this project
      sessions: state.sessions.map((s) =>
        s.project_id === projectId ? { ...s, project_id: null } : s
      ),
    }));
  },

  moveSession: async (sessionId: string, projectId: string | null) => {
    const updated = await sessionsApi.patch(sessionId, projectId);
    set((state) => ({
      sessions: state.sessions.map((s) => (s.id === sessionId ? updated : s)),
    }));
  },

  // Session actions
  loadSessions: async () => {
    set({ sessionsLoading: true, sessionsError: null });
    try {
      const sessions = await sessionsApi.list();
      // Sort sessions by updated_at (most recently used first), fallback to created_at
      const sortedSessions = [...sessions].sort((a, b) => {
        const dateA = new Date(a.updated_at ?? a.created_at ?? 0).getTime();
        const dateB = new Date(b.updated_at ?? b.created_at ?? 0).getTime();
        return dateB - dateA;
      });
      set({ sessions: sortedSessions, sessionsLoading: false });
    } catch (error) {
      set({
        sessionsError: error instanceof Error ? error.message : "Failed to load sessions",
        sessionsLoading: false,
      });
    }
  },

  createSession: async (name: string, model: string, projectId?: string | null) => {
    try {
      const { ws } = get();
      set({ ws: null, wsSessionId: null });
      if (ws) ws.close();
      const session = await sessionsApi.create(name, model, projectId);
      set((state) => ({
        sessions: [session, ...state.sessions],
        currentSession: session,
        messages: [],
        threads: [],
        activeThreadId: null,
        ws: null,
        wsSessionId: null,
        wsThreadId: null,
        files: [],
        spec: null,
        codeFiles: [],
        synthesisRuns: [],
        selectedSynthesisRunId: null,
        report: null,
        artifactsVisible: false,
        // v2 caches are per-session — never leak across a switch.
        dirCache: {},
        fileCache: {},
        artifactCache: {},
        activity: emptyActivity(),
      }));
      // Materialize the session's default thread ("Chat 1") for the switcher.
      await get().loadThreads();
    } catch (error) {
      throw error;
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      await sessionsApi.delete(sessionId);
      set((state) => {
        const newSessions = state.sessions.filter((s) => s.id !== sessionId);
        const newCurrentSession =
          state.currentSession?.id === sessionId
            ? newSessions[0] || null
            : state.currentSession;
        return {
          sessions: newSessions,
          currentSession: newCurrentSession,
          messages: state.currentSession?.id === sessionId ? [] : state.messages,
        };
      });
    } catch (error) {
      throw error;
    }
  },

  selectSession: async (session: Session | null) => {
    // Close existing WebSocket
    const { ws } = get();
    set({ ws: null, wsSessionId: null });
    if (ws) {
      ws.close();
    }

    set({
      currentSession: session,
      messages: [],
      threads: [],
      activeThreadId: null,
      ws: null,
      wsSessionId: null,
      wsThreadId: null,
      spec: null,
      codeFiles: [],
      selectedCodeFile: null,
      waveformFiles: [],
      selectedWaveform: null,
      waveformData: null,
      synthesisRuns: [],
      selectedSynthesisRunId: null,
      report: null,
      files: [],
      // v2 caches are per-session — never leak across a switch.
      dirCache: {},
      fileCache: {},
      artifactCache: {},
      activity: emptyActivity(),
    });

    if (session) {
      // Threads first (sets activeThreadId), then that thread's history, then the
      // workbench (manifest + runs + workspace) in ONE snapshot hydration. This
      // is the single load on open — callers no longer follow with loadWorkbench
      // (F4: was a double refresh).
      await get().loadThreads();
      await get().loadChatHistory();
      await get().loadWorkbench();
    }
  },

  // Chat actions
  loadChatHistory: async () => {
    const { currentSession, activeThreadId } = get();
    if (!currentSession) return;

    try {
      const history = activeThreadId
        ? await chatApi.getThreadHistory(currentSession.id, activeThreadId)
        : await chatApi.getHistory(currentSession.id);
      const messages: Message[] = history.map((msg) => ({
        id: generateId(),
        role: msg.role as "user" | "assistant",
        content: msg.content,
        tool_calls: msg.tool_calls,
        tool_results: msg.tool_results,
        blocks: buildBlocks(msg.content ?? "", msg.tool_calls, msg.tool_results),
      }));
      // Reopen reconciliation (F4): if the last assistant turn ends on a tool call
      // with no closing summary, it was interrupted before finishing (e.g. the WS
      // dropped mid-synthesis). Mark it honestly instead of leaving a dangling
      // "Waiting for Synthesis" that looks perpetually in-progress — the real
      // status lives in the Runs / Signoff panel.
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        const b = last.blocks ?? [];
        if (b.length > 0 && b[b.length - 1].type === "tool") {
          last.blocks = [
            ...b,
            { type: "text", content: "_The reply was interrupted before a summary — see the Runs / Signoff panel for the final status._" },
          ];
        }
      }
      set({ messages, chatError: null });
    } catch (error) {
      // A fresh session with no history is NOT an error — the backend now
      // returns 200 [] for it. Treat "session not found"/empty-history failures
      // as a calm empty state (no messages, no red banner) rather than alarming
      // the user before they've even started.
      const msg = error instanceof Error ? error.message : "Failed to load history";
      if (/session not found|not found|no history/i.test(msg)) {
        set({ messages: [], chatError: null });
      } else {
        set({ chatError: msg });
      }
    }
  },

  sendMessage: (content: string) => {
    const { currentSession, ws: existingWs, wsSessionId, wsThreadId, activeThreadId, messages } = get();
    if (!currentSession || !content.trim()) return;
    const messageContent = content;
    // The chat thread this message belongs to (defaults to Chat 1 = session id).
    const threadId = activeThreadId || currentSession.id;

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: messageContent,
      blocks: [{ type: "text", content: messageContent }],
      timestamp: new Date().toISOString(),
    };

    set({ messages: [...messages, userMessage] });

    // Create or reuse WebSocket. Reconnect when the session OR the active thread
    // changed, so each chat checkpoints under its own thread_id.
    let ws = existingWs;
    const mismatch = wsSessionId !== currentSession.id || wsThreadId !== threadId;
    if (ws && (ws.readyState !== WebSocket.OPEN || mismatch)) {
      ws.close();
      ws = null;
    }

    if (!ws) {
      ws = chatApi.createConnection(currentSession.id, threadId);
      const socket = ws;
      set({ ws: socket, wsSessionId: currentSession.id, wsThreadId: threadId });

      socket.onopen = () => {
        // Ignore stale socket opens after session/socket replacement.
        if (get().ws !== socket) return;
        socket.send(JSON.stringify({ message: messageContent, thread_id: threadId }));
      };
    } else {
      ws.send(JSON.stringify({ message: messageContent, thread_id: threadId }));
    }

    // Create streaming message placeholder
    const streamingMessage: Message = {
      id: generateId(),
      role: "assistant",
      content: "",
      tool_calls: [],
      tool_results: [],
      blocks: [],
      timestamp: new Date().toISOString(),
    };

    set({ isStreaming: true, streamingMessage, chatError: null, chatErrorCode: null });

    let terminalReceived = false;
    const socket = ws;
    socket.onmessage = (event) => {
      if (get().ws !== socket) return;
      const data = JSON.parse(event.data);
      const { streamingMessage: msg, messages: currentMessages } = get();

      if (!msg) return;

      switch (data.type) {
        case "text_delta":
        case "text": {
          const updatedBlocks = [...(msg.blocks ?? [])];
          const lastIdx = updatedBlocks.length - 1;
          if (lastIdx >= 0 && updatedBlocks[lastIdx].type === "text") {
            updatedBlocks[lastIdx] = { type: "text", content: data.content };
          } else {
            updatedBlocks.push({ type: "text", content: data.content });
          }
          set({ streamingMessage: { ...msg, content: data.content, blocks: updatedBlocks } });
          break;
        }

        case "tool_call": {
          const newToolBlock: ContentBlock = { type: "tool", toolCall: data.tool as ToolCall };
          set({
            streamingMessage: {
              ...msg,
              tool_calls: [...(msg.tool_calls || []), data.tool as ToolCall],
              blocks: [...(msg.blocks ?? []), newToolBlock],
            },
          });
          // Live activity: surface the tool immediately as a synthetic running
          // event (the server log page catches up on the debounced refresh).
          const tc = data.tool as ToolCall;
          _wsToolStart.set(tc.id, Date.now());
          get().appendLocalActivity({
            id: `ws:${tc.id}`,
            ts: new Date().toISOString(),
            source: "agent",
            tool: tc.name,
            args: tc.args ?? {},
            status: "running",
            resultSummary: "",
            durationMs: null,
            runId: null,
            threadId,
          });
          break;
        }

        case "tool_result": {
          const result: ToolResult = {
            tool_call_id: data.tool_call_id,
            status: data.status,
            content: data.content,
          };
          const updatedBlocks = (msg.blocks ?? []).map((block) =>
            block.type === "tool" && block.toolCall.id === data.tool_call_id
              ? { ...block, result }
              : block
          );
          set({
            streamingMessage: {
              ...msg,
              tool_results: [...(msg.tool_results || []), result],
              blocks: updatedBlocks,
            },
          });
          // Refresh workspace when file-writing tools complete to show artifacts immediately
          const toolCall = msg.tool_calls?.find((tc) => tc.id === data.tool_call_id);
          if (toolCall && ["write_spec", "write_file", "edit_file_tool", "generate_report_tool"].includes(toolCall.name)) {
            get().refreshWorkspace();
          }
          // Live activity: upgrade the synthetic running event to ok/error with
          // a local-clock duration; keep the original (call-time) timestamp.
          const startedAt = _wsToolStart.get(data.tool_call_id);
          _wsToolStart.delete(data.tool_call_id);
          const prevLocal = get().activity.localEvents.find(
            (e) => e.id === `ws:${data.tool_call_id}`
          );
          const resultStatus = String(data.status ?? "").toLowerCase();
          get().appendLocalActivity({
            id: `ws:${data.tool_call_id}`,
            ts: prevLocal?.ts ?? new Date().toISOString(),
            source: "agent",
            tool: toolCall?.name ?? prevLocal?.tool ?? "unknown",
            args: toolCall?.args ?? prevLocal?.args ?? {},
            status: ["error", "fail", "failed"].includes(resultStatus) ? "error" : "ok",
            resultSummary: typeof data.content === "string" ? data.content.slice(0, 200) : "",
            durationMs: startedAt != null ? Date.now() - startedAt : null,
            runId: null,
            threadId,
          });
          // Reconcile with the durable log soon (one debounced GET /activity per
          // burst of tool frames) and refetch the dirs this tool may have changed.
          scheduleActivityRefresh(get);
          if (toolCall) {
            const dirPrefixes = TOOL_DIR_INVALIDATION[toolCall.name];
            if (dirPrefixes) get().invalidateDirs(dirPrefixes);
          }
          break;
        }

        case "ping":
          break; // server keepalive during long tool jobs; no UI effect

        case "done":
          terminalReceived = true;
          const { streamingMessage: finalMsg, messages: finalMessages } = get();
          if (finalMsg) {
            set({
              messages: [...finalMessages, finalMsg],
              isStreaming: false,
              streamingMessage: null,
            });
          }
          // Final workspace refresh after completion
          get().refreshWorkspace();
          // Reflect server-side auto-title / last-active reordering in the switcher.
          get().loadThreads();
          break;

        case "error": {
          terminalReceived = true;
          // Keep whatever streamed so far instead of discarding the trace.
          const { streamingMessage: em, messages: emsgs } = get();
          const keep = em && ((em.blocks?.length ?? 0) > 0 || em.content);
          set({
            messages: keep ? [...emsgs, em!] : emsgs,
            chatError: data.error,
            chatErrorCode: data.code ?? null,
            isStreaming: false,
            streamingMessage: null,
          });
          break;
        }
      }
    };

    // A socket that closes/errors WITHOUT a done/error frame is an unexpected drop
    // (e.g. an idle/proxy timeout during a long tool job). Recover instead of
    // leaving the UI stuck "streaming": preserve the partial trace, re-enable
    // input, surface the state, and refetch persisted history — the agent can keep
    // running server-side (Cloud Run), so the completed result often lands there.
    // Guarded so error+close only handle the drop once.
    const finalizeDrop = () => {
      if (get().ws !== socket) return;
      if (terminalReceived) {
        set({ ws: null, wsSessionId: null, wsThreadId: null });
        return;
      }
      terminalReceived = true;
      const { streamingMessage: dm, messages: dmsgs } = get();
      const keep = dm && ((dm.blocks?.length ?? 0) > 0 || dm.content);
      set({
        messages: keep ? [...dmsgs, dm!] : dmsgs,
        streamingMessage: null,
        isStreaming: false,
        ws: null,
        wsSessionId: null,
        wsThreadId: null,
        chatError: "Connection lost — fetching the latest result from the server…",
        chatErrorCode: "ws_dropped",
      });
      // Pragmatic resume: refetch persisted history (with a couple of backoff
      // retries) to pick up a run the server finished after the socket dropped.
      let attempt = 0;
      const poll = () => {
        attempt += 1;
        void get().loadChatHistory().finally(() => {
          if (attempt < 3) setTimeout(poll, attempt * 2000);
        });
      };
      setTimeout(poll, 1500);
    };

    socket.onerror = finalizeDrop;
    socket.onclose = finalizeDrop;
  },

  stopStreaming: () => {
    const { ws, streamingMessage, messages } = get();
    if (ws) ws.close();
    if (streamingMessage) {
      const stoppedText = "\n\n[Stopped]";
      const blocks = [...(streamingMessage.blocks ?? [])];
      const last = blocks.length - 1;
      if (last >= 0 && blocks[last].type === "text") {
        const prev = blocks[last] as { type: "text"; content: string };
        blocks[last] = { type: "text", content: prev.content + stoppedText };
      } else {
        blocks.push({ type: "text", content: stoppedText });
      }
      set({
        messages: [...messages, { ...streamingMessage, content: streamingMessage.content + stoppedText, blocks }],
        isStreaming: false,
        streamingMessage: null,
        ws: null,
        wsSessionId: null,
        wsThreadId: null,
      });
    }
  },

  // Chat thread actions — many conversations per workspace. Threads share the
  // LIVE workspace; switching a thread only swaps the conversation history.
  loadThreads: async () => {
    const { currentSession } = get();
    if (!currentSession) return;
    set({ threadsLoading: true });
    try {
      const threads = await threadsApi.list(currentSession.id);
      const cur = get().activeThreadId;
      // Keep the active thread if it still exists; else land on newest-active.
      const active = cur && threads.some((t) => t.id === cur) ? cur : threads[0]?.id ?? null;
      set({ threads, activeThreadId: active, threadsLoading: false });
    } catch (error) {
      set({
        threadsLoading: false,
        chatError: error instanceof Error ? error.message : "Failed to load chats",
      });
    }
  },

  newThread: async () => {
    const { currentSession, ws } = get();
    if (!currentSession) return;
    const thread = await threadsApi.create(currentSession.id);
    if (ws) ws.close();
    set((state) => ({
      threads: [thread, ...state.threads],
      activeThreadId: thread.id,
      messages: [],
      ws: null,
      wsSessionId: null,
      wsThreadId: null,
      chatError: null,
    }));
  },

  selectThread: async (threadId: string) => {
    const { currentSession, activeThreadId, ws } = get();
    if (!currentSession || threadId === activeThreadId) return;
    if (ws) ws.close();
    set({ activeThreadId: threadId, messages: [], ws: null, wsSessionId: null, wsThreadId: null });
    await get().loadChatHistory();
  },

  deleteThread: async (threadId: string) => {
    const { currentSession, activeThreadId, threads, ws } = get();
    if (!currentSession) return;
    await threadsApi.delete(currentSession.id, threadId);
    const remaining = threads.filter((t) => t.id !== threadId);
    const wasActive = activeThreadId === threadId;
    if (wasActive && ws) ws.close();
    set({
      threads: remaining,
      activeThreadId: wasActive ? remaining[0]?.id ?? null : activeThreadId,
      ...(wasActive ? { messages: [], ws: null, wsSessionId: null, wsThreadId: null } : {}),
    });
    if (wasActive) {
      // Re-materialize (ensures a Chat 1 exists) and load the next conversation.
      await get().loadThreads();
      await get().loadChatHistory();
    }
  },

  renameThread: async (threadId: string, title: string) => {
    const { currentSession } = get();
    if (!currentSession) return;
    await threadsApi.patch(currentSession.id, threadId, { title });
    set((state) => ({
      threads: state.threads.map((t) => (t.id === threadId ? { ...t, title } : t)),
    }));
  },

  // Model actions — the chosen model lives on the active thread; the WS reads it.
  loadModels: async () => {
    if (get().modelsLoaded) return;
    try {
      const data = await modelsApi.list();
      // Be defensive about the response shape so the picker never crashes.
      set({ models: Array.isArray(data?.models) ? data.models : [], modelsLoaded: true });
    } catch {
      set({ models: [], modelsLoaded: true });
    }
  },

  setActiveThreadModel: async (modelId: string) => {
    const { currentSession, activeThreadId } = get();
    if (!currentSession) return;
    // If no thread is active yet, load threads to get the real default thread UUID
    // (never use the session ID as a thread ID — threads have auto-generated UUIDs).
    let tid = activeThreadId;
    if (!tid) {
      await get().loadThreads();
      tid = get().activeThreadId;
    }
    if (!tid) return; // no thread exists at all; bail silently
    // Persist on the thread; the next message uses it (WS reads the thread model).
    await threadsApi.patch(currentSession.id, tid, { model: modelId });
    set((state) => ({
      activeThreadId: tid,
      threads: state.threads.some((t) => t.id === tid)
        ? state.threads.map((t) => (t.id === tid ? { ...t, model: modelId } : t))
        : state.threads,
    }));
  },

  // UI actions
  toggleSidebar: () => {
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }));
  },

  toggleArtifacts: () => {
    set((state) => ({ artifactsVisible: !state.artifactsVisible }));
  },

  setArtifactTab: (tab: ArtifactTab) => {
    set({ activeArtifactTab: tab, artifactsVisible: true });
  },

  setSettingsOpen: (open: boolean) => {
    set({ settingsOpen: open });
  },

  // Workspace actions
  refreshWorkspace: async () => {
    const { currentSession } = get();
    if (!currentSession) return;
    return singleFlight(`refresh:${currentSession.id}`, async () => {

    const parseModified = (modified?: string) => (modified ? new Date(modified).getTime() : 0);

    const fileTypeToArtifactTab = (type: FileInfo["type"]): ArtifactTab | null => {
      switch (type) {
        case "spec":
          return "spec";
        case "verilog":
          return "code";
        case "waveform":
          return "waveform";
        case "schematic":
          return "schematic";
        case "report":
          return "report";
        default:
          return null;
      }
    };

    const getNewestArtifactFromFiles = (files: FileInfo[]) => {
      let best: { tab: ArtifactTab; ts: number } | null = null;
      for (const f of files) {
        const tab = fileTypeToArtifactTab(f.type);
        if (!tab) continue;
        const ts = parseModified(f.modified);
        if (!best || ts > best.ts) best = { tab, ts };
      }
      return best;
    };

    const prevNewestArtifact = getNewestArtifactFromFiles(get().files);

    // Capture previous state for comparison
    const prevSpec = get().spec;
    const prevCodeCount = get().codeFiles.length;
    const prevWaveformCount = get().waveformFiles.length;
    const prevSchematicCount = get().schematicFiles.length;
    const prevReport = get().report;

    try {
      // listFiles is the canonical "did the workspace load" probe — track its
      // failure explicitly so a transient/unavailable workspace surfaces a
      // banner instead of masquerading as an empty new session. The secondary
      // lists stay best-effort.
      let workspaceLoadFailed = false;
      const [files, waveformFiles, layoutFiles, schematicFiles, synthesisRuns] = await Promise.all([
        workspaceApi.listFiles(currentSession.id).catch(() => {
          workspaceLoadFailed = true;
          return [];
        }),
        workspaceApi.listWaveforms(currentSession.id).catch(() => []),
        workspaceApi.listLayouts(currentSession.id).catch(() => []),
        workspaceApi.listSchematics(currentSession.id).catch(() => []),
        workspaceApi.listSynthesisRuns(currentSession.id).catch(() => []),
      ]);

      set({
        workspaceError: workspaceLoadFailed
          ? "Couldn't load this session's workspace. It may be temporarily unavailable — retry."
          : null,
      });

      const currentRunId = get().selectedSynthesisRunId;
      const nextRunId =
        synthesisRuns.find((run) => run.run_id === currentRunId)?.run_id ??
        synthesisRuns[0]?.run_id ??
        null;

      set({ files, waveformFiles, layoutFiles, schematicFiles, synthesisRuns, selectedSynthesisRunId: nextRunId });

      const newNewestArtifact = getNewestArtifactFromFiles(files);

      // Auto-load spec and code if they exist
      const hasSpec = files.some((f) => f.type === "spec");
      const hasCode = files.some((f) => f.type === "verilog");
      const hasReport = files.some((f) => f.type === "report") || synthesisRuns.some((run) => run.report_available);

      // Load content in parallel — spec, code and report set independent state
      // slices, so serial awaits only added latency (spec blocked code blocked
      // report). Fetch them concurrently.
      await Promise.all([
        hasSpec ? get().loadSpec() : Promise.resolve(),
        hasCode ? get().loadCodeFiles() : Promise.resolve(),
        hasReport ? get().loadReport(nextRunId) : Promise.resolve(),
      ]);

      // Get updated state after loading
      const newState = get();
      let newTab: ArtifactTab | null = null;

      // Prefer switching to the most recently modified artifact type
      const newestArtifactIsNewer =
        newNewestArtifact &&
        (!prevNewestArtifact || newNewestArtifact.ts > prevNewestArtifact.ts);

      if (newestArtifactIsNewer) {
        newTab = newNewestArtifact!.tab;
      } else {
        // Fallback: detect "new" by presence/count deltas
        // (priority: report > waveform > code > schematic > spec)
        const specIsNew = hasSpec && newState.spec && !prevSpec;
        const codeIsNew = newState.codeFiles.length > prevCodeCount;
        const waveformIsNew = waveformFiles.length > prevWaveformCount;
        const schematicIsNew = schematicFiles.length > prevSchematicCount;
        const reportIsNew = hasReport && newState.report && !prevReport;

        if (reportIsNew) {
          newTab = "report";
        } else if (waveformIsNew) {
          newTab = "waveform";
        } else if (codeIsNew) {
          newTab = "code";
        } else if (schematicIsNew) {
          newTab = "schematic";
        } else if (specIsNew) {
          newTab = "spec";
        }
      }

      // Show artifacts panel and switch tab if we have content
      const hasContent = hasSpec || hasCode || hasReport || waveformFiles.length > 0 || schematicFiles.length > 0;
      if (hasContent) {
        if (newTab) {
          set({ artifactsVisible: true, activeArtifactTab: newTab });
        } else if (!newState.artifactsVisible) {
          // Open panel if it's closed and we have content
          set({ artifactsVisible: true });
        }
      }
    } catch (error) {
      console.error("Failed to refresh workspace:", error);
    }
    });
  },

  loadSpec: async () => {
    const { currentSession } = get();
    if (!currentSession) return;

    try {
      const spec = await workspaceApi.getSpec(currentSession.id);
      set({ spec });
    } catch {
      set({ spec: null });
    }
  },

  loadCodeFiles: async () => {
    const { currentSession } = get();
    if (!currentSession) return;

    set({ codeLoading: true });
    try {
      const codeFiles = await workspaceApi.getCodeFiles(currentSession.id);
      set({
        codeFiles,
        selectedCodeFile: codeFiles[0]?.filename || null,
      });
    } catch {
      set({ codeFiles: [], selectedCodeFile: null });
    } finally {
      set({ codeLoading: false });
    }
  },

  selectCodeFile: (filename: string) => {
    set({ selectedCodeFile: filename });
  },

  saveCodeFile: async (filename: string, content: string) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const res = await workbenchApi.saveCode(currentSession.id, filename, content);
    set({ manifest: res.manifest });
    // Reflect the edit in the open viewer + refresh roles/files.
    set((state) => ({
      codeFiles: state.codeFiles.map((f) => (f.filename === filename ? { ...f, content } : f)),
    }));
    await get().loadCodeFiles();
    set({ selectedCodeFile: filename });
  },

  loadWaveforms: async () => {
    const { currentSession } = get();
    if (!currentSession) return;

    try {
      const waveformFiles = await workspaceApi.listWaveforms(currentSession.id);
      set({ waveformFiles });
    } catch {
      set({ waveformFiles: [] });
    }
  },

  selectWaveform: async (filename: string) => {
    const { currentSession } = get();
    if (!currentSession) return;

    set({ selectedWaveform: filename });

    try {
      const waveformData = await workspaceApi.getWaveform(currentSession.id, filename);
      set({ waveformData });
    } catch {
      set({ waveformData: null });
    }
  },

  loadSynthesisRuns: async () => {
    const { currentSession } = get();
    if (!currentSession) return;

    try {
      const synthesisRuns = await workspaceApi.listSynthesisRuns(currentSession.id);
      set((state) => ({
        synthesisRuns,
        selectedSynthesisRunId:
          synthesisRuns.find((run) => run.run_id === state.selectedSynthesisRunId)?.run_id ??
          synthesisRuns[0]?.run_id ??
          null,
      }));
    } catch {
      set({ synthesisRuns: [], selectedSynthesisRunId: null });
    }
  },

  selectSynthesisRun: async (runId: string | null) => {
    // Re-selecting the already-selected run would refetch the same report for
    // nothing (the report is already loaded for it).
    if (runId === get().selectedSynthesisRunId) return;
    set({ selectedSynthesisRunId: runId });
    await get().loadReport(runId);
  },

  loadReport: async (runId?: string | null) => {
    const { currentSession } = get();
    if (!currentSession) return;

    set({ reportLoading: true });
    try {
      const targetRunId = runId === undefined ? get().selectedSynthesisRunId : runId;
      const report = await workspaceApi.getReport(currentSession.id, targetRunId);
      set({ report });
    } catch {
      set({ report: null });
    } finally {
      set({ reportLoading: false });
    }
  },

  generateReport: async (runId?: string | null) => {
    const { currentSession } = get();
    if (!currentSession) return;

    try {
      const targetRunId = runId === undefined ? get().selectedSynthesisRunId : runId;
      const report = await workspaceApi.generateReport(currentSession.id, targetRunId);
      set({ report, selectedSynthesisRunId: report.run_id ?? targetRunId ?? null });
      await get().loadSynthesisRuns();
    } catch (error) {
      throw error;
    }
  },

  selectLayout: (filename: string) => {
    set({ selectedLayout: filename });
  },

  // ====================== Workbench actions ======================

  loadWorkbench: async () => {
    const { currentSession } = get();
    if (!currentSession) return;
    const sid = currentSession.id;
    // F4: single-flight + a ONE-hydration snapshot instead of the ~18-call
    // fan-out. Falls back to the granular loaders if the snapshot is
    // unavailable (older backend) or errors — behavior stays correct.
    return singleFlight(`workbench:${sid}`, async () => {
      try {
        const snap = await workbenchApi.getWorkbench(sid);
        if (get().currentSession?.id !== sid) return; // switched away mid-flight
        const files = snap.files ?? [];
        const runs = snap.runs ?? [];
        const synthesisRuns = snap.synthesisRuns ?? [];
        set((state) => ({
          manifest: snap.manifest ?? null,
          manifestLoading: false,
          runs,
          runsLoading: false,
          selectedRunId:
            runs.find((r) => r.id === state.selectedRunId)?.id ?? runs[0]?.id ?? null,
          files,
          spec: snap.spec ?? null,
          codeFiles: snap.code ?? [],
          selectedCodeFile:
            snap.code?.find((f) => f.filename === state.selectedCodeFile)?.filename ??
            snap.code?.[0]?.filename ??
            null,
          report: snap.report ?? null,
          synthesisRuns,
          selectedSynthesisRunId:
            synthesisRuns.find((r) => r.run_id === state.selectedSynthesisRunId)?.run_id ??
            synthesisRuns[0]?.run_id ??
            null,
          // Derive the artifact file-lists from the single files listing.
          waveformFiles: files.filter((f) => f.type === "waveform").map((f) => f.name),
          layoutFiles: files.filter((f) => f.type === "layout").map((f) => f.name),
          schematicFiles: files.filter((f) => f.type === "schematic").map((f) => f.name),
          // v2: seed the file-tree root + activity feed from the snapshot so
          // their first paint costs no extra round trips.
          ...(snap.rootDir
            ? {
                dirCache: {
                  ...state.dirCache,
                  "": { status: "ready" as SliceStatus, entries: snap.rootDir, error: null },
                },
              }
            : {}),
          ...(snap.activity
            ? {
                activity: {
                  ...state.activity,
                  serverEvents: snap.activity,
                  status: "ready" as SliceStatus,
                  error: null,
                  // Snapshot carries the newest 50 — if full, older pages may
                  // exist past the last event id.
                  nextBefore:
                    snap.activity.length >= 50
                      ? snap.activity[snap.activity.length - 1]?.id ?? null
                      : null,
                },
              }
            : {}),
        }));
        // Reveal the artifacts panel on the newest artifact (initial-load UX).
        const hasContent =
          !!snap.spec || (snap.code?.length ?? 0) > 0 || !!snap.report || files.length > 0;
        if (hasContent) {
          const tab = newestArtifactTab(files);
          set((s) => ({
            artifactsVisible: true,
            activeArtifactTab: tab ?? s.activeArtifactTab,
          }));
        }
      } catch {
        // Snapshot unavailable → the original granular fan-out (still correct).
        await Promise.all([get().loadManifest(), get().loadRuns(), get().refreshWorkspace()]);
      }
    });
  },

  loadManifest: async () => {
    const { currentSession } = get();
    if (!currentSession) return;
    set({ manifestLoading: true });
    try {
      const manifest = await workbenchApi.getManifest(currentSession.id);
      set({ manifest });
    } catch {
      set({ manifest: null });
    } finally {
      set({ manifestLoading: false });
    }
  },

  setFileRole: async (name: string, role: FileRole) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const manifest = await workbenchApi.updateManifest(currentSession.id, { files: [{ name, role }] });
    set({ manifest });
  },

  uploadFiles: async (files: File[]) => {
    const { currentSession } = get();
    if (!currentSession || files.length === 0) return { uploaded: [], notShown: [] };
    const res = await workbenchApi.uploadFiles(currentSession.id, files);
    set({ manifest: res.manifest });
    // Files the server stored but the manifest doesn't surface (non-design types
    // like .txt) — so the upload isn't a silent black box (hobbyist feedback).
    const shown = new Set(res.manifest.files.map((f) => f.name));
    const notShown = res.uploaded.filter((n) => !shown.has(n));
    const notice =
      `✓ Uploaded ${res.uploaded.length} file(s)` +
      (notShown.length ? ` · ${notShown.length} non-design file(s) stored, not shown` : "");
    // Store-driven so the confirmation shows regardless of which surface triggered
    // the upload (file-tree button, drag-drop, or the onboarding CTA).
    set({ uploadNotice: notice });
    get().pushToast({
      kind: "success",
      title: `Uploaded ${res.uploaded.length} file(s)`,
      detail: notShown.length ? `${notShown.length} non-design file(s) stored, not shown` : undefined,
    });
    const token = ++_uploadNoticeToken;
    setTimeout(() => {
      if (_uploadNoticeToken === token) useStore.setState({ uploadNotice: null });
    }, 5000);
    await get().refreshWorkspace();
    return { uploaded: res.uploaded, notShown };
  },

  loadRuns: async () => {
    const { currentSession, runKindFilter } = get();
    if (!currentSession) return;
    // F5: single-flight so the two synth-time loops (the lib/commands job poll and
    // the useWorkbenchSync active-run poll) never double-pull the run list.
    return singleFlight(`runs:${currentSession.id}:${runKindFilter}`, async () => {
      set({ runsLoading: true });
      try {
        const runs = await workbenchApi.listRuns(currentSession.id, runKindFilter);
        set((state) => ({
          runs,
          selectedRunId:
            runs.find((r) => r.id === state.selectedRunId)?.id ?? runs[0]?.id ?? null,
        }));
      } catch {
        set({ runs: [] });
      } finally {
        set({ runsLoading: false });
      }
    });
  },

  setRunKindFilter: (kind) => {
    // Clicking the already-active filter shouldn't trigger a refetch.
    if (get().runKindFilter === kind) return;
    set({ runKindFilter: kind });
    void get().loadRuns();
  },

  selectRun: async (runId: string | null, opts?: { keepTab?: boolean }) => {
    set({ selectedRunId: runId });
    if (!runId) return;
    const run = get().runs.find((r) => r.id === runId);
    if (!run) return;

    if (run.kind === "sim") {
      if (run.vcdPath) {
        await get().selectWaveform(run.vcdPath);
        if (!opts?.keepTab) set({ artifactsVisible: true, activeArtifactTab: "waveform" });
      }
    } else {
      set({ selectedSynthesisRunId: runId });
      await get().loadReport(runId);
      if (!opts?.keepTab) set({ artifactsVisible: true, activeArtifactTab: "report" });
    }
  },

  pinRun: async (runId: string, pinned: boolean) => {
    const { currentSession } = get();
    if (!currentSession) return;
    await workbenchApi.pinRun(currentSession.id, runId, pinned);
    set((state) => ({ runs: state.runs.map((r) => (r.id === runId ? { ...r, pinned } : r)) }));
  },

  // After a synth reaches a passed state, re-pull the artifact file lists and
  // ensure a report exists — so Layout/Schematic/Report update live (the review
  // found they said "No layout yet" until a hard reload).
  refreshSynthArtifacts: async (runId?: string | null) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const sid = currentSession.id;
    const targetRunId = runId ?? get().selectedSynthesisRunId ?? null;
    try {
      const [layoutFiles, schematicFiles] = await Promise.all([
        workspaceApi.listLayouts(sid).catch(() => get().layoutFiles),
        workspaceApi.listSchematics(sid).catch(() => get().schematicFiles),
      ]);
      set({ layoutFiles, schematicFiles });
      if (layoutFiles.length > 0 && !get().selectedLayout) {
        set({ selectedLayout: layoutFiles[0] });
      }
      await get().loadSynthesisRuns();
      // Auto-generate the report once (idempotent on the backend) so a passed
      // synth shows its timing/PPA summary without a manual click.
      try {
        await get().generateReport(targetRunId);
      } catch {
        // Generation may legitimately not apply (e.g. failed run) — fall back to
        // loading whatever report exists.
        await get().loadReport(targetRunId);
      }
    } catch {
      /* best-effort refresh */
    }
  },

  // ====================== Workbench v2 data layer ======================

  loadDir: async (path, opts) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const sid = currentSession.id;
    const cached = get().dirCache[path];
    const populated =
      !!cached && (cached.status === "ready" || cached.status === "revalidating");
    // Ready and not asked to revalidate → serve the cache, no fetch.
    if (populated && !opts?.revalidate) return;
    // SWR iron rule: populated → "revalidating" (entries stay visible),
    // never back to "loading".
    set((s) => ({
      dirCache: {
        ...s.dirCache,
        [path]: {
          status: populated ? "revalidating" : "loading",
          entries: cached?.entries ?? [],
          error: null,
        },
      },
    }));
    await singleFlight(`dir:${sid}:${path}`, async () => {
      try {
        const res = await workspaceApi.getDir(sid, path);
        if (get().currentSession?.id !== sid) return;
        set((s) => ({
          dirCache: {
            ...s.dirCache,
            [path]: { status: "ready", entries: res.entries, error: null },
          },
        }));
      } catch (e) {
        if (get().currentSession?.id !== sid) return;
        // Failed revalidate keeps the old entries visible + records the error.
        set((s) => ({
          dirCache: {
            ...s.dirCache,
            [path]: {
              status: "error",
              entries: s.dirCache[path]?.entries ?? [],
              error: errMsg(e),
            },
          },
        }));
      }
    });
  },

  invalidateDirs: (prefixes) => {
    const matches = (path: string, prefix: string): boolean =>
      prefix === "" ? path === "" : path === prefix || path.startsWith(`${prefix}/`);
    for (const path of Object.keys(get().dirCache)) {
      if (prefixes.some((p) => matches(path, p))) {
        void get().loadDir(path, { revalidate: true });
      }
    }
  },

  loadFile: async (path, opts) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const sid = currentSession.id;
    const cached = get().fileCache[path];
    const wanted = opts?.modified ?? null;
    // Cache hit only when both modified stamps agree AND are non-null — a null
    // stamp means we can't prove freshness, so it's always stale.
    if (cached?.file && wanted !== null && cached.modified === wanted) {
      set((s) => ({
        fileCache: {
          ...s.fileCache,
          [path]: { ...s.fileCache[path], lastAccess: lruTick() },
        },
      }));
      return;
    }
    const populated = !!cached?.file;
    set((s) => ({
      fileCache: {
        ...s.fileCache,
        [path]: {
          status: populated ? "revalidating" : "loading",
          file: cached?.file ?? null,
          modified: cached?.modified ?? null,
          error: null,
          lastAccess: lruTick(),
        },
      },
    }));
    await singleFlight(`file:${sid}:${path}`, async () => {
      try {
        const file = await workspaceApi.getFileSmart(sid, path);
        if (get().currentSession?.id !== sid) return;
        set((s) => ({
          fileCache: evictLru(
            {
              ...s.fileCache,
              [path]: {
                status: "ready",
                file,
                modified: wanted,
                error: null,
                lastAccess: lruTick(),
              },
            },
            FILE_CACHE_CAP
          ),
        }));
      } catch (e) {
        if (get().currentSession?.id !== sid) return;
        set((s) => {
          const prev = s.fileCache[path];
          return {
            fileCache: {
              ...s.fileCache,
              [path]: {
                status: "error",
                file: prev?.file ?? null, // keep stale content visible
                modified: prev?.modified ?? null,
                error: errMsg(e),
                lastAccess: lruTick(),
              },
            },
          };
        });
      }
    });
  },

  loadArtifact: async (key, loader, opts) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const sid = currentSession.id;
    const cached = get().artifactCache[key];
    // Terminal + ready → immutable, never refetch (just bump LRU recency).
    if (cached && cached.terminal && cached.status === "ready") {
      set((s) => ({
        artifactCache: {
          ...s.artifactCache,
          [key]: { ...s.artifactCache[key], lastAccess: lruTick() },
        },
      }));
      return;
    }
    const populated = cached != null && cached.data != null;
    set((s) => ({
      artifactCache: {
        ...s.artifactCache,
        [key]: {
          status: populated ? "revalidating" : "loading",
          data: cached?.data ?? null,
          terminal: opts.terminal,
          error: null,
          lastAccess: lruTick(),
        },
      },
    }));
    await singleFlight(`artifact:${sid}:${key}`, async () => {
      try {
        const data = await loader();
        if (get().currentSession?.id !== sid) return;
        set((s) => ({
          artifactCache: evictLru(
            {
              ...s.artifactCache,
              [key]: {
                status: "ready",
                data,
                terminal: opts.terminal,
                error: null,
                lastAccess: lruTick(),
              },
            },
            ARTIFACT_CACHE_CAP
          ),
        }));
      } catch (e) {
        if (get().currentSession?.id !== sid) return;
        set((s) => {
          const prev = s.artifactCache[key];
          return {
            artifactCache: {
              ...s.artifactCache,
              [key]: {
                status: "error",
                data: prev?.data ?? null, // keep stale data visible
                terminal: opts.terminal,
                error: errMsg(e),
                lastAccess: lruTick(),
              },
            },
          };
        });
      }
    });
  },

  loadWaveformArtifact: async (runId, vcdPath) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const sid = currentSession.id;
    const run = get().runs.find((r) => r.id === runId);
    const terminal = run?.status === "passed" || run?.status === "failed";
    await get().loadArtifact(
      makeArtifactKey("wave", runId),
      () => workspaceApi.getWaveform(sid, vcdPath),
      { terminal }
    );
  },

  loadReportArtifact: async (runId) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const sid = currentSession.id;
    const run = get().runs.find((r) => r.id === runId);
    const terminal = run?.status === "passed" || run?.status === "failed";
    await get().loadArtifact(
      makeArtifactKey("report", runId),
      () => workspaceApi.getReport(sid, runId),
      { terminal }
    );
  },

  loadActivity: async (opts) => {
    const { currentSession } = get();
    if (!currentSession) return;
    const sid = currentSession.id;
    const more = opts?.more === true;
    const before = more ? get().activity.nextBefore : null;
    if (more && !before) return; // log exhausted
    const populated =
      get().activity.serverEvents.length > 0 || get().activity.status === "ready";
    set((s) => ({
      activity: { ...s.activity, status: populated ? "revalidating" : "loading" },
    }));
    await singleFlight(`activity:${sid}:${before ?? "head"}`, async () => {
      try {
        const res = await workbenchApi.getActivity(sid, {
          limit: 50,
          before: before ?? undefined,
        });
        if (get().currentSession?.id !== sid) return;
        set((s) => {
          let serverEvents: ActivityEvent[];
          let nextBefore: string | null;
          if (more) {
            const known = new Set(s.activity.serverEvents.map((e) => e.id));
            serverEvents = [
              ...s.activity.serverEvents,
              ...res.events.filter((e) => !known.has(e.id)),
            ];
            nextBefore = res.nextBefore;
          } else {
            // Head refresh: fresh page wins; retain older, already-paged events
            // past the page boundary so "load more" state isn't lost.
            const pageIds = new Set(res.events.map((e) => e.id));
            const olderRetained = s.activity.serverEvents.filter((e) => !pageIds.has(e.id));
            serverEvents = [...res.events, ...olderRetained];
            nextBefore = olderRetained.length > 0 ? s.activity.nextBefore : res.nextBefore;
          }
          // Prune local events the server log now covers (bounds memory).
          const localEvents = s.activity.localEvents.filter(
            (l) => !serverEvents.some((sv) => isDuplicateOfServer(l, sv))
          );
          return {
            activity: {
              serverEvents,
              localEvents,
              status: "ready",
              nextBefore,
              error: null,
            },
          };
        });
      } catch (e) {
        if (get().currentSession?.id !== sid) return;
        // Failed (re)fetch keeps whatever events we have + records the error.
        set((s) => ({
          activity: { ...s.activity, status: "error", error: errMsg(e) },
        }));
      }
    });
  },

  appendLocalActivity: (event) => {
    set((s) => ({
      activity: {
        ...s.activity,
        localEvents: upsertActivityEvent(s.activity.localEvents, event),
      },
    }));
  },
}));

// Memoized merged Activity view (server pages + live WS events, newest-first,
// deduped). Reference-stable while neither input list changes, so components
// can use it directly as a zustand selector without re-render churn.
let _activityMemo: {
  server: ActivityEvent[];
  local: ActivityEvent[];
  merged: ActivityEvent[];
} | null = null;
export function selectActivity(state: Pick<AppState, "activity">): ActivityEvent[] {
  const { serverEvents, localEvents } = state.activity;
  if (
    _activityMemo &&
    _activityMemo.server === serverEvents &&
    _activityMemo.local === localEvents
  ) {
    return _activityMemo.merged;
  }
  const merged = mergeActivity(serverEvents, localEvents);
  _activityMemo = { server: serverEvents, local: localEvents, merged };
  return merged;
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

// Normalize the backend job-status payload into the typed SynthJobStatus the
// live-stage UI consumes (exported for lib/commands' job poll).
export function toSynthJobStatus(jobId: string, runId: string, job: Record<string, unknown>): SynthJobStatus {
  const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
  return {
    jobId,
    runId,
    status: String(job.status ?? ""),
    currentStage: (job.current_stage as string | null) ?? null,
    stages: (job.stages as SynthJobStatus["stages"]) ?? undefined,
    elapsedSec: num(job.elapsed_sec),
    backend: typeof job.backend === "string" ? job.backend : null,
    remote: typeof job.remote === "boolean" ? job.remote : null,
    executionLabel: typeof job.execution_label === "string" ? job.execution_label : null,
  };
}

// Token so a newer upload notice isn't cleared early by an older timeout.
let _uploadNoticeToken = 0;
