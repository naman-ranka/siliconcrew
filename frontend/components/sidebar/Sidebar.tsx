"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import {
  PanelLeftClose,
  PanelLeft,
  Plus,
  Trash2,
  Settings,
  BarChart3,
  Cpu,
  Zap,
  MessageSquare,
  FolderOpen,
  FolderPlus,
  ChevronDown,
  ChevronRight,
  MoreHorizontal,
  ArrowRightLeft,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { formatTokens, formatRelativeTime } from "@/lib/utils";
import type { Project, Session } from "@/types";

// ---------------------------------------------------------------------------
// Model selector — shared between create dialog and inline forms
// ---------------------------------------------------------------------------

const MODELS = [
  { value: "gemini-3.1-flash",        label: "Gemini 3.1 Flash", sub: "Compat alias to Gemini 3 Flash", icon: <Zap  className="h-3 w-3 text-yellow-500" /> },
  { value: "gemini-3-flash-preview",  label: "Gemini 3 Flash",   sub: "Google latest 3-series Flash",   icon: <Zap  className="h-3 w-3 text-yellow-400" /> },
  { value: "gemini-3.1-flash-lite-preview", label: "Gemini 3.1 Flash-Lite", sub: "Google fastest & cheapest", icon: <Zap  className="h-3 w-3 text-lime-500" /> },
  { value: "gemini-3.1-pro-preview",  label: "Gemini 3.1 Pro",   sub: "Google top-tier reasoning",      icon: <Cpu  className="h-3 w-3 text-primary" /> },
  { value: "gpt-5-mini",              label: "GPT-5 Mini",        sub: "OpenAI mid-tier",          icon: <Cpu  className="h-3 w-3 text-green-500" /> },
  { value: "gpt-5.3-codex",           label: "GPT-5.3 Codex",    sub: "OpenAI top-tier coding",   icon: <Cpu  className="h-3 w-3 text-emerald-500" /> },
  { value: "gpt-5.4",                 label: "GPT-5.4",           sub: "OpenAI flagship",          icon: <Cpu  className="h-3 w-3 text-emerald-400" /> },
  { value: "gpt-5.4-mini",            label: "GPT-5.4 Mini",      sub: "OpenAI fast & cheap",      icon: <Zap  className="h-3 w-3 text-green-400" /> },
  { value: "claude-sonnet-4-6",       label: "Claude Sonnet 4.6", sub: "Anthropic mid-tier",       icon: <Cpu  className="h-3 w-3 text-orange-500" /> },
  { value: "claude-opus-4-6",         label: "Claude Opus 4.6",   sub: "Anthropic top-tier",       icon: <Cpu  className="h-3 w-3 text-amber-500" /> },
];
const MODEL_LABELS = new Map(MODELS.map((model) => [model.value, model.label]));

function ModelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="bg-surface-2 border-border">
        <SelectValue placeholder="Select model" />
      </SelectTrigger>
      <SelectContent className="bg-surface-1 border-border">
        {MODELS.map((m) => (
          <SelectItem key={m.value} value={m.value}>
            <div className="flex items-center gap-2">
              {m.icon}
              <div>
                <span>{m.label}</span>
                <span className="text-xs text-muted-foreground ml-2">{m.sub}</span>
              </div>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// ---------------------------------------------------------------------------
// Create Session Dialog
// ---------------------------------------------------------------------------

type ProjectMode = "none" | "existing" | "new";

interface CreateSessionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-select a project when opening from a project's + button */
  preselectedProjectId?: string | null;
}

function CreateSessionDialog({ open, onOpenChange, preselectedProjectId }: CreateSessionDialogProps) {
  const { projects, createSession, createProject, loadProjects } = useStore();

  const [name, setName] = useState("");
  const [model, setModel] = useState("gemini-3.1-flash");
  const [projectMode, setProjectMode] = useState<ProjectMode>(preselectedProjectId ? "existing" : "none");
  const [selectedProjectId, setSelectedProjectId] = useState<string>(preselectedProjectId ?? "");
  const [newProjectName, setNewProjectName] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Sync preselectedProjectId when dialog opens
  useEffect(() => {
    if (open) {
      loadProjects();
      if (preselectedProjectId) {
        setProjectMode("existing");
        setSelectedProjectId(preselectedProjectId);
      }
    }
  }, [open, preselectedProjectId, loadProjects]);

  const handleCreate = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) { setError("Please enter a session name"); return; }

    let projectId: string | null = null;

    try {
      setError(null);

      if (projectMode === "existing") {
        if (!selectedProjectId) { setError("Please select a project"); return; }
        projectId = selectedProjectId;
      } else if (projectMode === "new") {
        const trimmedProject = newProjectName.trim();
        if (!trimmedProject) { setError("Please enter a project name"); return; }
        const project = await createProject(trimmedProject);
        projectId = project.id;
      }

      await createSession(trimmedName, model, projectId);
      setName("");
      setNewProjectName("");
      setProjectMode("none");
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create session");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-surface-1 border-border">
        <DialogHeader>
          <DialogTitle>New Session</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Start a new design session with the RTL Agent.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Project picker */}
          <div>
            <label className="text-sm font-medium mb-2 block">Project</label>
            <div className="flex gap-2">
              {(["none", "existing", "new"] as ProjectMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setProjectMode(mode)}
                  className={cn(
                    "flex-1 text-xs py-1.5 px-2 rounded border transition-colors",
                    projectMode === mode
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30"
                  )}
                >
                  {mode === "none" ? "No project" : mode === "existing" ? "Existing" : "New project"}
                </button>
              ))}
            </div>

            {projectMode === "existing" && (
              <div className="mt-2">
                {projects.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No projects yet — create one first.</p>
                ) : (
                  <Select value={selectedProjectId} onValueChange={setSelectedProjectId}>
                    <SelectTrigger className="bg-surface-2 border-border">
                      <SelectValue placeholder="Select project" />
                    </SelectTrigger>
                    <SelectContent className="bg-surface-1 border-border">
                      {projects.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          <div className="flex items-center gap-2">
                            <FolderOpen className="h-3 w-3 text-muted-foreground" />
                            {p.name}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            )}

            {projectMode === "new" && (
              <Input
                className="mt-2 bg-surface-2 border-border"
                placeholder="Project name, e.g. asu_hackathon"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
            )}
          </div>

          {/* Session name */}
          <div>
            <label className="text-sm font-medium mb-2 block">Session name</label>
            <Input
              placeholder="e.g. counter_4bit_run1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              className="bg-surface-2 border-border"
              autoFocus
            />
          </div>

          {/* Model */}
          <div>
            <label className="text-sm font-medium mb-2 block">Model</label>
            <ModelSelect value={model} onChange={setModel} />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-border">
            Cancel
          </Button>
          <Button onClick={handleCreate}>Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Move-to-project popover (tiny inline dropdown)
// ---------------------------------------------------------------------------

function MoveToProjectMenu({
  session,
  projects,
  onMove,
  onClose,
}: {
  session: Session;
  projects: Project[];
  onMove: (projectId: string | null) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute right-0 top-8 z-50 w-48 rounded-lg border border-border bg-surface-1 shadow-lg py-1 text-sm"
    >
      <p className="px-3 py-1.5 text-xs text-muted-foreground font-medium uppercase tracking-wider">
        Move to project
      </p>
      {session.project_id && (
        <button
          type="button"
          className="w-full text-left px-3 py-1.5 hover:bg-surface-2 text-muted-foreground"
          onClick={() => { onMove(null); onClose(); }}
        >
          Remove from project
        </button>
      )}
      {projects.filter((p) => p.id !== session.project_id).map((p) => (
        <button
          key={p.id}
          type="button"
          className="w-full text-left px-3 py-1.5 hover:bg-surface-2 flex items-center gap-2"
          onClick={() => { onMove(p.id); onClose(); }}
        >
          <FolderOpen className="h-3 w-3 text-muted-foreground shrink-0" />
          {p.name}
        </button>
      ))}
      {projects.filter((p) => p.id !== session.project_id).length === 0 && !session.project_id && (
        <p className="px-3 py-1.5 text-xs text-muted-foreground">No other projects</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session row
// ---------------------------------------------------------------------------

function SessionRow({
  session,
  isActive,
  projects,
  onSelect,
  onDelete,
  onMove,
}: {
  session: Session;
  isActive: boolean;
  projects: Project[];
  onSelect: () => void;
  onDelete: (e: React.MouseEvent) => void;
  onMove: (projectId: string | null) => void;
}) {
  const [showMoveMenu, setShowMoveMenu] = useState(false);

  const modelLabel = MODEL_LABELS.get(session.model_name ?? "") || session.model_name || "Gemini 3 Flash";
  const isProModel = session.model_name?.includes("pro") || session.model_name?.includes("opus") || session.model_name?.includes("5.4");

  return (
    <div
      className={cn(
        "group relative flex items-center justify-between rounded-lg px-3 py-2.5 mx-1 mb-1 cursor-pointer transition-all",
        isActive ? "bg-surface-2 border-l-2 border-l-primary" : "hover:bg-surface-2/50"
      )}
      onClick={onSelect}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className={cn(
          "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
          isActive ? "bg-primary/20" : "bg-surface-2"
        )}>
          <MessageSquare className={cn("h-4 w-4", isActive ? "text-primary" : "text-muted-foreground")} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate">
            {session.name?.includes("/") ? session.name.split("/").slice(1).join("/") : (session.name ?? session.id)}
          </p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className={cn("inline-flex items-center gap-1", isProModel ? "text-primary" : "text-yellow-500")}>
              {isProModel ? <Cpu className="h-3 w-3" /> : <Zap className="h-3 w-3" />}
              {modelLabel}
            </span>
            {(session.updated_at ?? session.created_at) && (
              <>
                <span className="text-border">•</span>
                <span>{formatRelativeTime(session.updated_at ?? session.created_at ?? "")}</span>
              </>
            )}
            {session.total_tokens > 0 && (
              <>
                <span className="text-border">•</span>
                <span>{formatTokens(session.total_tokens)}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Action buttons — visible on hover */}
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 shrink-0" onClick={(e) => e.stopPropagation()}>
        {/* Move to project */}
        <div className="relative">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 hover:bg-surface-2"
                onClick={() => setShowMoveMenu((v) => !v)}
              >
                <ArrowRightLeft className="h-3 w-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top">Move to project</TooltipContent>
          </Tooltip>
          {showMoveMenu && (
            <MoveToProjectMenu
              session={session}
              projects={projects}
              onMove={onMove}
              onClose={() => setShowMoveMenu(false)}
            />
          )}
        </div>

        {/* Delete */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 hover:bg-destructive/10 hover:text-destructive"
              onClick={onDelete}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top">Delete session</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Project group header
// ---------------------------------------------------------------------------

function ProjectGroupHeader({
  label,
  count,
  collapsed,
  onToggle,
  onAddSession,
  onDeleteProject,
  isReal, // false = "No Project" virtual group
}: {
  label: string;
  count: number;
  collapsed: boolean;
  onToggle: () => void;
  onAddSession: () => void;
  onDeleteProject?: () => void;
  isReal: boolean;
}) {
  return (
    <div className="flex items-center gap-1 px-2 py-1.5 group/header">
      <button
        type="button"
        className="flex items-center gap-1.5 flex-1 min-w-0 text-xs font-medium text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
        onClick={onToggle}
      >
        {collapsed ? <ChevronRight className="h-3 w-3 shrink-0" /> : <ChevronDown className="h-3 w-3 shrink-0" />}
        {isReal ? <FolderOpen className="h-3 w-3 shrink-0" /> : <MoreHorizontal className="h-3 w-3 shrink-0" />}
        <span className="truncate">{label}</span>
        <span className="text-[10px] text-muted-foreground/60 normal-case tracking-normal ml-1">{count}</span>
      </button>

      <div className="flex items-center gap-0.5 opacity-0 group-hover/header:opacity-100 transition-opacity">
        {/* Add session to this project */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" className="h-5 w-5 hover:bg-surface-2" onClick={onAddSession}>
              <Plus className="h-3 w-3" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">New session{isReal ? ` in ${label}` : ""}</TooltipContent>
        </Tooltip>

        {/* Delete project (only for real projects) */}
        {isReal && onDeleteProject && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 hover:bg-destructive/10 hover:text-destructive"
                onClick={onDeleteProject}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Delete project</TooltipContent>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Sidebar
// ---------------------------------------------------------------------------

export function Sidebar() {
  const {
    sessions,
    projects,
    currentSession,
    sidebarCollapsed,
    sessionsLoading,
    loadSessions,
    loadProjects,
    deleteSession,
    deleteProject,
    moveSession,
    selectSession,
    toggleSidebar,
  } = useStore();

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [createDialogProjectId, setCreateDialogProjectId] = useState<string | null>(null);
  const [isDeleteSessionDialogOpen, setIsDeleteSessionDialogOpen] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadSessions();
    loadProjects();
  }, [loadSessions, loadProjects]);

  // Group sessions: real projects first (sorted by name), then "No Project"
  const sessionGroups = useMemo(() => {
    const byProject = new Map<string, Session[]>();

    // Seed with all known projects (even empty ones)
    for (const p of projects) {
      byProject.set(p.id, []);
    }
    byProject.set("__none__", []);

    for (const s of sessions) {
      const key = s.project_id ?? "__none__";
      if (!byProject.has(key)) byProject.set(key, []);
      byProject.get(key)!.push(s);
    }

    const groups: Array<{ key: string; label: string; isReal: boolean; sessions: Session[] }> = [];

    // Real projects first
    for (const p of projects) {
      groups.push({ key: p.id, label: p.name, isReal: true, sessions: byProject.get(p.id) ?? [] });
    }

    // Orphan sessions (project deleted / pre-existing flat sessions)
    const orphans = byProject.get("__none__") ?? [];
    if (orphans.length > 0 || projects.length === 0) {
      groups.push({ key: "__none__", label: "No Project", isReal: false, sessions: orphans });
    }

    return groups;
  }, [sessions, projects]);

  useEffect(() => {
    setCollapsedGroups((prev) => {
      const next = { ...prev };
      for (const g of sessionGroups) {
        if (!(g.key in next)) next[g.key] = false;
      }
      for (const k of Object.keys(next)) {
        if (!sessionGroups.some((g) => g.key === k)) delete next[k];
      }
      return next;
    });
  }, [sessionGroups]);

  const openCreateDialog = (projectId: string | null = null) => {
    setCreateDialogProjectId(projectId);
    setIsCreateDialogOpen(true);
  };

  const confirmDeleteSession = (session: Session, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessionToDelete(session);
    setIsDeleteSessionDialogOpen(true);
  };

  const handleDeleteSession = async () => {
    if (!sessionToDelete) return;
    await deleteSession(sessionToDelete.id);
    setSessionToDelete(null);
    setIsDeleteSessionDialogOpen(false);
  };

  const handleDeleteProject = async (projectId: string) => {
    if (!confirm("Delete this project? Sessions will be kept but unassigned.")) return;
    await deleteProject(projectId);
  };

  // ---- Collapsed sidebar ----
  if (sidebarCollapsed) {
    return (
      <div className="flex flex-col h-full w-14 bg-surface-1 border-r border-border">
        <div className="flex items-center justify-center h-14 border-b border-border">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" onClick={toggleSidebar} className="hover:bg-surface-2">
                <PanelLeft className="h-5 w-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Expand sidebar (Ctrl+B)</TooltipContent>
          </Tooltip>
        </div>

        <div className="flex-1 flex flex-col items-center py-4 gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" className="hover:bg-surface-2" onClick={() => openCreateDialog()}>
                <Plus className="h-5 w-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">New Session</TooltipContent>
          </Tooltip>

          <Separator className="my-2 w-8 bg-border" />

          {sessions.slice(0, 5).map((session) => (
            <Tooltip key={session.id}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className={cn(
                    "hover:bg-surface-2",
                    currentSession?.id === session.id && "bg-surface-2 border-l-2 border-l-primary"
                  )}
                  onClick={() => selectSession(session)}
                >
                  <MessageSquare className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-[200px]">
                <p className="font-medium">{session.name ?? session.id}</p>
                {(session.updated_at ?? session.created_at) && (
                  <p className="text-xs text-muted-foreground">
                    {formatRelativeTime(session.updated_at ?? session.created_at ?? "")}
                  </p>
                )}
              </TooltipContent>
            </Tooltip>
          ))}
        </div>

        <div className="flex flex-col items-center py-4 gap-2 border-t border-border">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" className="hover:bg-surface-2">
                <Settings className="h-5 w-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Settings</TooltipContent>
          </Tooltip>
        </div>

        <CreateSessionDialog
          open={isCreateDialogOpen}
          onOpenChange={setIsCreateDialogOpen}
          preselectedProjectId={createDialogProjectId}
        />
      </div>
    );
  }

  // ---- Full sidebar ----
  return (
    <div className="flex flex-col h-full w-64 bg-surface-1 border-r border-border">
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Cpu className="h-4 w-4 text-primary" />
          </div>
          <span className="font-semibold text-sm">SiliconCrew</span>
        </div>
        <Button variant="ghost" size="icon" onClick={toggleSidebar} className="hover:bg-surface-2 h-8 w-8">
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>

      {/* New session + new project buttons */}
      <div className="p-3 flex gap-2">
        <Button className="flex-1 bg-primary hover:bg-primary/90" size="sm" onClick={() => openCreateDialog()}>
          <Plus className="h-4 w-4 mr-1.5" />
          New Session
        </Button>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="outline" size="sm" className="border-border px-2" onClick={async () => {
              const name = prompt("Project name:");
              if (name?.trim()) {
                try { await useStore.getState().createProject(name.trim()); }
                catch (e) { alert(e instanceof Error ? e.message : "Failed"); }
              }
            }}>
              <FolderPlus className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>New Project</TooltipContent>
        </Tooltip>
      </div>

      <Separator className="bg-border" />

      {/* Session list grouped by project */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="px-1 py-2">
            {sessionsLoading ? (
              <div className="space-y-2 px-2">
                {[1, 2, 3].map((i) => <div key={i} className="h-14 rounded-lg animate-shimmer" />)}
              </div>
            ) : sessions.length === 0 && projects.length === 0 ? (
              <div className="text-center py-8 px-4">
                <MessageSquare className="h-10 w-10 mx-auto mb-3 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">No sessions yet</p>
                <p className="text-xs text-muted-foreground/70 mt-1">Create a new session to start designing</p>
              </div>
            ) : (
              sessionGroups.map((group) => (
                <div key={group.key} className="mb-3">
                  <ProjectGroupHeader
                    label={group.label}
                    count={group.sessions.length}
                    collapsed={collapsedGroups[group.key] ?? false}
                    onToggle={() => setCollapsedGroups((prev) => ({ ...prev, [group.key]: !prev[group.key] }))}
                    onAddSession={() => openCreateDialog(group.isReal ? group.key : null)}
                    onDeleteProject={group.isReal ? () => handleDeleteProject(group.key) : undefined}
                    isReal={group.isReal}
                  />

                  {!(collapsedGroups[group.key]) && (
                    group.sessions.length === 0 ? (
                      <p className="text-xs text-muted-foreground/50 px-4 py-1">No sessions yet</p>
                    ) : (
                      group.sessions.map((session) => (
                        <SessionRow
                          key={session.id}
                          session={session}
                          isActive={currentSession?.id === session.id}
                          projects={projects}
                          onSelect={() => selectSession(session)}
                          onDelete={(e) => confirmDeleteSession(session, e)}
                          onMove={(pid) => moveSession(session.id, pid)}
                        />
                      ))
                    )
                  )}
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Footer */}
      <div className="border-t border-border p-2">
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" className="flex-1 justify-start text-muted-foreground hover:text-foreground hover:bg-surface-2 h-9">
            <Settings className="h-4 w-4 mr-2" />
            Settings
          </Button>
          <Button variant="ghost" size="sm" className="flex-1 justify-start text-muted-foreground hover:text-foreground hover:bg-surface-2 h-9">
            <BarChart3 className="h-4 w-4 mr-2" />
            Usage
          </Button>
        </div>
      </div>

      {/* Dialogs */}
      <CreateSessionDialog
        open={isCreateDialogOpen}
        onOpenChange={setIsCreateDialogOpen}
        preselectedProjectId={createDialogProjectId}
      />

      <Dialog open={isDeleteSessionDialogOpen} onOpenChange={setIsDeleteSessionDialogOpen}>
        <DialogContent className="bg-surface-1 border-border">
          <DialogHeader>
            <DialogTitle>Delete Session</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Are you sure you want to delete &quot;{sessionToDelete?.name ?? sessionToDelete?.id}&quot;? This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDeleteSessionDialogOpen(false)} className="border-border">
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteSession}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
