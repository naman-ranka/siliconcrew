import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  threadsApi: {},
  modelsApi: {},
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
}));

const push = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
}));

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { Breadcrumb } from "@/components/workbench/Breadcrumb";

const SESSION = {
  id: "sync_fifo",
  name: "sync_fifo",
  model_name: null,
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const THREADS = [
  {
    id: "t1",
    session_id: "sync_fifo",
    title: "FIFO signoff",
    model: null,
    created_at: null,
    last_active: "2026-07-03T09:00:00Z",
  },
  {
    id: "t2",
    session_id: "sync_fifo",
    title: "Debug overflow assert",
    model: null,
    created_at: null,
    last_active: null,
  },
];

beforeEach(() => {
  push.mockClear();
  replace.mockClear();
  useWorkbenchUiStore.setState({ quickSwitchOpen: false });
  useStore.setState({
    currentSession: SESSION,
    threads: THREADS,
    activeThreadId: "t1",
  });
});

describe("Breadcrumb", () => {
  it("renders Home › session from the store — no chat crumb", () => {
    render(<Breadcrumb />);
    expect(screen.getByTestId("breadcrumb-home")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb-session")).toHaveTextContent("sync_fifo");
    // Calm crumb: no status dot on the workspace segment (revision 1 spirit).
    // Thread switching lives solely in the ChatArea's ThreadSwitcher now.
    expect(screen.queryByTestId("breadcrumb-chat")).not.toBeInTheDocument();
  });

  it("renders only Home when no session is selected yet", () => {
    useStore.setState({ currentSession: null });
    render(<Breadcrumb />);
    expect(screen.getByTestId("breadcrumb-home")).toBeInTheDocument();
    expect(screen.queryByTestId("breadcrumb-session")).not.toBeInTheDocument();
  });

  it("Home routes to the Launcher; workspace crumb opens the ⌘O quick-switch", () => {
    render(<Breadcrumb />);
    fireEvent.click(screen.getByTestId("breadcrumb-home"));
    expect(push).toHaveBeenCalledWith("/");
    fireEvent.click(screen.getByTestId("breadcrumb-session"));
    expect(useWorkbenchUiStore.getState().quickSwitchOpen).toBe(true);
  });

  it("shows no 'forked from' chip for a normal session", () => {
    render(<Breadcrumb />);
    expect(screen.queryByTestId("forked-from-chip")).not.toBeInTheDocument();
  });

  it("shows a 'forked from' chip when the session has template provenance", () => {
    useStore.setState({
      currentSession: {
        ...SESSION,
        source_template: { id: "sync_fifo", name: "Synchronous FIFO", forked_at: "2026-07-06T00:00:00+00:00" },
      },
    });
    render(<Breadcrumb />);
    expect(screen.getByTestId("forked-from-chip")).toHaveTextContent("forked from Synchronous FIFO");
  });
});
