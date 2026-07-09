"use client";

import { useEffect, useRef, useState } from "react";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { ThreadSwitcher } from "./ThreadSwitcher";
import { CHAT_COMPACT_MAX_W, ChatDensityProvider } from "./density";
import { useStore } from "@/lib/store";
import { cn, formatTokens, formatCost } from "@/lib/utils";
import { Cpu, Zap, Coins, Hash, AlertCircle, X, KeyRound, Loader2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

const API_KEY_NOTICE_DISMISSED = "sc-apikey-notice-dismissed";

// WS error codes (from the Slice-1 resolver) that mean "this model needs a key
// you can add" — we turn these into an actionable CTA, not a dead error.
const KEY_ERROR_CODES = new Set(["no_key", "hosted_tier_exhausted"]);

export function ChatArea({
  tailSlot,
  footerSlot,
  hideHeader = false,
}: {
  /** Rendered between the messages and the composer — the agent shell injects
   * its inline manual-action cards here (S5-2); the IDE rail passes nothing. */
  tailSlot?: React.ReactNode;
  /** Rendered under the composer — the agent shell's context strip (manifest
   * facts + session totals, Wave 8); the IDE rail passes nothing. */
  footerSlot?: React.ReactNode;
  /** Wave 8: the agent shell owns session/thread chrome in ITS header, so it
   * hides this one. Error banners below always render — they are chat state,
   * not chrome. */
  hideHeader?: boolean;
}) {
  const { currentSession, chatError, chatErrorCode, agentRuntime, activeThreadId, codexSetup, isStreaming } = useStore();
  // The API-key note competes with toasts as a second notification channel, so
  // make its dismissal sticky (localStorage) — once waved off it stays gone.
  const [apiNoticeDismissed, setApiNoticeDismissed] = useState(false);
  useEffect(() => {
    try {
      setApiNoticeDismissed(localStorage.getItem(API_KEY_NOTICE_DISMISSED) === "1");
    } catch {
      /* ignore */
    }
  }, []);

  // TTFT 3B: pre-warm the Codex worker the moment a Codex thread is on screen,
  // so the cold start overlaps the user's read-and-type time instead of
  // blocking their first message. The action no-ops (and clears the chip) for
  // native threads; stale watches are superseded internally on every change.
  useEffect(() => {
    void useStore.getState().prewarmAgentRuntime();
  }, [agentRuntime, activeThreadId, currentSession?.id]);

  // Container-driven density: the same ChatArea is a ~350px IDE rail and the
  // centered agent conversation. Measure OUR width (not the viewport) and
  // flip one compact flag; typography follows via [data-density] in
  // globals.css, layout via the ChatDensityProvider context.
  const rootRef = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const el = rootRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      if (w > 0) setCompact(w < CHAT_COMPACT_MAX_W);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // The "Ready" confirmation is transient chrome — fade it out after a beat.
  // (Hiding the chip asserts nothing; a dead worker re-shows "Setting up" on
  // the next open/prewarm — honest state either way.)
  const [readyChipVisible, setReadyChipVisible] = useState(true);
  useEffect(() => {
    if (codexSetup?.state !== "ready") {
      setReadyChipVisible(true);
      return;
    }
    const t = setTimeout(() => setReadyChipVisible(false), 2500);
    return () => clearTimeout(t);
  }, [codexSetup?.state, codexSetup?.threadId]);

  return (
    // data-runtime scopes the Codex theme accent (see globals.css): all
    // text-primary / ring-primary inside recolor to violet without touching
    // component classes — same shared components, a different paint.
    // data-density scopes the container-width type scale the same way.
    <ChatDensityProvider value={compact}>
    <div
      ref={rootRef}
      className="flex flex-col h-full bg-background"
      data-runtime={agentRuntime}
      data-density={compact ? "compact" : "comfortable"}
    >
      {/* Header */}
      {!hideHeader && (
      <div className={cn(
        "flex items-center justify-between border-b border-border bg-surface-0",
        compact ? "min-h-12 px-3 py-1.5" : "h-14 px-4"
      )}>
        <div className="flex min-w-0 items-center gap-3">
          {currentSession ? (
            <>
              {/* The badge is decoration — in a narrow rail its 32px belong
                  to the session name and thread switcher. */}
              {!compact && (
                <div className="w-8 h-8 shrink-0 rounded-lg bg-primary/10 flex items-center justify-center">
                  {currentSession.model_name?.includes("pro") ? (
                    <Cpu className="h-4 w-4 text-primary" />
                  ) : (
                    <Zap className="h-4 w-4 text-yellow-500" />
                  )}
                </div>
              )}
              <div className="min-w-0">
                <h1 className="font-semibold text-sm truncate">{currentSession.name ?? currentSession.id}</h1>
                {/* Chat switcher: many conversations per workspace (shared files). */}
                <ThreadSwitcher />
              </div>
            </>
          ) : (
            <>
              <div className="w-8 h-8 shrink-0 rounded-lg bg-surface-2 flex items-center justify-center">
                <Cpu className="h-4 w-4 text-muted-foreground" />
              </div>
              <div>
                <h1 className="font-semibold text-sm">SiliconCrew Architect</h1>
                <p className="text-xs text-muted-foreground">AI-powered RTL design</p>
              </div>
            </>
          )}
        </div>

        {/* Token/cost totals need room to breathe — in the rail they'd crowd
            the session name out (the numbers stay one click away in the
            launcher / agent context strip). */}
        {!compact && currentSession && (currentSession.total_tokens > 0 || currentSession.total_cost > 0) && (
          <div className="flex shrink-0 items-center gap-4 pl-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Hash className="h-3.5 w-3.5" />
              <span>{formatTokens(currentSession.total_tokens)}</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Coins className="h-3.5 w-3.5" />
              <span>{formatCost(currentSession.total_cost)}</span>
            </div>
          </div>
        )}
      </div>
      )}

      {/* Error banner. A missing-API-key is a config note, not a failure — the
          lint/sim/synth tools work without the LLM — so render it calmly rather
          than as an alarming red banner. */}
      {/* The model needs a key the user can add → actionable CTA that opens the
          API Keys settings, instead of a dead red error. */}
      {chatError && chatErrorCode && KEY_ERROR_CODES.has(chatErrorCode) && (
        <div
          className="flex items-center justify-between gap-3 bg-info/10 border-b border-info/20 px-4 py-2.5"
          role="region"
          aria-label="Missing API key"
          data-testid="chat-no-key-cta"
        >
          <div className="flex items-center gap-2 min-w-0">
            <KeyRound className="h-4 w-4 text-info shrink-0" />
            <p className="text-xs text-info truncate">{chatError}</p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {agentRuntime === "codex" ? (
              // Codex runs on a ChatGPT account (or its own quota) — the remedy
              // is the "Connect ChatGPT" control, not adding an LLM API key.
              <span className="text-xs text-info whitespace-nowrap">Use “Connect ChatGPT” above, or check your plan’s quota.</span>
            ) : (
              <Button
                size="sm"
                className="h-7 gap-1.5 text-xs"
                data-testid="chat-add-key"
                onClick={() => {
                  useStore.setState({ chatError: null, chatErrorCode: null });
                  useStore.getState().setSettingsOpen(true);
                }}
              >
                <KeyRound className="h-3.5 w-3.5" /> Add an API key
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 hover:bg-info/20"
              aria-label="Dismiss notice"
              onClick={() => useStore.setState({ chatError: null, chatErrorCode: null })}
            >
              <X className="h-3.5 w-3.5 text-info" />
            </Button>
          </div>
        </div>
      )}

      {chatError && !(chatErrorCode && KEY_ERROR_CODES.has(chatErrorCode)) && (() => {
        const isConfig = /api key|api_key/i.test(chatError);
        // Stay dismissed across the session once the user has waved off the note.
        if (isConfig && apiNoticeDismissed) return null;
        return (
          <div
            className={
              isConfig
                ? "flex items-center justify-between gap-3 bg-info/10 border-b border-info/20 px-4 py-2"
                : "flex items-center justify-between gap-3 bg-destructive/10 border-b border-destructive/20 px-4 py-2.5"
            }
          >
            <div className="flex items-center gap-2">
              <AlertCircle className={isConfig ? "h-4 w-4 text-info shrink-0" : "h-4 w-4 text-destructive shrink-0"} />
              <p className={isConfig ? "text-xs text-info" : "text-sm text-destructive"}>
                {isConfig ? "AI assistant needs ANTHROPIC_API_KEY — lint/sim/synth work without it." : chatError}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className={isConfig ? "h-6 w-6 shrink-0 hover:bg-info/20" : "h-6 w-6 shrink-0 hover:bg-destructive/20"}
              aria-label="Dismiss notice"
              onClick={() => {
                if (isConfig) {
                  setApiNoticeDismissed(true);
                  try {
                    localStorage.setItem(API_KEY_NOTICE_DISMISSED, "1");
                  } catch {
                    /* ignore */
                  }
                }
                useStore.setState({ chatError: null });
              }}
            >
              <X className={isConfig ? "h-3.5 w-3.5 text-info" : "h-3.5 w-3.5 text-destructive"} />
            </Button>
          </div>
        );
      })()}

      {/* Messages */}
      <MessageList />

      {tailSlot}

      {/* TTFT 3C: honest Codex worker setup state. "Setting up" while the
          pre-warmed worker spawns (a send during this window is queued
          server-side and fires the moment it's ready); a brief "Ready"
          confirmation; nothing at all when there's nothing truthful to show. */}
      {codexSetup && (codexSetup.state === "starting" || readyChipVisible) && (
        <div
          data-testid="codex-setup-state"
          data-state={codexSetup.state}
          className="flex items-center gap-2 px-4 py-1.5 text-xs text-muted-foreground border-t border-border bg-surface-0"
          role="status"
        >
          {codexSetup.state === "starting" ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin text-primary" />
              <span>{isStreaming ? "Starting your first turn — Codex is setting up…" : "Setting up Codex…"}</span>
            </>
          ) : (
            <>
              <Check className="h-3 w-3 text-success" />
              <span>Codex ready</span>
            </>
          )}
        </div>
      )}

      {/* Input */}
      <ChatInput />

      {footerSlot}
    </div>
    </ChatDensityProvider>
  );
}
