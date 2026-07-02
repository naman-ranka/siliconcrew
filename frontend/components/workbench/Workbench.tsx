"use client";

import { useEffect } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { useWorkbenchSync } from "@/lib/useWorkbenchSync";
import { useSessionUi } from "@/lib/workbenchUiStore";
import { useWorkbenchShortcuts } from "@/hooks/useWorkbenchShortcuts";
import { Button } from "@/components/ui/button";
import { ChatArea } from "@/components/chat/ChatArea";
import { SettingsModal } from "@/components/settings/SettingsModal";
import { TopBar } from "./TopBar";
import { FileExplorer } from "./FileExplorer";
import { FileContextMenu } from "./FileContextMenu";
import { ArtifactCenter } from "./ArtifactCenter";
import { BottomDock } from "./BottomDock";
import { CommandPalette } from "./CommandPalette";
import { CommandModal } from "./CommandModal";
import { QuickOpen } from "./QuickOpen";
import { Toaster } from "./Toaster";

/**
 * SiliconCrew Workbench v2 — a pure layout shell.
 *
 * Top bar, then three columns: the file explorer (left), the artifact center
 * over the Activity/Runs dock (center), and the collapsible assistant rail
 * (right). Every surface is prop-less and reads the stores itself; ephemeral
 * overlays (⌘K palette, param modal, quick-open, context menu) mount once at
 * the bottom and render from workbenchUiStore state.
 */
export function Workbench() {
  const { currentSession, loadSessions, selectSession, loadWorkbench, workspaceError } = useStore();
  const { status: authStatus } = useAuth();
  // The assistant rail is collapsible (per-session, persisted) so the artifact
  // center gets full width when the user is driving the pipeline themselves.
  const { chatOpen, setChatOpen } = useSessionUi(currentSession?.id);

  // Keep the workbench fresh w.r.t. changes made by other clients (e.g. the
  // user's AI app via MCP): revalidate on focus + poll while a run is active.
  useWorkbenchSync();
  useWorkbenchShortcuts();

  // Ensure a session is active and the workbench data is loaded. A single
  // deterministic effect (reading fresh state via getState) avoids the races a
  // multi-effect/closure approach has during first mount.
  useEffect(() => {
    if (authStatus === "loading") return;

    void (async () => {
      let list = useStore.getState().sessions;
      if (list.length === 0) {
        await loadSessions();
        list = useStore.getState().sessions;
      }
      const cur = useStore.getState().currentSession;
      if (cur) {
        // Already selected (remount) → load its workbench once.
        await loadWorkbench();
      } else if (list.length > 0) {
        // selectSession loads the workbench itself — F4: no second refresh.
        await selectSession(list[0]);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authStatus]);

  return (
    <main
      data-testid="workbench-v2"
      className="h-screen w-screen overflow-hidden flex flex-col bg-surface-0"
    >
      <TopBar />

      {/* Workspace-load failure — surfaced so a transient/unavailable workspace
          never silently reads as an empty new session. */}
      {workspaceError && (
        <div
          role="alert"
          className="flex items-center gap-2 px-3 py-1.5 text-xs border-b border-status-fail/30 bg-status-fail/10 text-status-fail"
        >
          <span className="flex-1 truncate">{workspaceError}</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs text-status-fail hover:bg-status-fail/15"
            onClick={() => void loadWorkbench()}
          >
            Retry
          </Button>
        </div>
      )}

      {/* Content row */}
      <div className="flex flex-1 min-h-0">
        <PanelGroup direction="horizontal" className="flex-1 min-w-0">
          {/* Left — file explorer */}
          <Panel defaultSize={19} minSize={14} maxSize={26}>
            <div className="flex h-full min-h-0 flex-col border-r border-border bg-surface-0">
              <FileExplorer />
            </div>
          </Panel>

          <PanelResizeHandle className="w-1 bg-border hover:bg-primary transition-colors" />

          {/* Center — artifact center over the Activity/Runs dock */}
          <Panel defaultSize={55} minSize={30}>
            <div className="flex h-full min-h-0 flex-col">
              <div className="flex-1 min-h-0">
                <ArtifactCenter />
              </div>
              <BottomDock />
            </div>
          </Panel>

          {/* Right — assistant rail (ChatArea brings its own header). */}
          {chatOpen && (
            <>
              <PanelResizeHandle className="w-1 bg-border hover:bg-primary transition-colors" />
              <Panel defaultSize={26} minSize={20} maxSize={36}>
                <div className="flex h-full min-h-0 flex-col border-l border-border">
                  {/* Slim rail strip: just the collapse control (ChatArea's own
                      header already shows session name + thread switcher). */}
                  <div className="flex h-7 shrink-0 items-center justify-end border-b border-border bg-surface-1 px-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      title="Collapse assistant"
                      aria-label="Collapse assistant"
                      onClick={() => setChatOpen(false)}
                    >
                      <PanelRightClose className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <div className="flex-1 min-h-0">
                    <ChatArea />
                  </div>
                </div>
              </Panel>
            </>
          )}
        </PanelGroup>

        {/* Collapsed rail — a slim vertical strip that reopens the assistant. */}
        {!chatOpen && (
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            title="Open assistant"
            aria-label="Open assistant"
            data-testid="assistant-rail-open"
            className="flex w-9 shrink-0 flex-col items-center gap-2 border-l border-border bg-surface-1 pt-3 text-muted-foreground outline-none transition-colors hover:bg-surface-2 hover:text-primary focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary/60"
          >
            <PanelRightOpen className="h-4 w-4" />
            <span className="text-[10px] uppercase tracking-wide [writing-mode:vertical-rl]">
              Assistant
            </span>
          </button>
        )}
      </div>

      {/* Global overlays — mounted once, driven by workbenchUiStore state. */}
      <CommandPalette />
      <CommandModal />
      <QuickOpen />
      <FileContextMenu />
      <Toaster />
      <SettingsModal />
    </main>
  );
}
