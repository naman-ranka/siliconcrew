import { create } from "zustand";
import type { Session, Message, ToolCall, ToolResult, ArtifactTab, SpecData, CodeFile, WaveformData, FileInfo } from "@/types";
import { sessionsApi, chatApi, workspaceApi } from "./api";
import { generateId } from "./utils";

interface AppState {
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
  report: { filename: string; content: string } | null;
  layoutFiles: string[];
  schematicFiles: string[];

  // Actions
  loadSessions: () => Promise<void>;
  createSession: (name: string, model: string) => Promise<void>;
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
  loadWaveforms: () => Promise<void>;
  selectWaveform: (filename: string) => Promise<void>;
  loadReport: () => Promise<void>;
  generateReport: () => Promise<void>;
}

export const useStore = create<AppState>((set, get) => ({
  // Initial state
  sessions: [],
  currentSession: null,
  sessionsLoading: false,
  sessionsError: null,

  messages: [],
  isStreaming: false,
  streamingMessage: null,
  chatError: null,

  ws: null,

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
  report: null,
  layoutFiles: [],
  schematicFiles: [],

  // Session actions
  loadSessions: async () => {
    set({ sessionsLoading: true, sessionsError: null });
    try {
      const sessions = await sessionsApi.list();
      // Sort sessions by created_at (latest first)
      const sortedSessions = [...sessions].sort((a, b) => {
        const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
        const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
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

  createSession: async (name: string, model: string) => {
    try {
      const session = await sessionsApi.create(name, model);
      set((state) => ({
        sessions: [session, ...state.sessions],
        currentSession: session,
        messages: [],
        files: [],
        spec: null,
        codeFiles: [],
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
    if (ws) {
      ws.close();
    }

    set({
      currentSession: session,
      messages: [],
      ws: null,
      spec: null,
      codeFiles: [],
      selectedCodeFile: null,
      waveformFiles: [],
      selectedWaveform: null,
      waveformData: null,
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
      const messages: Message[] = history.map((msg, idx) => ({
        id: generateId(),
        role: msg.role as "user" | "assistant",
        content: msg.content,
        tool_calls: msg.tool_calls,
        tool_results: msg.tool_results,
      }));
      set({ messages, chatError: null });
    } catch (error) {
      set({ chatError: error instanceof Error ? error.message : "Failed to load history" });
    }
  },

  sendMessage: (content: string) => {
    const { currentSession, ws: existingWs, messages } = get();
    if (!currentSession || !content.trim()) return;

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: content.trim(),
      timestamp: new Date().toISOString(),
    };

    set({ messages: [...messages, userMessage] });

    // Create or reuse WebSocket
    let ws = existingWs;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      ws = chatApi.createConnection(currentSession.id);
      set({ ws });

      ws.onopen = () => {
        ws!.send(JSON.stringify({ message: content.trim() }));
      };
    } else {
      ws.send(JSON.stringify({ message: content.trim() }));
    }

    // Create streaming message placeholder
    const streamingMessage: Message = {
      id: generateId(),
      role: "assistant",
      content: "",
      tool_calls: [],
      tool_results: [],
      timestamp: new Date().toISOString(),
    };

    set({ isStreaming: true, streamingMessage, chatError: null });

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const { streamingMessage: msg, messages: currentMessages } = get();

      if (!msg) return;

      switch (data.type) {
        case "text_delta":
        case "text":
          // Text streaming - update content
          set({
            streamingMessage: { ...msg, content: data.content },
          });
          break;

        case "tool_call":
          set({
            streamingMessage: {
              ...msg,
              tool_calls: [...(msg.tool_calls || []), data.tool as ToolCall],
            },
          });
          break;

        case "tool_result":
          const result: ToolResult = {
            tool_call_id: data.tool_call_id,
            status: data.status,
            content: data.content,
          };
          set({
            streamingMessage: {
              ...msg,
              tool_results: [...(msg.tool_results || []), result],
            },
          });
          // Refresh workspace when file-writing tools complete to show artifacts immediately
          const toolCall = msg.tool_calls?.find((tc) => tc.id === data.tool_call_id);
          if (toolCall && ["write_spec", "write_file", "edit_file_tool", "generate_report_tool"].includes(toolCall.name)) {
            get().refreshWorkspace();
          }
          break;

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

    ws.onerror = () => {
      set({
        chatError: "WebSocket connection error",
        isStreaming: false,
        streamingMessage: null,
      });
    };

    ws.onclose = () => {
      set({ ws: null });
    };
  },

  stopStreaming: () => {
    const { ws, streamingMessage, messages } = get();
    if (ws) {
      ws.close();
    }
    if (streamingMessage) {
      set({
        messages: [...messages, { ...streamingMessage, content: streamingMessage.content + "\n\n[Stopped]" }],
        isStreaming: false,
        streamingMessage: null,
        ws: null,
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

    // Capture previous state for comparison
    const prevSpec = get().spec;
    const prevCodeCount = get().codeFiles.length;
    const prevWaveformCount = get().waveformFiles.length;
    const prevSchematicCount = get().schematicFiles.length;
    const prevReport = get().report;

    try {
      const [files, waveformFiles, layoutFiles, schematicFiles] = await Promise.all([
        workspaceApi.listFiles(currentSession.id).catch(() => []),
        workspaceApi.listWaveforms(currentSession.id).catch(() => []),
        workspaceApi.listLayouts(currentSession.id).catch(() => []),
        workspaceApi.listSchematics(currentSession.id).catch(() => []),
      ]);

      set({ files, waveformFiles, layoutFiles, schematicFiles });

      // Auto-load spec and code if they exist
      const hasSpec = files.some((f) => f.type === "spec");
      const hasCode = files.some((f) => f.type === "verilog");
      const hasReport = files.some((f) => f.type === "report");

      // Load content
      if (hasSpec) {
        await get().loadSpec();
      }
      if (hasCode) {
        await get().loadCodeFiles();
      }
      if (hasReport) {
        await get().loadReport();
      }

      // Get updated state after loading
      const newState = get();
      let newTab: ArtifactTab | null = null;

      // Detect what's new (priority: report > waveform > code > schematic > spec)
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

  loadReport: async () => {
    const { currentSession } = get();
    if (!currentSession) return;

    try {
      const report = await workspaceApi.getReport(currentSession.id);
      set({ report });
    } catch {
      set({ report: null });
    }
  },

  generateReport: async () => {
    const { currentSession } = get();
    if (!currentSession) return;

    try {
      const report = await workspaceApi.generateReport(currentSession.id);
      set({ report });
    } catch (error) {
      throw error;
    }
  },
}));
