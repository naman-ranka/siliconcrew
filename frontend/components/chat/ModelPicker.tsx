"use client";

import { useStore } from "@/lib/store";
import { ChevronDown, Check, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { ModelInfo } from "@/types";

const PROVIDER_ORDER: ModelInfo["provider"][] = ["anthropic", "openai", "gemini"];
const PROVIDER_LABEL: Record<ModelInfo["provider"], string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Google",
};
// Provider dots are kept clearly distinct from the orange brand (--primary ≈
// hsl(14 …), i.e. ~14° hue) and the green/red status colors. Anthropic must NOT
// use amber — it lands in the brand-orange band and collides with the selected
// row's orange check. Violet / teal / blue sit well outside both bands.
const PROVIDER_DOT: Record<ModelInfo["provider"], string> = {
  anthropic: "bg-violet-500",
  openai: "bg-teal-500",
  gemini: "bg-blue-500",
};

/**
 * Model picker for the NATIVE (LangChain) agent, at the composer's
 * bottom-left. The chosen model lives on the ACTIVE chat thread (so each chat
 * can use a different model); the WebSocket reads it on the next message.
 * Grouped by provider; unavailable models are greyed with "needs key" so we
 * never offer a model that would 500. The Codex agent has its OWN picker over
 * a separately curated registry — see CodexModelPicker.
 */
export function ModelPicker() {
  const {
    currentSession,
    threads,
    activeThreadId,
    models,
    defaultModel,
    loadModels,
    setActiveThreadModel,
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

  const activeThread = threads.find((t) => t.id === activeThreadId);
  // Fall back to the registry's declared default (no hardcoded model id here —
  // the backend catalog is the single source of truth).
  const currentId = activeThread?.model || currentSession?.model_name || defaultModel || "";
  const currentLabel = models.find((m) => m.id === currentId)?.label || currentId;
  const currentProvider = models.find((m) => m.id === currentId)?.provider;

  const grouped = useMemo(() => {
    const by: Record<string, ModelInfo[]> = {};
    for (const m of models) (by[m.provider] ??= []).push(m);
    return by;
  }, [models]);

  const pick = async (m: ModelInfo) => {
    if (!m.available) return;
    setOpen(false);
    await setActiveThreadModel(m.id);
  };

  if (!currentSession) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground/70">
        <Sparkles className="h-3 w-3" />
        <span>AI-powered RTL design assistant</span>
      </div>
    );
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className="flex items-center gap-1.5 text-xs rounded-md px-1.5 py-1 text-muted-foreground hover:bg-surface-2 hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Model: ${currentLabel}. Change model`}
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={cn("h-2 w-2 rounded-full", currentProvider ? PROVIDER_DOT[currentProvider] : "bg-muted-foreground")}
          aria-hidden
        />
        <span className="font-medium text-foreground">{currentLabel}</span>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Select model"
          className="absolute bottom-full mb-1 left-0 z-50 w-80 max-h-[26rem] overflow-y-auto rounded-md border border-border bg-popover shadow-e2 p-1 animate-in fade-in-0 zoom-in-95 slide-in-from-bottom-1 motion-reduce:animate-none"
        >
          {models.length === 0 && (
            <div className="px-3 py-3 text-xs text-muted-foreground">No models available.</div>
          )}
          {PROVIDER_ORDER.filter((p) => grouped[p]?.length).map((provider) => (
            <div key={provider} className="mb-1 last:mb-0">
              <div className="flex items-center gap-1.5 px-2 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/80">
                <span className={cn("h-1.5 w-1.5 rounded-full", PROVIDER_DOT[provider])} aria-hidden />
                {PROVIDER_LABEL[provider]}
              </div>
              {grouped[provider].map((m) => {
                const isCurrent = m.id === currentId;
                return (
                  <button
                    key={m.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={isCurrent}
                    // The active model is never greyed/disabled, even with no key
                    // — it's the one in use, so it must read as selected, not
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
                        {m.free && (
                          <span className="text-[10px] rounded border border-primary/40 bg-primary/10 px-1 py-0.5 text-primary shrink-0">
                            Free
                          </span>
                        )}
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
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
