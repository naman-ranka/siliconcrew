"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronRight,
  CircuitBoard,
  Folder,
  FolderOpen,
  Github,
  Hash,
  Home,
  Menu,
  MessageSquare,
  Plus,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { threadsApi } from "@/lib/api";
import { sessionUrl, replaceThreadUrl } from "@/lib/nav";
import { cn, inertWhenClosed } from "@/lib/utils";
import { IconTooltip } from "@/components/ui/tooltip";
import { CreateSessionModal } from "@/components/launcher/CreateSessionModal";
import { groupSwatch } from "@/components/launcher/util";
import { relativeTime } from "./runStatus";
import { ProfileMenu, REPO_URL } from "./ProfileMenu";
import { ThemeToggle } from "./ThemeToggle";
import { McpModal } from "./McpModal";
import type { ChatThread } from "@/types";

// Agent-shell left nav rail (Wave 8) — a Codex-style OVERLAY, closed by
// default (⌘O / the ☰ button): purely navigational. Sessions grouped by
// project with their chats nested under them; click a chat to go there.
// No status dots (a session has many runs — one verdict is ambiguous;
// revision 1) and nothing here mutates: the thread list endpoint is
// read-only, so browsing other sessions' chats never materializes rows.

type ThreadsState = { status: "loading" } | { status: "error" } | { status: "ready"; threads: ChatThread[] };

export function NavRail() {
  const router = useRouter();
  const open = useWorkbenchUiStore((s) => s.navRailOpen);
  const setOpen = useWorkbenchUiStore((s) => s.setNavRailOpen);
  const { currentSession, sessions, projects, threads, activeThreadId, loadSessions, loadProjects, selectThread } =
    useStore();
  const sid = currentSession?.id ?? null;

  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  // Lazy per-session chats, fetched on first expand while the rail is open.
  // The CURRENT session always renders the live store list instead.
  const [threadCache, setThreadCache] = useState<Record<string, ThreadsState>>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [mcpOpen, setMcpOpen] = useState(false);
  const asideRef = useRef<HTMLElement>(null);

  // Opening the rail refreshes the nav data and re-reveals the current
  // session's chats; the stale lazy cache is dropped so re-expands refetch.
  useEffect(() => {
    if (!open) return;
    void loadSessions();
    void loadProjects();
    setThreadCache({});
    setExpanded(new Set(sid ? [sid] : []));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Esc closes the rail — but NOT while its create-modal is up (the modal's
  // own handler consumes that press), and mark consumption so the artifact
  // panel's Esc listener never doubles up.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || createOpen || mcpOpen || e.defaultPrevented) return;
      e.preventDefault();
      setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, createOpen, mcpOpen, setOpen]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    // First expand of a non-current session → fetch its chats (read-only).
    if (id !== sid && !threadCache[id]) {
      setThreadCache((c) => ({ ...c, [id]: { status: "loading" } }));
      threadsApi
        .list(id)
        .then((list) => setThreadCache((c) => ({ ...c, [id]: { status: "ready", threads: list } })))
        .catch(() => setThreadCache((c) => ({ ...c, [id]: { status: "error" } })));
    }
  };

  const openChat = async (sessionId: string, threadId: string | null) => {
    setOpen(false);
    if (sessionId === sid) {
      // Same workspace: switch the conversation in place (no navigation).
      if (threadId && threadId !== activeThreadId) {
        await selectThread(threadId);
        replaceThreadUrl(router, sessionId, threadId);
      }
    } else {
      router.push(sessionUrl(sessionId, { chat: threadId, view: "agent" }));
    }
  };

  // Sessions grouped by project (launcher order), ungrouped at the tail.
  const sections = useMemo(() => {
    const rows: { gid: string | null; label: string; color: string | null; list: typeof sessions }[] =
      projects.map((p, i) => ({
        gid: p.id,
        label: p.name,
        color: groupSwatch(i),
        list: sessions.filter((s) => s.project_id === p.id),
      }));
    rows.push({ gid: null, label: "Ungrouped", color: null, list: sessions.filter((s) => !s.project_id) });
    return rows.filter((r) => r.list.length > 0);
  }, [projects, sessions]);

  const chatsFor = (sessionId: string): ThreadsState =>
    sessionId === sid ? { status: "ready", threads } : threadCache[sessionId] ?? { status: "loading" };

  return (
    <>
      {/* Scrim — click-away closes. Kept mounted for the fade. */}
      <div
        aria-hidden
        onMouseDown={() => setOpen(false)}
        className={cn(
          "fixed inset-0 z-[80] bg-black/40 transition-opacity duration-200",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
      />
      <aside
        ref={asideRef}
        data-testid="agent-nav-rail"
        data-open={open}
        aria-hidden={!open}
        {...inertWhenClosed(open)}
        className={cn(
          "fixed bottom-0 left-0 top-0 z-[90] flex w-[264px] flex-col border-r border-border bg-surface-1",
          "shadow-e3 transition-transform duration-200 ease-out",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand + collapse. The ☰ sits in the top-left where the shell
            header's opener is, so the SAME corner control both opens and
            closes the rail (F7 — the open rail no longer buries its opener,
            which it covers at z-90). */}
        <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3">
          <button
            type="button"
            title="Collapse (Esc)"
            aria-label="Toggle navigation"
            data-testid="rail-collapse"
            onClick={() => setOpen(false)}
            className="-ml-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-surface-2 hover:text-foreground"
          >
            <Menu className="h-4 w-4" aria-hidden />
          </button>
          <div className="grid h-6 w-6 place-items-center rounded-md bg-primary/15">
            <CircuitBoard className="h-3.5 w-3.5 text-primary" aria-hidden />
          </div>
          <span className="text-[13px] font-semibold" data-testid="agent-brand">
            SiliconCrew
          </span>
        </div>

        {/* New session */}
        <div className="px-2.5 pb-1.5 pt-2.5">
          <button
            type="button"
            data-testid="rail-new-session"
            onClick={() => setCreateOpen(true)}
            className="flex h-8 w-full items-center gap-2 rounded-md border border-primary/25 bg-primary/10 px-2 text-[12px] font-medium text-primary hover:bg-primary/15"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden /> New session
          </button>
        </div>

        <div className="flex items-center gap-1.5 px-3 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
          <Home className="h-3 w-3" aria-hidden /> Sessions
        </div>

        {/* Grouped sessions with nested chats */}
        <div className="flex-1 overflow-y-auto thin-scrollbar px-1.5 pb-2">
          {sections.length === 0 && (
            <p className="px-2 py-2 text-[11px] text-muted-foreground/60">No sessions yet.</p>
          )}
          {sections.map((sec) => (
            <div key={sec.gid ?? "__none__"} className="mb-1.5">
              <div className="flex items-center gap-1.5 px-2 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/55">
                {sec.color ? (
                  <span className="h-2 w-2 rounded-full" style={{ background: sec.color }} aria-hidden />
                ) : (
                  <Hash className="h-3 w-3" aria-hidden />
                )}
                <span className="truncate">{sec.label}</span>
              </div>
              {sec.list.map((s) => {
                const isCurrent = s.id === sid;
                const isExpanded = expanded.has(s.id);
                const chats = chatsFor(s.id);
                return (
                  <div key={s.id}>
                    <button
                      type="button"
                      data-testid={`rail-session-${s.id}`}
                      onClick={() => toggleExpand(s.id)}
                      className={cn(
                        "flex h-8 w-full items-center gap-1.5 rounded-md pl-1.5 pr-2 text-left",
                        isCurrent ? "bg-surface-2" : "hover:bg-surface-2/60"
                      )}
                    >
                      <ChevronRight
                        className={cn(
                          "h-3.5 w-3.5 shrink-0 text-muted-foreground/60 transition-transform",
                          isExpanded && "rotate-90"
                        )}
                        aria-hidden
                      />
                      {isCurrent ? (
                        <FolderOpen className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
                      ) : (
                        <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" aria-hidden />
                      )}
                      <span
                        className={cn(
                          "truncate font-mono text-[12px]",
                          isCurrent ? "font-medium text-foreground" : "text-foreground/85"
                        )}
                      >
                        {s.name ?? s.id}
                      </span>
                      <span className="ml-auto shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/45">
                        {s.thread_count ?? ""}
                      </span>
                    </button>
                    {isExpanded && (
                      <div className="my-0.5 ml-[18px] border-l border-border/60 pl-2">
                        {chats.status === "loading" && (
                          <p className="px-2 py-1 text-[10.5px] text-muted-foreground/50">Loading…</p>
                        )}
                        {chats.status === "error" && (
                          <p className="px-2 py-1 text-[10.5px] text-muted-foreground/60">
                            Couldn&apos;t load chats.
                          </p>
                        )}
                        {chats.status === "ready" && chats.threads.length === 0 && (
                          <button
                            type="button"
                            onClick={() => void openChat(s.id, null)}
                            className="flex h-7 w-full items-center gap-2 rounded-md px-2 text-left text-[11.5px] text-foreground/80 hover:bg-surface-2/50"
                          >
                            Open workspace
                          </button>
                        )}
                        {chats.status === "ready" &&
                          chats.threads.map((t) => {
                            const isActive = isCurrent && t.id === activeThreadId;
                            return (
                              <button
                                key={t.id}
                                type="button"
                                data-testid={`rail-chat-${t.id}`}
                                onClick={() => void openChat(s.id, t.id)}
                                className={cn(
                                  "flex h-7 w-full items-center gap-2 rounded-md px-2 text-left",
                                  isActive ? "bg-surface-2" : "hover:bg-surface-2/50"
                                )}
                              >
                                <MessageSquare
                                  className={cn(
                                    "h-3 w-3 shrink-0",
                                    isActive ? "text-primary" : "text-muted-foreground/55"
                                  )}
                                  aria-hidden
                                />
                                <span
                                  className={cn(
                                    "truncate text-[11.5px]",
                                    isActive ? "text-foreground" : "text-foreground/80"
                                  )}
                                >
                                  {t.title || "Untitled chat"}
                                </span>
                                <span className="ml-auto shrink-0 font-mono text-[9px] text-muted-foreground/45">
                                  {relativeTime(t.last_active ?? t.created_at)}
                                </span>
                              </button>
                            );
                          })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer: repo · theme · profile (MCP handoff modal owned here). */}
        <div className="flex items-center gap-1 border-t border-border p-2">
          <IconTooltip label="Open-source repo">
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              aria-label="Open-source repo"
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              <Github className="h-3.5 w-3.5" aria-hidden />
            </a>
          </IconTooltip>
          <ThemeToggle />
          <div className="ml-auto">
            <ProfileMenu placement="top-start" onConnectMcp={() => setMcpOpen(true)} />
          </div>
        </div>
      </aside>

      {createOpen && (
        <CreateSessionModal defaultStartIn="agent" onClose={() => setCreateOpen(false)} />
      )}
      <McpModal open={mcpOpen} onOpenChange={setMcpOpen} />
    </>
  );
}
