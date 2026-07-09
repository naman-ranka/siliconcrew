import { describe, it, expect, beforeEach, vi } from "vitest";
import { render } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
}));

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { CommandPalette } from "@/components/workbench/CommandPalette";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "x",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

beforeEach(() => {
  useStore.setState({ currentSession: SESSION as any, runs: [] });
  useWorkbenchUiStore.setState({ paletteOpen: false });
});

describe("CommandPalette accessibility (F5)", () => {
  it("opens without a Radix 'DialogContent requires a DialogTitle' console error", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    useWorkbenchUiStore.setState({ paletteOpen: true });
    render(<CommandPalette />);
    const titleErrors = errSpy.mock.calls.filter((call) =>
      call.some((arg) => typeof arg === "string" && arg.includes("DialogTitle"))
    );
    expect(titleErrors).toEqual([]);
    errSpy.mockRestore();
  });
});
