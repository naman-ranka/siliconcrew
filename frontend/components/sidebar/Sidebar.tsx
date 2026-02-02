"use client";

import { useEffect, useState } from "react";
import {
  PanelLeftClose,
  PanelLeft,
  Plus,
  Trash2,
  FolderOpen,
  Settings,
  BarChart3,
  Cpu,
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
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { formatTokens, formatCost, formatRelativeTime } from "@/lib/utils";
import type { Session } from "@/types";

export function Sidebar() {
  const {
    sessions,
    currentSession,
    sidebarCollapsed,
    sessionsLoading,
    loadSessions,
    createSession,
    deleteSession,
    selectSession,
    toggleSidebar,
  } = useStore();

  const [newSessionName, setNewSessionName] = useState("");
  const [selectedModel, setSelectedModel] = useState("gemini-2.5-flash");
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleCreateSession = async () => {
    if (!newSessionName.trim()) {
      setCreateError("Please enter a session name");
      return;
    }

    try {
      setCreateError(null);
      await createSession(newSessionName.trim(), selectedModel);
      setNewSessionName("");
      setIsCreateDialogOpen(false);
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "Failed to create session");
    }
  };

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

  if (sidebarCollapsed) {
    return (
      <div className="flex flex-col h-full w-14 bg-secondary/50 border-r border-border">
        <div className="flex items-center justify-center h-14 border-b border-border">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" onClick={toggleSidebar}>
                <PanelLeft className="h-5 w-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Expand sidebar</TooltipContent>
          </Tooltip>
        </div>

        <div className="flex-1 flex flex-col items-center py-4 gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsCreateDialogOpen(true)}
              >
                <Plus className="h-5 w-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">New Session</TooltipContent>
          </Tooltip>

          <Separator className="my-2 w-8" />

          {sessions.slice(0, 5).map((session) => (
            <Tooltip key={session.id}>
              <TooltipTrigger asChild>
                <Button
                  variant={currentSession?.id === session.id ? "secondary" : "ghost"}
                  size="icon"
                  onClick={() => selectSession(session)}
                >
                  <FolderOpen className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">{session.id}</TooltipContent>
            </Tooltip>
          ))}
        </div>

        <div className="flex flex-col items-center py-4 gap-2 border-t border-border">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon">
                <Settings className="h-5 w-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Settings</TooltipContent>
          </Tooltip>
        </div>

        {/* Create Dialog */}
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Session</DialogTitle>
              <DialogDescription>
                Start a new design session with the RTL Agent.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <Input
                placeholder="Session name (e.g., counter_design)"
                value={newSessionName}
                onChange={(e) => setNewSessionName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateSession()}
              />
              <Select value={selectedModel} onValueChange={setSelectedModel}>
                <SelectTrigger>
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="gemini-2.5-flash">Gemini 2.5 Flash</SelectItem>
                  <SelectItem value="gemini-3-pro-preview">Gemini 3 Pro (Preview)</SelectItem>
                </SelectContent>
              </Select>
              {createError && (
                <p className="text-sm text-destructive">{createError}</p>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateSession}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-64 bg-secondary/50 border-r border-border">
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Cpu className="h-5 w-5 text-primary" />
          <span className="font-semibold text-sm">SiliconCrew</span>
        </div>
        <Button variant="ghost" size="icon" onClick={toggleSidebar}>
          <PanelLeftClose className="h-5 w-5" />
        </Button>
      </div>

      {/* New Session Button */}
      <div className="p-3">
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button className="w-full" variant="outline">
              <Plus className="h-4 w-4 mr-2" />
              New Session
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Session</DialogTitle>
              <DialogDescription>
                Start a new design session with the RTL Agent.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <Input
                placeholder="Session name (e.g., counter_design)"
                value={newSessionName}
                onChange={(e) => setNewSessionName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateSession()}
              />
              <Select value={selectedModel} onValueChange={setSelectedModel}>
                <SelectTrigger>
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="gemini-2.5-flash">Gemini 2.5 Flash</SelectItem>
                  <SelectItem value="gemini-3-pro-preview">Gemini 3 Pro (Preview)</SelectItem>
                </SelectContent>
              </Select>
              {createError && (
                <p className="text-sm text-destructive">{createError}</p>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateSession}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Separator />

      {/* Sessions List */}
      <div className="flex-1 overflow-hidden">
        <div className="px-3 py-2">
          <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Sessions
          </h3>
        </div>
        <ScrollArea className="h-[calc(100%-2rem)]">
          <div className="px-2 pb-4">
            {sessionsLoading ? (
              <div className="text-sm text-muted-foreground text-center py-4">
                Loading...
              </div>
            ) : sessions.length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-4">
                No sessions yet
              </div>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.id}
                  className={cn(
                    "group flex items-center justify-between rounded-md px-3 py-2 mb-1 cursor-pointer transition-colors",
                    currentSession?.id === session.id
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-accent/50"
                  )}
                  onClick={() => selectSession(session)}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <FolderOpen className="h-4 w-4 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{session.id}</p>
                      <p className="text-xs text-muted-foreground">
                        {session.model_name?.split("-").slice(0, 2).join("-") || "unknown"}
                        {session.total_tokens > 0 && (
                          <span> | {formatTokens(session.total_tokens)}</span>
                        )}
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 group-hover:opacity-100 shrink-0"
                    onClick={(e) => confirmDelete(session, e)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Footer */}
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="flex-1 justify-start">
            <Settings className="h-4 w-4 mr-2" />
            Settings
          </Button>
          <Button variant="ghost" size="sm" className="flex-1 justify-start">
            <BarChart3 className="h-4 w-4 mr-2" />
            Stats
          </Button>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Session</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{sessionToDelete?.id}"? This action
              cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
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
