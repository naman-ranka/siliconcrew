"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Home,
  MessageSquare,
  Plus,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { replaceThreadUrl } from "@/lib/nav";
import { cn, formatRelativeTime } from "@/lib/utils";

/**
 * Breadcrumb anchor — Home › <block> › <chat> (S3). The nav says the mental
 * model out loud: a session IS a workspace IS one design block; chats are
 * conversations about it. Home routes to the Launcher, the workspace crumb
 * opens the ⌘O quick-switch (no status dot — with many runs a single verdict
 * is ambiguous; revision 1), and the chat crumb drops down the thread list
 * (same store selectors/actions as the ChatArea's ThreadSwitcher, so the two
 * stay consistent).
 */
export function Breadcrumb() {
  const router = useRouter();
  const { currentSession, threads, activeThreadId, newThread, selectThread } = useStore();
  const setQuickSwitchOpen = useWorkbenchUiStore((s) => s.setQuickSwitchOpen);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Standard popover affordances: Escape + click-outside to close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const active = threads.find((t) => t.id === activeThreadId);
  const activeTitle = active?.title || "Chat 1";
  const sessionName = currentSession ? currentSession.name ?? currentSession.id : null;

  // Mirror thread changes into ?chat= exactly like the ThreadSwitcher does
  // (shared replaceThreadUrl helper — replace, not push; keeps ?view=).
  const onPick = async (id: string) => {
    setOpen(false);
    await selectThread(id);
    if (currentSession) replaceThreadUrl(router, currentSession.id, id);
  };

  const onNew = async () => {
    setOpen(false);
    await newThread();
    if (currentSession)
      replaceThreadUrl(router, currentSession.id, useStore.getState().activeThreadId);
  };

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

          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/40" aria-hidden />

          {/* Chat crumb → thread dropdown */}
          <div className="relative min-w-0" ref={ref}>
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={open}
              aria-label="Switch chat"
              data-testid="breadcrumb-chat"
              onClick={() => setOpen((v) => !v)}
              className="flex h-7 min-w-0 items-center gap-1.5 rounded-md px-2 hover:bg-surface-2 outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              <MessageSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
              <span className="max-w-[180px] truncate text-[13px] text-foreground/85">
                {activeTitle}
              </span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            </button>

            {open && (
              <div
                role="menu"
                aria-label={`Chats in ${sessionName}`}
                className="absolute left-0 top-9 z-50 w-[280px] rounded-lg border border-border bg-popover p-1.5 shadow-e2 animate-in fade-in-0 zoom-in-95 slide-in-from-top-1 motion-reduce:animate-none"
              >
                <div className="flex items-center justify-between px-2 pb-1.5 pt-1">
                  <span className="truncate text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                    Chats in {sessionName}
                  </span>
                  <span className="shrink-0 text-[10px] text-muted-foreground/50">
                    {threads.length}
                  </span>
                </div>
                <div className="max-h-[280px] overflow-y-auto thin-scrollbar">
                  {threads.length === 0 && (
                    <div className="px-2 py-2 text-xs text-muted-foreground">No chats yet</div>
                  )}
                  {threads.map((t) => {
                    const isActive = t.id === activeThreadId;
                    return (
                      <button
                        key={t.id}
                        type="button"
                        role="menuitemradio"
                        aria-checked={isActive}
                        onClick={() => void onPick(t.id)}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-2 outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                          isActive && "bg-surface-2"
                        )}
                      >
                        <Check
                          className={cn(
                            "h-3.5 w-3.5 shrink-0",
                            isActive ? "text-primary" : "text-transparent"
                          )}
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                          {t.title || "Untitled chat"}
                        </span>
                        {t.last_active && (
                          <span className="shrink-0 text-[10px] text-muted-foreground">
                            {formatRelativeTime(t.last_active)}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
                <div className="mt-1 border-t border-border pt-1.5">
                  <button
                    type="button"
                    onClick={() => void onNew()}
                    className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] text-primary hover:bg-surface-2 outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  >
                    <Plus className="h-3.5 w-3.5" aria-hidden /> New chat — same workspace
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
