import { describe, it, expect, beforeEach } from "vitest";

import { useWorkbenchUiStore, emptySessionUi } from "@/lib/workbenchUiStore";

beforeEach(() => {
  localStorage.clear();
  useWorkbenchUiStore.setState({
    perSession: {},
    paletteOpen: false,
    quickOpenOpen: false,
    commandModal: null,
    flashKey: null,
    contextMenu: null,
  });
});

describe("workbenchUiStore: tabs", () => {
  it("openTab appends new keys and focuses (not duplicates) already-open ones", () => {
    const s = useWorkbenchUiStore.getState();
    s.openTab("s1", "code:counter.v");
    s.openTab("s1", "spec");
    let ui = useWorkbenchUiStore.getState().perSession["s1"];
    expect(ui.openTabs).toEqual(["code:counter.v", "spec"]);
    expect(ui.activeTab).toBe("spec");

    // Re-opening an open tab focuses it without appending.
    useWorkbenchUiStore.getState().openTab("s1", "code:counter.v");
    ui = useWorkbenchUiStore.getState().perSession["s1"];
    expect(ui.openTabs).toEqual(["code:counter.v", "spec"]);
    expect(ui.activeTab).toBe("code:counter.v");
    // openTab flags the tab for the attention flash.
    expect(useWorkbenchUiStore.getState().flashKey).toBe("code:counter.v");
  });

  it("closeTab falls back to the last remaining tab (or null) when closing the active one", () => {
    const s = useWorkbenchUiStore.getState();
    s.openTab("s1", "a");
    s.openTab("s1", "b");
    s.openTab("s1", "c"); // active: c

    useWorkbenchUiStore.getState().closeTab("s1", "c");
    let ui = useWorkbenchUiStore.getState().perSession["s1"];
    expect(ui.openTabs).toEqual(["a", "b"]);
    expect(ui.activeTab).toBe("b");

    // Closing a non-active tab keeps the active one.
    useWorkbenchUiStore.getState().closeTab("s1", "a");
    ui = useWorkbenchUiStore.getState().perSession["s1"];
    expect(ui.activeTab).toBe("b");

    useWorkbenchUiStore.getState().closeTab("s1", "b");
    ui = useWorkbenchUiStore.getState().perSession["s1"];
    expect(ui.openTabs).toEqual([]);
    expect(ui.activeTab).toBeNull();
  });
});

describe("workbenchUiStore: per-session isolation", () => {
  it("keeps each session's tabs, unread runs and dirs separate", () => {
    const s = useWorkbenchUiStore.getState();
    s.openTab("s1", "code:a.v");
    s.openTab("s2", "spec");
    s.markUnread("s1", "sim_0001");
    s.toggleDir("s2", "sim_runs");

    const state = useWorkbenchUiStore.getState();
    expect(state.perSession["s1"].openTabs).toEqual(["code:a.v"]);
    expect(state.perSession["s2"].openTabs).toEqual(["spec"]);
    expect(state.perSession["s1"].unreadRunIds).toEqual(["sim_0001"]);
    expect(state.perSession["s2"].unreadRunIds).toEqual([]);
    expect(state.perSession["s2"].expandedDirs).toEqual(["sim_runs"]);
    expect(state.perSession["s1"].expandedDirs).toEqual([]);
  });

  it("markUnread dedups; clearUnread removes; toggleDir round-trips", () => {
    const s = useWorkbenchUiStore.getState();
    s.markUnread("s1", "r1");
    s.markUnread("s1", "r1");
    expect(useWorkbenchUiStore.getState().perSession["s1"].unreadRunIds).toEqual(["r1"]);
    useWorkbenchUiStore.getState().clearUnread("s1", "r1");
    expect(useWorkbenchUiStore.getState().perSession["s1"].unreadRunIds).toEqual([]);

    useWorkbenchUiStore.getState().toggleDir("s1", "src");
    useWorkbenchUiStore.getState().toggleDir("s1", "src");
    expect(useWorkbenchUiStore.getState().perSession["s1"].expandedDirs).toEqual([]);
  });

  it("emptySessionUi provides the documented defaults", () => {
    expect(emptySessionUi()).toEqual({
      openTabs: [],
      activeTab: null,
      unreadRunIds: [],
      expandedDirs: [],
      dockTab: "activity",
      dockCollapsed: false,
      chatOpen: true,
      // Wave 8: the agent shell rests as header + conversation — the
      // artifact panel opens on demand, so the default is CLOSED.
      artifactsOpen: false,
    });
  });

  it("setArtifactsOpen toggles the agent-shell panel per session (S4)", () => {
    useWorkbenchUiStore.getState().setArtifactsOpen("s1", false);
    expect(useWorkbenchUiStore.getState().perSession["s1"].artifactsOpen).toBe(false);
    useWorkbenchUiStore.getState().setArtifactsOpen("s1", true);
    expect(useWorkbenchUiStore.getState().perSession["s1"].artifactsOpen).toBe(true);
  });
});

describe("workbenchUiStore: persistence (partialize)", () => {
  it("persists ONLY perSession + lastSessionId — ephemeral fields never reach localStorage", () => {
    const s = useWorkbenchUiStore.getState();
    s.openTab("s1", "spec");
    s.setLastSessionId("s1");
    s.setPaletteOpen(true);
    s.setQuickOpenOpen(true);
    s.setCommandModal("run-sim");
    s.setContextMenu({ x: 10, y: 20, path: "counter.v" });

    const raw = localStorage.getItem("sc-workbench-ui");
    expect(raw).toBeTruthy();
    const persisted = JSON.parse(raw!);
    expect(persisted.version).toBe(1);
    expect(Object.keys(persisted.state).sort()).toEqual(["lastSessionId", "perSession"]);
    expect(persisted.state.perSession["s1"].openTabs).toEqual(["spec"]);
    // S1: the /workbench redirect shim reads this back after a reload.
    expect(persisted.state.lastSessionId).toBe("s1");
    // flashKey is set by openTab but must stay ephemeral too.
    expect(persisted.state).not.toHaveProperty("flashKey");
    expect(persisted.state).not.toHaveProperty("paletteOpen");
    expect(persisted.state).not.toHaveProperty("contextMenu");
  });
});
