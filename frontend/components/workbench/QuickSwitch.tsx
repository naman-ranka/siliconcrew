"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Clock,
  Columns2,
  CornerDownRight,
  Folder,
  FolderOpen,
  Hash,
  MessageSquare,
  Plus,
  Search,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { threadsApi } from "@/lib/api";
import { openSession, type ViewMode } from "@/lib/nav";
import {
  filterSessions,
  flattenSections,
  groupSessions,
  moveHighlight,
} from "@/lib/quickSwitch";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { relativeTime } from "./runStatus";
import { groupSwatch, plural } from "@/components/launcher/util";
import type { ChatThread } from "@/types";

type ThreadsEntry =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; threads: ChatThread[] };

/**
 * ⌘O session quick-switch (S3) — block-hopping for hardware designers.
 *
 * LEFT: every session, grouped by group (projects), keyboard-first (↑↓/Enter/
 * Esc). RIGHT: detail for the highlighted session — shell choice (Chat/IDE,
 * stored preference highlighted), a lazy "jump to a chat" list (threadsApi on
 * highlight, ~200ms debounce so arrowing through the list doesn't fetch every
 * row), and new-chat. Creating a session routes to the Launcher — that's where
 * the create modal lives.
 */
export function QuickSwitch() {
  const router = useRouter();
  const open = useWorkbenchUiStore((s) => s.quickSwitchOpen);
  const setOpen = useWorkbenchUiStore((s) => s.setQuickSwitchOpen);
  const perSession = useWorkbenchUiStore((s) => s.perSession);
  const sessions = useStore((s) => s.sessions);
  const projects = useStore((s) => s.projects);
  const currentId = useStore((s) => s.currentSession?.id ?? null);

  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  // Lazy per-session thread lists — fetched once per open, on highlight.
  const [threadMap, setThreadMap] = useState<Record<string, ThreadsEntry>>({});
  const requestedRef = useRef<Set<string>>(new Set());

  const sections = useMemo(
    () => groupSessions(filterSessions(sessions, q), projects),
    [sessions, projects, q]
  );
  const flat = useMemo(() => flattenSections(sections), [sections]);
  const highlighted = flat.length > 0 ? flat[Math.min(hi, flat.length - 1)] : undefined;
  const highlightedId = highlighted?.id ?? null;

  // Fresh slate per open; sessions/groups load lazily if the workbench was
  // deep-linked and the lists were never fetched.
  useEffect(() => {
    if (!open) return;
    setQ("");
    setHi(0);
    setThreadMap({});
    requestedRef.current = new Set();
    const store = useStore.getState();
    if (store.sessions.length === 0) void store.loadSessions();
    if (store.projects.length === 0) void store.loadProjects();
  }, [open]);

  // Typing re-anchors the highlight to the top hit.
  useEffect(() => {
    setHi(0);
  }, [q]);

  // Debounced lazy thread fetch for the highlighted session (once per open).
  useEffect(() => {
    if (!open || !highlightedId) return;
    if (requestedRef.current.has(highlightedId)) return;
    const timer = setTimeout(() => {
      if (requestedRef.current.has(highlightedId)) return;
      requestedRef.current.add(highlightedId);
      setThreadMap((m) => ({ ...m, [highlightedId]: { status: "loading" } }));
      threadsApi
        .list(highlightedId)
        .then((threads) =>
          setThreadMap((m) => ({ ...m, [highlightedId]: { status: "ready", threads } }))
        )
        .catch(() => setThreadMap((m) => ({ ...m, [highlightedId]: { status: "error" } })));
    }, 200);
    return () => clearTimeout(timer);
  }, [open, highlightedId]);

  // Navigate with the same shell semantics as the Launcher: explicit view
  // persists the preference; absent view falls back to the stored shell.
  // S4: flip the fallback to stored-shell ?? "agent" once the agent shell ships.
  const navigate = (sessionId: string, opts?: { chat?: string | null; view?: ViewMode }) => {
    const ui = useWorkbenchUiStore.getState();
    if (opts?.view) ui.setShell(sessionId, opts.view);
    const view = opts?.view ?? ui.perSession[sessionId]?.shell ?? "ide";
    setOpen(false);
    openSession(router, sessionId, { chat: opts?.chat ?? null, view });
  };

  const newChat = async (sessionId: string) => {
    try {
      const thread = await threadsApi.create(sessionId);
      navigate(sessionId, { chat: thread.id });
    } catch {
      // Creation failed (offline / stale session) — still land in the workspace.
      navigate(sessionId);
    }
  };

  // Overlay keyboard model: ↑↓ move the highlight, Enter opens it, Esc closes.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setHi((h) => moveHighlight(h, 1, flat.length));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHi((h) => moveHighlight(h, -1, flat.length));
      } else if (e.key === "Enter" && highlightedId) {
        e.preventDefault();
        navigate(highlightedId);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, flat.length, highlightedId]);

  if (!open) return null;

  const groupColor = (projectId: string) =>
    groupSwatch(projects.findIndex((p) => p.id === projectId));
  const indexOf = new Map(flat.map((s, i) => [s.id, i]));
  const detailThreads = highlightedId ? threadMap[highlightedId] : undefined;
  const detailShell: ViewMode = highlighted
    ? perSession[highlighted.id]?.shell ?? "ide"
    : "ide";
  const detailGroup = highlighted?.project_id
    ? projects.find((p) => p.id === highlighted.project_id) ?? null
    : null;

  return (
    <div
      data-testid="quick-switch"
      role="dialog"
      aria-modal="true"
      aria-label="Switch session"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-6 pt-[9vh] animate-fade-in"
      onMouseDown={() => setOpen(false)}
    >
      <div
        className="w-full max-w-[720px] overflow-hidden rounded-xl border border-border bg-surface-1 shadow-e3 animate-scale-in"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Search */}
        <div className="flex h-12 items-center gap-2.5 border-b border-border px-4">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Switch to a session…"
            aria-label="Switch to a session"
            className="h-full flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/60"
          />
          <Kbd>⌘O</Kbd>
        </div>

        <div className="flex h-[380px]">
          {/* LEFT — grouped session list */}
          <div className="w-[46%] overflow-y-auto thin-scrollbar border-r border-border py-2">
            {flat.length === 0 && (
              <p className="px-3 py-4 text-xs text-muted-foreground" data-testid="qs-empty">
                {q ? `No sessions match "${q}"` : "No sessions yet."}
              </p>
            )}
            {sections.map(({ project, sessions: list }) => (
              <div key={project?.id ?? "__none__"} className="mb-1">
                <div className="flex items-center gap-1.5 px-3 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                  {project ? (
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: groupColor(project.id) }}
                    />
                  ) : (
                    <Hash className="h-3 w-3" aria-hidden />
                  )}
                  {project ? project.name : "Ungrouped"}
                </div>
                {list.map((s) => {
                  const idx = indexOf.get(s.id) ?? 0;
                  const on = highlightedId === s.id;
                  const cur = s.id === currentId;
                  const when = relativeTime(s.updated_at ?? s.created_at);
                  return (
                    <button
                      key={s.id}
                      type="button"
                      data-testid={`qs-session-${s.id}`}
                      onMouseEnter={() => setHi(idx)}
                      onClick={() => navigate(s.id)}
                      className={cn(
                        "flex w-full items-center gap-2.5 border-l-2 px-3 py-2 text-left",
                        on ? "border-primary bg-surface-2" : "border-transparent hover:bg-surface-2/50"
                      )}
                    >
                      {cur || on ? (
                        <FolderOpen className="h-4 w-4 shrink-0 text-primary" aria-hidden />
                      ) : (
                        <Folder className="h-4 w-4 shrink-0 text-muted-foreground/70" aria-hidden />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 truncate font-mono text-[12.5px] text-foreground/90">
                          <span className="truncate">{s.name ?? s.id}</span>
                          {cur && (
                            <span className="shrink-0 rounded bg-primary/15 px-1 font-sans text-[9px] font-medium text-primary">
                              current
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-muted-foreground/70">
                          {plural(s.thread_count ?? 0, "chat")}
                          {when && <> · {when}</>}
                        </div>
                      </div>
                      {on && (
                        <CornerDownRight
                          className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60"
                          aria-hidden
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
            {/* Create lives on the Launcher — this routes home. */}
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                router.push("/");
              }}
              className="flex w-full items-center gap-2.5 border-l-2 border-transparent px-3 py-2 text-left text-primary hover:bg-surface-2/50"
            >
              <Plus className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="text-[12.5px] font-medium">New session…</span>
              <span className="ml-auto shrink-0 text-[10px] text-muted-foreground/60">
                create from the launcher
              </span>
            </button>
          </div>

          {/* RIGHT — detail pane for the highlighted session */}
          <div className="flex min-w-0 flex-1 flex-col" data-testid="qs-detail">
            {highlighted && (
              <>
                <div className="border-b border-border px-4 pb-2.5 pt-3">
                  <div className="flex items-center gap-2">
                    <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-primary/25 bg-primary/15 text-primary">
                      <Folder className="h-4 w-4" aria-hidden />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-mono text-[13px] font-medium">
                        {highlighted.name ?? highlighted.id}
                      </div>
                      <div className="truncate font-mono text-[10px] text-muted-foreground">
                        workspace/{highlighted.id}/
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-3.5 text-[11px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <MessageSquare className="h-3.5 w-3.5" aria-hidden />
                      {plural(highlighted.thread_count ?? 0, "chat")}
                    </span>
                    {relativeTime(highlighted.updated_at ?? highlighted.created_at) && (
                      <span className="inline-flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" aria-hidden />
                        {relativeTime(highlighted.updated_at ?? highlighted.created_at)}
                      </span>
                    )}
                    {detailGroup && (
                      <span className="ml-auto inline-flex min-w-0 items-center gap-1.5">
                        <span
                          className="h-1.5 w-1.5 shrink-0 rounded-full"
                          style={{ background: groupColor(detailGroup.id) }}
                        />
                        <span className="truncate">{detailGroup.name}</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Shell choice — the stored preference is highlighted. */}
                <div className="flex gap-2 px-3 pt-2.5">
                  <button
                    type="button"
                    onClick={() => navigate(highlighted.id, { view: "agent" })}
                    className={cn(
                      "flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md text-[12px] font-medium",
                      detailShell === "agent"
                        ? "border border-primary/30 bg-primary/15 text-primary"
                        : "bg-surface-2 text-foreground/85 hover:bg-surface-3"
                    )}
                  >
                    <MessageSquare className="h-3.5 w-3.5" aria-hidden /> Open in Chat
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(highlighted.id, { view: "ide" })}
                    className={cn(
                      "flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md text-[12px] font-medium",
                      detailShell === "ide"
                        ? "border border-primary/30 bg-primary/15 text-primary"
                        : "bg-surface-2 text-foreground/85 hover:bg-surface-3"
                    )}
                  >
                    <Columns2 className="h-3.5 w-3.5" aria-hidden /> Open in IDE
                  </button>
                </div>

                {/* Jump to a chat — lazy on highlight (debounced). */}
                <div className="px-2 pb-1 pt-2.5">
                  <span className="px-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                    Jump to a chat
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto thin-scrollbar px-2 pb-2">
                  {!detailThreads || detailThreads.status === "loading" ? (
                    <div className="space-y-1 px-1 pt-1">
                      {[0, 1].map((i) => (
                        <Skeleton key={i} className="h-8 w-full" />
                      ))}
                    </div>
                  ) : detailThreads.status === "error" ? (
                    <p className="px-2.5 py-2 text-[11px] text-muted-foreground">
                      Couldn&apos;t load chats.
                    </p>
                  ) : (
                    <>
                      {detailThreads.threads.length === 0 && (
                        <p className="px-2.5 py-2 text-[11px] text-muted-foreground">
                          No chats yet.
                        </p>
                      )}
                      {detailThreads.threads.map((t) => {
                        const when = relativeTime(t.last_active ?? t.created_at);
                        return (
                          <button
                            key={t.id}
                            type="button"
                            onClick={() => navigate(highlighted.id, { chat: t.id })}
                            className="group flex w-full gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-surface-2/60"
                          >
                            <MessageSquare
                              className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/60"
                              aria-hidden
                            />
                            <span className="min-w-0 flex-1 truncate text-[12.5px] text-foreground/85">
                              {t.title || "Untitled chat"}
                            </span>
                            {when && (
                              <span className="ml-auto shrink-0 text-[10px] text-muted-foreground/60">
                                {when}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => void newChat(highlighted.id)}
                    className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-primary hover:bg-surface-2/60"
                  >
                    <Plus className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    <span className="truncate text-[12.5px] font-medium">
                      New chat in {highlighted.name ?? highlighted.id}
                    </span>
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Footer — the keyboard contract. */}
        <div className="flex h-9 items-center gap-3 border-t border-border px-4 text-[10px] text-muted-foreground/70">
          <span className="flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> session
          </span>
          <span className="flex items-center gap-1">
            <Kbd>↵</Kbd> open
          </span>
          <span className="flex items-center gap-1">
            <Kbd>esc</Kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-4 min-w-[16px] items-center justify-center rounded border border-border bg-surface-2 px-1 font-mono text-[9px] text-muted-foreground">
      {children}
    </kbd>
  );
}
