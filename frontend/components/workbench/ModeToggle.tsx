"use client";

import { useRouter } from "next/navigation";
import { Columns2, MessagesSquare } from "lucide-react";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { sessionUrl, type ViewMode } from "@/lib/nav";
import { cn } from "@/lib/utils";

/**
 * Agent ↔ IDE posture switch (S5-3). Posture is layout emphasis only — same
 * session, same tabs, same runs — so switching ROUTES (`?view=`, replace: not
 * a history entry) and persists the per-session shell preference. Mounted
 * compact in the IDE TopBar and as a floating pill in the agent shell.
 */
export function ModeToggle({ mode, className }: { mode: ViewMode; className?: string }) {
  const router = useRouter();
  const sessionId = useStore((s) => s.currentSession?.id ?? null);
  const activeThreadId = useStore((s) => s.activeThreadId);
  const setShell = useWorkbenchUiStore((s) => s.setShell);

  const switchTo = (view: ViewMode) => {
    if (view === mode || !sessionId) return;
    setShell(sessionId, view);
    router.replace(sessionUrl(sessionId, { chat: activeThreadId, view }));
  };

  const seg = (view: ViewMode, label: string, Icon: typeof Columns2) => (
    <button
      type="button"
      onClick={() => switchTo(view)}
      aria-pressed={mode === view}
      data-testid={`mode-toggle-${view}`}
      className={cn(
        "flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-medium transition-colors",
        "outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
        mode === view
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:text-foreground"
      )}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {label}
    </button>
  );

  if (!sessionId) return null;

  return (
    <div
      data-testid="mode-toggle"
      role="group"
      aria-label="Shell posture"
      className={cn(
        "flex items-center rounded-full border border-border bg-surface-1/95 p-0.5",
        className
      )}
    >
      {seg("agent", "Agent", MessagesSquare)}
      {seg("ide", "IDE", Columns2)}
    </div>
  );
}
