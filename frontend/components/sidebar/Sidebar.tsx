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
  Clock,
  Zap,
  MessageSquare,
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
import { formatTokens, formatCost, formatRelativeTime } from "@/lib/utils";
import type { Session } from "@/types";

// Shared dialog for creating a new session
interface CreateSessionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}

function CreateSessionDialog({ open, onOpenChange, onCreated }: CreateSessionDialogProps) {
  const { createSession } = useStore();
  const [name, setName] = useState("");
  const [model, setModel] = useState("gemini-2.5-flash");
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!name.trim()) {
      setError("Please enter a session name");
      return;
    }
    try {
      setError(null);
      await createSession(name.trim(), model);
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
            <label className="text-sm font-medium mb-2 block">Session Name</label>
            <Input
              placeholder="e.g., counter_design"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              className="bg-surface-2 border-border"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-2 block">Model</label>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger className="bg-surface-2 border-border">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent className="bg-surface-1 border-border">
                <SelectItem value="gemini-2.5-flash">
                  <div className="flex items-center gap-2">
                    <Zap className="h-3 w-3 text-yellow-500" />
                    <div>
                      <span>Gemini 2.5 Flash</span>
                      <span className="text-xs text-muted-foreground ml-2">Fast &amp; efficient</span>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="gpt-4o">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3 w-3 text-green-500" />
                    <div>
                      <span>GPT-4o</span>
                      <span className="text-xs text-muted-foreground ml-2">OpenAI</span>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="claude-3-5-sonnet-20241022">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3 w-3 text-purple-500" />
                    <div>
                      <span>Claude 3.5 Sonnet</span>
                      <span className="text-xs text-muted-foreground ml-2">Anthropic</span>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="gemini-3-pro-preview">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3 w-3 text-primary" />
                    <div>
                      <span>Gemini 3 Pro</span>
                      <span className="text-xs text-muted-foreground ml-2">Most capable</span>
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

// Group sessions by time period
function groupSessionsByDate(sessions: Session[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
  const lastWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
  const lastMonth = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);

  const groups: { label: string; sessions: Session[] }[] = [
    { label: "Today", sessions: [] },
    { label: "Yesterday", sessions: [] },
    { label: "Last 7 days", sessions: [] },
    { label: "Last 30 days", sessions: [] },
    { label: "Older", sessions: [] },
  ];

  sessions.forEach((session) => {
    const date = new Date(session.updated_at ?? session.created_at ?? 0);
    if (date >= today) {
      groups[0].sessions.push(session);
    } else if (date >= yesterday) {
      groups[1].sessions.push(session);
    } else if (date >= lastWeek) {
      groups[2].sessions.push(session);
    } else if (date >= lastMonth) {
      groups[3].sessions.push(session);
    } else {
      groups[4].sessions.push(session);
    }
  });

  return groups.filter((g) => g.sessions.length > 0);
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

  const sessionGroups = useMemo(() => groupSessionsByDate(sessions), [sessions]);

  // Collapsed sidebar
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
            <TooltipContent side="right">Expand sidebar (⌘B)</TooltipContent>
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
                {(session.updated_at ?? session.created_at) && <p className="text-xs text-muted-foreground">{formatRelativeTime(session.updated_at ?? session.created_at ?? "")}</p>}
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

        {/* Create Dialog */}
        <CreateSessionDialog
          open={isCreateDialogOpen}
          onOpenChange={setIsCreateDialogOpen}
          onCreated={() => {}}
        />
      </div>
    );
  }

  // Expanded sidebar
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

      {/* New Session Button */}
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

      {/* Sessions List */}
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
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider px-3 py-2 flex items-center gap-2">
                    <Clock className="h-3 w-3" />
                    {group.label}
                  </h3>
                  {group.sessions.map((session) => (
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
                          <p className="text-sm font-medium truncate">{session.name ?? session.id}</p>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span className={cn(
                              "inline-flex items-center gap-1",
                              session.model_name?.includes("gpt") ? "text-green-500" :
                              session.model_name?.includes("claude") ? "text-purple-500" :
                              session.model_name?.includes("pro") ? "text-primary" : "text-yellow-500"
                            )}>
                              {session.model_name?.includes("gpt") || session.model_name?.includes("claude") || session.model_name?.includes("pro") ? (
                                <Cpu className="h-3 w-3" />
                              ) : (
                                <Zap className="h-3 w-3" />
                              )}
                              {
                                session.model_name?.includes("gpt") ? "GPT-4o" :
                                session.model_name?.includes("claude") ? "Claude 3.5" :
                                session.model_name?.split("-").slice(1, 2).join("-") || "flash"
                              }
                            </span>
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

      {/* Delete Confirmation Dialog */}
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
