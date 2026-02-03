"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Square, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function ChatInput() {
  const { currentSession, isStreaming, sendMessage, stopStreaming } = useStore();
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
    }
  }, [input]);

  const handleSubmit = () => {
    if (!input.trim() || isStreaming || !currentSession) return;
    sendMessage(input.trim());
    setInput("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isDisabled = !currentSession || (!input.trim() && !isStreaming);

  return (
    <div className="border-t border-border bg-surface-0 px-4 py-4">
      <div className="max-w-3xl mx-auto">
        <div className="relative">
          <div className="relative rounded-xl border border-border bg-surface-1 shadow-sm focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary/50 transition-all">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                currentSession
                  ? "Describe your RTL design requirements..."
                  : "Select or create a session to start"
              }
              disabled={!currentSession || isStreaming}
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
              {isStreaming ? (
                <Button
                  variant="destructive"
                  size="sm"
                  className="h-9 px-3 gap-2 font-medium"
                  onClick={stopStreaming}
                >
                  <Square className="h-3.5 w-3.5" />
                  Stop
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

          {/* Footer hints */}
          <div className="flex items-center justify-between mt-2.5 px-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground/70">
              <Sparkles className="h-3 w-3" />
              <span>
                {currentSession
                  ? `Using ${currentSession.model_name || "gemini-2.5-flash"}`
                  : "AI-powered RTL design assistant"
                }
              </span>
            </div>
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
