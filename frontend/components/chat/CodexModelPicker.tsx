"use client";

import { useStore } from "@/lib/store";
import { ChevronDown, Check, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { ModelInfo } from "@/types";

/**
 * Model picker for the CODEX agent — a separate component over a separately
 * curated registry (`codexModels`, from the backend's CODEX_CATALOG), NOT a
 * provider filter of the native picker's list. The Codex runtime runs on its
 * own model set, so the two pickers are maintained independently and can
 * diverge freely.
 *
 * Availability: the registry's `available` flag knows BYOK/env OpenAI keys
 * only. A connected ChatGPT account bypasses key resolution entirely
 * (codex_runtime.py: account auth wins over BYOK), so a connected account
 * makes every Codex model selectable here.
 */
export function CodexModelPicker() {
  const {
    currentSession,
    threads,
    activeThreadId,
    codexModels,
    codexDefaultModel,
    loadModels,
    setActiveThreadModel,
    codexAccountConnected,
  } = useStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void loadModels();
  }, [loadModels]);

  useEffect(() => {
    if (!open) return;
    void loadModels();
    // Consume the Esc (see ThreadSwitcher) — handler only exists while open.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
      }
    };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open, loadModels]);

  const visibleModels = useMemo(
    () =>
      codexAccountConnected
        ? codexModels.map((m) => ({ ...m, available: true }))
        : codexModels,
    [codexModels, codexAccountConnected]
  );

  const activeThread = threads.find((t) => t.id === activeThreadId);
  const currentId = activeThread?.model || codexDefaultModel || "";
  const currentLabel = visibleModels.find((m) => m.id === currentId)?.label || currentId || "Codex";

  const pick = async (m: ModelInfo) => {
    if (!m.available) return;
    setOpen(false);
    await setActiveThreadModel(m.id);
  };

  if (!currentSession) return null;

  return (
    <div className="relative" ref={ref} data-testid="codex-model-picker">
      <button
        type="button"
        className="flex items-center gap-1.5 text-xs rounded-md px-1.5 py-1 text-muted-foreground hover:bg-surface-2 hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Model: ${currentLabel}. Change model`}
        onClick={() => setOpen((v) => !v)}
      >
        {/* text-primary reads violet inside data-runtime="codex" */}
        <Sparkles className="h-3 w-3 text-primary" aria-hidden />
        <span className="font-medium text-foreground">{currentLabel}</span>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Select Codex model"
          className="absolute bottom-full mb-1 left-0 z-50 w-80 max-h-[26rem] overflow-y-auto rounded-md border border-border bg-popover shadow-e2 p-1 animate-in fade-in-0 zoom-in-95 slide-in-from-bottom-1 motion-reduce:animate-none"
        >
          <div className="flex items-center gap-1.5 px-2 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/80">
            <Sparkles className="h-3 w-3 text-primary" aria-hidden />
            Codex
          </div>
          {visibleModels.length === 0 && (
            <div className="px-3 py-3 text-xs text-muted-foreground">No Codex models available.</div>
          )}
          {visibleModels.map((m) => {
            const isCurrent = m.id === currentId;
            return (
              <button
                key={m.id}
                type="button"
                role="menuitemradio"
                aria-checked={isCurrent}
                // The active model is never greyed/disabled, even with no key —
                // it's the one in use, so it must read as selected, not
                // unavailable.
                aria-disabled={!m.available && !isCurrent}
                disabled={!m.available && !isCurrent}
                onClick={() => void pick(m)}
                className={cn(
                  "w-full text-left rounded px-2 py-1.5 flex items-start gap-2 outline-none",
                  "focus-visible:ring-2 focus-visible:ring-primary/60",
                  m.available || isCurrent ? "hover:bg-surface-2 cursor-pointer" : "opacity-50 cursor-not-allowed",
                  isCurrent && "bg-surface-2"
                )}
              >
                <Check
                  className={cn("h-3.5 w-3.5 mt-0.5 shrink-0", isCurrent ? "text-primary" : "text-transparent")}
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="text-xs font-medium text-foreground truncate">{m.label}</span>
                    {!m.available && !isCurrent && (
                      <span className="text-[10px] rounded border border-border px-1 py-0.5 text-muted-foreground shrink-0">
                        needs key
                      </span>
                    )}
                  </span>
                  {m.hint && <span className="block text-[11px] text-muted-foreground">{m.hint}</span>}
                  {m.pricing && (
                    <span className="block text-[10px] text-muted-foreground/70">
                      ${m.pricing.input}/${m.pricing.output} per Mtok (in/out)
                    </span>
                  )}
                </span>
              </button>
            );
          })}
          <div className="mt-1 border-t border-border px-2 py-1.5 text-[10px] leading-snug text-muted-foreground/70">
            {codexAccountConnected
              ? "Using your ChatGPT account."
              : "Connect ChatGPT or add an OpenAI API key to use Codex."}
          </div>
        </div>
      )}
    </div>
  );
}
