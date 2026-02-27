"use client";

import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { useStore } from "@/lib/store";
import { formatTokens, formatCost } from "@/lib/utils";
import { Cpu, Zap, Coins, Hash, AlertCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ChatArea() {
  const { currentSession, chatError } = useStore();

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
              <div>
                <h1 className="font-semibold text-sm">{currentSession.name ?? currentSession.id}</h1>
                <p className="text-xs text-muted-foreground">
                  {currentSession.model_name || "gemini-3-flash-preview"}
                </p>
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

      {/* Error banner */}
      {chatError && (
        <div className="flex items-center justify-between gap-3 bg-destructive/10 border-b border-destructive/20 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
            <p className="text-sm text-destructive">{chatError}</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 shrink-0 hover:bg-destructive/20"
            onClick={() => useStore.setState({ chatError: null })}
          >
            <X className="h-3.5 w-3.5 text-destructive" />
          </Button>
        </div>
      )}

      {/* Messages */}
      <MessageList />

      {/* Input */}
      <ChatInput />
    </div>
  );
}
