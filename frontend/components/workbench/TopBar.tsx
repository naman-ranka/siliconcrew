"use client";

import { useState } from "react";
import { CircuitBoard, Github, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { IconTooltip } from "@/components/ui/tooltip";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { SessionPicker } from "./SessionPicker";
import { ThemeToggle } from "./ThemeToggle";
import { LivePill } from "./LivePill";
import { ProfileMenu, REPO_URL } from "./ProfileMenu";
import { McpModal } from "./McpModal";

/**
 * v2 top chrome — one compact 40px strip: brand · session · the single honest
 * status pill, then (right) command palette, repo, theme, and the profile
 * menu. Prop-less by design: it reads the stores itself so Workbench stays a
 * pure layout shell. The MCP handoff modal is owned here and opened from the
 * profile menu.
 */
export function TopBar() {
  const setPaletteOpen = useWorkbenchUiStore((s) => s.setPaletteOpen);
  const [mcpOpen, setMcpOpen] = useState(false);

  return (
    <header
      data-testid="wb-topbar"
      className="flex h-10 shrink-0 items-center gap-2 border-b border-border bg-surface-1 px-3"
    >
      {/* Brand */}
      <div className="flex items-center gap-2">
        <div className="rounded bg-primary/15 p-1">
          <CircuitBoard className="h-3.5 w-3.5 text-primary" aria-hidden />
        </div>
        <span className="hidden text-sm font-medium sm:inline" data-testid="wb-brand">
          SiliconCrew
        </span>
      </div>

      <Separator orientation="vertical" className="h-5" />

      <SessionPicker />
      <LivePill />

      {/* Right cluster */}
      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => setPaletteOpen(true)}
          aria-label="Open command palette"
          data-testid="topbar-commands"
        >
          <Search className="h-3.5 w-3.5" aria-hidden />
          <span className="hidden sm:inline">Commands</span>
          <kbd className="rounded border border-border bg-surface-2 px-1 py-px font-mono text-[10px] text-muted-foreground">
            ⌘K
          </kbd>
        </Button>

        <IconTooltip label="Open-source repo">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="Open-source repo"
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Github className="h-3.5 w-3.5" aria-hidden />
          </a>
        </IconTooltip>

        <ThemeToggle />

        <Separator orientation="vertical" className="h-5" />

        <ProfileMenu onConnectMcp={() => setMcpOpen(true)} />
      </div>

      <McpModal open={mcpOpen} onOpenChange={setMcpOpen} />
    </header>
  );
}
