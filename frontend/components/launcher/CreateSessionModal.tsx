"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Check,
  Columns2,
  Folder,
  Layers,
  MessageSquare,
  Plus,
  X,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { sessionUrl, type ViewMode } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { slugify } from "./util";

export interface CreateSessionModalProps {
  /** Pre-filled group NAME (opened from a group's "+ Add"). */
  presetGroup?: string | null;
  onClose: () => void;
}

/**
 * New-workspace modal: name with a live `workspace/<slug>/` preview, a
 * "Start in" Chat|IDE choice (persisted as the session's shell), and an
 * optional group (a tag — created on the fly if the name is new). No model
 * picker: the model is a per-chat choice; creation uses the catalog default.
 */
export function CreateSessionModal({ presetGroup, onClose }: CreateSessionModalProps) {
  const router = useRouter();
  const { projects, createSession, createProject, loadProjects, loadModels } = useStore();

  const [name, setName] = useState("");
  // S4 resolved: both shells are real; IDE stays the default pre-selection
  // (the stored per-session shell preference takes over after first open).
  const [startIn, setStartIn] = useState<ViewMode>("ide");
  const [showGroup, setShowGroup] = useState(!!presetGroup);
  const [group, setGroup] = useState(presetGroup ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadProjects();
    loadModels();
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", h);
    };
  }, [loadProjects, loadModels, onClose]);

  const slug = slugify(name) || "untitled";

  const submit = async () => {
    if (busy) return;
    if (!name.trim()) {
      setError("Give the workspace a name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Resolve the group: match an existing project by display name OR by
      // slug/id (renames change the name but never the immutable slug-id, so
      // "Demo" must still match a group whose id is `Demo` even after it was
      // renamed to "Prod"). On a 409 (created elsewhere / stale list), reload
      // and re-match instead of failing the whole session creation.
      let projectId: string | null = null;
      const groupName = group.trim();
      if (groupName) {
        const wanted = groupName.toLowerCase();
        const wantedSlug = slugify(groupName).toLowerCase();
        const match = (list: typeof projects) =>
          list.find(
            (p) =>
              p.name.toLowerCase() === wanted || p.id.toLowerCase() === wantedSlug
          );
        const existing = match(projects);
        if (existing) {
          projectId = existing.id;
        } else {
          try {
            projectId = (await createProject(groupName)).id;
          } catch (err) {
            if ((err as { status?: number }).status === 409) {
              await useStore.getState().loadProjects();
              const found = match(useStore.getState().projects);
              if (!found) throw err;
              projectId = found.id;
            } else {
              throw err;
            }
          }
        }
      }
      // Model: the real catalog default (loaded above); sessionsApi falls back
      // to its own default when the registry hasn't landed.
      const { defaultModel, models } = useStore.getState();
      const model = defaultModel ?? models[0]?.id ?? "gemini-3.1-flash";
      const session = await createSession(slug, model, projectId);
      useWorkbenchUiStore.getState().setShell(session.id, startIn);
      router.push(sessionUrl(session.id, { view: startIn }));
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create the workspace");
      setBusy(false);
    }
  };

  const StartCard = ({
    id,
    icon: Icon,
    label,
    hint,
  }: {
    id: ViewMode;
    icon: typeof MessageSquare;
    label: string;
    hint: string;
  }) => {
    const on = startIn === id;
    return (
      <button
        type="button"
        onClick={() => setStartIn(id)}
        className={cn(
          "flex-1 flex items-center gap-2.5 h-[52px] px-3 rounded-md border text-left transition-colors",
          on ? "border-primary/60 bg-primary/10" : "border-border bg-surface-2 hover:bg-surface-3"
        )}
      >
        <Icon className={cn("h-4 w-4 shrink-0", on ? "text-primary" : "text-muted-foreground")} />
        <div className="min-w-0">
          <div className={cn("text-[12.5px] font-medium", on ? "text-foreground" : "text-foreground/85")}>
            {label}
          </div>
          <div className="text-[10px] text-muted-foreground truncate">{hint}</div>
        </div>
        {on && <Check className="h-3.5 w-3.5 text-primary ml-auto shrink-0" />}
      </button>
    );
  };

  return (
    <div
      className="fixed inset-0 z-[120] grid place-items-center p-6 bg-black/55"
      onMouseDown={onClose}
      role="dialog"
      aria-label="New session"
    >
      <div
        className="w-full max-w-[420px] rounded-lg border border-border bg-surface-1 shadow-lg animate-in fade-in-0 slide-in-from-bottom-2 duration-200"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center px-5 h-[52px] border-b border-border">
          <span className="text-sm font-semibold">New session</span>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="ml-auto h-7 w-7 grid place-items-center rounded-md hover:bg-surface-2 text-muted-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div className="space-y-1.5">
            <input
              ref={inputRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="Workspace name — e.g. sync_fifo"
              className="w-full h-10 px-3 rounded-md border border-border bg-surface-2 text-sm outline-none focus:border-primary/50 placeholder:text-muted-foreground/50"
            />
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70 font-mono pl-0.5">
              <Folder className="h-3 w-3" /> workspace/<span className="text-foreground/70">{slug}</span>/
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-muted-foreground">Start in</label>
            <div className="flex gap-2">
              <StartCard id="agent" icon={MessageSquare} label="Chat" hint="Agent-led" />
              <StartCard id="ide" icon={Columns2} label="IDE" hint="Editor + tools" />
            </div>
          </div>

          {!showGroup ? (
            <button
              type="button"
              onClick={() => setShowGroup(true)}
              className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <Plus className="h-3 w-3" /> Add to a group{" "}
              <span className="text-muted-foreground/50">(optional)</span>
            </button>
          ) : (
            <div className="space-y-1.5">
              <label className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                <Layers className="h-3 w-3" /> Group{" "}
                <span className="text-muted-foreground/50 font-normal">— a tag, not a folder</span>
              </label>
              <input
                value={group}
                onChange={(e) => setGroup(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="asu_hackathon"
                list="launcher-groups"
                className="w-full h-9 px-3 rounded-md border border-border bg-surface-2 text-sm outline-none focus:border-primary/50 placeholder:text-muted-foreground/50 font-mono"
              />
              <datalist id="launcher-groups">
                {projects.map((p) => (
                  <option key={p.id} value={p.name} />
                ))}
              </datalist>
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t border-border">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={busy}>
            Create session <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
