"use client";

import { useStore } from "@/lib/store";
import { ChevronDown, Plus } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

/** Minimal session switcher for the workbench top bar. */
export function SessionPicker() {
  const { sessions, currentSession, selectSession, createSession, loadWorkbench } = useStore();
  const [open, setOpen] = useState(false);

  const pick = async (id: string) => {
    setOpen(false);
    const s = sessions.find((x) => x.id === id) ?? null;
    await selectSession(s);
    await loadWorkbench();
  };

  const create = async () => {
    setOpen(false);
    const name = `workbench-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "")}`;
    await createSession(name, currentSession?.model_name || "claude-sonnet-4-6");
    await loadWorkbench();
  };

  return (
    <div className="relative">
      <button
        type="button"
        className="flex items-center gap-2 text-sm rounded-md px-2 py-1 hover:bg-surface-2"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-medium truncate max-w-[200px]">
          {currentSession ? currentSession.name ?? currentSession.id : "Select session"}
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-64 max-h-80 overflow-y-auto rounded-md border border-border bg-popover shadow-lg p-1">
          <button
            type="button"
            onClick={create}
            className="w-full flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-surface-2 text-primary"
          >
            <Plus className="h-3.5 w-3.5" /> New session
          </button>
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
