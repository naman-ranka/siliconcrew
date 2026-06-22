"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useStore } from "@/lib/store";
import { ArtifactsPanel } from "@/components/artifacts/ArtifactsPanel";
import { ChatArea } from "@/components/chat/ChatArea";
import { PipelineStepper } from "./PipelineStepper";
import { FileTree } from "./FileTree";
import { RunsTimeline } from "./RunsTimeline";
import { Console } from "./Console";
import { ViewingBanner } from "./ViewingBanner";
import { Onboarding } from "./Onboarding";
import { SessionPicker } from "./SessionPicker";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "@/components/ui/button";
import { CircuitBoard, MessagesSquare, MessageSquare, PanelRightClose, PanelRightOpen } from "lucide-react";

/**
 * SiliconCrew Workbench — hardware-design-first, artifact-first.
 *
 * Layout: a top bar, then the pipeline spine (Spec→…→Signoff that doubles as
 * the run actions), then three columns:
 *   left   — manifest file tree + the unified runs timeline
 *   center — "viewing X" banner + the reused artifact viewers + the console
 *   right  — the agent rail (same tools, same workspace, same runs)
 */
export function Workbench() {
  const { currentSession, loadSessions, selectSession, loadWorkbench, artifactsVisible, manifest, runs, activeArtifactTab } = useStore();
  // The agent rail is collapsible so the waveform/report get full width when the
  // user is driving the pipeline themselves (re-review feedback).
  const [chatOpen, setChatOpen] = useState(true);

  // First-run guidance: empty workspace, nothing run yet, and not actively in the
  // editor (so "Write a file" still reaches the Code tab).
  const showOnboarding =
    !!currentSession &&
    (manifest?.files.length ?? 0) === 0 &&
    runs.length === 0 &&
    activeArtifactTab !== "code";

  // Ensure a session is active and the workbench data is loaded. A single
  // deterministic effect (reading fresh state via getState) avoids the races a
  // multi-effect/closure approach has during first mount.
  useEffect(() => {
    void (async () => {
      useStore.setState({ artifactsVisible: true });
      let list = useStore.getState().sessions;
      if (list.length === 0) {
        await loadSessions();
        list = useStore.getState().sessions;
      }
      let cur = useStore.getState().currentSession;
      if (!cur && list.length > 0) {
        await selectSession(list[0]);
        cur = useStore.getState().currentSession;
      }
      if (cur) await loadWorkbench();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="h-screen w-screen overflow-hidden flex flex-col bg-background">
      {/* Top bar */}
      <header className="flex items-center justify-between h-12 px-3 border-b border-border bg-surface-0 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary/15 flex items-center justify-center">
              <CircuitBoard className="h-4 w-4 text-primary" />
            </div>
            <span className="font-semibold text-sm" data-testid="wb-brand">SiliconCrew</span>
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground border border-border rounded px-1.5 py-0.5">
              Workbench
            </span>
          </div>
          <div className="h-5 w-px bg-border" />
          <span className="text-[11px] text-muted-foreground hidden sm:inline">Session</span>
          <SessionPicker />
        </div>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <Link href="/">
            <Button variant="ghost" size="sm" className="gap-1.5 text-xs">
              <MessagesSquare className="h-3.5 w-3.5" /> Chat view
            </Button>
          </Link>
        </div>
      </header>

      {/* Pipeline spine = orientation + run actions */}
      <PipelineStepper />

      {/* Body */}
      <PanelGroup direction="horizontal" className="flex-1 min-h-0">
        {/* Left rail */}
        <Panel defaultSize={20} minSize={14} maxSize={32}>
          <div className="flex flex-col h-full bg-surface-0 border-r border-border min-h-0">
            <div className="flex-1 min-h-0 overflow-y-auto thin-scrollbar">
              <FileTree />
            </div>
            <RunsTimeline />
          </div>
        </Panel>

        <PanelResizeHandle className="w-1 bg-border hover:bg-primary transition-colors" />

        {/* Center — artifacts + console */}
        <Panel defaultSize={52} minSize={30}>
          <div className="flex flex-col h-full min-h-0">
            <ViewingBanner />
            <div className="flex-1 min-h-0">
              {showOnboarding ? (
                <Onboarding />
              ) : artifactsVisible ? (
                <ArtifactsPanel />
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                  Artifacts hidden
                </div>
              )}
            </div>
            <Console />
          </div>
        </Panel>

        {chatOpen && <PanelResizeHandle className="w-1 bg-border hover:bg-primary transition-colors" />}

        {/* Right — agent rail (shares tools, workspace, runs); collapsible. */}
        {chatOpen && (
          <Panel defaultSize={28} minSize={18} maxSize={42}>
            <div className="flex flex-col h-full border-l border-border min-h-0">
              <div className="flex items-center gap-2 h-9 px-3 border-b border-border bg-surface-1 shrink-0">
                <MessageSquare className="h-3.5 w-3.5 text-primary" />
                <span className="text-xs font-semibold">AI Assistant</span>
                <span className="text-[10px] text-muted-foreground ml-auto mr-1">same tools · same workspace</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  title="Collapse assistant"
                  onClick={() => setChatOpen(false)}
                >
                  <PanelRightClose className="h-4 w-4" />
                </Button>
              </div>
              <div className="flex-1 min-h-0">
                <ChatArea />
              </div>
            </div>
          </Panel>
        )}
      </PanelGroup>

      {/* Collapsed rail handle — reopen the assistant. */}
      {!chatOpen && (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          title="Open AI Assistant"
          className="fixed right-0 top-1/2 -translate-y-1/2 z-50 flex items-center gap-1 bg-surface-2 border border-border border-r-0 rounded-l-md px-2 py-3 text-xs text-muted-foreground hover:text-primary hover:bg-surface-3"
        >
          <PanelRightOpen className="h-4 w-4" />
          <span className="[writing-mode:vertical-rl] rotate-180">AI Assistant</span>
        </button>
      )}
    </main>
  );
}
