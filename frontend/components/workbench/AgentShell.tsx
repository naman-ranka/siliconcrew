"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Crown,
  FolderOpen,
  Layers,
  Menu,
  PanelLeftClose,
  PanelRightClose,
  Search,
  X,
} from "lucide-react";
import { selectActivity, useStore } from "@/lib/store";
import { useSessionUi, useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { splitInlineActions } from "@/lib/inlineActions";
import { cn, formatCost, formatTokens, inertWhenClosed } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ChatArea } from "@/components/chat/ChatArea";
import { ThreadSwitcher } from "@/components/chat/ThreadSwitcher";
import { InlineActionCard } from "@/components/chat/InlineActionCard";
import { ArtifactCenter } from "./ArtifactCenter";
import { ArtifactIndex } from "./ArtifactIndex";
import { ModeToggle } from "./ModeToggle";
import { NavRail } from "./NavRail";

// The agent-first shell, Wave 8 (slide-over revision) — prompt + view ONLY:
// no command palette, no command modal/surface, no context menus, no file
// creation. The resting state is just HEADER + CONVERSATION (Codex-style);
// everything else appears on demand:
//   left  — NavRail overlay (☰ / ⌘O): sessions grouped, chats nested.
//   right — artifact panel, a docked split that ANIMATES its width open
//           (chat recenters; Esc dismisses; narrow ↔ wide toggle). Its home
//           tab is the Runs/Files Index — the old fixed sidebar's lists,
//           relocated to live WITH the artifacts they open.

/** Panel width presets — the outer wrapper animates between 0 and this, the
 *  inner body holds it FIXED so content never reflows mid-transition. One
 *  formula, vw-based, for BOTH: mixing % (of the flex container) with vw (of
 *  the viewport) clips the inner body whenever container ≠ viewport.
 *  The `max(360px, …)` floor is load-bearing (F6): the inner body needs 360px
 *  to keep its tab strip whole, so the wrapper must never resolve below that —
 *  on a narrow viewport (42vw < 360 ⇒ <~857px) an un-floored width would let
 *  the wrapper's overflow-hidden clip the tab strip's right edge. */
export const PANEL_W = {
  normal: "max(360px, min(42vw, 520px))",
  wide: "max(360px, min(62vw, 760px))",
} as const;

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

  // Temporarily hidden: the "From your AI (MCP)" inline action cards duplicate
  // the in-message tool cards during Codex turns (Codex drives the SiliconCrew
  // tools over the bound MCP server, which also logs them here). Flip to true to
  // restore, or make it runtime-aware later so it only shows external-MCP-client
  // actions.
  const SHOW_INLINE_MCP_ACTIONS = false;

  const { live, whileAway } = useMemo(
    () => splitInlineActions(events, mountTsRef.current, threadLastActive),
    [events, threadLastActive]
  );

  if (!SHOW_INLINE_MCP_ACTIONS || (live.length === 0 && whileAway.length === 0)) return null;

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

/** Composer context strip — REAL data only: manifest facts (synth top ·
 *  clock · platform) plus the session's token/cost totals (the same live
 *  numbers the IDE chat header shows; per-thread metering doesn't exist,
 *  so nothing per-thread is invented). Pieces hide when absent. */
function ContextStrip() {
  const manifest = useStore((s) => s.manifest);
  const session = useStore((s) => s.currentSession);
  if (!manifest && !session) return null;
  const showTotals = !!session && (session.total_tokens > 0 || session.total_cost > 0);

  return (
    <div
      data-testid="agent-context-strip"
      className="mx-auto flex w-full max-w-3xl items-center gap-3 px-5 pb-2 text-[10px] text-muted-foreground/60"
    >
      {manifest?.synthTop && (
        <span className="flex items-center gap-1 font-mono">
          <Crown className="h-2.5 w-2.5 text-info/60" aria-hidden />
          {manifest.synthTop}
        </span>
      )}
      {manifest && (
        <span className="font-mono">
          clk {manifest.clockPeriodNs}ns · {manifest.platform}
        </span>
      )}
      {showTotals && (
        <span className="ml-auto flex items-center gap-2 font-mono" title="Estimated model usage for this workspace. On the free model without your own key, this is covered by the platform.">
          <span>{formatTokens(session.total_tokens)}</span>
          <span>{formatCost(session.total_cost)}</span>
        </span>
      )}
    </div>
  );
}

/** The Artifacts chip — the panel's toggle; unread evidence surfaces here. */
function ArtifactsChip({
  open,
  unread,
  onClick,
}: {
  open: boolean;
  unread: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={open ? "Hide artifacts (Esc)" : "Show artifacts"}
      data-testid="agent-artifacts-chip"
      className={cn(
        "flex h-7 items-center gap-1.5 rounded-md border pl-2 pr-2.5 text-[11.5px] font-medium transition-colors",
        "outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
        open
          ? "border-primary/50 bg-primary/10 text-foreground"
          : "border-border bg-surface-1 text-foreground/85 hover:bg-surface-2"
      )}
    >
      <Layers className={cn("h-3.5 w-3.5", open ? "text-primary" : "text-muted-foreground")} aria-hidden />
      Artifacts
      {unread > 0 && (
        <span className="ml-0.5 inline-flex items-center gap-1 border-l border-border/60 pl-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse-subtle" />
          <span className="tabular-nums text-primary">{unread}</span>
        </span>
      )}
    </button>
  );
}

/** Shell header — ALL the resting-state chrome: ☰ rail toggle · session ·
 *  thread switcher · mode toggle · artifacts chip. No status dot on the
 *  session (many runs — one verdict is ambiguous; revision 1). */
function ShellHeader({
  artifactsOpen,
  unread,
  onToggleArtifacts,
}: {
  artifactsOpen: boolean;
  unread: number;
  onToggleArtifacts: () => void;
}) {
  const currentSession = useStore((s) => s.currentSession);
  const setNavRailOpen = useWorkbenchUiStore((s) => s.setNavRailOpen);
  const navRailOpen = useWorkbenchUiStore((s) => s.navRailOpen);

  return (
    <div
      data-testid="agent-header"
      className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-surface-0 px-3"
    >
      <Button
        variant="ghost"
        size="icon"
        title="Sessions (⌘O)"
        aria-label="Toggle navigation"
        data-testid="agent-rail-toggle"
        onClick={() => setNavRailOpen(!navRailOpen)}
      >
        <Menu className="h-4 w-4" aria-hidden />
      </Button>
      <div className="mx-0.5 h-5 w-px bg-border/70" aria-hidden />

      {/* Session → nav rail (the rail IS the switcher in this posture). */}
      <button
        type="button"
        title="Switch session (⌘O)"
        data-testid="agent-session-button"
        onClick={() => setNavRailOpen(true)}
        className="flex h-7 min-w-0 items-center gap-1.5 rounded-md px-2 hover:bg-surface-2 outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        <FolderOpen className="h-4 w-4 shrink-0 text-primary" aria-hidden />
        <span className="truncate font-mono text-[13px] font-medium">
          {currentSession?.name ?? currentSession?.id ?? "—"}
        </span>
      </button>

      {currentSession && (
        <>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/40" aria-hidden />
          <ThreadSwitcher />
        </>
      )}

      <div className="ml-auto flex items-center gap-2">
        <ModeToggle mode="agent" />
        <ArtifactsChip open={artifactsOpen} unread={unread} onClick={onToggleArtifacts} />
      </div>
    </div>
  );
}

/** Panel chrome over the EXISTING ArtifactCenter (Index home = Runs/Files). */
function ArtifactsPanel({
  wide,
  onToggleWide,
  onCollapse,
}: {
  wide: boolean;
  onToggleWide: () => void;
  onCollapse: () => void;
}) {
  const sid = useStore((s) => s.currentSession?.id ?? null);
  const { unreadRunIds } = useSessionUi(sid);
  const setQuickOpenOpen = useWorkbenchUiStore((s) => s.setQuickOpenOpen);

  return (
    <div className="flex h-full min-h-0 flex-col border-l border-border bg-surface-0">
      <div className="flex h-9 shrink-0 items-center gap-1.5 border-b border-border/70 bg-surface-1 px-2">
        <Layers className="h-3.5 w-3.5 shrink-0 pl-0 text-primary" aria-hidden />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
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
            className={cn("h-6 w-6", wide && "text-primary")}
            title={wide ? "Narrow panel" : "Widen panel"}
            aria-label={wide ? "Narrow panel" : "Widen panel"}
            data-testid="agent-artifacts-wide"
            onClick={onToggleWide}
          >
            {wide ? (
              <PanelRightClose className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <PanelLeftClose className="h-3.5 w-3.5" aria-hidden />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            title="Close (Esc)"
            aria-label="Hide artifacts"
            data-testid="agent-artifacts-collapse"
            onClick={onCollapse}
          >
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <ArtifactCenter readOnly homeSlot={<ArtifactIndex />} />
      </div>
    </div>
  );
}

export function AgentShell() {
  const sid = useStore((s) => s.currentSession?.id ?? null);
  const { artifactsOpen, artifactsWide, activeTab, unreadRunIds, setArtifactsOpen, setArtifactsWide } =
    useSessionUi(sid);
  const flashKey = useWorkbenchUiStore((s) => s.flashKey);

  // openArtifact must reveal the panel: every openTab() sets flashKey and/or
  // moves activeTab — a CHANGE in either (never the mount snapshot) expands a
  // collapsed panel. Collapsing never re-triggers (values are unchanged).
  const prevOpenRef = useRef<{ sid: string | null; flash: string | null; active: string | null } | null>(null);
  useEffect(() => {
    const prev = prevOpenRef.current;
    prevOpenRef.current = { sid, flash: flashKey, active: activeTab };
    // Mount snapshot AND session-switch snapshot: switching sessions changes
    // activeTab (per-session UI) — that must never override a deliberate
    // collapse stored for the incoming session.
    if (!prev || prev.sid !== sid) return;
    const flashed = flashKey !== null && flashKey !== prev.flash;
    const switched = activeTab !== null && activeTab !== prev.active;
    if (flashed || switched) setArtifactsOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, flashKey, activeTab]);

  // Same-keypress grace: when a store-driven overlay (QuickOpen via cmdk,
  // the rail, settings) closes itself on Esc BEFORE our window listener
  // runs, the flags below already read "closed" for that very press —
  // remember "an overlay was open" for one tick so the panel doesn't also
  // close. Local popovers (ThreadSwitcher, ModelPicker, ProfileMenu) mark
  // consumption with preventDefault instead, checked after a 0-timeout so
  // handler registration order can't matter.
  const overlayGraceRef = useRef(false);
  useEffect(() => {
    const arm = () => {
      overlayGraceRef.current = true;
      setTimeout(() => {
        overlayGraceRef.current = false;
      }, 0);
    };
    const unsubUi = useWorkbenchUiStore.subscribe((s, prev) => {
      const was = prev.quickOpenOpen || prev.quickSwitchOpen || prev.navRailOpen;
      const is = s.quickOpenOpen || s.quickSwitchOpen || s.navRailOpen;
      if (was && !is) arm();
    });
    const unsubData = useStore.subscribe((s, prev) => {
      if (prev.settingsOpen && !s.settingsOpen) arm();
    });
    return () => {
      unsubUi();
      unsubData();
    };
  }, []);

  // Esc dismisses the panel — only when nothing else consumed the press.
  useEffect(() => {
    if (!sid) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setTimeout(() => {
        if (e.defaultPrevented || overlayGraceRef.current) return;
        const ui = useWorkbenchUiStore.getState();
        if (ui.quickOpenOpen || ui.quickSwitchOpen || ui.navRailOpen) return;
        if (useStore.getState().settingsOpen) return;
        const open = ui.perSession[sid]?.artifactsOpen ?? false; // default = closed (Wave 8)
        if (open) ui.setArtifactsOpen(sid, false);
      }, 0);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sid]);

  const width = artifactsWide ? PANEL_W.wide : PANEL_W.normal;

  return (
    <div className="flex min-h-0 flex-1" data-testid="agent-shell">
      <NavRail />

      {/* Conversation — the only permanent surface (self-centers, max-w-3xl). */}
      <div className="flex min-w-0 flex-1 flex-col">
        <ShellHeader
          artifactsOpen={artifactsOpen}
          unread={unreadRunIds.length}
          onToggleArtifacts={() => setArtifactsOpen(!artifactsOpen)}
        />
        <div className="min-h-0 flex-1">
          <ChatArea
            hideHeader
            tailSlot={<InlineActionsTail key={sid ?? "none"} />}
            footerSlot={<ContextStrip />}
          />
        </div>
      </div>

      {/* Artifact panel — ALWAYS MOUNTED, animating width (keep-alive viewers
          survive dismiss/reopen); the fixed-width inner body never reflows
          during the transition. */}
      <div
        data-testid="agent-artifacts-panel"
        data-open={artifactsOpen}
        aria-hidden={!artifactsOpen}
        {...inertWhenClosed(artifactsOpen)}
        className="shrink-0 overflow-hidden transition-[width] duration-300 motion-reduce:transition-none"
        style={{
          width: artifactsOpen ? width : 0,
          transitionTimingFunction: "cubic-bezier(.22,1,.36,1)",
        }}
      >
        <div className="h-full" data-testid="agent-artifacts-body" style={{ width }}>
          <ArtifactsPanel
            wide={!!artifactsWide}
            onToggleWide={() => setArtifactsWide(!artifactsWide)}
            onCollapse={() => setArtifactsOpen(false)}
          />
        </div>
      </div>
    </div>
  );
}
