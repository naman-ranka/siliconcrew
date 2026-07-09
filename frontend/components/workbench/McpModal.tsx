"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy, Github } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useStore } from "@/lib/store";
import { getApiBase } from "@/lib/runtime-config";
import { cn } from "@/lib/utils";
import { REPO_URL } from "./ProfileMenu";
import type { RunSummary, Session } from "@/types";

/**
 * "Continue in your own AI" — the MCP handoff modal. SiliconCrew is an open
 * MCP server, so the pitch is concrete: add the server to your client, sign
 * in via OAuth, and paste a prompt that is built from the REAL current
 * session/run state (not a generic placeholder).
 */

type ClientTab = "claude-code" | "claude-desktop" | "cursor";

function mcpJsonSnippet(url: string): string {
  return JSON.stringify({ mcpServers: { siliconcrew: { url } } }, null, 2);
}

/** The "continue this session" prompt, built from live workbench state. */
export function continuePrompt(
  session: Pick<Session, "id" | "name"> | null,
  latestRun: RunSummary | undefined
): string {
  let p =
    `Using the "siliconcrew" MCP server: call set_active_session("${session?.id ?? ""}"), ` +
    `then get_manifest and list the runs. We're working on ${session?.name ?? "this project"}.`;
  if (latestRun) {
    const wns =
      latestRun.kind === "synth" && latestRun.ppa?.wnsNs != null
        ? `, WNS ${latestRun.ppa.wnsNs}ns`
        : "";
    p += ` Latest run: ${latestRun.id} (${latestRun.status}${wns}).`;
  }
  p += " After any RTL edit: lint, then simulate.";
  return p;
}

export const NEW_SESSION_PROMPT =
  'Using the "siliconcrew" MCP server: create a new session and scaffold an 8-bit synchronous FIFO — write the spec, generate RTL, then lint and simulate.';

/** Code block with a copy button (Copy → Check for 1.5s). */
function CopyBlock({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — nothing to do */
    }
  };
  return (
    <div className={cn("relative rounded bg-surface-2 p-2", className)}>
      <pre className="overflow-x-auto whitespace-pre-wrap break-all pr-8 font-mono text-[11px] leading-relaxed text-foreground">
        {text}
      </pre>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={copied ? "Copied" : "Copy to clipboard"}
        className="absolute right-1.5 top-1.5 rounded p-1 text-muted-foreground hover:bg-surface-3 hover:text-foreground"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-status-pass" aria-hidden />
        ) : (
          <Copy className="h-3.5 w-3.5" aria-hidden />
        )}
      </button>
    </div>
  );
}

/** Small circled step index, e.g. (1) Add the server. */
function StepHeading({ index, title }: { index: number; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-[10px] font-medium text-primary">
        {index}
      </span>
      <h3 className="text-xs font-semibold text-foreground">{title}</h3>
    </div>
  );
}

const CLIENT_TABS: { id: ClientTab; label: string }[] = [
  { id: "claude-code", label: "Claude Code" },
  { id: "claude-desktop", label: "Claude Desktop" },
  { id: "cursor", label: "Cursor" },
];

export function McpModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const currentSession = useStore((s) => s.currentSession);
  const runs = useStore((s) => s.runs);
  const [tab, setTab] = useState<ClientTab>("claude-code");
  const [headlessOpen, setHeadlessOpen] = useState(false);

  const mcpUrl = `${getApiBase()}/mcp`;
  const latestRun = runs[0];

  const snippet =
    tab === "claude-code"
      ? `claude mcp add --transport http siliconcrew ${mcpUrl}`
      : mcpJsonSnippet(mcpUrl);
  const snippetHint =
    tab === "claude-code"
      ? "Run in your terminal."
      : tab === "claude-desktop"
      ? "Add to claude_desktop_config.json."
      : "Add to ~/.cursor/mcp.json.";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80vh] w-[640px] max-w-[640px] gap-4 overflow-auto bg-surface-1 p-5">
        <DialogHeader>
          <DialogTitle className="text-base">Continue in your own AI</DialogTitle>
          <DialogDescription className="text-xs">
            SiliconCrew is an open MCP server — connect any client to this workspace.
          </DialogDescription>
        </DialogHeader>

        {/* Step 1 — add the server */}
        <section className="space-y-2">
          <StepHeading index={1} title="Add the server" />
          <div className="flex gap-1 rounded-md bg-surface-2 p-0.5 w-fit" role="tablist" aria-label="MCP client">
            {CLIENT_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "rounded px-2 py-1 text-[11px] transition-colors",
                  tab === t.id
                    ? "bg-surface-0 text-foreground shadow-e1"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <CopyBlock text={snippet} />
          <p className="text-[11px] text-muted-foreground">{snippetHint}</p>
        </section>

        {/* Step 2 — sign in */}
        <section className="space-y-2">
          <StepHeading index={2} title="Sign in" />
          <div className="rounded-md border border-border bg-surface-2/50 p-2.5 text-[11px] text-muted-foreground">
            Connecting opens SiliconCrew&apos;s sign-in (OAuth via Google). No API key to paste.
          </div>
          <button
            type="button"
            onClick={() => setHeadlessOpen((v) => !v)}
            aria-expanded={headlessOpen}
            className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            {headlessOpen ? (
              <ChevronDown className="h-3 w-3" aria-hidden />
            ) : (
              <ChevronRight className="h-3 w-3" aria-hidden />
            )}
            CI &amp; headless
          </button>
          {headlessOpen && (
            <div className="space-y-1.5 rounded-md border border-border bg-surface-2/50 p-2.5 text-[11px] text-muted-foreground">
              <p>
                For CI or headless clients, send a bearer token instead — mint a token under{" "}
                <span className="text-foreground">API keys</span>:
              </p>
              <code className="block rounded bg-surface-2 p-1.5 font-mono text-[11px] text-foreground">
                Authorization: Bearer $SILICONCREW_MCP_TOKEN
              </code>
            </div>
          )}
        </section>

        {/* Step 3 — prompts built from real state */}
        <section className="space-y-2">
          <StepHeading index={3} title="Tell your AI what to do" />
          <div className="space-y-1 rounded-md border border-primary/40 p-2.5">
            <div className="text-[11px] font-medium text-foreground">Continue this session</div>
            <CopyBlock text={continuePrompt(currentSession, latestRun)} />
          </div>
          <div className="space-y-1 rounded-md border border-border p-2.5">
            <div className="text-[11px] font-medium text-foreground">Start a new session</div>
            <CopyBlock text={NEW_SESSION_PROMPT} />
          </div>
        </section>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border pt-3 text-[11px] text-muted-foreground">
          <span className="truncate">
            {currentSession ? `session ${currentSession.id}` : "no active session"}
          </span>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="flex shrink-0 items-center gap-1 hover:text-foreground"
          >
            <Github className="h-3 w-3" aria-hidden />
            naman-ranka/siliconcrew
          </a>
        </div>
      </DialogContent>
    </Dialog>
  );
}
