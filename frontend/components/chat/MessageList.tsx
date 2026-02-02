"use client";

import { useEffect, useRef } from "react";
import { User, Bot, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useStore } from "@/lib/store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ToolCallCard } from "./ToolCallCard";
import { cn } from "@/lib/utils";
import type { Message, ToolResult } from "@/types";

function formatTimestamp(timestamp?: string): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function MessageContent({ message }: { message: Message }) {
  const { setArtifactTab } = useStore();

  // Find matching tool results
  const getToolResult = (toolCallId: string): ToolResult | undefined => {
    return message.tool_results?.find((r) => r.tool_call_id === toolCallId);
  };

  return (
    <div className="space-y-4">
      {/* Text content */}
      {message.content && (
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || "");
                const isInline = !match;

                if (isInline) {
                  return (
                    <code
                      className="bg-muted px-1.5 py-0.5 rounded text-sm"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                }

                return (
                  <div className="relative group">
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match[1]}
                      PreTag="div"
                      className="rounded-lg !bg-zinc-900 text-sm"
                    >
                      {String(children).replace(/\n$/, "")}
                    </SyntaxHighlighter>
                    <button
                      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-muted/80 hover:bg-muted px-2 py-1 rounded text-xs"
                      onClick={() => {
                        navigator.clipboard.writeText(String(children));
                      }}
                    >
                      Copy
                    </button>
                  </div>
                );
              },
              a({ href, children }) {
                // Check if it's an artifact link
                if (href?.startsWith("#artifact:")) {
                  const tab = href.replace("#artifact:", "");
                  return (
                    <button
                      className="text-primary underline"
                      onClick={() => setArtifactTab(tab as any)}
                    >
                      {children}
                    </button>
                  );
                }
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary underline"
                  >
                    {children}
                  </a>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      )}

      {/* Tool calls */}
      {message.tool_calls && message.tool_calls.length > 0 && (
        <div className="space-y-2">
          {message.tool_calls.map((toolCall, idx) => (
            <ToolCallCard
              key={toolCall.id || idx}
              toolCall={toolCall}
              result={getToolResult(toolCall.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function StreamingMessage() {
  const { streamingMessage, isStreaming } = useStore();

  if (!isStreaming || !streamingMessage) return null;

  // Track which tool calls are still running (no result yet)
  const runningToolIds = new Set<string>();
  streamingMessage.tool_calls?.forEach((tc) => {
    const hasResult = streamingMessage.tool_results?.some(
      (r) => r.tool_call_id === tc.id
    );
    if (!hasResult) {
      runningToolIds.add(tc.id);
    }
  });

  return (
    <div className="flex gap-4 p-4">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
        <Bot className="h-5 w-5 text-primary" />
      </div>
      <div className="flex-1 min-w-0 space-y-4">
        {/* Text content */}
        {streamingMessage.content && (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {streamingMessage.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Tool calls */}
        {streamingMessage.tool_calls && streamingMessage.tool_calls.length > 0 && (
          <div className="space-y-2">
            {streamingMessage.tool_calls.map((toolCall, idx) => (
              <ToolCallCard
                key={toolCall.id || idx}
                toolCall={toolCall}
                result={streamingMessage.tool_results?.find(
                  (r) => r.tool_call_id === toolCall.id
                )}
                isRunning={runningToolIds.has(toolCall.id)}
              />
            ))}
          </div>
        )}

        {/* Loading indicator */}
        {!streamingMessage.content && streamingMessage.tool_calls?.length === 0 && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">Thinking...</span>
          </div>
        )}
      </div>
    </div>
  );
}

export function MessageList() {
  const { messages, currentSession, isStreaming } = useStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  if (!currentSession) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <Bot className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
          <h2 className="text-xl font-semibold mb-2">Welcome to SiliconCrew</h2>
          <p className="text-muted-foreground">
            Select a session from the sidebar or create a new one to start
            designing hardware.
          </p>
        </div>
      </div>
    );
  }

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-lg">
          <Bot className="h-12 w-12 mx-auto mb-4 text-primary" />
          <h2 className="text-xl font-semibold mb-2">Start Designing</h2>
          <p className="text-muted-foreground mb-6">
            Ask me to design hardware modules. I'll create specifications,
            implement RTL, and verify your designs.
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            {[
              "Design an 8-bit counter with async reset",
              "Create a FIFO with depth 16",
              "Design a simple ALU",
            ].map((prompt) => (
              <button
                key={prompt}
                className="text-sm bg-muted hover:bg-muted/80 px-3 py-2 rounded-lg transition-colors"
                onClick={() => useStore.getState().sendMessage(prompt)}
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea ref={scrollRef} className="flex-1">
      <TooltipProvider>
        <div className="max-w-4xl mx-auto py-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                "flex gap-4 p-4 group",
                message.role === "user" ? "bg-muted/30" : ""
              )}
            >
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    className={cn(
                      "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center cursor-default",
                      message.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-primary/10"
                    )}
                  >
                    {message.role === "user" ? (
                      <User className="h-5 w-5" />
                    ) : (
                      <Bot className="h-5 w-5 text-primary" />
                    )}
                  </div>
                </TooltipTrigger>
                {message.timestamp && (
                  <TooltipContent side="right">
                    <p className="text-xs">{formatTimestamp(message.timestamp)}</p>
                  </TooltipContent>
                )}
              </Tooltip>
              <div className="flex-1 min-w-0">
                <MessageContent message={message} />
              </div>
            </div>
          ))}

          <StreamingMessage />
        </div>
      </TooltipProvider>
    </ScrollArea>
  );
}
