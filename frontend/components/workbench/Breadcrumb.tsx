"use client";

import { useRouter } from "next/navigation";
import { ChevronRight, FolderOpen, GitFork, Home } from "lucide-react";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";

/**
 * Breadcrumb anchor — Home › <block>. The nav says the mental model out loud:
 * a session IS a workspace IS one design block. Home routes to the Launcher,
 * and the workspace crumb opens the ⌘O quick-switch (no status dot — with
 * many runs a single verdict is ambiguous; revision 1). There is no chat
 * crumb: thread switching lives in the assistant rail (ChatArea's
 * ThreadSwitcher).
 */
export function Breadcrumb() {
  const router = useRouter();
  const { currentSession } = useStore();
  const setQuickSwitchOpen = useWorkbenchUiStore((s) => s.setQuickSwitchOpen);

  const sessionName = currentSession ? currentSession.name ?? currentSession.id : null;
  const forkedFrom = currentSession?.source_template ?? null;

  return (
    <div data-testid="breadcrumb" className="flex min-w-0 items-center gap-1">
      {/* Home → Launcher */}
      <button
        type="button"
        title="All sessions"
        aria-label="All sessions"
        data-testid="breadcrumb-home"
        onClick={() => router.push("/")}
        className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-surface-2 hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        <Home className="h-4 w-4" aria-hidden />
      </button>

      {currentSession && (
        <>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/40" aria-hidden />

          {/* Workspace crumb → ⌘O quick-switch. Calm on purpose: no status dot. */}
          <button
            type="button"
            title="Switch session (⌘O)"
            aria-label="Switch session"
            data-testid="breadcrumb-session"
            onClick={() => setQuickSwitchOpen(true)}
            className="flex h-7 min-w-0 items-center gap-1.5 rounded-md px-2 hover:bg-surface-2 outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <FolderOpen className="h-4 w-4 shrink-0 text-primary" aria-hidden />
            <span className="truncate font-mono text-[13px] font-medium">{sessionName}</span>
          </button>

          {/* Provenance chip — this workspace was forked from an example bundle. */}
          {forkedFrom && (
            <span
              data-testid="forked-from-chip"
              title={`Forked from the ${forkedFrom.name} example`}
              className="hidden sm:inline-flex h-6 shrink-0 items-center gap-1 rounded-md border border-border bg-surface-2/60 px-1.5 text-[11px] text-muted-foreground"
            >
              <GitFork className="h-3 w-3" aria-hidden />
              <span className="truncate max-w-[140px]">forked from {forkedFrom.name}</span>
            </span>
          )}
        </>
      )}
    </div>
  );
}
