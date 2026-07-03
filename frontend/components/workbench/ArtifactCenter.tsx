"use client";

import { useEffect } from "react";
import {
  Activity,
  BarChart3,
  CircuitBoard,
  Code2,
  FileText,
  Layers,
  X,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useSessionUi, useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { parseArtifactKey } from "@/lib/artifactKeys";
import { artifactLabel } from "@/lib/openArtifact";
import { cn } from "@/lib/utils";
import type { ArtifactKind } from "@/types";
import { CodeArtifact } from "./viewers/CodeArtifact";
import { SpecArtifact } from "./viewers/SpecArtifact";
import { WaveArtifact } from "./viewers/WaveArtifact";
import { ReportArtifact } from "./viewers/ReportArtifact";
import { LayoutArtifact } from "./viewers/LayoutArtifact";
import { SchematicArtifact } from "./viewers/SchematicArtifact";
import { ViewerEmpty } from "./viewers/panels";

const KIND_ICON: Record<ArtifactKind, React.ComponentType<{ className?: string }>> = {
  code: Code2,
  spec: FileText,
  wave: Activity,
  report: BarChart3,
  layout: Layers,
  schematic: CircuitBoard,
};

// Route one open tab to its wrapper viewer. Wrappers load their own data via
// the store caches on mount — that (plus keep-alive below) is what makes
// revisiting a tab free.
function ArtifactBody({ artifactKey, readOnly }: { artifactKey: string; readOnly: boolean }) {
  const parsed = parseArtifactKey(artifactKey);
  if (!parsed) {
    return <ViewerEmpty icon={<Layers />} title="Unknown artifact" detail={artifactKey} />;
  }
  switch (parsed.kind) {
    case "code":
      return <CodeArtifact path={parsed.ref ?? ""} forceReadOnly={readOnly} />;
    case "spec":
      return <SpecArtifact />;
    case "wave":
      return <WaveArtifact runId={parsed.ref ?? ""} />;
    case "report":
      return <ReportArtifact runId={parsed.ref ?? ""} />;
    case "layout":
      return <LayoutArtifact runId={parsed.ref ?? ""} />;
    case "schematic":
      return <SchematicArtifact name={parsed.ref ?? ""} />;
  }
}

/**
 * v2 center area — an open-tab editor model over artifact keys. Every open
 * tab's viewer stays MOUNTED (non-active ones are display:none), so switching
 * tabs is instant: no VCD re-parse, no Monaco re-boot, no report refetch.
 */
export function ArtifactCenter({
  readOnly = false,
  emptyHint = "Open a file from the tree, or an artifact from a run. Press ⌘P to quick-open anything.",
}: {
  /** Agent posture is prompt + view only — forces the code viewer read-only. */
  readOnly?: boolean;
  /** Empty-state guidance — the default speaks IDE (file tree); the agent
   * shell passes prompt-posture copy (tool cards + ⌘P). */
  emptyHint?: string;
}) {
  const sessionId = useStore((s) => s.currentSession?.id ?? null);
  const { openTabs, activeTab, closeTab, setActiveTab } = useSessionUi(sessionId);
  const flashKey = useWorkbenchUiStore((s) => s.flashKey);
  const clearFlash = useWorkbenchUiStore((s) => s.clearFlash);

  // The attention pulse is one-shot: let the animation play, then clear the
  // key so re-opening the same tab can flash again.
  useEffect(() => {
    if (!flashKey) return;
    const t = setTimeout(() => clearFlash(), 700);
    return () => clearTimeout(t);
  }, [flashKey, clearFlash]);

  if (openTabs.length === 0) {
    return (
      <div className="flex flex-col h-full items-center justify-center bg-surface-0" data-testid="artifact-center-empty">
        <div className="h-12 w-12 rounded-xl bg-surface-2 flex items-center justify-center mb-4">
          <Layers className="h-6 w-6 text-muted-foreground" />
        </div>
        <p className="text-sm font-medium text-foreground">Nothing open</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-[300px] text-center">
          {emptyHint}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-surface-0" data-testid="artifact-center">
      {/* Tab strip */}
      <div
        role="tablist"
        aria-label="Open artifacts"
        className="flex h-9 items-stretch border-b border-border bg-surface-1 shrink-0 overflow-x-auto thin-scrollbar"
      >
        {openTabs.map((key) => {
          const parsed = parseArtifactKey(key);
          const Icon = parsed ? KIND_ICON[parsed.kind] : Layers;
          const active = key === activeTab;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active}
              title={artifactLabel(key)}
              onClick={() => setActiveTab(key)}
              onAuxClick={(e) => {
                // Middle-click closes (button 1).
                if (e.button === 1) {
                  e.preventDefault();
                  closeTab(key);
                }
              }}
              onMouseDown={(e) => {
                // Stop middle-click autoscroll from hijacking the close.
                if (e.button === 1) e.preventDefault();
              }}
              className={cn(
                "group relative flex items-center gap-1.5 px-3 text-xs border-b-2 shrink-0 max-w-[240px]",
                "transition-colors [transition-duration:var(--dur-fast)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                active
                  ? "border-primary text-foreground bg-surface-0"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:bg-surface-2/60",
                flashKey === key && "animate-flash"
              )}
            >
              <Icon className={cn("h-3.5 w-3.5 shrink-0", active ? "text-primary" : "text-muted-foreground")} />
              <span className="truncate max-w-[24ch]">{artifactLabel(key)}</span>
              <span
                role="button"
                aria-label={`Close ${artifactLabel(key)}`}
                tabIndex={-1}
                onClick={(e) => {
                  e.stopPropagation();
                  closeTab(key);
                }}
                className={cn(
                  "shrink-0 rounded p-0.5 -mr-1 opacity-0 group-hover:opacity-100",
                  "hover:bg-surface-3 text-muted-foreground hover:text-foreground",
                  "transition-opacity [transition-duration:var(--dur-fast)]"
                )}
              >
                <X className="h-3 w-3" />
              </span>
            </button>
          );
        })}
      </div>

      {/* Keep-alive bodies: every open tab stays mounted; non-active hidden. */}
      <div className="flex-1 min-h-0 relative">
        {openTabs.map((key) => (
          <div
            key={key}
            role="tabpanel"
            className={cn("h-full min-h-0", key !== activeTab && "hidden")}
            data-testid={`artifact-panel-${key}`}
          >
            <ArtifactBody readOnly={readOnly} artifactKey={key} />
          </div>
        ))}
      </div>
    </div>
  );
}
