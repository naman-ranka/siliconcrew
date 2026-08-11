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
vi.mock("@/lib/commands", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/commands")>()),
  runCommand: vi.fn(),
}));

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { Workbench } from "@/components/workbench/Workbench";
import { runCommand } from "@/lib/commands";

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
    // The real cause is shown, and the copy does not claim the session is gone.
    expect(screen.getByText(/fetch failed/)).toBeInTheDocument();
    expect(screen.getByText(/may still be there/)).toBeInTheDocument();

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

  it("stops accusing the old id the moment the URL moves to another session", async () => {
    // Adversarial review: Workbench is not keyed by sid, so navigating away
    // from the failure screen (via the QuickSwitch it now mounts) left the old
    // failure on screen reading the NEW id — "Session healthy-block was not
    // found" about a session that is merely still loading.
    let resolve: (v: unknown) => void = () => {};
    useStore.setState(
      baseState(async (id: string) =>
        id === "ghost"
          ? { ok: false, reason: "not_found", message: "Session not found" }
          : new Promise((r) => {
              resolve = r;
            })
      )
    );
    const { rerender } = render(<Workbench sessionId="ghost" />);
    await screen.findByTestId("workbench-not-found");

    rerender(<Workbench sessionId="healthy-block" />);
    await waitFor(() => expect(screen.queryByTestId("workbench-not-found")).toBeNull());
    expect(screen.queryByText(/healthy-block was not found/)).toBeNull();
    resolve({ ok: true });
  });

  it("claims ONLY ⌘O — no run key may fire against the previous session", async () => {
    // Adversarial review, HIGH: the failure screen does not clear
    // `currentSession`. With the IDE scope, ⌘R on an error page swallowed the
    // browser reload and dispatched a real simulation against whichever
    // session the store still held; ⌘K/⌘P armed overlays that are not mounted
    // here and popped open over the NEXT session.
    useStore.setState({
      ...(baseState(async () => ({
        ok: false,
        reason: "not_found",
        message: "Session not found",
      })) as object),
      currentSession: { id: "previously-open" },
    } as never);
    render(<Workbench sessionId="ghost" />);
    await screen.findByTestId("workbench-not-found");

    for (const key of ["r", "l", "y", "e", "j", "k", "p"]) {
      const ev = new KeyboardEvent("keydown", {
        key,
        metaKey: true,
        bubbles: true,
        cancelable: true,
      });
      window.dispatchEvent(ev);
      // Not claimed → the browser keeps the key (⌘R must still reload).
      expect(ev.defaultPrevented, `⌘${key} must fall through`).toBe(false);
    }
    const ui = useWorkbenchUiStore.getState();
    expect(ui.paletteOpen).toBe(false);
    expect(ui.quickOpenOpen).toBe(false);
    expect(runCommand).not.toHaveBeenCalled();
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
