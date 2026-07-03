"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  Check,
  Clock,
  Columns2,
  FileCode2,
  Folder,
  MessageSquare,
  Plus,
  X,
} from "lucide-react";
import { threadsApi, workbenchApi } from "@/lib/api";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import type { ViewMode } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { relativeTime } from "@/components/workbench/runStatus";
import { plural } from "./util";
import type { ChatThread, Session } from "@/types";

export interface ThreadDrawerProps {
  session: Session;
  /** Group tag shown in the meta row (null = ungrouped). */
  groupName?: string | null;
  groupColor?: string | null;
  onClose: () => void;
  /** Navigate into the workspace. `view` present = explicit shell choice
   * (persisted by the caller); absent = stored-shell default. */
  onOpen: (opts?: { chat?: string | null; view?: ViewMode }) => void;
  /** Create a thread then navigate to it (?chat=). */
  onNewChat: () => void;
}

type FilesState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; files: string[] };

type ThreadsState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; threads: ChatThread[] };

/**
 * Right-hand drawer on card select — the launcher's ONE per-session hydration:
 * a lazy manifest fetch (file count + chips) and the thread list. Rows carry
 * no previews yet (plan: ship without; preview endpoint is a fast-follow).
 */
export function ThreadDrawer({
  session,
  groupName,
  groupColor,
  onClose,
  onOpen,
  onNewChat,
}: ThreadDrawerProps) {
  const [filesState, setFilesState] = useState<FilesState>({ status: "loading" });
  const [threadsState, setThreadsState] = useState<ThreadsState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setFilesState({ status: "loading" });
    setThreadsState({ status: "loading" });
    workbenchApi
      .getManifest(session.id)
      .then((manifest) => {
        if (cancelled) return;
        setFilesState({ status: "ready", files: (manifest.files ?? []).map((f) => f.name) });
      })
      .catch(() => {
        if (!cancelled) setFilesState({ status: "error" });
      });
    threadsApi
      .list(session.id)
      .then((threads) => {
        if (!cancelled) setThreadsState({ status: "ready", threads });
      })
      .catch(() => {
        if (!cancelled) setThreadsState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [session.id]);

  const files = filesState.status === "ready" ? filesState.files : null;
  const chatCount =
    threadsState.status === "ready" ? threadsState.threads.length : session.thread_count ?? 0;
  const updated = relativeTime(session.updated_at ?? session.created_at);
  const name = session.name ?? session.id;

  return (
    <div
      data-testid="thread-drawer"
      className="w-[336px] h-full flex flex-col border-l border-border bg-surface-1 animate-in slide-in-from-right-4 duration-200"
    >
      {/* Header */}
      <div className="px-4 pt-4 pb-3.5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg grid place-items-center shrink-0 border bg-primary/15 text-primary border-primary/25">
            <Folder className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="font-mono text-sm font-medium truncate">{name}</div>
            <div className="text-[10px] text-muted-foreground font-mono truncate">
              workspace/{session.id}/
            </div>
          </div>
          <button
            type="button"
            aria-label="Close drawer"
            onClick={onClose}
            className="h-6 w-6 grid place-items-center rounded-md hover:bg-surface-2 text-muted-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Meta row — file count comes from the lazy manifest fetch. */}
        <div className="mt-3 flex items-center gap-4 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <FileCode2 className="h-3.5 w-3.5" />
            {filesState.status === "loading" ? (
              <Skeleton className="h-3 w-10" />
            ) : filesState.status === "error" ? (
              "—"
            ) : (
              plural(files!.length, "file")
            )}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <MessageSquare className="h-3.5 w-3.5" />
            {plural(chatCount, "chat")}
          </span>
          {updated && (
            <span className="inline-flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" />
              {updated}
            </span>
          )}
          {groupName && (
            <span className="ml-auto inline-flex items-center gap-1.5 min-w-0">
              <span
                className="h-1.5 w-1.5 rounded-full shrink-0"
                style={groupColor ? { background: groupColor } : undefined}
              />
              <span className="truncate">{groupName}</span>
            </span>
          )}
        </div>

        {/* File chips — drawer-only per revision 1. */}
        {files && files.length > 0 && (
          <div className="mt-3 flex items-center gap-1 flex-wrap">
            {files.slice(0, 3).map((f) => (
              <span
                key={f}
                className="inline-flex items-center gap-1 h-5 px-1.5 rounded bg-surface-2 text-[10px] font-mono text-foreground/70"
              >
                <FileCode2 className="h-2.5 w-2.5 text-muted-foreground/70" />
                {f}
              </span>
            ))}
            {files.length > 3 && (
              <span className="text-[10px] font-mono text-muted-foreground/60">
                +{files.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Chats */}
      <div className="px-3 pt-3 pb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Chats
        </span>
        <button
          type="button"
          onClick={onNewChat}
          className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
        >
          <Plus className="h-3 w-3" /> New chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {threadsState.status === "loading" ? (
          <div className="space-y-1 px-1 pt-1">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : threadsState.status === "error" ? (
          <p className="px-2.5 py-2 text-[11px] text-muted-foreground">Couldn&apos;t load chats.</p>
        ) : threadsState.threads.length === 0 ? (
          <p className="px-2.5 py-2 text-[11px] text-muted-foreground">No chats yet.</p>
        ) : (
          threadsState.threads.map((t) => (
            <ThreadRow key={t.id} thread={t} onClick={() => onOpen({ chat: t.id })} />
          ))
        )}
      </div>

      {/* Footer — choose the shell at open time. */}
      <div className="p-3 border-t border-border">
        <OpenSplit sessionId={session.id} onOpen={onOpen} />
      </div>
    </div>
  );
}

function ThreadRow({ thread, onClick }: { thread: ChatThread; onClick: () => void }) {
  const when = relativeTime(thread.last_active ?? thread.created_at);
  return (
    <button
      type="button"
      onClick={onClick}
      className="group w-full text-left rounded-md px-2.5 py-2 transition-colors flex gap-2.5 hover:bg-surface-2/60"
    >
      <MessageSquare className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground/60" />
      <div className="min-w-0 flex-1 flex items-center gap-2">
        <span className="text-[12.5px] truncate text-foreground/85">
          {thread.title || "Untitled chat"}
        </span>
        {when && <span className="ml-auto text-[10px] text-muted-foreground/60 shrink-0">{when}</span>}
      </div>
    </button>
  );
}

/** Split open button: primary opens the stored shell (default IDE until S4);
 * the chevron picks the other and persists the choice. */
function OpenSplit({
  sessionId,
  onOpen,
}: {
  sessionId: string;
  onOpen: (opts?: { view?: ViewMode }) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  // S4: flip default to stored-shell ?? "agent" once the agent shell ships.
  const shell = useWorkbenchUiStore((s) => s.perSession[sessionId]?.shell) ?? "ide";

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const pick = (view: ViewMode) => {
    setOpen(false);
    onOpen({ view });
  };

  return (
    <div className="relative flex items-stretch" ref={ref}>
      <Button className="flex-1 h-10 rounded-r-none" onClick={() => onOpen()}>
        Open in {shell === "ide" ? "IDE" : "Chat"}
      </Button>
      <button
        type="button"
        aria-label="Choose shell"
        onClick={() => setOpen((o) => !o)}
        className="h-10 w-9 grid place-items-center rounded-md rounded-l-none bg-primary text-primary-foreground hover:bg-primary/90 border-l border-primary-foreground/25"
      >
        <ChevronDown className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute bottom-11 right-0 w-[184px] rounded-md border border-border bg-surface-1 shadow-lg p-1 z-10">
          <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
            Open in
          </div>
          <button
            type="button"
            onClick={() => pick("agent")}
            className="w-full flex items-center gap-2.5 px-2.5 h-8 rounded hover:bg-surface-2 text-[12.5px]"
          >
            <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" /> Chat
            {shell === "agent" && <Check className="h-3.5 w-3.5 ml-auto text-primary" />}
          </button>
          <button
            type="button"
            onClick={() => pick("ide")}
            className={cn("w-full flex items-center gap-2.5 px-2.5 h-8 rounded hover:bg-surface-2 text-[12.5px]")}
          >
            <Columns2 className="h-3.5 w-3.5 text-muted-foreground" /> IDE
            {shell === "ide" && <Check className="h-3.5 w-3.5 ml-auto text-primary" />}
          </button>
        </div>
      )}
    </div>
  );
}
