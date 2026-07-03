"use client";

import { useEffect } from "react";
import { useStore } from "@/lib/store";
import { emptySessionUi, useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { runCommand } from "@/lib/commands";

// Workbench v2 global shortcuts (mounted only by Workbench — the `/` Launcher
// has no global shortcuts). Scoped by shell posture (S4):
//   "ide"   — full set: ⌘K command palette · ⌘O session quick-switch · ⌘P
//             quick-open · ⌘J toggle dock · ⌘L lint · ⌘R simulate · ⌘Y
//             synthesize · ⌘E retry-P&R modal
//   "agent" — prompt + view ONLY (revision 3): ⌘P quick-open and ⌘O
//             quick-switch. No command invocation keys — ⌘K/⌘L/⌘R/⌘Y/⌘E/⌘J
//             fall through to the browser untouched.
// ⌘K/⌘O/⌘P/⌘J work even while typing (they are navigation, not text editing);
// the run shortcuts don't, so typing "l" in the chat never lints. ⌘R
// deliberately shadows browser reload while the IDE workbench is focused.

const ALWAYS_KEYS = new Set(["k", "o", "p", "j"]);

/** Keys the agent posture claims — viewing/navigation only, never invocation. */
const AGENT_KEYS = new Set(["o", "p"]);

function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable;
}

export function useWorkbenchShortcuts(scope: "ide" | "agent" = "ide"): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      // Plain mod-combos only: ⌘⇧P (print), ⌘⇧R (hard reload), ⌥-combos etc.
      // stay with the browser.
      if (!mod || e.shiftKey || e.altKey) return;
      const key = e.key.toLowerCase();
      // Agent shell: everything except ⌘P/⌘O stays with the browser.
      if (scope === "agent" && !AGENT_KEYS.has(key)) return;
      if (isEditable(e.target) && !ALWAYS_KEYS.has(key)) return;

      const ui = useWorkbenchUiStore.getState();
      const session = useStore.getState().currentSession;

      switch (key) {
        case "k":
          e.preventDefault();
          ui.setPaletteOpen(true);
          return;
        case "o":
          // Session quick-switch — shadows the browser's "open file" dialog
          // on purpose while the workbench is focused.
          e.preventDefault();
          ui.setQuickSwitchOpen(true);
          return;
        case "p":
          e.preventDefault();
          ui.setQuickOpenOpen(true);
          return;
        case "j": {
          e.preventDefault();
          if (!session) return;
          const collapsed =
            ui.perSession[session.id]?.dockCollapsed ?? emptySessionUi().dockCollapsed;
          ui.setDockCollapsed(session.id, !collapsed);
          return;
        }
        case "l":
          if (!session) return;
          e.preventDefault();
          void runCommand("lint");
          return;
        case "r":
          if (!session) return;
          e.preventDefault();
          void runCommand("sim");
          return;
        case "y":
          if (!session) return;
          e.preventDefault();
          void runCommand("synth");
          return;
        case "e":
          if (!session) return;
          e.preventDefault();
          ui.setCommandModal("pnr");
          return;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [scope]);
}
