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
//   "agent" — prompt + view ONLY (revision 3): ⌘P quick-open and ⌘O nav
//             rail (the rail IS the session/chat switcher in this posture;
//             Wave 8). No command invocation keys — ⌘K/⌘L/⌘R/⌘Y/⌘E/⌘J
//             fall through to the browser untouched.
// ⌘K/⌘O/⌘P/⌘J work even while typing (they are navigation, not text editing);
// the run shortcuts don't, so typing "l" in the chat never lints. ⌘R
// deliberately shadows browser reload while the IDE workbench is focused.

export type Scope = "ide" | "agent" | "recovery";

const ALWAYS_KEYS = new Set(["k", "o", "p", "j"]);

/** Keys each non-IDE scope claims. Everything outside the set falls through to
 *  the browser untouched — the scope must never claim a key whose target it
 *  does not mount, or the keypress arms a store flag that pops a stale overlay
 *  on the NEXT session (and, for the run keys, silently dispatches work
 *  against whatever session the store still holds). */
const SCOPE_KEYS: Record<Exclude<Scope, "ide">, Set<string>> = {
  // Agent posture: viewing/navigation only, never invocation.
  agent: new Set(["o", "p"]),
  // The deep-link failure screen mounts QuickSwitch and nothing else, so ⌘O
  // is the ONLY key it may claim. ⌘R/⌘L/⌘Y would run lint/sim/synth on the
  // previously-loaded session; ⌘K/⌘P would arm overlays that are not there.
  recovery: new Set(["o"]),
};

function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable;
}

export function useWorkbenchShortcuts(scope: Scope = "ide", enabled: boolean = true): void {
  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      // Plain mod-combos only: ⌘⇧P (print), ⌘⇧R (hard reload), ⌥-combos etc.
      // stay with the browser.
      if (!mod || e.shiftKey || e.altKey) return;
      const key = e.key.toLowerCase();
      // Narrowed scopes claim only the keys whose targets they mount.
      if (scope !== "ide" && !SCOPE_KEYS[scope].has(key)) return;
      if (isEditable(e.target) && !ALWAYS_KEYS.has(key)) return;

      const ui = useWorkbenchUiStore.getState();
      const session = useStore.getState().currentSession;

      switch (key) {
        case "k":
          e.preventDefault();
          ui.setPaletteOpen(true);
          return;
        case "o":
          // Shadows the browser's "open file" dialog on purpose while the
          // workbench is focused. IDE: session quick-switch modal. Agent:
          // toggle the nav rail (the rail is the switcher there, Wave 8).
          e.preventDefault();
          if (scope === "agent") ui.setNavRailOpen(!ui.navRailOpen);
          else ui.setQuickSwitchOpen(true);
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
    // `enabled` must re-run the effect: toggling true→false has to actually
    // unregister the listener (stale-effect bug, Wave 8 review F4).
  }, [scope, enabled]);
}
