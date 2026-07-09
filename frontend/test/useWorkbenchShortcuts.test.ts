import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  threadsApi: {},
  modelsApi: {},
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
}));
vi.mock("@/lib/commands", () => ({ runCommand: vi.fn() }));

import { useWorkbenchShortcuts } from "@/hooks/useWorkbenchShortcuts";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { useStore } from "@/lib/store";
import { runCommand } from "@/lib/commands";

const press = (key: string, target?: EventTarget) => {
  const event = new KeyboardEvent("keydown", { key, metaKey: true, bubbles: true });
  (target ?? window).dispatchEvent(event);
};

beforeEach(() => {
  useWorkbenchUiStore.setState({
    paletteOpen: false,
    quickOpenOpen: false,
    quickSwitchOpen: false,
  });
});

describe("useWorkbenchShortcuts: ⌘O quick-switch", () => {
  it("⌘O opens the session quick-switch", () => {
    const { unmount } = renderHook(() => useWorkbenchShortcuts());
    press("o");
    expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(true);
    unmount();
  });

  it("⌘O works while typing (navigation key, like ⌘K/⌘P)", () => {
    const { unmount } = renderHook(() => useWorkbenchShortcuts());
    const input = document.createElement("input");
    document.body.appendChild(input);
    press("o", input);
    expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(true);
    input.remove();
    unmount();
  });

  it("a plain 'o' (no modifier) does nothing", () => {
    const { unmount } = renderHook(() => useWorkbenchShortcuts());
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "o", bubbles: true }));
    expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(false);
    unmount();
  });

  it("⌘⇧O stays with the browser (only plain mod-combos are claimed)", () => {
    const { unmount } = renderHook(() => useWorkbenchShortcuts());
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "o", metaKey: true, shiftKey: true, bubbles: true })
    );
    expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(false);
    unmount();
  });
});

// S4: the agent posture claims ONLY viewing keys (⌘P/⌘O) — no palette, no
// run shortcuts, no dock toggle (revision 3: prompt + view only). Wave 8:
// agent ⌘O toggles the NAV RAIL (the rail is the switcher in this posture;
// the QuickSwitch modal is IDE-only).
describe("useWorkbenchShortcuts: agent scope", () => {
  it("⌘P quick-opens; ⌘O toggles the nav rail (not QuickSwitch)", () => {
    const { unmount } = renderHook(() => useWorkbenchShortcuts("agent"));
    press("p");
    expect(useWorkbenchUiStore.getState().quickOpenOpen).toBe(true);
    press("o");
    expect(useWorkbenchUiStore.getState().navRailOpen).toBe(true);
    expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(false);
    press("o");
    expect(useWorkbenchUiStore.getState().navRailOpen).toBe(false);
    unmount();
  });

  it("⌘K does not open the palette; ⌘E does not open the retry modal", () => {
    useStore.setState({ currentSession: { id: "s1" } as never });
    const { unmount } = renderHook(() => useWorkbenchShortcuts("agent"));
    press("k");
    expect(useWorkbenchUiStore.getState().paletteOpen).toBe(false);
    press("e");
    expect(useWorkbenchUiStore.getState().commandModal).toBeNull();
    unmount();
  });

  it("⌘L/⌘R/⌘Y never invoke commands in the agent shell", () => {
    useStore.setState({ currentSession: { id: "s1" } as never });
    const { unmount } = renderHook(() => useWorkbenchShortcuts("agent"));
    press("l");
    press("r");
    press("y");
    expect(runCommand).not.toHaveBeenCalled();
    unmount();
  });
});
