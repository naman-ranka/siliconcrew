"use client";

import { useState } from "react";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { statusDotClass } from "./runStatus";
import { Button } from "@/components/ui/button";
import { ChevronUp, ChevronDown, Terminal, Pencil, Play } from "lucide-react";
import type { ConsoleChannel } from "@/types";

const TABS: { id: ConsoleChannel; label: string }[] = [
  { id: "lint", label: "Lint" },
  { id: "sim", label: "Sim" },
  { id: "synth", label: "Synth" },
];

/**
 * Console = transparency. Every action shows the exact command the tool ran
 * (we never shell raw EDA from the UI). The "edit & re-run command" escape
 * hatch is opt-in (collapsed by default), per the brief — re-running goes back
 * through the same action endpoint, never executing arbitrary shell text.
 */
export function Console() {
  const { consoleEntries, activeConsole, setActiveConsole, runLint, runSim, runSynth, setArtifactTab } = useStore();
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);

  const entries = consoleEntries.filter((e) => e.channel === activeConsole);
  const last = entries[entries.length - 1];

  const rerun = () => {
    if (activeConsole === "lint") void runLint();
    else if (activeConsole === "sim") void runSim();
    else void runSynth();
  };

  const lastByChannel = (ch: ConsoleChannel) => {
    for (let i = consoleEntries.length - 1; i >= 0; i--) if (consoleEntries[i].channel === ch) return consoleEntries[i];
    return undefined;
  };

  return (
    <div className={cn("flex flex-col border-t border-border bg-surface-1", expanded ? "h-64" : "h-auto")}>
      <div className="flex items-center gap-1 px-2 h-9 border-b border-border">
        <Terminal className="h-3.5 w-3.5 text-muted-foreground mr-1" />
        {TABS.map((t) => {
          const le = lastByChannel(t.id);
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveConsole(t.id)}
              className={cn(
                "flex items-center gap-1.5 text-xs px-2 py-1 rounded-md",
                activeConsole === t.id ? "bg-surface-2 text-foreground" : "text-muted-foreground hover:bg-surface-2"
              )}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", statusDotClass(le?.status === "info" ? undefined : le?.status))} />
              {t.label}
              {le?.runId && <span className="font-mono text-[10px] text-muted-foreground">· {le.runId}</span>}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setExpanded((v) => !v)}>
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Peek line (always visible) */}
      {!expanded && (
        <div className="px-3 py-2 text-xs flex items-center gap-2 min-h-[2.25rem]">
          {last ? (
            <>
              <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDotClass(last.status === "info" ? undefined : last.status))} />
              <span className="truncate">{last.summary}</span>
              {activeConsole === "sim" && last.status === "failed" && (
                <button
                  type="button"
                  className="ml-auto text-info hover:underline shrink-0"
                  onClick={() => setArtifactTab("waveform")}
                >
                  open waveform →
                </button>
              )}
            </>
          ) : (
            <span className="text-muted-foreground">No {activeConsole} output yet.</span>
          )}
        </div>
      )}

      {/* Expanded body */}
      {expanded && (
        <div className="flex-1 overflow-y-auto thin-scrollbar p-2 space-y-2 font-mono text-[11px]">
          {entries.length === 0 && <div className="text-muted-foreground px-1">No {activeConsole} output yet.</div>}
          {entries.map((e, i) => (
            <div key={i} className="border border-border rounded-md p-2 bg-surface-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={cn("h-1.5 w-1.5 rounded-full", statusDotClass(e.status === "info" ? undefined : e.status))} />
                <span className="text-foreground">{e.summary}</span>
              </div>
              {e.command && (
                <pre className="whitespace-pre-wrap text-[10px] text-info bg-surface-2 rounded px-2 py-1 overflow-x-auto">
                  $ {e.command}
                </pre>
              )}
              {e.detail && (
                <pre className="whitespace-pre-wrap text-[10px] text-muted-foreground mt-1 max-h-40 overflow-y-auto">
                  {e.detail}
                </pre>
              )}
            </div>
          ))}

          {/* Opt-in escape hatch */}
          <div className="pt-1">
            {!editing ? (
              <button
                type="button"
                className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1"
                onClick={() => setEditing(true)}
              >
                <Pencil className="h-3 w-3" /> edit &amp; re-run command
              </button>
            ) : (
              <div className="space-y-1">
                <textarea
                  defaultValue={last?.command ?? ""}
                  rows={2}
                  className="w-full bg-surface-0 border border-border rounded p-1 text-[10px] font-mono"
                />
                <div className="flex items-center gap-2">
                  <Button size="sm" className="h-6 gap-1 text-[10px]" onClick={rerun}>
                    <Play className="h-3 w-3" /> Re-run {activeConsole}
                  </Button>
                  <button type="button" className="text-[10px] text-muted-foreground" onClick={() => setEditing(false)}>
                    cancel
                  </button>
                  <span className="text-[9px] text-muted-foreground">
                    re-runs via the tool — the UI never shells raw EDA
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
