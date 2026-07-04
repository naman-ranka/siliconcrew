import { useMemo } from "react";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

// Workbench v2 UI-chrome store — SEPARATE from the data store (lib/store.ts) so
// pure view state (open tabs, dock layout, expanded dirs) survives reloads via
// localStorage without ever persisting data-layer caches. Only `perSession` is
// persisted (partialize); everything else is ephemeral per page load.

export interface SessionUiState {
  // Artifact keys (lib/artifactKeys.ts) open in the center tab strip.
  openTabs: string[];
  activeTab: string | null;
  unreadRunIds: string[];
  expandedDirs: string[];
  dockTab: "activity" | "runs";
  dockCollapsed: boolean;
  chatOpen: boolean;
  /** Agent-shell right panel (ArtifactCenter wrapper) open/collapsed (S4). */
  artifactsOpen: boolean;
  /** Agent-shell artifact panel width toggle (Wave 8): false = normal split,
   * true = wide. Optional-field pattern (like `shell`) — absent means false,
   * and pre-Wave-8 persisted state needs no migration. */
  artifactsWide?: boolean;
  /** Preferred shell posture ("Open in Chat" vs "Open in IDE") — a viewing
   * preference, so it lives client-side. Absent = never chosen; "ide" stays
   * the fallback everywhere ("Open in Chat" opens the agent shell, S4). */
  shell?: "agent" | "ide";
}

export function emptySessionUi(): SessionUiState {
  return {
    openTabs: [],
    activeTab: null,
    unreadRunIds: [],
    expandedDirs: [],
    dockTab: "activity",
    dockCollapsed: false,
    chatOpen: true,
    artifactsOpen: true,
  };
}

export interface ContextMenuState {
  x: number;
  y: number;
  path: string;
  /** Row kind — dir rows get the (smaller) folder menu. Default: "file". */
  kind?: "file" | "dir" | "empty";
}

interface WorkbenchUiState {
  // Persisted (partialize): per-session UI chrome, keyed by session id.
  perSession: Record<string, SessionUiState>;
  // Persisted (partialize): last session opened at /w/{id} — set by the /w
  // page when a session loads successfully; the legacy /workbench shim
  // redirects here (S1).
  lastSessionId: string | null;

  // Ephemeral (never persisted).
  paletteOpen: boolean;
  quickOpenOpen: boolean;
  /** ⌘O session quick-switch overlay (S3). */
  quickSwitchOpen: boolean;
  /** Agent-shell left nav rail overlay (Wave 8; ⌘O in the agent posture). */
  navRailOpen: boolean;
  commandModal: string | null;
  commandSurfaceOpen: boolean;
  // Tab key to flash (attention pulse) — set by openTab, cleared by clearFlash.
  flashKey: string | null;
  contextMenu: ContextMenuState | null;
  // FileExplorer "New file" inline input: null = closed; "" = root; a dir
  // path pre-fills the input with `<dir>/`.
  newFilePrefix: string | null;
  /** What the inline creator makes: a file, or a folder (via its .gitkeep). */
  newFileKind: "file" | "folder";

  // Actions
  openTab: (sessionId: string, key: string) => void;
  closeTab: (sessionId: string, key: string) => void;
  setActiveTab: (sessionId: string, key: string | null) => void;
  markUnread: (sessionId: string, runId: string) => void;
  clearUnread: (sessionId: string, runId: string) => void;
  toggleDir: (sessionId: string, path: string) => void;
  setDockTab: (sessionId: string, tab: "activity" | "runs") => void;
  setDockCollapsed: (sessionId: string, collapsed: boolean) => void;
  setChatOpen: (sessionId: string, open: boolean) => void;
  setArtifactsOpen: (sessionId: string, open: boolean) => void;
  setArtifactsWide: (sessionId: string, wide: boolean) => void;
  setShell: (sessionId: string, shell: "agent" | "ide") => void;
  setLastSessionId: (sessionId: string | null) => void;
  setPaletteOpen: (open: boolean) => void;
  setQuickOpenOpen: (open: boolean) => void;
  setQuickSwitchOpen: (open: boolean) => void;
  setNavRailOpen: (open: boolean) => void;
  setCommandModal: (id: string | null) => void;
  setCommandSurfaceOpen: (open: boolean) => void;
  setContextMenu: (menu: ContextMenuState | null) => void;
  setNewFilePrefix: (prefix: string | null, kind?: "file" | "folder") => void;
  clearFlash: () => void;
}

export const useWorkbenchUiStore = create<WorkbenchUiState>()(
  persist(
    (set) => {
      // Update one session's UI slice, defaulting missing sessions.
      const updateSession = (
        sessionId: string,
        fn: (ui: SessionUiState) => SessionUiState
      ) =>
        set((s) => ({
          perSession: {
            ...s.perSession,
            [sessionId]: fn(s.perSession[sessionId] ?? emptySessionUi()),
          },
        }));

      return {
        perSession: {},
        lastSessionId: null,

        paletteOpen: false,
        commandSurfaceOpen: false,
        quickOpenOpen: false,
        quickSwitchOpen: false,
        navRailOpen: false,
        commandModal: null,
        flashKey: null,
        contextMenu: null,
        newFilePrefix: null,
        newFileKind: "file",

        openTab: (sessionId, key) => {
          updateSession(sessionId, (ui) => ({
            ...ui,
            // Focus if already open, else append.
            openTabs: ui.openTabs.includes(key) ? ui.openTabs : [...ui.openTabs, key],
            activeTab: key,
          }));
          set({ flashKey: key });
        },

        closeTab: (sessionId, key) => {
          updateSession(sessionId, (ui) => {
            const openTabs = ui.openTabs.filter((k) => k !== key);
            return {
              ...ui,
              openTabs,
              // Closing the active tab falls back to the last remaining tab.
              activeTab:
                ui.activeTab === key
                  ? openTabs[openTabs.length - 1] ?? null
                  : ui.activeTab,
            };
          });
        },

        setActiveTab: (sessionId, key) => {
          updateSession(sessionId, (ui) => ({ ...ui, activeTab: key }));
        },

        markUnread: (sessionId, runId) => {
          updateSession(sessionId, (ui) => ({
            ...ui,
            unreadRunIds: ui.unreadRunIds.includes(runId)
              ? ui.unreadRunIds
              : [...ui.unreadRunIds, runId],
          }));
        },

        clearUnread: (sessionId, runId) => {
          updateSession(sessionId, (ui) => ({
            ...ui,
            unreadRunIds: ui.unreadRunIds.filter((id) => id !== runId),
          }));
        },

        toggleDir: (sessionId, path) => {
          updateSession(sessionId, (ui) => ({
            ...ui,
            expandedDirs: ui.expandedDirs.includes(path)
              ? ui.expandedDirs.filter((p) => p !== path)
              : [...ui.expandedDirs, path],
          }));
        },

        setDockTab: (sessionId, tab) => {
          updateSession(sessionId, (ui) => ({ ...ui, dockTab: tab }));
        },

        setDockCollapsed: (sessionId, collapsed) => {
          updateSession(sessionId, (ui) => ({ ...ui, dockCollapsed: collapsed }));
        },

        setChatOpen: (sessionId, open) => {
          updateSession(sessionId, (ui) => ({ ...ui, chatOpen: open }));
        },

        setArtifactsOpen: (sessionId, open) => {
          updateSession(sessionId, (ui) => ({ ...ui, artifactsOpen: open }));
        },

        setArtifactsWide: (sessionId, wide) => {
          updateSession(sessionId, (ui) => ({ ...ui, artifactsWide: wide }));
        },

        setShell: (sessionId, shell) => {
          updateSession(sessionId, (ui) => ({ ...ui, shell }));
        },

        setLastSessionId: (sessionId) => set({ lastSessionId: sessionId }),

        setPaletteOpen: (open) => set({ paletteOpen: open }),
        setCommandSurfaceOpen: (open) => set({ commandSurfaceOpen: open }),
        setQuickOpenOpen: (open) => set({ quickOpenOpen: open }),
        setQuickSwitchOpen: (open) => set({ quickSwitchOpen: open }),
        setNavRailOpen: (open) => set({ navRailOpen: open }),
        setCommandModal: (id) => set({ commandModal: id }),
        setContextMenu: (menu) => set({ contextMenu: menu }),
        setNewFilePrefix: (prefix, kind) =>
          set({ newFilePrefix: prefix, newFileKind: prefix == null ? "file" : kind ?? "file" }),
        clearFlash: () => set({ flashKey: null }),
      };
    },
    {
      name: "sc-workbench-ui",
      version: 1,
      // SSR-safe: on the server `localStorage` doesn't exist — createJSONStorage
      // catches the getter throwing and persist quietly skips hydration.
      storage: createJSONStorage(() => localStorage),
      // Persist ONLY the per-session chrome + last-opened session id;
      // palette/menus/flash are ephemeral.
      partialize: (s) => ({ perSession: s.perSession, lastSessionId: s.lastSessionId }),
    }
  )
);

// Bound per-session view: the session's UI state (or defaults) plus actions
// pre-bound to that session id. Safe with a null session (no-op actions).
export function useSessionUi(sessionId: string | null | undefined) {
  const session = useWorkbenchUiStore((s) =>
    sessionId ? s.perSession[sessionId] : undefined
  );
  return useMemo(() => {
    const a = useWorkbenchUiStore.getState();
    const sid = sessionId ?? null;
    const ui = session ?? emptySessionUi();
    return {
      ...ui,
      // Migration default: sessions persisted before S4 lack artifactsOpen.
      artifactsOpen: ui.artifactsOpen ?? true,
      artifactsWide: ui.artifactsWide ?? false,
      openTab: (key: string) => (sid ? a.openTab(sid, key) : undefined),
      closeTab: (key: string) => (sid ? a.closeTab(sid, key) : undefined),
      setActiveTab: (key: string | null) => (sid ? a.setActiveTab(sid, key) : undefined),
      markUnread: (runId: string) => (sid ? a.markUnread(sid, runId) : undefined),
      clearUnread: (runId: string) => (sid ? a.clearUnread(sid, runId) : undefined),
      toggleDir: (path: string) => (sid ? a.toggleDir(sid, path) : undefined),
      setDockTab: (tab: "activity" | "runs") => (sid ? a.setDockTab(sid, tab) : undefined),
      setDockCollapsed: (collapsed: boolean) =>
        sid ? a.setDockCollapsed(sid, collapsed) : undefined,
      setChatOpen: (open: boolean) => (sid ? a.setChatOpen(sid, open) : undefined),
      setArtifactsOpen: (open: boolean) => (sid ? a.setArtifactsOpen(sid, open) : undefined),
      setArtifactsWide: (wide: boolean) => (sid ? a.setArtifactsWide(sid, wide) : undefined),
    };
  }, [session, sessionId]);
}
