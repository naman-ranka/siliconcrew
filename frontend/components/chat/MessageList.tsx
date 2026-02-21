"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { User, Bot, Sparkles, ChevronDown, ChevronRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useStore } from "@/lib/store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ToolCallCard } from "./ToolCallCard";
import { cn } from "@/lib/utils";
import type { Message, ContentBlock } from "@/types";

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

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <button
      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-surface-2 hover:bg-surface-3 px-2 py-1 rounded text-xs text-muted-foreground hover:text-foreground"
      onClick={handleCopy}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function isThinkingBlock(blocks: ContentBlock[], idx: number): boolean {
  return blocks.slice(idx + 1).some((b) => b.type === "tool");
}

function ThinkingContent({ content }: { content: string }) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div>
      <button
        className="flex items-center gap-1 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors mb-1.5"
        onClick={() => setCollapsed(!collapsed)}
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
        <span>Thinking</span>
      </button>
      {!collapsed && (
        <div className="border-l border-border/40 pl-3 text-muted-foreground/70 text-sm">
          <MarkdownContent content={content} />
        </div>
      )}
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  const { setArtifactTab, toggleArtifacts } = useStore();

  return (
    <div className="prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-surface-2 prose-pre:border prose-pre:border-border">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const isInline = !match;

            if (isInline) {
              return (
                <code
                  className="bg-surface-2 text-primary px-1.5 py-0.5 rounded text-sm font-mono"
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return (
              <div className="relative group rounded-lg overflow-hidden border border-border">
                <div className="flex items-center justify-between px-4 py-2 bg-surface-2 border-b border-border">
                  <span className="text-xs text-muted-foreground font-mono">{match[1]}</span>
                  <CopyButton text={String(children)} />
                </div>
                <SyntaxHighlighter
                  style={oneDark}
                  language={match[1]}
                  PreTag="div"
                  className="!bg-surface-1 !m-0 text-sm !rounded-t-none"
                  customStyle={{
                    margin: 0,
                    padding: "1rem",
                    background: "hsl(var(--surface-1))",
                  }}
                >
                  {String(children).replace(/\n$/, "")}
                </SyntaxHighlighter>
              </div>
            );
          },
          a({ href, children }) {
            if (href?.startsWith("#artifact:")) {
              const tab = href.replace("#artifact:", "");
              return (
                <button
                  className="text-primary hover:underline font-medium"
                  onClick={() => {
                    setArtifactTab(tab as any);
                    toggleArtifacts();
                  }}
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
                className="text-primary hover:underline"
              >
                {children}
              </a>
            );
          },
          table({ children }) {
            return (
              <div className="overflow-x-auto my-4 rounded-lg border border-border">
                <table className="min-w-full divide-y divide-border">{children}</table>
              </div>
            );
          },
          thead({ children }) {
            return <thead className="bg-surface-2">{children}</thead>;
          },
          th({ children }) {
            return (
              <th className="px-4 py-3 text-left text-xs font-semibold text-foreground uppercase tracking-wider">
                {children}
              </th>
            );
          },
          td({ children }) {
            return <td className="px-4 py-3 text-sm">{children}</td>;
          },
          ul({ children }) {
            return <ul className="list-disc pl-6 space-y-1">{children}</ul>;
          },
          ol({ children }) {
            return <ol className="list-decimal pl-6 space-y-1">{children}</ol>;
          },
          li({ children }) {
            return <li className="text-foreground">{children}</li>;
          },
          blockquote({ children }) {
            return (
              <blockquote className="border-l-4 border-primary pl-4 italic text-muted-foreground">
                {children}
              </blockquote>
            );
          },
          h1({ children }) {
            return <h1 className="text-xl font-semibold mt-6 mb-3">{children}</h1>;
          },
          h2({ children }) {
            return <h2 className="text-lg font-semibold mt-5 mb-2">{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="text-base font-semibold mt-4 mb-2">{children}</h3>;
          },
          p({ children }) {
            return <p className="my-3 leading-relaxed">{children}</p>;
          },
          strong({ children }) {
            return <strong className="font-semibold text-foreground">{children}</strong>;
          },
          hr() {
            return <hr className="my-6 border-border" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function MessageContent({ message }: { message: Message }) {
  return (
    <div className="space-y-3">
      {message.blocks.map((block, idx) =>
        block.type === "text" ? (
          isThinkingBlock(message.blocks, idx) ? (
            <ThinkingContent key={idx} content={block.content} />
          ) : (
            <MarkdownContent key={idx} content={block.content} />
          )
        ) : (
          <ToolCallCard
            key={block.toolCall.id || idx}
            toolCall={block.toolCall}
            result={block.result}
          />
        )
      )}
    </div>
  );
}

function StreamingMessage({ showIcon = true }: { showIcon?: boolean }) {
  const { streamingMessage, isStreaming } = useStore();

  if (!isStreaming || !streamingMessage) return null;

  return (
    <div className="flex items-start gap-3 px-4 py-3 animate-fade-in">
      <div className={cn("flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center", !showIcon && "invisible")}>
        <Bot className="h-4 w-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0 space-y-3">
        {streamingMessage.blocks.length === 0 ? (
          <div className="flex items-center gap-3 text-muted-foreground">
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: "300ms" }} />
            </div>
            <span className="text-sm">Thinking...</span>
          </div>
        ) : (
          streamingMessage.blocks.map((block, idx) =>
            block.type === "text" ? (
              isThinkingBlock(streamingMessage.blocks, idx) ? (
                <ThinkingContent key={idx} content={block.content} />
              ) : (
                <MarkdownContent key={idx} content={block.content} />
              )
            ) : (
              <ToolCallCard
                key={block.toolCall.id || idx}
                toolCall={block.toolCall}
                result={block.result}
                isRunning={!block.result}
              />
            )
          )
        )}
      </div>
    </div>
  );
}

const WELCOME_SUGGESTIONS = [
  {
    title: "Design an 8-bit counter",
    description: "with async reset and enable",
    prompt: "Design an 8-bit counter with asynchronous reset and enable signals",
  },
  {
    title: "Create a FIFO buffer",
    description: "16 entries deep, 8-bit width",
    prompt: "Create a synchronous FIFO with 16 entries depth and 8-bit data width",
  },
  {
    title: "Design a simple ALU",
    description: "add, sub, and, or operations",
    prompt: "Design a simple ALU that supports add, subtract, AND, and OR operations on 8-bit operands",
  },
  {
    title: "Build an FSM controller",
    description: "for a traffic light system",
    prompt: "Design a finite state machine controller for a traffic light system with red, yellow, and green states",
  },
];

function WelcomeScreen() {
  const sendMessage = useStore((state) => state.sendMessage);

  return (
    <div className="flex-1 flex items-center justify-center px-4">
      <div className="text-center max-w-2xl">
        <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-6">
          <Sparkles className="h-8 w-8 text-primary" />
        </div>
        <h2 className="text-2xl font-semibold mb-2">Welcome to SiliconCrew</h2>
        <p className="text-muted-foreground mb-8 max-w-md mx-auto">
          I can help you design digital hardware. Describe what you need, and I'll create
          specifications, implement RTL, and verify your designs.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto">
          {WELCOME_SUGGESTIONS.map((suggestion, idx) => (
            <button
              key={idx}
              className="text-left p-4 rounded-lg bg-surface-1 hover:bg-surface-2 border border-border hover:border-primary/50 transition-all group"
              onClick={() => sendMessage(suggestion.prompt)}
            >
              <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                {suggestion.title}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {suggestion.description}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function NoSessionScreen() {
  return (
    <div className="flex-1 flex items-center justify-center px-4">
      <div className="text-center max-w-md">
        <div className="w-16 h-16 rounded-2xl bg-surface-2 flex items-center justify-center mx-auto mb-6">
          <Bot className="h-8 w-8 text-muted-foreground" />
        </div>
        <h2 className="text-xl font-semibold mb-2">Select a Session</h2>
        <p className="text-muted-foreground">
          Choose an existing session from the sidebar or create a new one to start
          designing hardware with AI assistance.
        </p>
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
      const scrollElement = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight;
      }
    }
  }, [messages, isStreaming]);

  const groups = useMemo(() => {
    const result: { role: "user" | "assistant"; id: string; messages: Message[] }[] = [];
    for (const msg of messages) {
      const last = result[result.length - 1];
      if (last && last.role === "assistant" && msg.role === "assistant") {
        last.messages.push(msg);
      } else {
        result.push({ role: msg.role, id: msg.id, messages: [msg] });
      }
    }
    return result;
  }, [messages]);

  const lastGroupIsAssistant =
    groups.length > 0 && groups[groups.length - 1].role === "assistant";

  if (!currentSession) {
    return <NoSessionScreen />;
  }

  if (messages.length === 0 && !isStreaming) {
    return <WelcomeScreen />;
  }

  return (
    <ScrollArea ref={scrollRef} className="flex-1">
      <div className="max-w-3xl mx-auto py-6">
        {groups.map((group) =>
          group.role === "user" ? (
            <div key={group.id} className="flex justify-end gap-3 px-4 py-3">
              <div className="max-w-[75%]">
                <div className="bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
                  {group.messages[0].content}
                </div>
                {group.messages[0].timestamp && (
                  <p className="text-xs text-muted-foreground/50 text-right mt-1 px-1">
                    {formatTimestamp(group.messages[0].timestamp)}
                  </p>
                )}
              </div>
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center self-end mb-0.5">
                <User className="h-4 w-4 text-primary-foreground" />
              </div>
            </div>
          ) : (
            <div key={group.id} className="flex items-start gap-3 px-4 py-3">
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center cursor-default">
                    <Bot className="h-4 w-4 text-primary" />
                  </div>
                </TooltipTrigger>
                {group.messages[0].timestamp && (
                  <TooltipContent side="right">
                    <p className="text-xs">{formatTimestamp(group.messages[0].timestamp)}</p>
                  </TooltipContent>
                )}
              </Tooltip>
              <div className="flex-1 min-w-0 space-y-4">
                {group.messages.map((msg) => (
                  <MessageContent key={msg.id} message={msg} />
                ))}
              </div>
            </div>
          )
        )}

        <StreamingMessage showIcon={!lastGroupIsAssistant} />
      </div>
    </ScrollArea>
  );
}
