"use client";

import { useEffect, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { statusDotClass } from "./runStatus";
import { Button } from "@/components/ui/button";
import { ChevronUp, ChevronDown, Terminal, Pencil, Play, Copy, Check } from "lucide-react";
import type { ConsoleChannel, ConsoleEntry } from "@/types";

const TABS: { id: ConsoleChannel; label: string }[] = [
  { id: "lint", label: "Lint" },
  { id: "sim", label: "Sim" },
  { id: "synth", label: "Synth" },
];

/**
 * Console = transparency. Every action shows the exact command the tool ran
 * (we never shell raw EDA from the UI). The expanded body is a real, scrollable,
 * copyable per-run log: the command block + the full output/detail (failure line
 * + stdout/stderr tails). The "edit & re-run command" escape hatch is opt-in
 * (collapsed by default), per the brief — re-running goes back through the same
 * action endpoint, never executing arbitrary shell text.
 */
export function Console() {
  const {
    consoleEntries,
    activeConsole,
    setActiveConsole,
    consoleAttention,
    runLint,
    runSim,
    runSynth,
    setArtifactTab,
  } = useStore();
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pulse, setPulse] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  const entries = consoleEntries.filter((e) => e.channel === activeConsole);
  const last = entries[entries.length - 1];

  const rerun = () => {
    if (activeConsole === "lint") void runLint();
    else if (activeConsole === "sim") void runSim();
    else void runSynth();
  };

  const lastByChannel = (ch: ConsoleChannel): ConsoleEntry | undefined => {
    for (let i = consoleEntries.length - 1; i >= 0; i--) if (consoleEntries[i].channel === ch) return consoleEntries[i];
    return undefined;
  };

  // Draw attention to a fresh result (notably Lint, which has no center
  // artifact surface): focus its channel, auto-expand, and pulse once.
  const lastTick = useRef(0);
  useEffect(() => {
    if (!consoleAttention || consoleAttention.tick === lastTick.current) return;
    lastTick.current = consoleAttention.tick;
    setActiveConsole(consoleAttention.channel);
    setExpanded(true);
    setPulse(true);
    const t = setTimeout(() => setPulse(false), 1100);
    return () => clearTimeout(t);
  }, [consoleAttention, setActiveConsole]);

  // Keep the log pinned to the freshest output when expanded.
  useEffect(() => {
    if (expanded && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [expanded, last?.ts, activeConsole]);

  // Reset transient affordances when the viewed channel/entry changes.
  useEffect(() => {
    setCopied(false);
    setEditing(false);
  }, [activeConsole, last?.ts]);

  const copyLog = () => {
    if (!last) return;
    const text = [last.command ? `$ ${last.command}` : "", last.detail ?? "", last.detail ? "" : last.summary]
      .filter(Boolean)
      .join("\n");
    navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      data-testid="console"
      className={cn(
        "flex flex-col border-t border-border bg-surface-1 transition-[height] duration-base ease-swift",
        expanded ? "h-64" : "h-auto",
        pulse && "animate-pulse-subtle"
      )}
    >
      <div className="flex items-center gap-1 px-2 h-9 border-b border-border">
        <Terminal className="h-3.5 w-3.5 text-muted-foreground mr-1" />
        {TABS.map((t) => {
          const le = lastByChannel(t.id);
          const active = activeConsole === t.id;
          const dotStatus = le?.status === "info" ? undefined : le?.status;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setActiveConsole(t.id)}
              className={cn(
                "flex items-center gap-1.5 text-xs px-2 py-1 rounded-md transition-colors duration-fast ease-swift",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "bg-surface-2 text-foreground shadow-e1 font-medium"
                  : "text-muted-foreground hover:bg-surface-2/60 hover:text-foreground"
              )}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDotClass(dotStatus))} />
              {t.label}
              {le?.runId && (
                <span
                  className={cn(
                    "font-mono text-[10px] rounded px-1 py-px",
                    active ? "bg-surface-0 text-muted-foreground" : "text-muted-foreground"
                  )}
                >
                  {le.runId}
                </span>
              )}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label={expanded ? "Collapse console" : "Expand console"}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Peek line (collapsed) — latest status one-liner + deep-link.
          aria-live=polite so a fresh sim/lint/synth result is announced. */}
      {!expanded && (
        <div
          className="px-3 py-2 text-xs flex items-center gap-2 min-h-[2.25rem]"
          role="status"
          aria-live="polite"
        >
          {last ? (
            <>
              <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDotClass(last.status === "info" ? undefined : last.status))} />
              <span className="truncate">{last.summary}</span>
              {activeConsole === "sim" && last.status === "failed" && (
                <button
                  type="button"
                  className="ml-auto text-info hover:underline shrink-0 rounded outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
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

      {/* Expanded body — full, scrollable, copyable log of the latest run */}
      {expanded && (
        <div className="flex flex-col flex-1 min-h-0 animate-fade-in">
          {!last ? (
            <div className="flex-1 overflow-y-auto thin-scrollbar p-3 text-[11px] text-muted-foreground font-mono">
              No {activeConsole} output yet.
            </div>
          ) : (
            <>
              {/* Result header: status + summary, Copy + sim deep-link */}
              <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border text-xs">
                <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusDotClass(last.status === "info" ? undefined : last.status))} />
                <span className="truncate text-foreground">{last.summary}</span>
                {activeConsole === "sim" && last.status === "failed" && (
                  <button
                    type="button"
                    className="text-info hover:underline shrink-0 rounded outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                    onClick={() => setArtifactTab("waveform")}
                  >
                    open waveform →
                  </button>
                )}
                <button
                  type="button"
                  onClick={copyLog}
                  aria-label="Copy log"
                  className={cn(
                    "ml-auto flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md shrink-0",
                    "text-muted-foreground hover:bg-surface-2 hover:text-foreground transition-colors duration-fast",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  )}
                >
                  {copied ? <Check className="h-3 w-3 text-status-pass" /> : <Copy className="h-3 w-3" />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>

              {/* Scrollable log region: command block + full output/detail */}
              <div ref={logRef} className="flex-1 overflow-auto thin-scrollbar p-2 space-y-2 font-mono text-[11px]">
                {last.command && (
                  <pre className="whitespace-pre-wrap break-words text-[10px] leading-relaxed text-info bg-surface-2 rounded px-2 py-1.5">
                    {last.command
                      .split("\n")
                      .map((c) => `$ ${c}`)
                      .join("\n")}
                  </pre>
                )}
                {last.detail ? (
                  <pre className="whitespace-pre-wrap break-words text-[10px] leading-relaxed text-muted-foreground px-1">
                    {last.detail}
                  </pre>
                ) : (
                  !last.command && (
                    <div className="text-[10px] text-muted-foreground px-1">No further output.</div>
                  )
                )}
              </div>

              {/* Opt-in escape hatch */}
              <div className="border-t border-border px-2 py-1.5 text-[10px]">
                {!editing ? (
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors duration-fast rounded outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
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
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-foreground rounded outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                        onClick={() => setEditing(false)}
                      >
                        cancel
                      </button>
                      <span className="text-[9px] text-muted-foreground">
                        re-runs via the tool — the UI never shells raw EDA
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
