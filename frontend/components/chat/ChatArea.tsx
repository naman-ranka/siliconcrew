"use client";

import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { useStore } from "@/lib/store";
import { formatTokens, formatCost } from "@/lib/utils";

export function ChatArea() {
  const { currentSession, chatError } = useStore();

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-border">
        <div className="flex items-center gap-2">
          <h1 className="font-semibold">
            {currentSession ? currentSession.id : "SiliconCrew Architect"}
          </h1>
        </div>
        {currentSession && (
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>{currentSession.model_name || "gemini-2.5-flash"}</span>
            {currentSession.total_tokens > 0 && (
              <>
                <span>{formatTokens(currentSession.total_tokens)} tokens</span>
                <span>{formatCost(currentSession.total_cost)}</span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Error banner */}
      {chatError && (
        <div className="bg-destructive/10 border-b border-destructive/20 px-4 py-2">
          <p className="text-sm text-destructive">{chatError}</p>
        </div>
      )}

      {/* Messages */}
      <MessageList />

      {/* Input */}
      <ChatInput />
    </div>
  );
}
