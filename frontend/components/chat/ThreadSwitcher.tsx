"use client";

import { useRouter } from "next/navigation";
import { useStore } from "@/lib/store";
import { replaceThreadUrl } from "@/lib/nav";
import { ChevronDown, Check, Trash2, MessageSquarePlus, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn, formatRelativeTime } from "@/lib/utils";
import { CodexAccountControl } from "./CodexAccountControl";

/**
 * Chat thread switcher — many conversations per workspace.
 *
 * A chat is conversation history only; all threads share the LIVE workspace
 * (files/runs/manifest). Switching a thread swaps the message list and
 * reconnects the WebSocket with that thread_id; the left rail + center never
 * change. New chat → starts an empty conversation in the same workspace.
 */
export function ThreadSwitcher() {
  const {
    currentSession,
    threads,
    activeThreadId,
    agentRuntime,
    codexEnabled,
    setAgentRuntime,
    loadCodexCapability,
    newThread,
    selectThread,
    deleteThread,
    renameThread,
  } = useStore();
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Keep the URL's ?chat= in step with the active thread (S1) so refresh keeps
  // the conversation. replaceThreadUrl (shared with Breadcrumb) no-ops off /w/
  // routes and reads location inside the handler (not useSearchParams) so the
  // statically-prerendered legacy page needs no Suspense boundary.
  const syncThreadUrl = (threadId: string | null) => {
    const session = useStore.getState().currentSession;
    if (!session) return;
    replaceThreadUrl(router, session.id, threadId);
  };

  // Standard popover affordances: Escape + click-outside to close.
  // preventDefault marks the Esc as consumed: the agent shell's artifact
  // panel also closes on Esc (skipping defaultPrevented events), and a
  // popover-Esc must not also close the panel. Safe to always call here —
  // this handler is only attached while the popover is open (effect gated
  // on `open`).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
      }
    };
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

  // Discover whether the Codex runtime is enabled on this server (gates the
  // agent toggle). Cheap, once per mount.
  useEffect(() => {
    void loadCodexCapability();
  }, [loadCodexCapability]);

  if (!currentSession) return null;

  const isCodex = agentRuntime === "codex";
  // One agent occupies the panel at a time: show only this agent's threads.
  const visibleThreads = threads.filter((t) => (t.runtime === "codex") === isCodex);
  const active = visibleThreads.find((t) => t.id === activeThreadId);
  const activeTitle = active?.title || (isCodex ? "New Codex chat" : "Chat 1");

  const onNew = async () => {
    setOpen(false);
    await newThread(isCodex ? "codex" : undefined);
    syncThreadUrl(useStore.getState().activeThreadId);
  };

  const onSwitchAgent = async (rt: "langchain" | "codex") => {
    setOpen(false);
    // Await the runtime switch (it selects/creates this agent's thread) BEFORE
    // syncing the URL, so ?chat= reflects the actually-selected thread — not the
    // previous one (URL is the source of truth).
    await setAgentRuntime(rt);
    syncThreadUrl(useStore.getState().activeThreadId);
  };

  const onPick = async (id: string) => {
    setOpen(false);
    await selectThread(id);
    syncThreadUrl(id);
  };

  const onDelete = async (id: string) => {
    await deleteThread(id);
    // Deleting the active chat lands on the next one — mirror it in the URL.
    syncThreadUrl(useStore.getState().activeThreadId);
  };

  const startRename = (id: string, current: string | null) => {
    setEditingId(id);
    setDraft(current || "");
  };

  const commitRename = async (id: string) => {
    const title = draft.trim();
    setEditingId(null);
    if (title) await renameThread(id, title);
  };

  return (
    <div className="flex items-center gap-2">
      {/* Agent switcher: one agent occupies the panel at a time (not tabs).
          Only shown when the Codex runtime is enabled on the server. */}
      {codexEnabled && (
        <div className="inline-flex items-center rounded-md border border-border p-0.5 text-[11px]" role="group" aria-label="Agent">
          <button
            type="button"
            aria-pressed={!isCodex}
            onClick={() => onSwitchAgent("langchain")}
            className={cn("px-2 py-0.5 rounded transition-colors",
              !isCodex ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
          >
            Workbench
          </button>
          <button
            type="button"
            aria-pressed={isCodex}
            onClick={() => onSwitchAgent("codex")}
            className={cn("px-2 py-0.5 rounded flex items-center gap-1 transition-colors",
              isCodex ? "bg-violet-500 text-white" : "text-muted-foreground hover:text-foreground")}
          >
            <Sparkles className="h-3 w-3" /> Codex
          </button>
        </div>
      )}

      {codexEnabled && isCodex && <CodexAccountControl />}

      <div className="relative" ref={ref}>
      <button
        type="button"
        className={cn("flex items-center gap-1.5 text-xs rounded-md px-2 py-1 text-muted-foreground hover:bg-surface-2 hover:text-foreground outline-none focus-visible:ring-2",
          isCodex ? "focus-visible:ring-violet-500/60" : "focus-visible:ring-primary/60")}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Switch chat"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-medium truncate max-w-[160px] text-foreground">{activeTitle}</span>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Chats in this workspace"
          className="absolute z-50 mt-1 w-72 max-h-96 overflow-y-auto rounded-md border border-border bg-popover shadow-e2 p-1 animate-in fade-in-0 zoom-in-95 slide-in-from-top-1 motion-reduce:animate-none"
        >
          <button
            type="button"
            onClick={onNew}
            className={cn("w-full flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-surface-2 outline-none focus-visible:ring-2",
              isCodex ? "text-violet-500 focus-visible:ring-violet-500/60" : "text-primary focus-visible:ring-primary/60")}
          >
            {isCodex ? <Sparkles className="h-3.5 w-3.5" /> : <MessageSquarePlus className="h-3.5 w-3.5" />}
            {isCodex ? "New Codex chat" : "New chat"}
          </button>
          <div className="h-px bg-border my-1" />

          {visibleThreads.length === 0 && (
            <div className="px-2 py-2 text-xs text-muted-foreground">
              {isCodex ? "No Codex chats yet" : "No chats yet"}
            </div>
          )}

          {visibleThreads.map((t) => {
            const isActive = t.id === activeThreadId;
            const isEditing = editingId === t.id;
            return (
              <div
                key={t.id}
                className={cn(
                  "group flex items-center gap-1 rounded px-1.5 py-1 hover:bg-surface-2",
                  isActive && "bg-surface-2"
                )}
              >
                <Check
                  className={cn("h-3.5 w-3.5 shrink-0", isActive ? "text-primary" : "text-transparent")}
                  aria-hidden
                />
                {isEditing ? (
                  <input
                    autoFocus
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onBlur={() => void commitRename(t.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void commitRename(t.id);
                      if (e.key === "Escape") setEditingId(null);
                      e.stopPropagation();
                    }}
                    className="flex-1 min-w-0 bg-background text-xs px-1 py-0.5 rounded border border-border outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                    aria-label="Rename chat"
                  />
                ) : (
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={isActive}
                    onClick={() => void onPick(t.id)}
                    onDoubleClick={() => startRename(t.id, t.title)}
                    className="flex-1 min-w-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-primary/60 rounded"
                    title="Click to open · double-click to rename"
                  >
                    <div className="text-xs truncate text-foreground flex items-center gap-1">
                      {t.runtime === "codex" && (
                        <span className="text-[9px] px-1 rounded bg-violet-500/15 text-violet-500 font-medium shrink-0">Codex</span>
                      )}
                      <span className="truncate">{t.title || "Untitled chat"}</span>
                    </div>
                    {t.last_active && (
                      <div className="text-[10px] text-muted-foreground">
                        {formatRelativeTime(t.last_active)}
                      </div>
                    )}
                  </button>
                )}

                {!isEditing && visibleThreads.length > 1 && (
                  <button
                    type="button"
                    onClick={() => void onDelete(t.id)}
                    aria-label={`Delete chat ${t.title ?? ""}`}
                    className="shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 focus-visible:opacity-100 text-muted-foreground hover:text-destructive outline-none focus-visible:ring-2 focus-visible:ring-destructive/50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Live count for screen readers (the visible "New chat" action lives
          inside the open menu). */}
      <span className="sr-only">{visibleThreads.length} chats in this workspace</span>
      </div>
    </div>
  );
}
