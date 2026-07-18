"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { User, Bot, Sparkles, ChevronDown, ChevronRight, GitCompare, Info } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { openArtifact } from "@/lib/openArtifact";
import { useStore } from "@/lib/store";
import { Logo } from "@/components/branding/Logo";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ToolCallCard } from "./ToolCallCard";
import { useChatCompact } from "./density";
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

function PlanContent({ content }: { content: string }) {
  const lines = content.split("\n").map((l) => l.trim()).filter(Boolean);
  return (
    <div className="rounded-md border border-border/60 bg-surface-2/40 p-2.5 text-sm">
      <div className="text-xs font-medium text-muted-foreground mb-1.5">Plan</div>
      <ul className="space-y-1">
        {lines.map((l, i) => {
          const m = l.match(/^\[([x~ ])\]\s*(.*)$/);
          const mark = m?.[1] ?? " ";
          const text = m?.[2] ?? l;
          return (
            <li key={i} className="flex items-start gap-2">
              <span className={cn("mt-0.5 text-xs", mark === "x" ? "text-emerald-500" : mark === "~" ? "text-violet-500" : "text-muted-foreground/60")}>
                {mark === "x" ? "✓" : mark === "~" ? "◐" : "○"}
              </span>
              <span className={cn(mark === "x" && "text-muted-foreground line-through")}>{text}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Renders a single content block — visible assistant text, reasoning
 * ("thinking" stream), plan/todo, or a tool call. Shared by the
 * committed-message and streaming render paths.
 *
 * Only the dedicated `reasoning` stream collapses into the "Thinking" toggle.
 * Plain `text` is genuine assistant prose (an explanation before a tool call is
 * still an explanation) and always renders visibly — we key off the real block
 * type, never position relative to a tool call. */
function BlockView({ block, isStreaming = false }: {
  block: ContentBlock; isStreaming?: boolean;
}) {
  if (block.type === "reasoning") return <ThinkingContent content={block.content} />;
  if (block.type === "plan") return <PlanContent content={block.content} />;
  if (block.type === "diff") return (
    <details className="rounded-md border border-border/60 bg-surface-2/40 p-2.5 text-xs">
      <summary className="flex cursor-pointer items-center gap-1.5 font-medium text-muted-foreground">
        <GitCompare className="h-3.5 w-3.5" /> Changes in this turn
      </summary>
      <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-foreground/80">{block.content}</pre>
    </details>
  );
  if (block.type === "status") return (
    <div className="flex items-start gap-1.5 rounded border border-border/60 bg-surface-2/40 px-2 py-1.5 text-xs text-muted-foreground">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {block.content}
    </div>
  );
  if (block.type === "text") return <MarkdownContent content={block.content} />;
  return <ToolCallCard toolCall={block.toolCall} result={block.result} isRunning={isStreaming && !block.result} />;
}

function _blockKey(block: ContentBlock, idx: number): string | number {
  return block.type === "tool" ? block.toolCall.id || idx : idx;
}

function MarkdownContent({ content }: { content: string }) {
  const compact = useChatCompact();

  return (
    // One base size per density; everything inside scales in em off it (the
    // heading/code/table styles below), so rail and centered chat share one
    // type system instead of viewport-sized absolutes. (`prose-sm` is inert —
    // the typography plugin isn't installed; .prose in globals.css only sets
    // colors — so the explicit base here is what actually sizes the text.)
    <div
      className={cn(
        "prose dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-surface-2 prose-pre:border prose-pre:border-border",
        compact ? "text-[0.8125rem]" : "text-sm"
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const isInline = !match;

            if (isInline) {
              return (
                <code
                  className="bg-surface-2 text-primary px-1.5 py-0.5 rounded font-mono"
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return (
              <div className="relative group rounded-lg overflow-hidden border border-border">
                <div className={cn("flex items-center justify-between py-1.5 bg-surface-2 border-b border-border", compact ? "px-3" : "px-4")}>
                  <span className="text-[0.8em] text-muted-foreground font-mono">{match[1]}</span>
                  <CopyButton text={String(children)} />
                </div>
                <SyntaxHighlighter
                  style={oneDark}
                  language={match[1]}
                  PreTag="div"
                  className="!bg-surface-1 !m-0 text-[0.9em] !rounded-t-none"
                  customStyle={{
                    margin: 0,
                    padding: compact ? "0.75rem" : "1rem",
                    background: "hsl(var(--surface-1))",
                    fontSize: "inherit",
                  }}
                >
                  {String(children).replace(/\n$/, "")}
                </SyntaxHighlighter>
              </div>
            );
          },
          a({ href, children }) {
            if (href?.startsWith("#artifact:")) {
              // Legacy agent links carry a viewer NAME (spec/code/waveform/
              // report/layout), not an artifact key — resolve to the best real
              // artifact via the same openArtifact abstraction every surface
              // uses. Unresolvable (no runs yet, unknown name) => quiet no-op.
              const tab = href.replace("#artifact:", "");
              return (
                <button
                  className="text-primary hover:underline font-medium"
                  onClick={() => {
                    const st = useStore.getState();
                    const sid = st.currentSession?.id;
                    if (!sid) return;
                    const latest = (kind: "sim" | "synth") =>
                      st.runs.find((r) => r.kind === kind)?.id ?? null;
                    let key: string | null = null;
                    if (tab === "spec") key = "spec";
                    else if (tab === "code") {
                      const first = st.manifest?.files.find((f) => f.role === "rtl");
                      key = first ? `code:${first.path}` : null;
                    } else if (tab === "waveform" || tab === "wave") {
                      const id = latest("sim");
                      key = id ? `wave:${id}` : null;
                    } else if (tab === "report") {
                      const id = latest("synth");
                      key = id ? `report:${id}` : null;
                    } else if (tab === "layout") {
                      const id = latest("synth");
                      key = id ? `layout:${id}` : null;
                    }
                    if (key) openArtifact(sid, key);
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
          // Cell padding + sizes live in globals.css ([data-density] .prose) —
          // element rules there out-specificity utilities here.
          th({ children }) {
            return (
              <th className="text-left font-semibold text-foreground uppercase tracking-wider">
                {children}
              </th>
            );
          },
          td({ children }) {
            return <td>{children}</td>;
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
          // Sizes + margins live in globals.css ([data-density] .prose).
          h1({ children }) {
            return <h1 className="font-semibold">{children}</h1>;
          },
          h2({ children }) {
            return <h2 className="font-semibold">{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="font-semibold">{children}</h3>;
          },
          p({ children }) {
            return <p className="leading-relaxed">{children}</p>;
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

export function MessageContent({ message }: { message: Message }) {
  return (
    <div className="space-y-3">
      {message.blocks.map((block, idx) => (
        <BlockView key={_blockKey(block, idx)} block={block} />
      ))}
    </div>
  );
}

// Counts seconds while `active`; resets when inactive. Shows elapsed time during
// a "Thinking" gap so a long wait never reads as a frozen/broken spinner.
function useRunningSeconds(active: boolean): number {
  const [secs, setSecs] = useState(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!active) {
      startRef.current = null;
      setSecs(0);
      return;
    }
    startRef.current = Date.now();
    const id = setInterval(
      () => setSecs(Math.floor((Date.now() - (startRef.current ?? Date.now())) / 1000)),
      500
    );
    return () => clearInterval(id);
  }, [active]);
  return secs;
}

function StreamingMessage({ showIcon = true }: { showIcon?: boolean }) {
  const { streamingMessage, isStreaming } = useStore();
  const compact = useChatCompact();
  const thinking = isStreaming && !!streamingMessage && streamingMessage.blocks.length === 0;
  const thinkingSecs = useRunningSeconds(thinking);

  if (!isStreaming || !streamingMessage) return null;

  return (
    <div className={cn("flex items-start animate-fade-in", compact ? "px-3 py-2" : "gap-3 px-4 py-3")}>
      {!compact && (
        <div className={cn("flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center", !showIcon && "invisible")}>
          <Bot className="h-4 w-4 text-primary" />
        </div>
      )}
      <div className="flex-1 min-w-0 space-y-3">
        {streamingMessage.blocks.length === 0 ? (
          <div className="flex items-center gap-3 text-muted-foreground">
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" style={{ animationDelay: "300ms" }} />
            </div>
            <span className="text-sm">Thinking{thinkingSecs > 0 ? ` · ${thinkingSecs}s` : "…"}</span>
          </div>
        ) : (
          streamingMessage.blocks.map((block, idx) => (
            <BlockView key={_blockKey(block, idx)} block={block} isStreaming />
          ))
        )}
      </div>
    </div>
  );
}

// The four welcome cards (onboarding wave, plan: onboarding-and-example-cards).
// Card faces show only label + hint; clicking sends the FULL prompt as the
// user's own visible message (sendMessage — the transcript shows exactly what
// was sent, invariant 4). The prompt texts are validated research artifacts
// (tested against the live hosted agent) — do not reword casually.
export const WELCOME_CARDS = [
  {
    label: "Tour the tools",
    hint: "what can you actually do?",
    prompt:
      "I'm new here. Walk me through what you actually do, from a written spec down to a finished layout on sky130. Show me how you check the design along the way, and be honest about anything you can't do. Then pitch me three designs worth building to put it through its paces.",
  },
  {
    label: "Brief this workspace",
    hint: "what's designed, verified, built here",
    prompt:
      "Brief me on this workspace before I touch anything. Look at the files, the simulation runs, and the synthesis results first. In plain language: what's being designed, does it actually pass its tests, and what are the best area and timing numbers so far? Then give me the single most useful next step. If it's empty, just say so and tell me how we'd start. Don't run anything yet.",
  },
  {
    label: "Design a FIFO",
    hint: "spec, RTL, a testbench that tries to break it",
    prompt:
      "Build me a small synchronous FIFO, 16 deep and 8 bits wide, with full, empty, and almost full flags. Write a short spec first, then the Verilog, then a self checking testbench that really tries to break it: reset, overflow, underflow, and reads and writes at the same time. Get it passing simulation cleanly. Then ask me what I want next: a cocotb test, a SymbiYosys formal check that the flags can never lie, or taking it through synthesis.",
  },
  {
    label: "Explain RTL to GDS",
    hint: "a lesson, not a job",
    prompt:
      "I'm new to physical design. Walk me through how you take RTL to a finished sky130 layout, stage by stage, and what each stage produces. Explain WNS, TNS, and utilization simply, and show how retrying from a stage and comparing two runs works. Keep it concrete, the way you run it.",
  },
];

// Codes where the remedy is a key/model change, not a retry of the same setup.
const KEY_ERROR_CODES = new Set(["no_key", "hosted_tier_exhausted"]);

/**
 * In-thread failure card (blind-test S2a): when a turn errors, the failure —
 * and its remedies — appear WHERE the user is looking, attached to the
 * conversation, instead of only in a dismissible banner far from the message
 * that was silently swallowed. Presentation-only: reads chatError from the
 * store; the transcript itself is unchanged.
 */
function FailedTurnCard() {
  const chatError = useStore((s) => s.chatError);
  const chatErrorCode = useStore((s) => s.chatErrorCode);
  const isStreaming = useStore((s) => s.isStreaming);
  const messages = useStore((s) => s.messages);
  const models = useStore((s) => s.models);
  const compact = useChatCompact();
  if (!chatError || isStreaming) return null;

  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  const isKeyError = !!chatErrorCode && KEY_ERROR_CODES.has(chatErrorCode);
  const freeModel = models.find((m) => m.free && m.available);

  const clearError = () => useStore.setState({ chatError: null, chatErrorCode: null });
  const retry = () => {
    if (!lastUser) return;
    clearError();
    void useStore.getState().sendMessage(lastUser.content);
  };
  const switchToFreeAndRetry = async () => {
    if (!freeModel) return;
    await useStore.getState().setActiveThreadModel(freeModel.id);
    retry();
  };

  return (
    <div className={cn("flex items-start", compact ? "px-3 py-2" : "gap-3 px-4 py-3")}>
      {!compact && (
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-destructive/10 flex items-center justify-center">
          <Bot className="h-4 w-4 text-destructive" />
        </div>
      )}
      <div
        data-testid="failed-turn-card"
        className="flex-1 min-w-0 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5"
      >
        <p className="text-xs text-foreground/90 break-words">{chatError}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {isKeyError && freeModel && (
            <button
              type="button"
              data-testid="failed-turn-use-free"
              onClick={() => void switchToFreeAndRetry()}
              className="h-6 rounded bg-primary px-2 text-[11px] font-medium text-primary-foreground hover:bg-primary/90"
            >
              Use {freeModel.label} (free) and retry
            </button>
          )}
          {isKeyError && (
            <button
              type="button"
              onClick={() => {
                clearError();
                useStore.getState().setSettingsOpen(true);
              }}
              className="h-6 rounded border border-border px-2 text-[11px] text-foreground/80 hover:bg-surface-2"
            >
              Add a key
            </button>
          )}
          {lastUser && (
            <button
              type="button"
              data-testid="failed-turn-retry"
              onClick={retry}
              className="h-6 rounded border border-border px-2 text-[11px] text-foreground/80 hover:bg-surface-2"
            >
              Retry
            </button>
          )}
          <button
            type="button"
            onClick={clearError}
            className="h-6 rounded px-2 text-[11px] text-muted-foreground hover:text-foreground"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

function WelcomeScreen() {
  const sendMessage = useStore((state) => state.sendMessage);
  const compact = useChatCompact();

  return (
    <div className="flex-1 flex items-center justify-center px-4">
      {/* Sparse by design (Claude Code / ChatGPT register): the mark, one
          inviting line, and four SMALL cards as a nudge — not the main event.
          Density follows the CONTAINER (rail vs centered), not the viewport. */}
      <div className="text-center w-full max-w-md">
        <Logo
          className={cn(
            "mx-auto text-muted-foreground/60",
            compact ? "h-6 w-6 mb-3" : "h-8 w-8 mb-4"
          )}
        />
        <h2 className={cn("font-medium text-foreground", compact ? "text-[13.5px] mb-1" : "text-[15px] mb-1")}>
          What silicon will you design today?
        </h2>
        {!compact && (
          <p className="text-[11.5px] text-muted-foreground/80 mb-6">
            open EDA tools, one agent, spec to GDS
          </p>
        )}
        {compact && <div className="mb-4" />}
        <div className={cn("grid gap-1.5 mx-auto", compact ? "grid-cols-1 max-w-[260px]" : "grid-cols-2 max-w-sm")}>
          {WELCOME_CARDS.map((card) => (
            <button
              key={card.label}
              data-testid={`welcome-card-${card.label.toLowerCase().replace(/\s+/g, "-")}`}
              className={cn(
                "text-left rounded-md border border-border/60 bg-surface-1/40 hover:bg-surface-2 hover:border-border transition-colors group",
                compact ? "px-2.5 py-1.5" : "px-3 py-2"
              )}
              onClick={() => sendMessage(card.prompt)}
            >
              <p className="text-[11.5px] font-medium text-foreground/85 group-hover:text-foreground transition-colors truncate">
                {card.label}
              </p>
              <p className="text-[10.5px] text-muted-foreground/70 truncate">
                {card.hint}
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
  const compact = useChatCompact();
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
      {/* Rail (compact): full pane width so an unbreakable token can't grow the
          row past the ~415px pane. Centered agent view keeps max-w-3xl. */}
      <div className={cn(compact ? "max-w-full" : "max-w-3xl mx-auto", compact ? "py-4" : "py-6")}>
        {groups.map((group) =>
          group.role === "user" ? (
            // Compact drops the avatars: the right-aligned bubble already says
            // "you", and every avatar pixel comes out of the text column.
            <div key={group.id} className={cn("flex justify-end", compact ? "px-3 py-2" : "gap-3 px-4 py-3")}>
              <div className={compact ? "max-w-[90%]" : "max-w-[75%]"}>
                <div className="bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
                  {group.messages[0].content}
                </div>
                {group.messages[0].timestamp && (
                  <p className="text-xs text-muted-foreground/50 text-right mt-1 px-1">
                    {formatTimestamp(group.messages[0].timestamp)}
                  </p>
                )}
              </div>
              {!compact && (
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center self-end mb-0.5">
                  <User className="h-4 w-4 text-primary-foreground" />
                </div>
              )}
            </div>
          ) : (
            <div key={group.id} className={cn("flex items-start", compact ? "px-3 py-2" : "gap-3 px-4 py-3")}>
              {!compact && (
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
              )}
              <div className={cn("flex-1 min-w-0", compact ? "space-y-3" : "space-y-4")}>
                {group.messages.map((msg) => (
                  <MessageContent key={msg.id} message={msg} />
                ))}
              </div>
            </div>
          )
        )}

        <StreamingMessage showIcon={!lastGroupIsAssistant} />
        <FailedTurnCard />
      </div>
    </ScrollArea>
  );
}
