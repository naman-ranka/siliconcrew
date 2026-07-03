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
