"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { useWorkbenchSync } from "@/lib/useWorkbenchSync";
import { useSessionUi, useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { useWorkbenchShortcuts } from "@/hooks/useWorkbenchShortcuts";
import { Button } from "@/components/ui/button";
import { ChatArea } from "@/components/chat/ChatArea";
import { SettingsModal } from "@/components/settings/SettingsModal";
import { AgentShell } from "./AgentShell";
import { TopBar } from "./TopBar";
import { FileExplorer } from "./FileExplorer";
import { FileContextMenu } from "./FileContextMenu";
import { ArtifactCenter } from "./ArtifactCenter";
import { BottomDock } from "./BottomDock";
import { CommandPalette } from "./CommandPalette";
import { CommandModal } from "./CommandModal";
import { CommandSurface } from "./CommandSurface";
import { QuickOpen } from "./QuickOpen";
import { QuickSwitch } from "./QuickSwitch";
import { Toaster } from "./Toaster";

export interface WorkbenchProps {
  /** Session id from the URL (`/w/[...sid]`) — the source of truth (S1). */
  sessionId: string;
  /** Thread id from the `?chat=` param, if any. */
  threadId?: string | null;
  /** `?view=` posture (S4): "agent" mounts the prompt+view AgentShell,
   * "ide" (default) the full IDE layout. Same stores either way. */
  view?: "agent" | "ide";
}

/**
 * SiliconCrew Workbench v2 — a pure layout shell.
 *
 * Top bar, then three columns: the file explorer (left), the artifact center
 * over the Activity/Runs dock (center), and the collapsible assistant rail
 * (right). Every surface is prop-less and reads the stores itself; ephemeral
 * overlays (⌘K palette, param modal, quick-open, context menu) mount once at
 * the bottom and render from workbenchUiStore state.
 *
 * Selection is URL-driven (S1): the store follows the sessionId/threadId
 * props, never the other way — refresh, share, and back/forward just work.
 */
export function Workbench({ sessionId, threadId = null, view = "ide" }: WorkbenchProps) {
  const { currentSession, selectSessionById, selectThread, loadWorkbench, workspaceError } =
    useStore();
  const { status: authStatus } = useAuth();
  // The assistant rail is collapsible (per-session, persisted) so the artifact
  // center gets full width when the user is driving the pipeline themselves.
  const { chatOpen, setChatOpen } = useSessionUi(currentSession?.id);
  // Honest 404 for a dead deep link — never an empty-looking workbench.
  const [notFound, setNotFound] = useState(false);
  // One workbench refresh per mount when the session was already selected
  // (client-side remount); thread-only URL changes must not re-hydrate.
  const booted = useRef(false);

  // Keep the workbench fresh w.r.t. changes made by other clients (e.g. the
  // user's AI app via MCP): revalidate on focus + poll while a run is active.
  useWorkbenchSync();
  // Agent posture claims only ⌘P/⌘O (viewing); the IDE gets the full set —
  // ⌘K/⌘L/⌘R/⌘Y/⌘E/⌘J must NOT fire in the agent shell (revision 3).
  useWorkbenchShortcuts(view === "agent" ? "agent" : "ide");

  // Store follows the URL: session + thread from props, re-run on back/forward
  // (prop changes). Compares before dispatching so URL-sync writes from the
  // ThreadSwitcher (router.replace) never loop. Auth-wait stays: never fetch
  // before the token is restored.
  useEffect(() => {
    if (authStatus === "loading" || !sessionId) return;
    let cancelled = false;

    void (async () => {
      if (useStore.getState().currentSession?.id === sessionId) {
        // Same session (remount or thread-only change) → refresh once per mount.
        if (!booted.current) await loadWorkbench();
        if (!cancelled) setNotFound(false);
      } else {
        const ok = await selectSessionById(sessionId);
        if (cancelled) return;
        setNotFound(!ok);
        if (!ok) return;
      }
      booted.current = true;
      useWorkbenchUiStore.getState().setLastSessionId(sessionId);
      // Thread follows the ?chat= param (minimal wiring; compare first).
      if (threadId && threadId !== useStore.getState().activeThreadId) {
        await selectThread(threadId);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authStatus, sessionId, threadId]);

  if (notFound) {
    return (
      <main
        data-testid="workbench-not-found"
        className="flex h-screen w-screen flex-col items-center justify-center gap-3 bg-surface-0"
      >
        <p className="text-sm text-muted-foreground">
          Session <span className="font-mono text-foreground">{sessionId}</span> was not found.
        </p>
        <Link href="/" className="text-sm text-primary hover:underline">
          Back to home
        </Link>
      </main>
    );
  }

  // Workspace-load failure — surfaced (in BOTH shells) so a transient or
  // unavailable workspace never silently reads as an empty new session.
  const workspaceErrorBanner = workspaceError ? (
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
  ) : null;

  if (view === "agent") {
    // Agent-first shell (S4) — prompt + view ONLY (revision 3): QuickOpen
    // (⌘P, viewing) and QuickSwitch (⌘O) stay; CommandPalette, CommandModal,
    // CommandSurface and the file context menu do NOT mount here.
    return (
      <main
        data-testid="workbench-agent"
        className="h-screen w-screen overflow-hidden flex flex-col bg-surface-0"
      >
        {workspaceErrorBanner}
        <AgentShell />

        {/* Shared overlays only — no command invocation surfaces. */}
        <QuickOpen />
        <QuickSwitch />
        <Toaster />
        <SettingsModal />
      </main>
    );
  }

  return (
    <main
      data-testid="workbench-v2"
      className="h-screen w-screen overflow-hidden flex flex-col bg-surface-0"
    >
      <TopBar />

      {workspaceErrorBanner}

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
      <CommandSurface />
      <QuickOpen />
      <QuickSwitch />
      <FileContextMenu />
      <Toaster />
      <SettingsModal />
    </main>
  );
}
