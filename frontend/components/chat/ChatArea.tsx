"use client";

import { useEffect, useState } from "react";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { ThreadSwitcher } from "./ThreadSwitcher";
import { useStore } from "@/lib/store";
import { formatTokens, formatCost } from "@/lib/utils";
import { Cpu, Zap, Coins, Hash, AlertCircle, X, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";

const API_KEY_NOTICE_DISMISSED = "sc-apikey-notice-dismissed";

// WS error codes (from the Slice-1 resolver) that mean "this model needs a key
// you can add" — we turn these into an actionable CTA, not a dead error.
const KEY_ERROR_CODES = new Set(["no_key", "hosted_tier_exhausted"]);

export function ChatArea() {
  const { currentSession, chatError, chatErrorCode } = useStore();
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

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-border bg-surface-0">
        <div className="flex items-center gap-3">
          {currentSession ? (
            <>
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                {currentSession.model_name?.includes("pro") ? (
                  <Cpu className="h-4 w-4 text-primary" />
                ) : (
                  <Zap className="h-4 w-4 text-yellow-500" />
                )}
              </div>
              <div className="min-w-0">
                <h1 className="font-semibold text-sm truncate">{currentSession.name ?? currentSession.id}</h1>
                {/* Chat switcher: many conversations per workspace (shared files). */}
                <ThreadSwitcher />
              </div>
            </>
          ) : (
            <>
              <div className="w-8 h-8 rounded-lg bg-surface-2 flex items-center justify-center">
                <Cpu className="h-4 w-4 text-muted-foreground" />
              </div>
              <div>
                <h1 className="font-semibold text-sm">SiliconCrew Architect</h1>
                <p className="text-xs text-muted-foreground">AI-powered RTL design</p>
              </div>
            </>
          )}
        </div>

        {currentSession && (currentSession.total_tokens > 0 || currentSession.total_cost > 0) && (
          <div className="flex items-center gap-4">
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

      {/* Input */}
      <ChatInput />
    </div>
  );
}
