"use client";

import { useRouter } from "next/navigation";
import { useStore } from "@/lib/store";
import { openSession, sessionUrl } from "@/lib/nav";
import { ChevronDown, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/** Minimal session switcher for the workbench top bar. */
export function SessionPicker() {
  const { sessions, currentSession, createSession, loadWorkbench } = useStore();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on Escape or click outside (standard popover affordances).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const pick = (id: string) => {
    setOpen(false);
    // Switching sessions ROUTES (S1): the /w page effect drives the store
    // selection from the URL, so refresh/share/back-button all just work.
    openSession(router, id);
  };

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // A sensible default placeholder if the user doesn't type a name.
  const defaultName = () => `workbench-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "")}`;

  const startCreate = () => {
    setCreating(true);
    setNewName("");
    // Focus the field on the next paint so the user can name it right away.
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const submitCreate = async () => {
    const name = newName.trim() || defaultName();
    setOpen(false);
    setCreating(false);
    setNewName("");
    await createSession(name, currentSession?.model_name || "claude-sonnet-4-6");
    await loadWorkbench();
    // Land on the new session's canonical URL (createSession already selected
    // it in the store; the /w effect sees it current and won't re-hydrate).
    const created = useStore.getState().currentSession;
    if (created) router.push(sessionUrl(created.id));
  };

  // Reset the inline create UI whenever the popover closes.
  useEffect(() => {
    if (!open) {
      setCreating(false);
      setNewName("");
    }
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className="flex items-center gap-2 text-sm rounded-md px-2 py-1 hover:bg-surface-2 outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Switch session"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-medium truncate max-w-[200px]">
          {currentSession ? currentSession.name ?? currentSession.id : "Select session"}
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-64 max-h-80 overflow-y-auto rounded-md border border-border bg-popover shadow-e2 p-1 animate-in fade-in-0 zoom-in-95 slide-in-from-top-1 motion-reduce:animate-none">
          {creating ? (
            <div className="flex items-center gap-1 px-1 py-1">
              <input
                ref={inputRef}
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void submitCreate();
                  if (e.key === "Escape") {
                    e.stopPropagation();
                    setCreating(false);
                  }
                }}
                placeholder={defaultName()}
                aria-label="New session name"
                className="flex-1 min-w-0 bg-surface-0 border border-border rounded px-2 py-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
              />
              <button
                type="button"
                onClick={() => void submitCreate()}
                aria-label="Create session"
                className="shrink-0 text-xs px-2 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90 outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
              >
                Create
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={startCreate}
              className="w-full flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-surface-2 text-primary outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              <Plus className="h-3.5 w-3.5" /> New session
            </button>
          )}
          <div className="h-px bg-border my-1" />
          {sessions.length === 0 && <div className="px-2 py-2 text-xs text-muted-foreground">No sessions yet</div>}
          {sessions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => void pick(s.id)}
              className={cn(
                "w-full text-left text-xs px-2 py-1.5 rounded hover:bg-surface-2 truncate",
                currentSession?.id === s.id && "bg-surface-2 text-primary"
              )}
            >
              {s.name ?? s.id}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
