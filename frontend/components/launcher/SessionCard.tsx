"use client";

import { Folder, MessageSquare, MoreHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/components/workbench/runStatus";
import { plural } from "./util";
import type { Session } from "@/types";

export interface SessionCardProps {
  session: Session;
  selected: boolean;
  /** Group tag (Recent view only) — null hides the tag. */
  groupName?: string | null;
  groupColor?: string | null;
  onSelect: () => void;
  /** Double-click / default open. */
  onOpen: () => void;
  onMenu: (e: React.MouseEvent) => void;
  // HTML5 drag-to-group.
  dragging: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
}

/**
 * Launcher card — REVISION 1 layout: recency leads. Glyph · mono name ·
 * thread count · "last worked on" · group tag (Recent view). No run-verdict
 * headline, no file chips — those live in the drawer (one lazy fetch for the
 * selected session only).
 */
export function SessionCard({
  session,
  selected,
  groupName,
  groupColor,
  onSelect,
  onOpen,
  onMenu,
  dragging,
  onDragStart,
  onDragEnd,
}: SessionCardProps) {
  const name = session.name ?? session.id;
  const threadCount = session.thread_count ?? 0;
  const updated = relativeTime(session.updated_at ?? session.created_at);

  return (
    <div
      data-testid={`session-card-${session.id}`}
      draggable
      onDragStart={(e) => {
        onDragStart();
        e.dataTransfer.effectAllowed = "move";
      }}
      onDragEnd={onDragEnd}
      onClick={onSelect}
      onDoubleClick={onOpen}
      onContextMenu={onMenu}
      className={cn(
        "group relative rounded-lg border p-3.5 cursor-pointer transition-all select-none",
        selected
          ? "border-primary/50 bg-surface-1 shadow-sm"
          : "border-border bg-surface-1/50 hover:bg-surface-1 hover:border-border/80",
        dragging && "opacity-40"
      )}
    >
      <div className="flex items-center gap-2.5">
        <div
          className={cn(
            "w-7 h-7 rounded-md grid place-items-center shrink-0 border",
            selected
              ? "bg-primary/15 text-primary border-primary/25"
              : "bg-surface-2 text-muted-foreground border-border"
          )}
        >
          <Folder className="h-4 w-4" />
        </div>
        <span className="font-mono text-[13px] font-medium text-foreground truncate">{name}</span>
        <button
          type="button"
          aria-label={`More actions for ${name}`}
          onClick={(e) => {
            e.stopPropagation();
            onMenu(e);
          }}
          className="ml-auto -mr-1 h-6 w-6 grid place-items-center rounded-md text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-surface-2 shrink-0"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1" title={plural(threadCount, "chat")}>
          <MessageSquare className="h-3 w-3" />
          {threadCount}
        </span>
        {updated && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span>{updated}</span>
          </>
        )}
        {groupName && (
          <span className="ml-auto inline-flex items-center gap-1.5 text-muted-foreground/80 min-w-0">
            <span
              className="h-1.5 w-1.5 rounded-full shrink-0"
              style={groupColor ? { background: groupColor } : undefined}
            />
            <span className="truncate">{groupName}</span>
          </span>
        )}
      </div>
    </div>
  );
}
