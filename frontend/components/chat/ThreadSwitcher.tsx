"use client";

import { useStore } from "@/lib/store";
import { ChevronDown, Check, Trash2, MessageSquarePlus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn, formatRelativeTime } from "@/lib/utils";

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
    newThread,
    selectThread,
    deleteThread,
    renameThread,
  } = useStore();
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
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

  if (!currentSession) return null;

  const active = threads.find((t) => t.id === activeThreadId);
  const activeTitle = active?.title || "Chat 1";

  const onNew = async () => {
    setOpen(false);
    await newThread();
  };

  const onPick = async (id: string) => {
    setOpen(false);
    await selectThread(id);
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
    <div className="relative" ref={ref}>
      <button
        type="button"
        className="flex items-center gap-1.5 text-xs rounded-md px-2 py-1 text-muted-foreground hover:bg-surface-2 hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
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
          className="absolute z-50 mt-1 w-72 max-h-96 overflow-y-auto rounded-md border border-border bg-popover shadow-lg p-1"
        >
          <button
            type="button"
            onClick={onNew}
            className="w-full flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-surface-2 text-primary outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            <MessageSquarePlus className="h-3.5 w-3.5" /> New chat
          </button>
          <div className="h-px bg-border my-1" />

          {threads.length === 0 && (
            <div className="px-2 py-2 text-xs text-muted-foreground">No chats yet</div>
          )}

          {threads.map((t) => {
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
                    <div className="text-xs truncate text-foreground">{t.title || "Untitled chat"}</div>
                    {t.last_active && (
                      <div className="text-[10px] text-muted-foreground">
                        {formatRelativeTime(t.last_active)}
                      </div>
                    )}
                  </button>
                )}

                {!isEditing && threads.length > 1 && (
                  <button
                    type="button"
                    onClick={() => void deleteThread(t.id)}
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

      {/* Quick "New chat" affordance next to the switcher. */}
      <span className="sr-only">{threads.length} chats in this workspace</span>
    </div>
  );
}
