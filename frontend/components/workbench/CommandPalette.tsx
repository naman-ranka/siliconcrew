"use client";

import * as React from "react";
import { Command } from "cmdk";
import {
  Cpu,
  FileText,
  GitCompareArrows,
  ListChecks,
  RotateCcw,
  Search,
  Settings2,
  Waves,
  type LucideIcon,
} from "lucide-react";
import {
  COMMANDS,
  RUN_ORDER,
  runCommand,
  synthRunChoices,
  type CommandId,
} from "@/lib/commands";
import { useStore } from "@/lib/store";
import { useSessionUi, useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { cn } from "@/lib/utils";

// The v2 command surface: ⌘K → type → Enter runs with manifest defaults (the
// fast path); the gear (or the modal) is the only place parameters live.

export const COMMAND_ICONS: Record<CommandId, LucideIcon> = {
  lint: FileText,
  sim: Waves,
  synth: Cpu,
  pnr: RotateCcw,
};

const COMMAND_KEYWORDS: Record<CommandId, string[]> = {
  lint: ["verilog", "check", "syntax", "verilator"],
  sim: ["testbench", "simulation", "waveform", "iverilog"],
  synth: ["ppa", "openroad", "synthesis", "place", "route", "flow"],
  pnr: ["place", "route", "retry", "pd", "physical", "design"],
};

function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex items-center rounded border border-border bg-surface-2 px-1 font-mono text-[10px] leading-4 text-muted-foreground",
        className
      )}
    >
      {children}
    </kbd>
  );
}

const itemClass =
  "flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-xs text-foreground outline-none data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground data-[disabled=true]:cursor-default data-[disabled=true]:opacity-40";

const groupClass =
  "px-1 py-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground";

export function CommandPalette() {
  const paletteOpen = useWorkbenchUiStore((s) => s.paletteOpen);
  const setPaletteOpen = useWorkbenchUiStore((s) => s.setPaletteOpen);
  const setQuickOpenOpen = useWorkbenchUiStore((s) => s.setQuickOpenOpen);
  const setCommandModal = useWorkbenchUiStore((s) => s.setCommandModal);

  const currentSession = useStore((s) => s.currentSession);
  const runs = useStore((s) => s.runs);
  const sessionUi = useSessionUi(currentSession?.id);

  const hasSynthRuns = synthRunChoices(runs).length > 0;

  const close = () => setPaletteOpen(false);

  const selectRun = (id: CommandId) => {
    if (!currentSession) return;
    close();
    void runCommand(id); // manifest defaults — the fast path
  };

  const openOptions = (id: CommandId) => {
    close();
    setCommandModal(id);
  };

  const openRunsPanel = () => {
    close();
    sessionUi.setDockCollapsed(false);
    sessionUi.setDockTab("runs");
  };

  return (
    <Command.Dialog
      open={paletteOpen}
      onOpenChange={setPaletteOpen}
      label="Command palette"
      overlayClassName="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
      contentClassName="fixed left-1/2 top-[14vh] z-50 w-[560px] max-w-[92vw] -translate-x-1/2"
      className="overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-e3"
    >
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <Command.Input
          placeholder="Run a command…"
          className="h-10 w-full bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
        />
        <Kbd>esc</Kbd>
      </div>

      <Command.List className="max-h-[320px] overflow-y-auto p-1">
        <Command.Empty className="px-3 py-6 text-center text-xs text-muted-foreground">
          No matching commands
        </Command.Empty>

        <Command.Group heading="Run" className={groupClass}>
          {RUN_ORDER.map((id) => {
            if (id === "pnr" && !hasSynthRuns) return null;
            const def = COMMANDS[id];
            const Icon = COMMAND_ICONS[id];
            const disabled = !currentSession;
            return (
              <Command.Item
                key={id}
                value={def.label}
                keywords={COMMAND_KEYWORDS[id]}
                disabled={disabled}
                onSelect={() => selectRun(id)}
                className={cn(itemClass, "group")}
              >
                <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
                <span className="flex-1 truncate">{def.label}</span>
                <button
                  type="button"
                  aria-label={`${def.label} options`}
                  disabled={disabled}
                  tabIndex={-1}
                  onPointerDown={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!disabled) openOptions(id);
                  }}
                  className="rounded p-1 text-muted-foreground opacity-60 transition-colors hover:bg-surface-2 hover:text-foreground hover:opacity-100 group-data-[selected=true]:opacity-100 disabled:pointer-events-none"
                >
                  <Settings2 className="h-3.5 w-3.5" aria-hidden />
                </button>
                <Kbd>⌘{def.shortcut}</Kbd>
              </Command.Item>
            );
          })}
        </Command.Group>

        <Command.Group heading="Runs" className={groupClass}>
          <Command.Item
            value="Open runs panel"
            keywords={["dock", "timeline", "history"]}
            onSelect={openRunsPanel}
            className={itemClass}
          >
            <ListChecks className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <span className="flex-1 truncate">Open runs panel</span>
            <Kbd>⌘J</Kbd>
          </Command.Item>
          <Command.Item
            value="Compare runs"
            keywords={["diff", "ppa", "baseline"]}
            onSelect={openRunsPanel}
            className={itemClass}
          >
            <GitCompareArrows className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <span className="flex-1 truncate">Compare runs</span>
          </Command.Item>
        </Command.Group>

        <Command.Group heading="Open" className={groupClass}>
          <Command.Item
            value="Quick open…"
            keywords={["file", "goto", "jump"]}
            onSelect={() => {
              close();
              setQuickOpenOpen(true);
            }}
            className={itemClass}
          >
            <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <span className="flex-1 truncate">Quick open…</span>
            <Kbd>⌘P</Kbd>
          </Command.Item>
        </Command.Group>
      </Command.List>

      <div className="flex items-center gap-1.5 border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">
        <Kbd>↵</Kbd>
        <span>run with manifest defaults</span>
        <span aria-hidden>·</span>
        <Settings2 className="h-3 w-3" aria-hidden />
        <span>options</span>
      </div>
    </Command.Dialog>
  );
}

export default CommandPalette;
