import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// S4 smoke: the agent shell renders the sidebar sections + artifacts wrapper,
// and mounts NO command surfaces (revision 3: prompt + view only).

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  threadsApi: {},
  modelsApi: {},
  chatApi: {},
  // ⌘P opens QuickOpen, which indexes the workspace on open.
  workspaceApi: { getDirPaths: async () => ({ ok: true, paths: [], truncated: false }) },
  workbenchApi: {},
}));
vi.mock("@/lib/useWorkbenchSync", () => ({ useWorkbenchSync: () => {} }));
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
  useWorkbenchUiStore.setState({ perSession: {}, paletteOpen: false, quickOpenOpen: false });
  useStore.setState({
    currentSession: SESSION as never,
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
    ] as never,
    activity: { serverEvents: [], localEvents: [], status: "ready", nextBefore: null, error: null },
    // Neutralize data loading — this is a layout smoke test.
    loadWorkbench: async () => {},
    selectSessionById: async () => true,
    selectThread: async () => {},
    loadModels: async () => {},
  } as never);
});

describe("AgentShell (view=agent)", () => {
  it("renders sidebar sections, chat, and the artifacts wrapper", async () => {
    render(<Workbench sessionId="s1" view="agent" />);

    expect(await screen.findByTestId("workbench-agent")).toBeInTheDocument();

    // Sidebar: brand, session block, runs + files sections.
    const sidebar = screen.getByTestId("agent-sidebar");
    expect(sidebar).toHaveTextContent("SiliconCrew");
    expect(screen.getByTestId("agent-session-button")).toHaveTextContent("sync_fifo");
    expect(sidebar).toHaveTextContent("Runs");
    expect(sidebar).toHaveTextContent("sim_0001");
    expect(sidebar).toHaveTextContent("Files");
    expect(screen.getByTestId("agent-file-alu.v")).toBeInTheDocument();

    // Artifacts wrapper: header + agent-posture empty copy in ArtifactCenter.
    const panel = screen.getByTestId("agent-artifacts-panel");
    expect(panel).toHaveTextContent("Artifacts");
    expect(panel).toHaveTextContent(
      "Click Open on a tool card, or press ⌘P. Nothing opens on its own."
    );

    // Mode toggle present (floating, agent active).
    expect(screen.getByTestId("mode-toggle-agent")).toHaveAttribute("aria-pressed", "true");
  });

  it("mounts NO command surfaces, and ⌘K does not open a palette", async () => {
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
  });

  it("sidebar clicks open artifacts via the shared open-tab model (panel auto-tracks)", async () => {
    render(<Workbench sessionId="s1" view="agent" />);
    await screen.findByTestId("workbench-agent");

    fireEvent.click(screen.getByTestId("agent-file-alu.v"));
    await waitFor(() =>
      expect(useWorkbenchUiStore.getState().perSession["s1"]?.openTabs).toContain("code:alu.v")
    );

    fireEvent.click(screen.getByTestId("agent-run-sim_0001"));
    await waitFor(() =>
      expect(useWorkbenchUiStore.getState().perSession["s1"]?.openTabs).toContain("wave:sim_0001")
    );
  });

  it("collapse hides the panel; opening an artifact expands it again", async () => {
    render(<Workbench sessionId="s1" view="agent" />);
    await screen.findByTestId("workbench-agent");

    fireEvent.click(screen.getByTestId("agent-artifacts-collapse"));
    expect(screen.queryByTestId("agent-artifacts-panel")).toBeNull();
    // Floating reopen affordance appears.
    expect(screen.getByTestId("agent-artifacts-open")).toBeInTheDocument();

    // openArtifact (here via a sidebar file click) must re-expand the panel.
    fireEvent.click(screen.getByTestId("agent-file-alu.v"));
    expect(await screen.findByTestId("agent-artifacts-panel")).toBeInTheDocument();
  });
});
