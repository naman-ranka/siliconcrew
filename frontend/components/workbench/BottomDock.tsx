"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, GitCompare, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { selectActivity, useStore } from "@/lib/store";
import { useSessionUi } from "@/lib/workbenchUiStore";
import { ActivityFeed } from "./ActivityFeed";
import { RunsPane } from "./RunsPane";
import { CompareDialog } from "./CompareDialog";

export interface BottomDockProps {
  className?: string;
}

/**
 * The v2 bottom dock of the center column: a unified Activity feed + Runs
 * table behind two tabs, with Compare, refresh and collapse. Collapsed it is
 * a single h-8 bar; open it is h-56 (h-8 tab bar + scroll body). Tab and
 * collapsed state persist per session (workbenchUiStore).
 */
export function BottomDock({ className }: BottomDockProps) {
  const currentSession = useStore((s) => s.currentSession);
  const runs = useStore((s) => s.runs);
  const loadRuns = useStore((s) => s.loadRuns);
  const loadActivity = useStore((s) => s.loadActivity);
  const events = useStore(selectActivity);
  const sid = currentSession?.id ?? null;
  const { dockTab, dockCollapsed, setDockTab, setDockCollapsed } = useSessionUi(sid);

  const [compareOpen, setCompareOpen] = useState(false);

  const anyRunning =
    runs.some((r) => r.status === "running") || events.some((e) => e.status === "running");
  const comparableCount = runs.filter((r) => r.kind === "synth" && r.ppa).length;

  const tabButton = (tab: "activity" | "runs", label: string, count: number) => {
    const active = dockTab === tab;
    return (
      <button
        type="button"
        onClick={() => {
          setDockTab(tab);
          if (dockCollapsed) setDockCollapsed(false);
        }}
        aria-pressed={active}
        className={cn(
          "relative flex h-8 items-center gap-1 px-2 text-xs outline-none focus-visible:ring-1 focus-visible:ring-primary/60",
          active ? "text-foreground" : "text-muted-foreground hover:text-foreground"
        )}
      >
        {label}
        <span className="text-[10px] text-muted-foreground">{count}</span>
        {active ? (
          <span
            aria-hidden
            className="absolute inset-x-1 bottom-0 h-0.5 rounded-full bg-primary"
          />
        ) : null}
      </button>
    );
  };

  return (
    <div
      className={cn(
        "flex flex-col border-t border-border bg-surface-1",
        dockCollapsed ? "h-8" : "h-56",
        className
      )}
      data-testid="bottom-dock"
    >
      {/* Tab bar (the whole dock when collapsed) */}
      <div
        className={cn(
          "flex h-8 shrink-0 items-center px-1",
          !dockCollapsed && "border-b border-border"
        )}
      >
        {tabButton("activity", "Activity", events.length)}
        {tabButton("runs", "Runs", runs.length)}
        {anyRunning ? (
          <span className="ml-1.5 flex items-center gap-1 rounded-full bg-status-running/10 px-1.5 py-px text-[10px] text-status-running animate-pulse-subtle">
            <span className="h-1.5 w-1.5 rounded-full bg-status-running" />
            running
          </span>
        ) : null}

        <div className="ml-auto flex items-center gap-0.5 pr-1">
          {dockTab === "runs" ? (
            <button
              type="button"
              title={
                comparableCount >= 2
                  ? "Compare two synth runs"
                  : "Compare needs two synth runs with PPA"
              }
              aria-label="Compare runs"
              disabled={comparableCount < 2}
              onClick={() => setCompareOpen(true)}
              className="flex h-6 items-center gap-1 rounded px-1.5 text-[11px] text-muted-foreground outline-none hover:bg-surface-2 hover:text-foreground focus-visible:ring-1 focus-visible:ring-primary/60 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <GitCompare className="h-3 w-3" />
              Compare
            </button>
          ) : null}
          <button
            type="button"
            title="Refresh activity + runs"
            aria-label="Refresh activity and runs"
            onClick={() => {
              void loadActivity();
              void loadRuns();
            }}
            className="rounded p-1 text-muted-foreground outline-none hover:bg-surface-2 hover:text-foreground focus-visible:ring-1 focus-visible:ring-primary/60"
          >
            <RefreshCw className="h-3 w-3" />
          </button>
          <button
            type="button"
            title={dockCollapsed ? "Expand dock" : "Collapse dock"}
            aria-label={dockCollapsed ? "Expand dock" : "Collapse dock"}
            aria-expanded={!dockCollapsed}
            onClick={() => setDockCollapsed(!dockCollapsed)}
            className="rounded p-1 text-muted-foreground outline-none hover:bg-surface-2 hover:text-foreground focus-visible:ring-1 focus-visible:ring-primary/60"
          >
            {dockCollapsed ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
        </div>
      </div>

      {/* Body */}
      {!dockCollapsed ? (
        <div className="min-h-0 flex-1 overflow-y-auto thin-scrollbar">
          {dockTab === "activity" ? <ActivityFeed /> : <RunsPane />}
        </div>
      ) : null}

      <CompareDialog open={compareOpen} onOpenChange={setCompareOpen} />
    </div>
  );
}
