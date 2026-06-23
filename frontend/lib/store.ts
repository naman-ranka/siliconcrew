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
  ConsoleChannel,
  ConsoleEntry,
  SynthJobStatus,
  Toast,
} from "@/types";
import { projectsApi, sessionsApi, threadsApi, modelsApi, chatApi, workspaceApi, workbenchApi } from "./api";
import { generateId } from "./utils";

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
  consoleEntries: ConsoleEntry[];
  activeConsole: ConsoleChannel;
  // Monotonic counter the Console watches to draw attention to a fresh result
  // (auto-expand + pulse) — e.g. a lint result that would otherwise be a quiet
  // one-liner while the center stays on Code. Carries which channel to focus.
  consoleAttention: { tick: number; channel: ConsoleChannel } | null;
  // Live ORFS synth job status (stages, elapsed, remote label) while a synth
  // runs; null when no synth is in flight. Drives the stage-progress UI.
  synthJob: SynthJobStatus | null;
  actionPending: { lint: boolean; sim: boolean; synth: boolean };
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
  setActiveConsole: (channel: ConsoleChannel) => void;
  runLint: () => Promise<void>;
  runSim: (opts?: { mode?: string; runId?: string }) => Promise<void>;
  runSynth: () => Promise<void>;
  refreshSynthArtifacts: (runId?: string | null) => Promise<void>;
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
  consoleEntries: [],
  activeConsole: "sim",
  consoleAttention: null,
  synthJob: null,
  actionPending: { lint: false, sim: false, synth: false },
  runsLoading: false,
  manifestLoading: false,
  reportLoading: false,
  codeLoading: false,
  uploadNotice: null,
  toasts: [],

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
    });

    if (session) {
      // Threads first (sets activeThreadId), then that thread's history, then files.
      await get().loadThreads();
      await get().loadChatHistory();
      await get().refreshWorkspace();
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

    set({ isStreaming: true, streamingMessage, chatError: null });

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
          break;
        }

        case "done":
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

        case "error":
          set({
            chatError: data.error,
            isStreaming: false,
            streamingMessage: null,
          });
          break;
      }
    };

    socket.onerror = () => {
      if (get().ws !== socket) return;
      set({
        chatError: "WebSocket connection error",
        isStreaming: false,
        streamingMessage: null,
      });
    };

    socket.onclose = () => {
      if (get().ws !== socket) return;
      set({ ws: null, wsSessionId: null, wsThreadId: null });
    };
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

  // Workspace actions
  refreshWorkspace: async () => {
    const { currentSession } = get();
    if (!currentSession) return;

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

      // Load content
      if (hasSpec) {
        await get().loadSpec();
      }
      if (hasCode) {
        await get().loadCodeFiles();
      }
      if (hasReport) {
        await get().loadReport(nextRunId);
      }

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
    await Promise.all([get().loadManifest(), get().loadRuns(), get().refreshWorkspace()]);
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
    pushConsole(set, get, {
      channel: get().activeConsole,
      status: "info",
      summary: notice,
    });
    await get().refreshWorkspace();
    return { uploaded: res.uploaded, notShown };
  },

  loadRuns: async () => {
    const { currentSession, runKindFilter } = get();
    if (!currentSession) return;
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
  },

  setRunKindFilter: (kind) => {
    set({ runKindFilter: kind });
    void get().loadRuns();
  },

  setActiveConsole: (channel) => set({ activeConsole: channel }),

  selectRun: async (runId: string | null, opts?: { keepTab?: boolean }) => {
    set({ selectedRunId: runId });
    if (!runId) return;
    const run = get().runs.find((r) => r.id === runId);
    if (!run) return;

    if (run.kind === "sim") {
      set({ activeConsole: "sim" });
      // Backfill the console from the selected run's stored record so a user
      // landing on a historical failure sees its command + ERROR immediately
      // (not "No sim output yet").
      pushConsole(set, get, {
        channel: "sim",
        status: run.status === "running" ? "running" : run.status,
        runId: run.id,
        command: [run.compileCommand, run.simCommand].filter(Boolean).join("\n") || undefined,
        summary:
          run.status === "passed"
            ? `${run.id} passed (${run.top})${run.passMarkerFound ? " · TEST PASSED" : ""}`
            : `${run.id} failed${run.failure?.timeNs != null ? ` @ ${run.failure.timeNs}ns` : ""}` +
              (run.failure?.firstFailureLine ? ` — ${run.failure.firstFailureLine.slice(0, 90)}` : ""),
        detail: [run.failure?.firstFailureLine, run.stdoutTail, run.stderrTail].filter(Boolean).join("\n") || undefined,
      });
      if (run.vcdPath) {
        await get().selectWaveform(run.vcdPath);
        if (!opts?.keepTab) set({ artifactsVisible: true, activeArtifactTab: "waveform" });
      }
    } else {
      set({ activeConsole: "synth", selectedSynthesisRunId: runId });
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

  runLint: async () => {
    const { currentSession } = get();
    if (!currentSession) return;
    set((s) => ({ activeConsole: "lint", actionPending: { ...s.actionPending, lint: true } }));
    pushConsole(set, get, { channel: "lint", status: "running", summary: "Linting…" });
    try {
      const result = await workbenchApi.lint(currentSession.id);
      set({ lintResult: result });
      const n = result.errors.length;
      pushConsole(set, get, {
        channel: "lint",
        status: result.status,
        command: result.command,
        summary:
          result.status === "passed"
            ? `Lint passed (${result.warnings.length} warning(s))`
            : `Lint failed — ${n} error(s), ${result.warnings.length} warning(s)`,
        detail: [...result.errors, ...result.warnings]
          .map((d) => `${d.file ?? ""}:${d.line ?? "?"} ${d.severity}: ${d.message}`)
          .join("\n"),
      });
      // Lint has no center-artifact surface, so make the result noticeable:
      // ask the Console to auto-expand + pulse on the Lint channel.
      bumpConsoleAttention(set, "lint");
    } catch (e) {
      pushConsole(set, get, { channel: "lint", status: "failed", summary: friendlyError(e) });
    } finally {
      set((s) => ({ actionPending: { ...s.actionPending, lint: false } }));
    }
  },

  runSim: async (opts) => {
    const { currentSession } = get();
    if (!currentSession) return;
    set((s) => ({ activeConsole: "sim", actionPending: { ...s.actionPending, sim: true } }));
    pushConsole(set, get, { channel: "sim", status: "running", summary: "Simulating…" });
    try {
      const run = await workbenchApi.simulate(currentSession.id, opts ?? {});
      await get().loadRuns();
      pushConsole(set, get, {
        channel: "sim",
        status: run.status,
        command: [run.compileCommand, run.simCommand].filter(Boolean).join("\n"),
        runId: run.id,
        summary:
          run.status === "passed"
            ? `${run.id} passed (${run.top})${run.passMarkerFound ? " · TEST PASSED" : ""}`
            : `${run.id} failed${run.failure?.timeNs != null ? ` @ ${run.failure.timeNs}ns` : ""}` +
              // surface the human reason inline, not just behind the console chevron
              (run.failure?.firstFailureLine ? ` — ${run.failure.firstFailureLine.slice(0, 90)}` : ""),
        detail: [run.failure?.firstFailureLine, run.stdoutTail, run.stderrTail].filter(Boolean).join("\n"),
      });
      // Keep the user on the Code tab if they're mid-iteration (edit→re-run),
      // otherwise reveal the waveform for the fresh run.
      const onCode = get().activeArtifactTab === "code";
      await get().selectRun(run.id, { keepTab: onCode });
      // Human-first titles: lead with the action ("Simulation passed/failed"),
      // demote the run id into the detail line (a run id reads like a DB key).
      get().pushToast(
        run.status === "passed"
          ? {
              kind: "success",
              title: "Simulation passed",
              detail: [run.id, run.top].filter(Boolean).join(" · ") || undefined,
            }
          : {
              kind: "error",
              title: `Simulation failed${run.failure?.timeNs != null ? ` @ ${run.failure.timeNs}ns` : ""}`,
              detail:
                [run.id, run.failure?.firstFailureLine].filter(Boolean).join(" — ") || undefined,
            }
      );
    } catch (e) {
      pushConsole(set, get, { channel: "sim", status: "failed", summary: friendlyError(e) });
      get().pushToast({ kind: "error", title: "Simulation failed", detail: friendlyError(e) });
    } finally {
      set((s) => ({ actionPending: { ...s.actionPending, sim: false } }));
    }
  },

  runSynth: async () => {
    const { currentSession } = get();
    if (!currentSession) return;
    set((s) => ({ activeConsole: "synth", actionPending: { ...s.actionPending, synth: true } }));
    pushConsole(set, get, { channel: "synth", status: "running", summary: "Starting synthesis…" });
    try {
      const { jobId, runId } = await workbenchApi.synthesize(currentSession.id);
      pushConsole(set, get, { channel: "synth", status: "running", runId, summary: `${runId} queued (job ${jobId})` });
      // Seed the live job status so the stage-progress UI appears immediately
      // (before the first poll lands).
      set({ synthJob: { jobId, runId, status: "queued", currentStage: "constraints" } });
      await get().loadRuns();

      // Poll the job until terminal (bounded), surfacing stage progress.
      const sid = currentSession.id;
      const deadline = Date.now() + 20 * 60 * 1000;
      let interval = 3000;
      // eslint-disable-next-line no-constant-condition
      while (Date.now() < deadline) {
        await sleep(interval);
        if (get().currentSession?.id !== sid) {
          set({ synthJob: null });
          return; // session switched away
        }
        let job: Record<string, unknown>;
        try {
          job = await workbenchApi.getJob(sid, jobId);
        } catch {
          continue;
        }
        const state = String(job.status ?? "");
        const stage = String(job.current_stage ?? job.stage ?? "");
        // Publish the structured job status for the stage-progress UI.
        set({ synthJob: toSynthJobStatus(jobId, runId, job) });
        pushConsole(set, get, { channel: "synth", status: "running", runId, summary: `${runId} ${state}${stage ? ` · ${stage}` : ""}` });
        if (state === "completed" || state === "failed") {
          await get().loadRuns();
          // On failure, surface whatever the job knows (notes + log tail) so the
          // user sees *why* (e.g. ORFS/Docker unavailable) instead of just "failed".
          const notes = job.check_notes;
          const logTail = Array.isArray(job.last_log_lines) ? (job.last_log_lines as string[]).slice(-12).join("\n") : "";
          const detail =
            state === "failed"
              ? [typeof notes === "string" ? notes : "", logTail, job.next_action as string]
                  .filter(Boolean)
                  .join("\n")
              : undefined;
          pushConsole(set, get, {
            channel: "synth",
            status: state === "completed" ? "passed" : "failed",
            runId,
            summary: `${runId} ${state}`,
            detail,
          });
          if (state === "completed") {
            // A successful tape-out must immediately LOOK successful without a
            // hard reload: refresh the layout/schematic file lists, auto-generate
            // the report, then select the run (lands on Report with PPA + GDS).
            await get().refreshSynthArtifacts(runId);
            await get().selectRun(runId);
          }
          set({ synthJob: null });
          break;
        }
        interval = Math.min(interval * 1.5, 30000);
      }
    } catch (e) {
      pushConsole(set, get, { channel: "synth", status: "failed", summary: friendlyError(e) });
      set({ synthJob: null });
    } finally {
      set((s) => ({ actionPending: { ...s.actionPending, synth: false } }));
    }
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
}));

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

// Translate the backend's terse action errors into plain language + a next step
// (the #1 quit-point for newcomers, per the first-time-user review).
function friendlyError(e: unknown): string {
  const raw = errMsg(e);
  const r = raw.toLowerCase();
  if (r.includes("no simtop"))
    return "No testbench found. Simulation needs a testbench (a *_tb.v that instantiates your design). Add or upload one, then Run Sim.";
  if (r.includes("no rtl/tb") || (r.includes("no files") && r.includes("simulate")))
    return "Nothing to simulate yet — add or upload your Verilog (RTL + a testbench) first.";
  if (r.includes("no rtl files") || r.includes("no_rtl"))
    return "No RTL to lint yet — add or upload a .v file, then Run Lint.";
  if (r.includes("no synthtop"))
    return "No top module for synthesis. Add your RTL (the design's top module), then Run Synth.";
  if (r.includes("no rtl files to synthesize"))
    return "Nothing to synthesize yet — add or upload your RTL first.";
  return raw;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Normalize the backend job-status payload into the typed SynthJobStatus the
// stage-progress UI consumes.
function toSynthJobStatus(jobId: string, runId: string, job: Record<string, unknown>): SynthJobStatus {
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

// Bump the attention counter so the Console auto-expands + pulses on a fresh
// result for `channel`. Monotonic tick lets the component fire its effect even
// when the channel is unchanged between consecutive results.
let _consoleAttentionTick = 0;
function bumpConsoleAttention(
  set: (fn: (s: AppState) => Partial<AppState>) => void,
  channel: ConsoleChannel
) {
  _consoleAttentionTick += 1;
  set(() => ({ consoleAttention: { tick: _consoleAttentionTick, channel } }));
}

// Append a console entry, collapsing the most recent "running" entry on the
// same channel so a finished action replaces its own spinner line.
function pushConsole(
  set: (fn: (s: AppState) => Partial<AppState>) => void,
  get: () => AppState,
  entry: Omit<ConsoleEntry, "ts">
) {
  const full: ConsoleEntry = { ...entry, ts: new Date().toISOString() };
  set((s) => {
    const entries = [...s.consoleEntries];
    const last = entries[entries.length - 1];
    // Collapse a finished action onto its own spinner line…
    if (last && last.channel === entry.channel && last.status === "running") {
      entries[entries.length - 1] = full;
    } else if (
      // …and skip exact re-selections (same channel+run+summary) so re-clicking
      // a historical run doesn't spam the console.
      last &&
      last.channel === entry.channel &&
      last.runId === entry.runId &&
      last.summary === entry.summary
    ) {
      return {};
    } else {
      entries.push(full);
    }
    return { consoleEntries: entries.slice(-100) };
  });
}
