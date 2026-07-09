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

const replaceMock = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
}));

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { ModeToggle } from "@/components/workbench/ModeToggle";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: null,
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

beforeEach(() => {
  replaceMock.mockClear();
  useStore.setState({ currentSession: SESSION as never, activeThreadId: "t1" });
  useWorkbenchUiStore.setState({ perSession: {} });
});

describe("ModeToggle (S5-3)", () => {
  it("routes to the other posture (replace, ?view= + active chat) and persists the shell", () => {
    render(<ModeToggle mode="agent" />);
    fireEvent.click(screen.getByTestId("mode-toggle-ide"));
    expect(replaceMock).toHaveBeenCalledWith("/w/s1?chat=t1&view=ide");
    expect(useWorkbenchUiStore.getState().perSession["s1"]?.shell).toBe("ide");
  });

  it("clicking the CURRENT posture is a no-op (no route, no shell write)", () => {
    render(<ModeToggle mode="agent" />);
    fireEvent.click(screen.getByTestId("mode-toggle-agent"));
    expect(replaceMock).not.toHaveBeenCalled();
    expect(useWorkbenchUiStore.getState().perSession["s1"]).toBeUndefined();
  });

  it("keeps the URL thread-less when no chat is active", () => {
    useStore.setState({ activeThreadId: null });
    render(<ModeToggle mode="ide" />);
    fireEvent.click(screen.getByTestId("mode-toggle-agent"));
    expect(replaceMock).toHaveBeenCalledWith("/w/s1?view=agent");
  });

  it("renders nothing without a session", () => {
    useStore.setState({ currentSession: null });
    render(<ModeToggle mode="ide" />);
    expect(screen.queryByTestId("mode-toggle")).toBeNull();
  });
});
