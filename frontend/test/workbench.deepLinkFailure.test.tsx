import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Issue #93 Bugs 2 + 5: a `/w/{id}` deep link that fails to resolve must say
// WHY (a real 404 vs a backend that never answered), offer a retry for the
// latter, and keep the ⌘O session switcher reachable — the old screen was a
// dead end that claimed every failure meant "your session is gone".

vi.mock("@/lib/api", () => ({
  projectsApi: { list: async () => [] },
  sessionsApi: { list: async () => [] },
  threadsApi: { list: async () => [] },
  modelsApi: {},
  chatApi: {},
  workspaceApi: { getDirPaths: async () => ({ ok: true, paths: [], truncated: false }) },
  workbenchApi: {},
}));
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

class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver ??= RO;
Element.prototype.scrollIntoView ??= function scrollIntoView() {};

const baseState = (selectSessionById: unknown) =>
  ({
    currentSession: null,
    sessions: [],
    projects: [],
    threads: [],
    activeThreadId: null,
    messages: [],
    isStreaming: false,
    workspaceError: null,
    runs: [],
    activity: { serverEvents: [], localEvents: [], status: "ready", nextBefore: null, error: null },
    loadWorkbench: async () => {},
    selectSessionById,
    selectThread: async () => {},
    loadModels: async () => {},
    loadSessions: async () => {},
    loadProjects: async () => {},
  }) as never;

beforeEach(() => {
  useWorkbenchUiStore.setState({
    perSession: {},
    paletteOpen: false,
    quickOpenOpen: false,
    navRailOpen: false,
    quickSwitchOpen: false,
  } as never);
});

describe("deep-link failure screens", () => {
  it("renders the honest not-found screen for a real 404", async () => {
    useStore.setState(
      baseState(async () => ({ ok: false, reason: "not_found", message: "Session not found" }))
    );
    render(<Workbench sessionId="ghost" />);
    expect(await screen.findByTestId("workbench-not-found")).toBeInTheDocument();
    expect(screen.queryByTestId("workbench-unreachable")).toBeNull();
  });

  it("renders a retryable outage — NOT 'not found' — when the backend never answered", async () => {
    let attempts = 0;
    useStore.setState(
      baseState(async () => {
        attempts += 1;
        return attempts === 1
          ? { ok: false, reason: "unreachable", message: "fetch failed" }
          : { ok: true };
      })
    );
    render(<Workbench sessionId="alive" />);

    expect(await screen.findByTestId("workbench-unreachable")).toBeInTheDocument();
    expect(screen.queryByTestId("workbench-not-found")).toBeNull();
    expect(screen.getByText("fetch failed")).toBeInTheDocument();

    // Retry resolves in place — no page reload needed once the backend is back.
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByTestId("workbench-unreachable")).toBeNull());
    expect(attempts).toBe(2);
  });

  it("keeps ⌘O alive on the failure screen (the switcher is mounted there)", async () => {
    useStore.setState(
      baseState(async () => ({ ok: false, reason: "not_found", message: "Session not found" }))
    );
    render(<Workbench sessionId="ghost" />);
    await screen.findByTestId("workbench-not-found");

    fireEvent.keyDown(window, { key: "o", metaKey: true });
    await waitFor(() =>
      expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(true)
    );
    // …and the overlay that consumes that state is actually on screen, so the
    // keypress opens something instead of arming a stale flag.
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("offers an explicit escape hatch button, not just the hotkey", async () => {
    useStore.setState(
      baseState(async () => ({ ok: false, reason: "not_found", message: "Session not found" }))
    );
    render(<Workbench sessionId="ghost" />);
    await screen.findByTestId("workbench-not-found");

    fireEvent.click(screen.getByRole("button", { name: /Open another session/ }));
    await waitFor(() =>
      expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(true)
    );
  });
});
