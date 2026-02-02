"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Square, Paperclip } from "lucide-react";
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
    <div className="border-t border-border bg-background p-4">
      <div className="max-w-4xl mx-auto">
        <div className="relative flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                currentSession
                  ? "Design an 8-bit counter with async reset..."
                  : "Select or create a session to start"
              }
              disabled={!currentSession || isStreaming}
              className={cn(
                "w-full resize-none rounded-lg border border-input bg-background px-4 py-3 pr-24 text-sm",
                "placeholder:text-muted-foreground",
                "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
                "disabled:cursor-not-allowed disabled:opacity-50",
                "min-h-[52px] max-h-[200px]"
              )}
              rows={1}
            />
            <div className="absolute right-2 bottom-2 flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                disabled={!currentSession}
              >
                <Paperclip className="h-4 w-4" />
              </Button>
              {isStreaming ? (
                <Button
                  variant="destructive"
                  size="icon"
                  className="h-8 w-8"
                  onClick={stopStreaming}
                >
                  <Square className="h-4 w-4" />
                </Button>
              ) : (
                <Button
                  variant="default"
                  size="icon"
                  className="h-8 w-8"
                  onClick={handleSubmit}
                  disabled={isDisabled}
                >
                  <Send className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Model indicator */}
        {currentSession && (
          <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
            <span>
              Model: {currentSession.model_name || "gemini-2.5-flash"}
            </span>
            <span>Shift+Enter for new line</span>
          </div>
        )}
      </div>
    </div>
  );
}
