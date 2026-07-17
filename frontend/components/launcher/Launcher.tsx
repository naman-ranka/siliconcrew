"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronDown,
  CircleDot,
  Clock,
  Columns2,
  FolderPlus,
  Folder,
  Github,
  Hash,
  Layers,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { sessionsApi, threadsApi } from "@/lib/api";
import { openSession, type ViewMode } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AccountChip } from "@/components/auth/AccountChip";
import { ThemeToggle } from "@/components/workbench/ThemeToggle";
import { Logo } from "@/components/branding/Logo";
import { Hero } from "@/components/branding/Hero";
import { LandingFooter } from "@/components/branding/LandingFooter";
import { REPO_URL, ISSUES_URL } from "@/components/branding/links";
import { SessionCard } from "./SessionCard";
import { ThreadDrawer } from "./ThreadDrawer";
import { ExampleCard } from "./ExampleCard";
import { TemplatePreview } from "./TemplatePreview";
import { CreateSessionModal } from "./CreateSessionModal";
import { NamePrompt, type NamePromptProps } from "./NamePrompt";
import { LauncherContextMenu, type MenuItem } from "./LauncherContextMenu";
import { groupSwatch } from "./util";
import type { Project, Session, TemplateSummary } from "@/types";

type SortMode = "recent" | "grouped";

// Sign-in-on-intent: a signed-out user who commits to a MUTATING action
// (New session / Fork) triggers the sign-in redirect with the intent stashed,
// so we complete it automatically on return instead of firing a doomed 401/403.
// sessionStorage survives the same-origin AuthKit round-trip (and the in-page
// Google flow), and is scoped to the tab.
const PENDING_INTENT_KEY = "sc-pending-intent";
type PendingIntent =
  | { kind: "new_session"; groupName: string | null }
  | { kind: "fork"; templateId: string };

function stashIntent(intent: PendingIntent) {
  try {
    sessionStorage.setItem(PENDING_INTENT_KEY, JSON.stringify(intent));
  } catch {
    /* storage unavailable — fall through; the action just won't resume */
  }
}

function takeIntent(): PendingIntent | null {
  try {
    const raw = sessionStorage.getItem(PENDING_INTENT_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(PENDING_INTENT_KEY);
    return JSON.parse(raw) as PendingIntent;
  } catch {
    return null;
  }
}

/**
 * The Launcher — the app's front door (`/`). A session IS a workspace IS one
 * design block; cards lead with recency (revision 1), groups are tags over
 * the existing projects API (revision 2), and opening ROUTES to /w/{id} (S1).
 */
export function Launcher() {
  const router = useRouter();
  const {
    sessions,
    projects,
    sessionsLoading,
    sessionsError,
    loadSessions,
    loadProjects,
    deleteSession,
    deleteProject,
    renameSession,
    renameProject,
    createProject,
    moveSession,
    templates,
    templatesError,
    loadTemplates,
    forkTemplate,
  } = useStore();
  const { enabled: authEnabled, status: authStatus, signIn } = useAuth();

  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortMode>("recent");
  const [selId, setSelId] = useState<string | null>(null);
  const [selTemplate, setSelTemplate] = useState<TemplateSummary | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null);
  const [prompt, setPrompt] = useState<Omit<NamePromptProps, "onCancel"> | null>(null);
  const [creating, setCreating] = useState(false);
  const [createGroup, setCreateGroup] = useState<string | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Session | null>(null);

  // Load on mount AND when sign-in completes (same gating the old sidebar had:
  // fetching before the token restores would return an empty list).
  useEffect(() => {
    if (authStatus === "loading") return;
    loadSessions();
    loadProjects();
  }, [loadSessions, loadProjects, authStatus]);

  // Templates are PUBLIC (no auth gate) — load once on mount so a brand-new user
  // with no sessions still sees examples to fork.
  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const groupColor = (projectId: string) =>
    groupSwatch(projects.findIndex((p) => p.id === projectId));
  const groupNameOf = (projectId: string | null) =>
    projectId ? projects.find((p) => p.id === projectId)?.name ?? null : null;

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const byRecency = [...sessions].sort((a, b) => {
      const ta = new Date(a.updated_at ?? a.created_at ?? 0).getTime();
      const tb = new Date(b.updated_at ?? b.created_at ?? 0).getTime();
      return tb - ta;
    });
    if (!needle) return byRecency;
    return byRecency.filter((s) => (s.name ?? s.id).toLowerCase().includes(needle));
  }, [sessions, q]);

  const sections = useMemo(() => {
    const rows: Array<{ key: string; project: Project | null; list: Session[] }> = projects.map(
      (p) => ({ key: p.id, project: p, list: filtered.filter((s) => s.project_id === p.id) })
    );
    rows.push({
      key: "__none__",
      project: null,
      list: filtered.filter((s) => !s.project_id || !projects.some((p) => p.id === s.project_id)),
    });
    return rows;
  }, [filtered, projects]);

  const selected = sessions.find((s) => s.id === selId) ?? null;

  // ---- navigation -----------------------------------------------------------

  const open = (sessionId: string, opts?: { chat?: string | null; view?: ViewMode }) => {
    const ui = useWorkbenchUiStore.getState();
    if (opts?.view) ui.setShell(sessionId, opts.view);
    // S4 resolved: "Open in Chat" genuinely opens the agent shell now; "ide"
    // stays the fallback when no shell preference is stored.
    const view = opts?.view ?? ui.perSession[sessionId]?.shell ?? "ide";
    openSession(router, sessionId, { chat: opts?.chat ?? null, view });
  };

  const newChat = async (sessionId: string) => {
    try {
      const thread = await threadsApi.create(sessionId);
      open(sessionId, { chat: thread.id });
    } catch {
      // Creation failed (offline / stale session) — still land in the workspace.
      open(sessionId);
    }
  };

  // Session and template selection share the ONE right-hand slide-over, so
  // selecting one dismisses the other.
  const selectSessionCard = (id: string) => {
    setSelTemplate(null);
    setSelId(id);
  };
  const selectExample = (t: TemplateSummary) => {
    setSelId(null);
    setSelTemplate(t);
  };

  // Sign-in-on-intent gate: if a signed-out user commits to a mutating action,
  // stash the intent and kick off sign-in instead of firing a doomed request.
  // Returns true when the caller should stop and let the resume finish it.
  const gateOnSignIn = (intent: PendingIntent): boolean => {
    if (authEnabled && authStatus === "anonymous") {
      stashIntent(intent);
      signIn();
      return true;
    }
    return false;
  };

  // Fork → new user-owned session, then route straight into it. Errors bubble
  // to the preview (e.g. a hosted deployment returns 400).
  const forkExample = async (templateId: string) => {
    if (gateOnSignIn({ kind: "fork", templateId })) return;
    const sessionId = await forkTemplate(templateId);
    open(sessionId);
  };

  // Resume a stashed intent once sign-in completes — the WorkOS redirect reload
  // and the in-page Google flow both land here when authStatus flips to
  // signed_in. Cleared before executing so it fires exactly once.
  useEffect(() => {
    if (authStatus !== "signed_in") return;
    const intent = takeIntent();
    if (!intent) return;
    if (intent.kind === "new_session") {
      setCreateGroup(intent.groupName);
      setCreating(true);
    } else if (intent.kind === "fork") {
      void forkExample(intent.templateId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authStatus]);

  // Drag-to-group: optimistic move, reverted on server failure.
  const moveToGroup = async (sessionId: string, projectId: string | null) => {
    // Revert scope: ONLY the moved session's project_id — restoring the whole
    // snapshot would clobber concurrent renames/moves that landed meanwhile.
    const prevProject =
      useStore.getState().sessions.find((s) => s.id === sessionId)?.project_id ?? null;
    const apply = (pid: string | null) =>
      useStore.setState((st) => ({
        sessions: st.sessions.map((s) => (s.id === sessionId ? { ...s, project_id: pid } : s)),
      }));
    apply(projectId);
    try {
      await sessionsApi.patch(sessionId, { project_id: projectId });
    } catch {
      apply(prevProject);
    }
  };

  // ---- menus ----------------------------------------------------------------

  const openSessionMenu = (e: React.MouseEvent, s: Session) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: "Open in Chat", icon: MessageSquare, onClick: () => open(s.id, { view: "agent" }) },
        { label: "Open in IDE", icon: Columns2, onClick: () => open(s.id, { view: "ide" }) },
        { label: "New chat", icon: Plus, onClick: () => void newChat(s.id) },
        { sep: true },
        {
          label: "Rename",
          icon: Pencil,
          onClick: () =>
            setPrompt({
              title: "Rename session",
              initial: s.name ?? s.id,
              cta: "Rename",
              onConfirm: (v) => {
                void renameSession(s.id, v);
                setPrompt(null);
              },
            }),
        },
        {
          label: "Move to group",
          icon: Layers,
          submenu: [
            ...projects.map((p) => ({
              label: p.name,
              dot: groupColor(p.id),
              check: s.project_id === p.id,
              onClick: () => void moveSession(s.id, p.id),
            })),
            { label: "Ungrouped", icon: Hash, check: !s.project_id, onClick: () => void moveSession(s.id, null) },
            {
              label: "New group…",
              icon: Plus,
              onClick: () =>
                setPrompt({
                  title: "New group",
                  placeholder: "group name",
                  cta: "Create",
                  onConfirm: (v) => {
                    void createProject(v).then((p) => moveSession(s.id, p.id));
                    setPrompt(null);
                  },
                }),
            },
          ],
        },
        { sep: true },
        { label: "Delete", icon: Trash2, danger: true, onClick: () => setToDelete(s) },
      ],
    });
  };

  const openGroupMenu = (e: React.MouseEvent, project: Project) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: "New session here", icon: Plus, onClick: () => startCreate(project.name) },
        {
          label: "Rename group",
          icon: Pencil,
          onClick: () =>
            setPrompt({
              title: "Rename group",
              initial: project.name,
              cta: "Rename",
              onConfirm: (v) => {
                void renameProject(project.id, v);
                setPrompt(null);
              },
            }),
        },
        { sep: true },
        {
          label: "Delete group",
          icon: Trash2,
          danger: true,
          hint: "keeps sessions",
          onClick: () => void deleteProject(project.id),
        },
      ],
    });
  };

  const openBgMenu = (e: React.MouseEvent) => {
    // Only for right-clicks on the launcher background itself.
    e.preventDefault();
    setMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: "New session", icon: Plus, onClick: () => startCreate(null) },
        {
          label: "New group",
          icon: FolderPlus,
          onClick: () =>
            setPrompt({
              title: "New group",
              placeholder: "group name",
              cta: "Create",
              onConfirm: (v) => {
                void createProject(v);
                setPrompt(null);
              },
            }),
        },
      ],
    });
  };

  const startCreate = (groupName: string | null) => {
    if (gateOnSignIn({ kind: "new_session", groupName })) return;
    setCreateGroup(groupName);
    setCreating(true);
  };

  const toggleSection = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const confirmDelete = async () => {
    if (!toDelete) return;
    await deleteSession(toDelete.id);
    if (selId === toDelete.id) setSelId(null);
    setToDelete(null);
  };

  const cardFor = (s: Session, showTag: boolean) => (
    <SessionCard
      key={s.id}
      session={s}
      selected={s.id === selId}
      groupName={showTag ? groupNameOf(s.project_id) : null}
      groupColor={showTag && s.project_id ? groupColor(s.project_id) : null}
      onSelect={() => selectSessionCard(s.id)}
      onOpen={() => open(s.id)}
      onMenu={(e) => openSessionMenu(e, s)}
      dragging={dragId === s.id}
      onDragStart={() => setDragId(s.id)}
      onDragEnd={() => {
        setDragId(null);
        setDropTarget(null);
      }}
    />
  );

  const isEmpty = !sessionsLoading && sessions.length === 0 && !sessionsError;
  const isBooting = sessionsLoading && sessions.length === 0;

  // Examples gallery — shown above the sessions grid whenever bundles exist
  // (including for a brand-new user with no sessions). SWR iron rule: the list
  // is populated from the store and never blanks on a refresh error.
  const examplesBlock =
    templates.length > 0 ? (
      <section data-testid="examples-section" className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="text-[12.5px] font-semibold text-foreground/90">Examples</span>
          <span className="text-[11px] text-muted-foreground/50 tabular-nums">
            {templates.length}
          </span>
          <span className="text-[11px] text-muted-foreground/60">
            — fork a finished design into your own workspace
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {templates.map((t) => (
            <ExampleCard
              key={t.id}
              template={t}
              selected={selTemplate?.id === t.id}
              onSelect={() => selectExample(t)}
              onOpen={() => selectExample(t)}
            />
          ))}
        </div>
      </section>
    ) : null;

  // Honest offline (invariant 4 / §3D): an unreachable gallery reads as "unable
  // to connect" with a Retry, NEVER a silent empty section. Cached templates
  // always win (the store keeps last-good), so this shows ONLY when the error
  // left us with nothing to display.
  const examplesUnavailableBlock =
    templatesError && templates.length === 0 ? (
      <section data-testid="examples-unavailable" className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="text-[12.5px] font-semibold text-foreground/90">Examples</span>
        </div>
        <div className="rounded-lg border border-dashed border-border/70 py-6 px-4 text-center">
          <p className="text-[12.5px] text-muted-foreground">
            Couldn&rsquo;t reach the examples gallery.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            data-testid="retry-templates"
            onClick={() => loadTemplates()}
          >
            Retry
          </Button>
        </div>
      </section>
    ) : null;

  // One gallery slot: the populated list wins; otherwise the honest-offline
  // panel (or nothing when simply empty/loading). Used in BOTH placements.
  const galleryBlock = examplesBlock ?? examplesUnavailableBlock;

  return (
    <div data-testid="launcher" className="h-full flex bg-surface-0">
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Toolbar */}
        <header className="h-14 px-6 flex items-center gap-3 border-b border-border shrink-0">
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-6 h-6 rounded-md bg-primary/15 grid place-items-center text-primary">
              <Logo className="h-3.5 w-3.5" />
            </div>
            <span className="text-[13px] font-semibold tracking-tight hidden md:block">
              SiliconCrew
            </span>
          </div>
          <div className="relative flex-1 max-w-[420px] ml-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/70" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search workspaces…"
              className="w-full h-9 pl-9 pr-3 rounded-lg border border-border bg-surface-1 text-sm outline-none focus:border-primary/50 placeholder:text-muted-foreground/50"
            />
          </div>
          <div className="ml-auto flex items-center gap-2">
            <div className="flex items-center gap-0.5 p-0.5 rounded-md bg-surface-2">
              <button
                type="button"
                onClick={() => setSort("recent")}
                className={cn(
                  "flex items-center gap-1.5 h-7 px-2.5 rounded text-[11.5px]",
                  sort === "recent"
                    ? "bg-surface-0 shadow-sm text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Clock className="h-3.5 w-3.5" /> Recent
              </button>
              <button
                type="button"
                onClick={() => setSort("grouped")}
                className={cn(
                  "flex items-center gap-1.5 h-7 px-2.5 rounded text-[11.5px]",
                  sort === "grouped"
                    ? "bg-surface-0 shadow-sm text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Layers className="h-3.5 w-3.5" /> Grouped
              </button>
            </div>
            <Button size="sm" className="h-9 px-3.5" onClick={() => startCreate(null)}>
              <Plus className="h-4 w-4 mr-1.5" /> New session
            </Button>
            {/* Open-source chrome: repo + issues, always visible. */}
            <div className="flex items-center gap-0.5 pl-1 ml-0.5 border-l border-border">
              <a
                href={REPO_URL}
                target="_blank"
                rel="noreferrer noopener"
                aria-label="GitHub repository"
                title="GitHub repository"
                className="h-8 w-8 grid place-items-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-2"
              >
                <Github className="h-4 w-4" />
              </a>
              <a
                href={ISSUES_URL}
                target="_blank"
                rel="noreferrer noopener"
                aria-label="Issues"
                title="Issues"
                className="h-8 w-8 grid place-items-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-2"
              >
                <CircleDot className="h-4 w-4" />
              </a>
            </div>
            <AccountChip />
            <ThemeToggle />
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label="Settings"
              data-testid="open-settings"
              onClick={() => useStore.getState().setSettingsOpen(true)}
            >
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {/* Content */}
        {isBooting ? (
          <div className="flex-1 overflow-y-auto px-6 py-6">
            <div className="max-w-[860px] w-full mx-auto grid grid-cols-1 md:grid-cols-2 gap-3">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-[86px] rounded-lg" />
              ))}
            </div>
          </div>
        ) : sessionsError && sessions.length === 0 ? (
          <div className="flex-1 grid place-items-center px-6 text-center">
            <div>
              <p className="text-sm text-muted-foreground">{sessionsError}</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => loadSessions()}>
                Retry
              </Button>
            </div>
          </div>
        ) : isEmpty ? (
          // Signed-out / empty account: sell the project first — identity + what
          // it is + forkable examples — with the create CTA below, so an empty
          // account is never a dead end.
          <div className="flex-1 overflow-y-auto px-6 py-6" onContextMenu={openBgMenu}>
            <div className="max-w-[860px] w-full mx-auto">
              <Hero />
              {galleryBlock}
              <EmptyLauncher onCreate={() => startCreate(null)} inline />
              <LandingFooter />
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-6 py-6" onContextMenu={openBgMenu}>
            <div className="max-w-[860px] w-full mx-auto">
              {/* Signed-in with work: their workspaces come first; the examples
                  gallery stays available below, and the OSS footer anchors it. */}
              {filtered.length === 0 ? (
                <div className="grid place-items-center py-24 text-center">
                  <div className="w-11 h-11 rounded-xl bg-surface-2 grid place-items-center mb-3">
                    <Search className="h-5 w-5 text-muted-foreground/60" />
                  </div>
                  <div className="text-sm font-medium">No workspaces match &ldquo;{q}&rdquo;</div>
                  <button
                    type="button"
                    onClick={() => startCreate(null)}
                    className="mt-2 text-[12px] text-primary hover:underline"
                  >
                    Create one →
                  </button>
                </div>
              ) : sort === "recent" ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {filtered.map((s) => cardFor(s, true))}
                </div>
              ) : (
                <div className="space-y-7">
                  {sections.map(({ key, project, list }) => {
                    if (!project && list.length === 0 && !dragId) return null;
                    const col = collapsed.has(key);
                    return (
                      <div
                        key={key}
                        onDragOver={(e) => {
                          if (dragId) {
                            e.preventDefault();
                            setDropTarget(key);
                          }
                        }}
                        onDragLeave={() => setDropTarget((t) => (t === key ? null : t))}
                        onDrop={(e) => {
                          e.preventDefault();
                          if (dragId) void moveToGroup(dragId, project?.id ?? null);
                          setDragId(null);
                          setDropTarget(null);
                        }}
                        className={cn(
                          "rounded-lg -mx-2 px-2 py-1 transition-colors",
                          dragId && dropTarget === key && "bg-primary/5 ring-1 ring-primary/30"
                        )}
                      >
                        <div className="flex items-center gap-2 mb-3 group/h">
                          <button
                            type="button"
                            onClick={() => toggleSection(key)}
                            onContextMenu={project ? (e) => openGroupMenu(e, project) : undefined}
                            className="flex items-center gap-2 min-w-0"
                          >
                            <ChevronDown
                              className={cn(
                                "h-3.5 w-3.5 text-muted-foreground/60 transition-transform",
                                col && "-rotate-90"
                              )}
                            />
                            {project ? (
                              <span
                                className="h-2.5 w-2.5 rounded-full"
                                style={{ background: groupColor(project.id) }}
                              />
                            ) : (
                              <Hash className="h-3.5 w-3.5 text-muted-foreground/60" />
                            )}
                            <span className="text-[12.5px] font-semibold text-foreground/90">
                              {project ? project.name : "Ungrouped"}
                            </span>
                            <span className="text-[11px] text-muted-foreground/50 tabular-nums">
                              {list.length}
                            </span>
                          </button>
                          {project && (
                            <button
                              type="button"
                              aria-label={`Group actions for ${project.name}`}
                              onClick={(e) => openGroupMenu(e, project)}
                              className="h-6 w-6 grid place-items-center rounded-md text-muted-foreground opacity-0 group-hover/h:opacity-100 hover:bg-surface-2"
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => startCreate(project?.name ?? null)}
                            className="ml-auto inline-flex items-center gap-1 text-[11px] text-muted-foreground/70 hover:text-foreground opacity-0 group-hover/h:opacity-100"
                          >
                            <Plus className="h-3 w-3" /> Add
                          </button>
                        </div>
                        {!col &&
                          (list.length === 0 ? (
                            <div className="rounded-lg border border-dashed border-border/70 py-6 text-center text-[11px] text-muted-foreground/60">
                              Drop a workspace here, or{" "}
                              <button
                                type="button"
                                onClick={() => startCreate(project?.name ?? null)}
                                className="text-primary hover:underline"
                              >
                                add one
                              </button>
                            </div>
                          ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {list.map((s) => cardFor(s, false))}
                            </div>
                          ))}
                      </div>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() =>
                      setPrompt({
                        title: "New group",
                        placeholder: "group name",
                        cta: "Create",
                        onConfirm: (v) => {
                          void createProject(v);
                          setPrompt(null);
                        },
                      })
                    }
                    className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground/70 hover:text-foreground"
                  >
                    <FolderPlus className="h-3.5 w-3.5" /> New group
                  </button>
                </div>
              )}
              {galleryBlock && <div className="mt-10">{galleryBlock}</div>}
              <LandingFooter />
            </div>
          </div>
        )}
      </div>

      {/* Right-hand slide-over — a template preview OR the session thread drawer
          (mutually exclusive; one lazy hydration for the selected item only). */}
      {selTemplate ? (
        <TemplatePreview
          template={selTemplate}
          onClose={() => setSelTemplate(null)}
          onFork={forkExample}
        />
      ) : selected ? (
        <ThreadDrawer
          session={selected}
          groupName={groupNameOf(selected.project_id)}
          groupColor={selected.project_id ? groupColor(selected.project_id) : null}
          onClose={() => setSelId(null)}
          onOpen={(opts) => open(selected.id, opts)}
          onNewChat={() => void newChat(selected.id)}
        />
      ) : null}

      {/* Overlays */}
      {menu && <LauncherContextMenu {...menu} onClose={() => setMenu(null)} />}
      {prompt && <NamePrompt {...prompt} onCancel={() => setPrompt(null)} />}
      {creating && (
        <CreateSessionModal presetGroup={createGroup} onClose={() => setCreating(false)} />
      )}

      {/* Delete confirm — same pattern the old sidebar used. */}
      <Dialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <DialogContent className="bg-surface-1 border-border">
          <DialogHeader>
            <DialogTitle>Delete session</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Are you sure you want to delete &quot;{toDelete?.name ?? toDelete?.id}&quot;? The
              workspace and its chats are removed. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)} className="border-border">
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void confirmDelete()}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EmptyLauncher({ onCreate, inline = false }: { onCreate: () => void; inline?: boolean }) {
  return (
    <div className={cn(inline ? "py-10 grid place-items-center" : "flex-1 grid place-items-center px-6")}>
      <div className="max-w-[380px] text-center">
        <div className="mx-auto w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 grid place-items-center mb-5 relative">
          <Folder className="h-7 w-7 text-primary" />
          <div className="absolute -bottom-1.5 -right-1.5 w-6 h-6 rounded-lg bg-primary text-primary-foreground grid place-items-center shadow-sm">
            <Plus className="h-3.5 w-3.5" />
          </div>
        </div>
        <h1 className="text-lg font-semibold tracking-tight">No workspaces yet</h1>
        <p className="text-[13px] text-muted-foreground mt-1.5">
          Create one to start designing with the agent.
        </p>
        <div className="mt-5">
          <Button className="h-10 px-5" onClick={onCreate}>
            <Plus className="h-4 w-4 mr-1.5" /> New session
          </Button>
        </div>
      </div>
    </div>
  );
}
