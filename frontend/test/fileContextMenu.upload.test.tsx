import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Right-click → "Upload files here…" (issue #93 follow-up). The menu never
// owns a file input: it names a target directory and the FileExplorer opens
// the picker, so both entry points share one upload path.

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workspaceApi: { downloadRawFile: vi.fn() },
  workbenchApi: {},
}));

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import { FileContextMenu } from "@/components/workbench/FileContextMenu";

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
  useStore.setState({ currentSession: SESSION as never, manifest: null, toasts: [] });
  useWorkbenchUiStore.setState({ contextMenu: null, uploadRequestDir: null });
});

describe("FileContextMenu upload", () => {
  it("targets the right-clicked folder, not the workspace root", () => {
    useWorkbenchUiStore.setState({ contextMenu: { x: 10, y: 10, path: "rtl/core", kind: "dir" } });
    render(<FileContextMenu />);

    fireEvent.click(screen.getByRole("menuitem", { name: /Upload files here/ }));

    expect(useWorkbenchUiStore.getState().uploadRequestDir).toBe("rtl/core");
    // The menu closes on select, like every other item.
    expect(useWorkbenchUiStore.getState().contextMenu).toBeNull();
  });

  it("targets the root from the empty-space menu", () => {
    useWorkbenchUiStore.setState({ contextMenu: { x: 10, y: 10, path: "", kind: "empty" } });
    render(<FileContextMenu />);

    fireEvent.click(screen.getByRole("menuitem", { name: /Upload files/ }));

    // "" is the root target — distinct from null, which means "no request".
    expect(useWorkbenchUiStore.getState().uploadRequestDir).toBe("");
  });

  it("offers no upload item on a file row (a file is not a destination)", () => {
    useWorkbenchUiStore.setState({ contextMenu: { x: 10, y: 10, path: "alu.v", kind: "file" } });
    render(<FileContextMenu />);

    expect(screen.queryByRole("menuitem", { name: /Upload/ })).toBeNull();
  });
});
