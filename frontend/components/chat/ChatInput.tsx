"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Square, X, Clock, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ModelPicker } from "./ModelPicker";
import { useStore, MAX_QUEUED_MESSAGES } from "@/lib/store";
import { cn } from "@/lib/utils";

export function ChatInput() {
  const { currentSession, isStreaming, stopPending, sendMessage, stopStreaming, queuedMessages, removeQueuedMessage } = useStore();
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const queueFull = queuedMessages.length >= MAX_QUEUED_MESSAGES;

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
    }
  }, [input]);

  const handleSubmit = () => {
    if (!input.trim() || !currentSession) return;
    // While a response is streaming, sendMessage queues the follow-up (shown
    // as a removable chip below) and dispatches it when the turn completes.
    // At the queue cap, keep the draft in the composer instead of dropping it.
    if (isStreaming && queueFull) return;
    sendMessage(input);
    setInput("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isDisabled = !currentSession || !input.trim();

  return (
    <div className="border-t border-border bg-surface-0 px-4 py-4">
      <div className="max-w-3xl mx-auto">
        <div className="relative">
          {queuedMessages.length > 0 && (
            <div className="flex flex-col gap-1.5 mb-2" data-testid="queued-messages">
              {queuedMessages.map((q) => (
                <div
                  key={q.id}
                  className="flex items-center gap-2 rounded-lg border border-border bg-surface-1 px-3 py-1.5 text-xs text-muted-foreground"
                >
                  <Clock className="h-3 w-3 shrink-0 opacity-60" />
                  <span className="truncate flex-1" title={q.content}>{q.content}</span>
                  <span className="shrink-0 opacity-50">queued</span>
                  <button
                    aria-label="Remove queued message"
                    className="shrink-0 rounded p-0.5 hover:bg-surface-2 hover:text-foreground transition-colors"
                    onClick={() => removeQueuedMessage(q.id)}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="relative rounded-xl border border-border bg-surface-1 shadow-sm focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary/50 transition-all">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                !currentSession
                  ? "Select or create a session to start"
                  : isStreaming
                    ? "Ask a follow-up — it'll be sent when this response finishes…"
                    : "Describe your RTL design requirements..."
              }
              disabled={!currentSession}
              className={cn(
                "w-full resize-none bg-transparent px-4 py-3.5 pr-28 text-sm",
                "placeholder:text-muted-foreground/60",
                "focus:outline-none",
                "disabled:cursor-not-allowed disabled:opacity-50",
                "min-h-[56px] max-h-[200px]"
              )}
              rows={1}
            />
            <div className="absolute right-2 bottom-2 flex items-center gap-1.5">
              {isStreaming && input.trim() && (
                <Button
                  variant="secondary"
                  size="sm"
                  className="h-9 px-3 gap-2 font-medium"
                  onClick={handleSubmit}
                  disabled={queueFull}
                  title={
                    queueFull
                      ? `Queue is full (max ${MAX_QUEUED_MESSAGES}) — remove a queued message first`
                      : "Queue this message — it sends when the current response finishes"
                  }
                >
                  <Send className="h-3.5 w-3.5" />
                  Queue
                </Button>
              )}
              {isStreaming ? (
                <Button
                  variant="destructive"
                  size="sm"
                  className="h-9 px-3 gap-2 font-medium"
                  onClick={stopStreaming}
                  disabled={stopPending}
                >
                  {stopPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Stopping…
                    </>
                  ) : (
                    <>
                      <Square className="h-3.5 w-3.5" />
                      Stop
                    </>
                  )}
                </Button>
              ) : (
                <Button
                  size="sm"
                  className={cn(
                    "h-9 px-3 gap-2 font-medium transition-all",
                    isDisabled
                      ? "bg-surface-2 text-muted-foreground hover:bg-surface-3"
                      : "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
                  )}
                  onClick={handleSubmit}
                  disabled={isDisabled}
                >
                  <Send className="h-3.5 w-3.5" />
                  Send
                </Button>
              )}
            </div>
          </div>

          {/* Footer: model picker (bottom-left) + keyboard hint. */}
          <div className="flex items-center justify-between mt-2.5 px-1">
            <ModelPicker />
            <span className="text-xs text-muted-foreground/50">
              <kbd className="px-1.5 py-0.5 rounded bg-surface-2 border border-border text-[10px] font-mono">Shift</kbd>
              {" + "}
              <kbd className="px-1.5 py-0.5 rounded bg-surface-2 border border-border text-[10px] font-mono">Enter</kbd>
              {" for new line"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
