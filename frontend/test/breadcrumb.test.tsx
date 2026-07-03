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
  it("renders Home › session › active chat from the store", () => {
    render(<Breadcrumb />);
    expect(screen.getByTestId("breadcrumb-home")).toBeInTheDocument();
    expect(screen.getByTestId("breadcrumb-session")).toHaveTextContent("sync_fifo");
    expect(screen.getByTestId("breadcrumb-chat")).toHaveTextContent("FIFO signoff");
    // Calm crumb: no status dot on the workspace segment (revision 1 spirit).
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

  it("chat dropdown lists threads (active checked) and picking one selects it", async () => {
    const selectThread = vi.fn().mockResolvedValue(undefined);
    useStore.setState({ selectThread });
    render(<Breadcrumb />);

    fireEvent.click(screen.getByTestId("breadcrumb-chat"));
    const activeRow = screen.getByRole("menuitemradio", { name: /FIFO signoff/ });
    expect(activeRow).toHaveAttribute("aria-checked", "true");
    const other = screen.getByRole("menuitemradio", { name: /Debug overflow assert/ });
    expect(other).toHaveAttribute("aria-checked", "false");

    fireEvent.click(other);
    expect(selectThread).toHaveBeenCalledWith("t2");
  });

  it("footer creates a new chat in the same workspace via the store action", async () => {
    const newThread = vi.fn().mockResolvedValue(undefined);
    useStore.setState({ newThread });
    render(<Breadcrumb />);

    fireEvent.click(screen.getByTestId("breadcrumb-chat"));
    fireEvent.click(screen.getByRole("button", { name: /New chat — same workspace/ }));
    expect(newThread).toHaveBeenCalled();
  });
});
