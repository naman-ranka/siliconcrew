"use client";

import { useEffect, useMemo, useState } from "react";
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
  ChevronDown,
  ChevronRight,
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
import type { Session } from "@/types";

interface CreateSessionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}

function CreateSessionDialog({ open, onOpenChange, onCreated }: CreateSessionDialogProps) {
  const { createSession } = useStore();
  const [project, setProject] = useState("");
  const [name, setName] = useState("");
  const [model, setModel] = useState("gemini-3-flash-preview");
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    const trimmedName = name.trim();
    const trimmedProject = project.trim().replace(/^\/+|\/+$/g, "");

    if (!trimmedName) {
      setError("Please enter a session name");
      return;
    }

    try {
      setError(null);
      const sessionName = trimmedProject ? `${trimmedProject}/${trimmedName}` : trimmedName;
      await createSession(sessionName, model);
      setProject("");
      setName("");
      onCreated();
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create session");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-surface-1 border-border">
        <DialogHeader>
          <DialogTitle>Create New Session</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Start a new design session with the RTL Agent.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div>
            <label className="text-sm font-medium mb-2 block">Project</label>
            <Input
              placeholder="e.g., asu_visible"
              value={project}
              onChange={(e) => setProject(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              className="bg-surface-2 border-border"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-2 block">Session Name</label>
            <Input
              placeholder="e.g., p5_run1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              className="bg-surface-2 border-border"
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Leave project empty to create a flat session. Existing flat sessions remain supported.
            </p>
          </div>
          <div>
            <label className="text-sm font-medium mb-2 block">Model</label>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger className="bg-surface-2 border-border">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent className="bg-surface-1 border-border">
                <SelectItem value="gemini-3-flash-preview">
                  <div className="flex items-center gap-2">
                    <Zap className="h-3 w-3 text-yellow-500" />
                    <div>
                      <span>Gemini 3 Flash</span>
                      <span className="text-xs text-muted-foreground ml-2">Google mid-tier</span>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="gemini-3.1-pro-preview">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3 w-3 text-primary" />
                    <div>
                      <span>Gemini 3.1 Pro</span>
                      <span className="text-xs text-muted-foreground ml-2">Google top-tier</span>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="gpt-5-mini">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3 w-3 text-green-500" />
                    <div>
                      <span>GPT-5 Mini</span>
                      <span className="text-xs text-muted-foreground ml-2">OpenAI mid-tier</span>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="gpt-5.3-codex">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3 w-3 text-emerald-500" />
                    <div>
                      <span>GPT-5.3 Codex</span>
                      <span className="text-xs text-muted-foreground ml-2">OpenAI top-tier coding</span>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="claude-sonnet-4-6">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3 w-3 text-orange-500" />
                    <div>
                      <span>Claude Sonnet 4.6</span>
                      <span className="text-xs text-muted-foreground ml-2">Anthropic mid-tier</span>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="claude-opus-4-6">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3 w-3 text-amber-500" />
                    <div>
                      <span>Claude Opus 4.6</span>
                      <span className="text-xs text-muted-foreground ml-2">Anthropic top-tier</span>
                    </div>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="border-border">
            Cancel
          </Button>
          <Button onClick={handleCreate}>Create Session</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function getSessionProject(session: Session): string {
  const slashIndex = session.id.indexOf("/");
  return slashIndex === -1 ? "ungrouped" : session.id.slice(0, slashIndex);
}

function getSessionDisplayName(session: Session): string {
  const label = session.name ?? session.id;
  const slashIndex = label.indexOf("/");
  return slashIndex === -1 ? label : label.slice(slashIndex + 1);
}

function groupSessionsByProject(sessions: Session[]) {
  const grouped = new Map<string, Session[]>();
  const sortedSessions = [...sessions].sort((a, b) => {
    const aDate = new Date(a.updated_at ?? a.created_at ?? 0).getTime();
    const bDate = new Date(b.updated_at ?? b.created_at ?? 0).getTime();
    return bDate - aDate;
  });

  for (const session of sortedSessions) {
    const project = getSessionProject(session);
    if (!grouped.has(project)) {
      grouped.set(project, []);
    }
    grouped.get(project)?.push(session);
  }

  return Array.from(grouped.entries())
    .sort(([a], [b]) => {
      if (a === "ungrouped") {
        return 1;
      }
      if (b === "ungrouped") {
        return -1;
      }
      return a.localeCompare(b);
    })
    .map(([label, projectSessions]) => ({ label, sessions: projectSessions }));
}

export function Sidebar() {
  const {
    sessions,
    currentSession,
    sidebarCollapsed,
    sessionsLoading,
    loadSessions,
    deleteSession,
    selectSession,
    toggleSidebar,
  } = useStore();

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleDeleteSession = async () => {
    if (!sessionToDelete) return;
    try {
      await deleteSession(sessionToDelete.id);
      setSessionToDelete(null);
      setIsDeleteDialogOpen(false);
    } catch (error) {
      console.error("Failed to delete session:", error);
    }
  };

  const confirmDelete = (session: Session, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessionToDelete(session);
    setIsDeleteDialogOpen(true);
  };

  const sessionGroups = useMemo(() => groupSessionsByProject(sessions), [sessions]);

  useEffect(() => {
    setCollapsedGroups((prev) => {
      const next = { ...prev };

      for (const group of sessionGroups) {
        if (!(group.label in next)) {
          next[group.label] = false;
        }
      }

      for (const key of Object.keys(next)) {
        if (!sessionGroups.some((group) => group.label === key)) {
          delete next[key];
        }
      }

      return next;
    });
  }, [sessionGroups]);

  const toggleGroup = (label: string) => {
    setCollapsedGroups((prev) => ({
      ...prev,
      [label]: !prev[label],
    }));
  };

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
              <Button
                variant="ghost"
                size="icon"
                className="hover:bg-surface-2"
                onClick={() => setIsCreateDialogOpen(true)}
              >
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
          onCreated={() => {}}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-64 bg-surface-1 border-r border-border">
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

      <div className="p-3">
        <Button className="w-full bg-primary hover:bg-primary/90" size="sm" onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Session
        </Button>
        <CreateSessionDialog
          open={isCreateDialogOpen}
          onOpenChange={setIsCreateDialogOpen}
          onCreated={() => {}}
        />
      </div>

      <Separator className="bg-border" />

      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="px-2 py-2">
            {sessionsLoading ? (
              <div className="space-y-2 px-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 rounded-lg animate-shimmer" />
                ))}
              </div>
            ) : sessions.length === 0 ? (
              <div className="text-center py-8 px-4">
                <MessageSquare className="h-10 w-10 mx-auto mb-3 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">No sessions yet</p>
                <p className="text-xs text-muted-foreground/70 mt-1">
                  Create a new session to start designing
                </p>
              </div>
            ) : (
              sessionGroups.map((group) => (
                <div key={group.label} className="mb-4">
                  <button
                    type="button"
                    className="w-full text-xs font-medium text-muted-foreground uppercase tracking-wider px-3 py-2 flex items-center gap-2 hover:text-foreground transition-colors"
                    onClick={() => toggleGroup(group.label)}
                  >
                    {collapsedGroups[group.label] ? (
                      <ChevronRight className="h-3 w-3 shrink-0" />
                    ) : (
                      <ChevronDown className="h-3 w-3 shrink-0" />
                    )}
                    <FolderOpen className="h-3 w-3 shrink-0" />
                    <span className="truncate">{group.label === "ungrouped" ? "Ungrouped" : group.label}</span>
                    <span className="text-[10px] text-muted-foreground/70 normal-case tracking-normal ml-auto">
                      {group.sessions.length}
                    </span>
                  </button>
                  {!collapsedGroups[group.label] && group.sessions.map((session) => (
                    <div
                      key={session.id}
                      className={cn(
                        "group flex items-center justify-between rounded-lg px-3 py-2.5 mx-1 mb-1 cursor-pointer transition-all",
                        currentSession?.id === session.id
                          ? "bg-surface-2 border-l-2 border-l-primary"
                          : "hover:bg-surface-2/50"
                      )}
                      onClick={() => selectSession(session)}
                    >
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className={cn(
                          "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                          currentSession?.id === session.id
                            ? "bg-primary/20"
                            : "bg-surface-2"
                        )}>
                          <MessageSquare className={cn(
                            "h-4 w-4",
                            currentSession?.id === session.id
                              ? "text-primary"
                              : "text-muted-foreground"
                          )} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium truncate">{getSessionDisplayName(session)}</p>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span className={cn(
                              "inline-flex items-center gap-1",
                              session.model_name?.includes("pro") ? "text-primary" : "text-yellow-500"
                            )}>
                              {session.model_name?.includes("pro") ? (
                                <Cpu className="h-3 w-3" />
                              ) : (
                                <Zap className="h-3 w-3" />
                              )}
                              {session.model_name?.split("-").slice(1, 2).join("-") || "flash"}
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
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 opacity-0 group-hover:opacity-100 shrink-0 hover:bg-destructive/10 hover:text-destructive"
                        onClick={(e) => confirmDelete(session, e)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </div>

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

      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent className="bg-surface-1 border-border">
          <DialogHeader>
            <DialogTitle>Delete Session</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Are you sure you want to delete &quot;{sessionToDelete?.name ?? sessionToDelete?.id}&quot;? This action
              cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
              className="border-border"
            >
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteSession}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
