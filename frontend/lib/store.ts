import { create } from "zustand";
import type {
  Project,
  Session,
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
} from "@/types";
import { projectsApi, sessionsApi, chatApi, workspaceApi, workbenchApi } from "./api";
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

  // WebSocket
  ws: WebSocket | null;
  wsSessionId: string | null;

  // Sidebar state
  sidebarCollapsed: boolean;

  // Artifacts panel state
  artifactsVisible: boolean;
  activeArtifactTab: ArtifactTab;

  // Workspace data
  files: FileInfo[];
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
  actionPending: { lint: boolean; sim: boolean; synth: boolean };

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

  ws: null,
  wsSessionId: null,

  sidebarCollapsed: false,

  artifactsVisible: false,
  activeArtifactTab: "spec",

  files: [],
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
  actionPending: { lint: false, sim: false, synth: false },

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
        ws: null,
        wsSessionId: null,
        files: [],
        spec: null,
        codeFiles: [],
        synthesisRuns: [],
        selectedSynthesisRunId: null,
        report: null,
        artifactsVisible: false,
      }));
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
      ws: null,
      wsSessionId: null,
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
      // Load chat history and workspace data
      await get().loadChatHistory();
      await get().refreshWorkspace();
    }
  },

  // Chat actions
  loadChatHistory: async () => {
    const { currentSession } = get();
    if (!currentSession) return;

    try {
      const history = await chatApi.getHistory(currentSession.id);
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
      set({ chatError: error instanceof Error ? error.message : "Failed to load history" });
    }
  },

  sendMessage: (content: string) => {
    const { currentSession, ws: existingWs, wsSessionId, messages } = get();
    if (!currentSession || !content.trim()) return;
    const messageContent = content;

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: messageContent,
      blocks: [{ type: "text", content: messageContent }],
      timestamp: new Date().toISOString(),
    };

    set({ messages: [...messages, userMessage] });

    // Create or reuse WebSocket
    let ws = existingWs;
    const sessionMismatch = wsSessionId !== currentSession.id;
    if (ws && (ws.readyState !== WebSocket.OPEN || sessionMismatch)) {
      ws.close();
      ws = null;
    }

    if (!ws) {
      ws = chatApi.createConnection(currentSession.id);
      const socket = ws;
      set({ ws: socket, wsSessionId: currentSession.id });

      socket.onopen = () => {
        // Ignore stale socket opens after session/socket replacement.
        if (get().ws !== socket) return;
        socket.send(JSON.stringify({ message: messageContent }));
      };
    } else {
      ws.send(JSON.stringify({ message: messageContent }));
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
      set({ ws: null, wsSessionId: null });
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
      });
    }
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
      const [files, waveformFiles, layoutFiles, schematicFiles, synthesisRuns] = await Promise.all([
        workspaceApi.listFiles(currentSession.id).catch(() => []),
        workspaceApi.listWaveforms(currentSession.id).catch(() => []),
        workspaceApi.listLayouts(currentSession.id).catch(() => []),
        workspaceApi.listSchematics(currentSession.id).catch(() => []),
        workspaceApi.listSynthesisRuns(currentSession.id).catch(() => []),
      ]);

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

    try {
      const codeFiles = await workspaceApi.getCodeFiles(currentSession.id);
      set({
        codeFiles,
        selectedCodeFile: codeFiles[0]?.filename || null,
      });
    } catch {
      set({ codeFiles: [], selectedCodeFile: null });
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

    try {
      const targetRunId = runId === undefined ? get().selectedSynthesisRunId : runId;
      const report = await workspaceApi.getReport(currentSession.id, targetRunId);
      set({ report });
    } catch {
      set({ report: null });
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
    try {
      const manifest = await workbenchApi.getManifest(currentSession.id);
      set({ manifest });
    } catch {
      set({ manifest: null });
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
    pushConsole(set, get, {
      channel: get().activeConsole,
      status: "info",
      summary:
        `Uploaded ${res.uploaded.length} file(s): ${res.uploaded.join(", ")}` +
        (notShown.length ? ` — ${notShown.length} non-design file(s) stored but not shown` : ""),
    });
    await get().refreshWorkspace();
    return { uploaded: res.uploaded, notShown };
  },

  loadRuns: async () => {
    const { currentSession, runKindFilter } = get();
    if (!currentSession) return;
    try {
      const runs = await workbenchApi.listRuns(currentSession.id, runKindFilter);
      set((state) => ({
        runs,
        selectedRunId:
          runs.find((r) => r.id === state.selectedRunId)?.id ?? runs[0]?.id ?? null,
      }));
    } catch {
      set({ runs: [] });
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
    } catch (e) {
      pushConsole(set, get, { channel: "sim", status: "failed", summary: friendlyError(e) });
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
      await get().loadRuns();

      // Poll the job until terminal (bounded), surfacing stage progress.
      const sid = currentSession.id;
      const deadline = Date.now() + 20 * 60 * 1000;
      let interval = 3000;
      // eslint-disable-next-line no-constant-condition
      while (Date.now() < deadline) {
        await sleep(interval);
        if (get().currentSession?.id !== sid) return; // session switched away
        let job: Record<string, unknown>;
        try {
          job = await workbenchApi.getJob(sid, jobId);
        } catch {
          continue;
        }
        const state = String(job.status ?? "");
        const stage = String(job.current_stage ?? job.stage ?? "");
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
          if (state === "completed") await get().selectRun(runId);
          break;
        }
        interval = Math.min(interval * 1.5, 30000);
      }
    } catch (e) {
      pushConsole(set, get, { channel: "synth", status: "failed", summary: friendlyError(e) });
    } finally {
      set((s) => ({ actionPending: { ...s.actionPending, synth: false } }));
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
