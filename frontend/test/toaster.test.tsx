import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {}, sessionsApi: {}, chatApi: {}, workspaceApi: {}, workbenchApi: {},
}));

import { useStore } from "@/lib/store";
import { Toaster } from "@/components/workbench/Toaster";

beforeEach(() => {
  useStore.setState({ toasts: [] });
});

describe("toast store", () => {
  it("pushToast adds a toast; dismissToast removes it", () => {
    act(() => useStore.getState().pushToast({ kind: "success", title: "sim_0001 passed" }, 0));
    expect(useStore.getState().toasts).toHaveLength(1);
    const id = useStore.getState().toasts[0].id;
    act(() => useStore.getState().dismissToast(id));
    expect(useStore.getState().toasts).toHaveLength(0);
  });

  it("auto-dismisses after the ttl", () => {
    vi.useFakeTimers();
    act(() => useStore.getState().pushToast({ kind: "error", title: "sim_0002 failed @ 11ns" }, 5000));
    expect(useStore.getState().toasts).toHaveLength(1);
    act(() => vi.advanceTimersByTime(5000));
    expect(useStore.getState().toasts).toHaveLength(0);
    vi.useRealTimers();
  });
});

describe("Toaster", () => {
  it("renders queued toasts with title + detail and a dismiss control", () => {
    act(() => useStore.getState().pushToast({ kind: "error", title: "sim_0002 failed @ 11ns", detail: "y=251 expected 5" }, 0));
    render(<Toaster />);
    expect(screen.getByText("sim_0002 failed @ 11ns")).toBeInTheDocument();
    expect(screen.getByText("y=251 expected 5")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Dismiss notification"));
    expect(useStore.getState().toasts).toHaveLength(0);
  });

  it("renders nothing when there are no toasts", () => {
    const { container } = render(<Toaster />);
    expect(container).toBeEmptyDOMElement();
  });
});
