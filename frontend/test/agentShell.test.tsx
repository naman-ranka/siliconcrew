import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Wave 8 smoke: the agent shell's resting state is header + conversation;
// the nav rail is a closed-by-default overlay, the artifact panel is an
// always-mounted width-animated split whose home tab is the Runs/Files
// Index. Still prompt + view only (revision 3): NO command surfaces.

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  threadsApi: { list: async () => [] },
  modelsApi: {},
  chatApi: {},
  // ⌘P opens QuickOpen, which indexes the workspace on open.
  workspaceApi: { getDirPaths: async () => ({ ok: true, paths: [], truncated: false }) },
  workbenchApi: {},
}));
// Neutralize only the hook — keep the real isTerminal/hasActiveRun helpers
// (ArtifactIndex uses isTerminal for the running-run Refresh affordance).
vi.mock("@/lib/useWorkbenchSync", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/useWorkbenchSync")>()),
  useWorkbenchSync: () => {},
}));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    enabled: false,
    status: "anonymous",
    user: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { Workbench } from "@/components/workbench/Workbench";

// cmdk (QuickOpen) observes its list size; jsdom has no ResizeObserver.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver ??= RO;
// …and scrolls the selected row into view (also missing in jsdom).
Element.prototype.scrollIntoView ??= function scrollIntoView() {};

const SESSION = {
  id: "s1",
  name: "sync_fifo",
  model_name: null,
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

beforeEach(() => {
  useWorkbenchUiStore.setState({
    perSession: {},
    paletteOpen: false,
    quickOpenOpen: false,
    navRailOpen: false,
  });
  useStore.setState({
    currentSession: SESSION as never,
    sessions: [SESSION] as never,
    projects: [],
    threads: [],
    activeThreadId: null,
    messages: [],
    isStreaming: false,
    workspaceError: null,
    manifest: {
      sessionId: "s1",
      files: [
        { name: "alu.v", role: "rtl", path: "alu.v" },
        { name: "cpu_tb.v", role: "tb", path: "cpu_tb.v" },
      ],
      synthTop: "alu",
      simTop: "cpu_tb",
      clockPeriodNs: 10,
      platform: "sky130hd",
    },
    runs: [
      {
        id: "sim_0001",
        kind: "sim",
        status: "failed",
        createdAt: new Date().toISOString(),
        top: "cpu_tb",
        pinned: false,
      },
      {
        id: "synth_0002",
        kind: "synth",
        status: "running",
        createdAt: new Date().toISOString(),
        top: "alu",
        pinned: false,
      },
    ] as never,
    activity: { serverEvents: [], localEvents: [], status: "ready", nextBefore: null, error: null },
    // Neutralize data loading — this is a layout smoke test.
    loadWorkbench: async () => {},
    selectSessionById: async () => true,
    selectThread: async () => {},
    loadModels: async () => {},
    loadSessions: async () => {},
    loadProjects: async () => {},
  } as never);
});

const panelOpen = () =>
  screen.getByTestId("agent-artifacts-panel").getAttribute("data-open") === "true";

describe("AgentShell (view=agent, Wave 8 slide-over)", () => {
  it("resting state is header + conversation: panel CLOSED; the chip opens the Index home", async () => {
    render(<Workbench sessionId="s1" view="agent" />);

    expect(await screen.findByTestId("workbench-agent")).toBeInTheDocument();

    // Header carries the chrome: rail toggle, session, mode toggle, chip.
    expect(screen.getByTestId("agent-header")).toBeInTheDocument();
    expect(screen.getByTestId("agent-rail-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("agent-session-button")).toHaveTextContent("sync_fifo");
    expect(screen.getByTestId("mode-toggle-agent")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("agent-artifacts-chip")).toBeInTheDocument();

    // The old fixed sidebar is GONE — and the panel rests CLOSED (locked
    // decision: resting state = header + conversation). Closed surfaces are
    // inert so keyboard users can't tab into invisible UI.
    expect(screen.queryByTestId("agent-sidebar")).toBeNull();
    expect(panelOpen()).toBe(false);
    expect(screen.getByTestId("agent-artifacts-panel")).toHaveAttribute("inert");
    expect(screen.getByTestId("agent-nav-rail").getAttribute("data-open")).toBe("false");
    expect(screen.getByTestId("agent-nav-rail")).toHaveAttribute("inert");

    // The chip opens the panel on its Index home: Runs + Files lists.
    fireEvent.click(screen.getByTestId("agent-artifacts-chip"));
    expect(panelOpen()).toBe(true);
    expect(screen.getByTestId("agent-artifacts-panel")).not.toHaveAttribute("inert");
    expect(screen.getByTestId("artifact-index")).toBeInTheDocument();
    expect(screen.getByTestId("agent-runs-section")).toHaveTextContent("Runs");
    expect(screen.getByTestId("agent-run-sim_0001")).toBeInTheDocument();
    expect(screen.getByTestId("agent-files-section")).toHaveTextContent("Files");
    expect(screen.getByTestId("agent-file-alu.v")).toBeInTheDocument();

    // The RUNNING run carries the compact user-gesture Refresh; terminal
    // runs don't (the UI never polls — refresh is an explicit act).
    expect(screen.getByTestId("agent-run-refresh-synth_0002")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-run-refresh-sim_0001")).toBeNull();
  });

  it("mounts NO command surfaces; ⌘K inert; ⌘P quick-open; ⌘O toggles the rail", async () => {
    render(<Workbench sessionId="s1" view="agent" />);
    await screen.findByTestId("workbench-agent");

    // No palette/modal/surface/context-menu inputs anywhere.
    expect(screen.queryByPlaceholderText("Run a command…")).toBeNull();

    fireEvent.keyDown(window, { key: "k", metaKey: true, bubbles: true });
    expect(useWorkbenchUiStore.getState().paletteOpen).toBe(false);
    expect(screen.queryByPlaceholderText("Run a command…")).toBeNull();

    // ⌘P (viewing) still works in the agent posture.
    fireEvent.keyDown(window, { key: "p", metaKey: true, bubbles: true });
    expect(useWorkbenchUiStore.getState().quickOpenOpen).toBe(true);
    useWorkbenchUiStore.setState({ quickOpenOpen: false });

    // ⌘O toggles the NAV RAIL here (the rail is the switcher in this
    // posture; QuickSwitch is IDE-only).
    fireEvent.keyDown(window, { key: "o", metaKey: true, bubbles: true });
    expect(useWorkbenchUiStore.getState().navRailOpen).toBe(true);
    expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(false);
    fireEvent.keyDown(window, { key: "o", metaKey: true, bubbles: true });
    expect(useWorkbenchUiStore.getState().navRailOpen).toBe(false);
  });

  it("Index clicks open artifacts as tabs; Back to index returns home", async () => {
    render(<Workbench sessionId="s1" view="agent" />);
    await screen.findByTestId("workbench-agent");

    fireEvent.click(screen.getByTestId("agent-artifacts-chip")); // panel rests closed
    fireEvent.click(screen.getByTestId("agent-file-alu.v"));
    await waitFor(() =>
      expect(useWorkbenchUiStore.getState().perSession["s1"]?.openTabs).toContain("code:alu.v")
    );

    // Viewing a tab → the footer path home appears; take it.
    fireEvent.click(screen.getByTestId("artifact-back-to-index"));
    expect(useWorkbenchUiStore.getState().perSession["s1"]?.activeTab).toBeNull();
    expect(screen.getByTestId("artifact-index")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("agent-run-sim_0001"));
    await waitFor(() =>
      expect(useWorkbenchUiStore.getState().perSession["s1"]?.openTabs).toContain("wave:sim_0001")
    );
    // The pinned Index tab can also take you home.
    fireEvent.click(screen.getByTestId("artifact-index-tab"));
    expect(useWorkbenchUiStore.getState().perSession["s1"]?.activeTab).toBeNull();
  });

  it("collapse animates the panel closed (stays MOUNTED); opening an artifact re-expands", async () => {
    render(<Workbench sessionId="s1" view="agent" />);
    await screen.findByTestId("workbench-agent");

    // Open, then collapse via the panel's own close button.
    fireEvent.click(screen.getByTestId("agent-artifacts-chip"));
    expect(panelOpen()).toBe(true);
    fireEvent.click(screen.getByTestId("agent-artifacts-collapse"));
    // Width-0 keep-alive: still in the DOM (viewers survive), just closed.
    expect(screen.getByTestId("agent-artifacts-panel")).toBeInTheDocument();
    expect(panelOpen()).toBe(false);

    // openArtifact (an Index file click) re-expands after a collapse.
    fireEvent.click(screen.getByTestId("agent-file-alu.v"));
    await waitFor(() => expect(panelOpen()).toBe(true));
  });

  it("☰ opens the nav rail overlay with the sessions list", async () => {
    render(<Workbench sessionId="s1" view="agent" />);
    await screen.findByTestId("workbench-agent");

    fireEvent.click(screen.getByTestId("agent-rail-toggle"));
    const rail = screen.getByTestId("agent-nav-rail");
    expect(rail.getAttribute("data-open")).toBe("true");
    expect(rail).toHaveTextContent("SiliconCrew");
    expect(screen.getByTestId("rail-new-session")).toBeInTheDocument();
    expect(screen.getByTestId("rail-session-s1")).toHaveTextContent("sync_fifo");
  });

  it("the rail's own top-left ☰ closes it — the opener corner also collapses (F7)", async () => {
    // The header ☰ is buried under the open rail (z-90); the rail carries a
    // matching ☰ in the same corner so the toggle is never unreachable.
    render(<Workbench sessionId="s1" view="agent" />);
    await screen.findByTestId("workbench-agent");

    fireEvent.click(screen.getByTestId("agent-rail-toggle"));
    expect(screen.getByTestId("agent-nav-rail").getAttribute("data-open")).toBe("true");

    fireEvent.click(screen.getByTestId("rail-collapse"));
    expect(useWorkbenchUiStore.getState().navRailOpen).toBe(false);
    expect(screen.getByTestId("agent-nav-rail").getAttribute("data-open")).toBe("false");
  });
});
