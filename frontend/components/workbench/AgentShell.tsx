"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  CircuitBoard,
  Cpu,
  FileCode2,
  Github,
  PanelRight,
  PanelRightClose,
  Search,
  Waves,
} from "lucide-react";
import { selectActivity, useStore } from "@/lib/store";
import { useSessionUi, useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { openArtifact, artifactKeyForFile } from "@/lib/openArtifact";
import { splitInlineActions } from "@/lib/inlineActions";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { IconTooltip } from "@/components/ui/tooltip";
import { ChatArea } from "@/components/chat/ChatArea";
import { InlineActionCard } from "@/components/chat/InlineActionCard";
import { ArtifactCenter } from "./ArtifactCenter";
import { ModeToggle } from "./ModeToggle";
import { ThemeToggle } from "./ThemeToggle";
import { ProfileMenu, REPO_URL } from "./ProfileMenu";
import { McpModal } from "./McpModal";
import { relativeTime, statusDotClass } from "./runStatus";
import type { RunSummary } from "@/types";

// The agent-first shell (S4) — prompt + view ONLY (revision 3): no command
// palette, no command modal/surface, no context menus, no file creation.
// Layout per prototype: compact 210px sidebar (session · runs · files ·
// footer) · conversation center · collapsible right panel = the EXISTING
// ArtifactCenter (same open tabs, keep-alive, unread state as the IDE —
// posture is layout emphasis only).

const SECTION_LABEL =
  "px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70";

function primaryArtifactKey(r: RunSummary): string {
  return r.kind === "sim" ? `wave:${r.id}` : `report:${r.id}`;
}

/** Sidebar runs list — VIEWING only (no pin/compare/retry; that's IDE power). */
function SidebarRuns() {
  const runs = useStore((s) => s.runs);
  const sid = useStore((s) => s.currentSession?.id ?? null);
  const { unreadRunIds, clearUnread } = useSessionUi(sid);

  return (
    <>
      <div className={cn(SECTION_LABEL, "flex items-center")} data-testid="agent-runs-section">
        Runs
        <span className="ml-auto font-mono text-muted-foreground/50">{runs.length}</span>
      </div>
      <div className="px-1">
        {runs.length === 0 && (
          <p className="px-2 py-1 text-[11px] text-muted-foreground/60">No runs yet.</p>
        )}
        {runs.map((r) => (
          <button
            key={r.id}
            type="button"
            data-testid={`agent-run-${r.id}`}
            onClick={() => {
              if (!sid) return;
              openArtifact(sid, primaryArtifactKey(r));
              clearUnread(r.id);
            }}
            className="group flex h-8 w-full items-center gap-2 rounded-md px-2 text-left hover:bg-surface-2"
          >
            <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDotClass(r.status))} />
            {r.kind === "sim" ? (
              <Waves className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
            ) : (
              <Cpu className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
            )}
            <span className="truncate font-mono text-[11px]">{r.id}</span>
            {unreadRunIds.includes(r.id) && (
              <span
                title="new"
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary animate-pulse-subtle"
              />
            )}
            <span className="ml-auto text-[9px] font-mono text-muted-foreground/50">
              {relativeTime(r.createdAt)}
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

/** Sidebar design files (manifest rtl/tb/sdc/include) — viewing only: no
 *  context menu, no new-file (IDE posture power). */
function SidebarFiles() {
  const manifest = useStore((s) => s.manifest);
  const sid = useStore((s) => s.currentSession?.id ?? null);
  const files = useMemo(
    () =>
      (manifest?.files ?? []).filter((f) =>
        ["rtl", "tb", "sdc", "include"].includes(f.role)
      ),
    [manifest]
  );

  return (
    <>
      <div className={cn(SECTION_LABEL, "pt-3")} data-testid="agent-files-section">
        Files
      </div>
      <div className="px-1">
        {files.length === 0 && (
          <p className="px-2 py-1 text-[11px] text-muted-foreground/60">No design files yet.</p>
        )}
        {files.map((f) => (
          <button
            key={f.path}
            type="button"
            data-testid={`agent-file-${f.path}`}
            onClick={() => sid && openArtifact(sid, artifactKeyForFile(f.path))}
            className="flex h-7 w-full items-center gap-2 rounded-md px-2 text-left hover:bg-surface-2"
          >
            <FileCode2 className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
            <span className="truncate font-mono text-[11px]">{f.name}</span>
            <span className="ml-auto text-[9px] uppercase text-muted-foreground/40">{f.role}</span>
          </button>
        ))}
      </div>
    </>
  );
}

function Sidebar() {
  const currentSession = useStore((s) => s.currentSession);
  const setQuickSwitchOpen = useWorkbenchUiStore((s) => s.setQuickSwitchOpen);
  const [mcpOpen, setMcpOpen] = useState(false);

  return (
    <aside
      data-testid="agent-sidebar"
      className="flex w-[210px] shrink-0 flex-col border-r border-border bg-surface-1 min-h-0"
    >
      {/* Logo */}
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3">
        <div className="grid h-6 w-6 place-items-center rounded-md bg-primary/15">
          <CircuitBoard className="h-3.5 w-3.5 text-primary" aria-hidden />
        </div>
        <span className="text-[13px] font-semibold" data-testid="agent-brand">
          SiliconCrew
        </span>
      </div>

      <div className="flex-1 overflow-y-auto thin-scrollbar py-2">
        {/* Session block → ⌘O quick-switch */}
        <div className={SECTION_LABEL}>Session</div>
        <div className="mb-3 px-2">
          <button
            type="button"
            data-testid="agent-session-button"
            title="Switch session (⌘O)"
            onClick={() => setQuickSwitchOpen(true)}
            className="flex h-8 w-full items-center gap-2 rounded-md bg-surface-2 px-2 text-xs hover:bg-surface-3"
          >
            <span className="truncate font-mono">
              {currentSession?.name ?? currentSession?.id ?? "—"}
            </span>
            <ChevronsUpDown className="ml-auto h-3 w-3 text-muted-foreground" aria-hidden />
          </button>
        </div>

        <SidebarRuns />
        <SidebarFiles />
      </div>

      {/* Footer: repo · theme · profile (MCP handoff modal owned here). */}
      <div className="flex items-center gap-1 border-t border-border p-2">
        <IconTooltip label="Open-source repo">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="Open-source repo"
            className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
          >
            <Github className="h-3.5 w-3.5" aria-hidden />
          </a>
        </IconTooltip>
        <ThemeToggle />
        <div className="ml-auto">
          <ProfileMenu placement="top-start" onConnectMcp={() => setMcpOpen(true)} />
        </div>
      </div>

      <McpModal open={mcpOpen} onOpenChange={setMcpOpen} />
    </aside>
  );
}

/**
 * Inline manual actions (S5-2): live foreign-actor events (user via IDE/REST,
 * MCP) interleave at the conversation tail as they occur; events that
 * happened while the user was away (after the active thread's last_active,
 * before shell mount) group under one honest collapsed divider — thread
 * history carries no message timestamps, so exact interleaving on reload
 * would be fake precision (plan-documented).
 */
function InlineActionsTail() {
  const events = useStore(selectActivity);
  const threads = useStore((s) => s.threads);
  const activeThreadId = useStore((s) => s.activeThreadId);
  const [awayOpen, setAwayOpen] = useState(false);
  // One mount timestamp per shell mount — the live/while-away boundary.
  const mountTsRef = useRef(Date.now());

  const threadLastActive =
    threads.find((t) => t.id === activeThreadId)?.last_active ?? null;

  const { live, whileAway } = useMemo(
    () => splitInlineActions(events, mountTsRef.current, threadLastActive),
    [events, threadLastActive]
  );

  if (live.length === 0 && whileAway.length === 0) return null;

  return (
    <div className="mx-auto w-full max-w-3xl shrink-0 space-y-3 px-4 pb-3">
      {whileAway.length > 0 && (
        <div data-testid="while-away-section">
          <button
            type="button"
            onClick={() => setAwayOpen((v) => !v)}
            className="flex w-full items-center gap-2 text-[11px] text-muted-foreground hover:text-foreground"
          >
            <span className="h-px flex-1 bg-border" />
            {awayOpen ? (
              <ChevronDown className="h-3 w-3" aria-hidden />
            ) : (
              <ChevronRight className="h-3 w-3" aria-hidden />
            )}
            While you were away — {whileAway.length} command
            {whileAway.length === 1 ? "" : "s"}
            <span className="h-px flex-1 bg-border" />
          </button>
          {awayOpen && (
            <div className="mt-3 space-y-3">
              {whileAway.map((e) => (
                <InlineActionCard key={e.id} event={e} />
              ))}
            </div>
          )}
        </div>
      )}

      {live.length > 0 && (
        <div className="max-h-56 space-y-3 overflow-y-auto thin-scrollbar" data-testid="live-actions">
          {live.map((e) => (
            <InlineActionCard key={e.id} event={e} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Right panel: slim "Artifacts" header over the EXISTING ArtifactCenter. */
function ArtifactsPanel({ onCollapse }: { onCollapse: () => void }) {
  const sid = useStore((s) => s.currentSession?.id ?? null);
  const { unreadRunIds } = useSessionUi(sid);
  const setQuickOpenOpen = useWorkbenchUiStore((s) => s.setQuickOpenOpen);

  return (
    <div
      data-testid="agent-artifacts-panel"
      className="flex h-full w-[40%] min-w-[340px] max-w-[560px] shrink-0 flex-col border-l border-border bg-surface-0 min-h-0"
    >
      <div className="flex h-9 shrink-0 items-center gap-1.5 border-b border-border/70 bg-surface-1 px-2">
        <span className="pl-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Artifacts
        </span>
        {unreadRunIds.length > 0 && (
          <span className="inline-flex items-center gap-1 text-[10px] text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse-subtle" />
            {unreadRunIds.length} new
          </span>
        )}
        <div className="ml-auto flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            title="Quick open (⌘P)"
            aria-label="Quick open"
            onClick={() => setQuickOpenOpen(true)}
          >
            <Search className="h-3.5 w-3.5" aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            title="Hide artifacts"
            aria-label="Hide artifacts"
            data-testid="agent-artifacts-collapse"
            onClick={onCollapse}
          >
            <PanelRightClose className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <ArtifactCenter emptyHint="Click Open on a tool card, or press ⌘P. Nothing opens on its own." />
      </div>
    </div>
  );
}

export function AgentShell() {
  const sid = useStore((s) => s.currentSession?.id ?? null);
  const { artifactsOpen, activeTab, unreadRunIds, setArtifactsOpen } = useSessionUi(sid);
  const flashKey = useWorkbenchUiStore((s) => s.flashKey);

  // openArtifact must reveal the panel: every openTab() sets flashKey and/or
  // moves activeTab — a CHANGE in either (never the mount snapshot) expands a
  // collapsed panel. Collapsing never re-triggers (values are unchanged).
  const prevOpenRef = useRef<{ flash: string | null; active: string | null } | null>(null);
  useEffect(() => {
    const prev = prevOpenRef.current;
    prevOpenRef.current = { flash: flashKey, active: activeTab };
    if (!prev) return; // mount snapshot — never auto-open on load
    const flashed = flashKey !== null && flashKey !== prev.flash;
    const switched = activeTab !== null && activeTab !== prev.active;
    if (flashed || switched) setArtifactsOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flashKey, activeTab]);

  return (
    <div className="flex flex-1 min-h-0" data-testid="agent-shell">
      <Sidebar />

      {/* Center — the conversation (ChatArea constrains its own column to
          max-w-3xl internally). The floating cluster top-right: mode toggle
          + the reopen button when the artifacts panel is collapsed. */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div className="absolute right-3 top-2 z-30 flex items-center gap-2">
          <ModeToggle mode="agent" className="shadow-e2 backdrop-blur" />
          {!artifactsOpen && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 bg-surface-1/95 text-xs shadow-e2 backdrop-blur"
              data-testid="agent-artifacts-open"
              onClick={() => setArtifactsOpen(true)}
            >
              <PanelRight className="h-3.5 w-3.5" aria-hidden />
              Artifacts
              {unreadRunIds.length > 0 && (
                <span className="inline-flex items-center gap-1 text-primary">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse-subtle" />
                  {unreadRunIds.length} new
                </span>
              )}
            </Button>
          )}
        </div>

        <ChatArea tailSlot={<InlineActionsTail />} />
      </div>

      {artifactsOpen && <ArtifactsPanel onCollapse={() => setArtifactsOpen(false)} />}
    </div>
  );
}
