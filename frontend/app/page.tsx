"use client";

import { useEffect, useCallback } from "react";
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { ChatArea } from "@/components/chat/ChatArea";
import { ArtifactsPanel } from "@/components/artifacts/ArtifactsPanel";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { PanelRight } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Home() {
  const {
    sidebarCollapsed,
    artifactsVisible,
    toggleSidebar,
    toggleArtifacts,
    loadSessions,
  } = useStore();

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + B: Toggle sidebar
      if ((e.metaKey || e.ctrlKey) && e.key === "b") {
        e.preventDefault();
        toggleSidebar();
      }
      // Cmd/Ctrl + ]: Toggle artifacts
      if ((e.metaKey || e.ctrlKey) && e.key === "]") {
        e.preventDefault();
        toggleArtifacts();
      }
      // Cmd/Ctrl + N: New session (if dialog component supports it)
      if ((e.metaKey || e.ctrlKey) && e.key === "n") {
        // This could open the new session dialog
        // For now, we'll leave this as a placeholder
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar, toggleArtifacts]);

  return (
    <main className="h-screen w-screen overflow-hidden flex">
      {/* Sidebar */}
      <Sidebar />

      {/* Main content area with resizable panels */}
      <PanelGroup direction="horizontal" className="flex-1">
        {/* Chat Panel */}
        <Panel defaultSize={artifactsVisible ? 60 : 100} minSize={40}>
          <ChatArea />
        </Panel>

        {/* Artifacts Panel */}
        {artifactsVisible && (
          <>
            <PanelResizeHandle className="w-1 bg-border hover:bg-primary transition-colors" />
            <Panel defaultSize={40} minSize={25} maxSize={60}>
              <ArtifactsPanel />
            </Panel>
          </>
        )}
      </PanelGroup>

      {/* Floating button to show artifacts if hidden */}
      {!artifactsVisible && (
        <div className="fixed bottom-4 right-4 z-50">
          <Button
            variant="outline"
            size="icon"
            className="h-10 w-10 rounded-full shadow-lg bg-background"
            onClick={toggleArtifacts}
          >
            <PanelRight className="h-5 w-5" />
          </Button>
        </div>
      )}
    </main>
  );
}
