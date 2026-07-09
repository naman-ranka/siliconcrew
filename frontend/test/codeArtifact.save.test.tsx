import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
}));

// Force the no-Monaco fallback so the editable <textarea> renders in jsdom.
vi.mock("@/lib/monaco", () => ({
  useMonacoLoadState: () => "fallback",
  useMonacoThemeName: () => "siliconcrew-dark",
}));

import { useStore } from "@/lib/store";
import { CodeArtifact } from "@/components/workbench/viewers/CodeArtifact";
import { Toaster } from "@/components/workbench/Toaster";

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

const PATH = "design.v";
const BODY = "module m; endmodule";

function seed(saveImpl: (path: string, content: string) => Promise<void>) {
  useStore.setState({
    currentSession: SESSION as any,
    toasts: [],
    saveCodeFile: saveImpl as any,
    fileCache: {
      [PATH]: {
        status: "ready",
        file: { filename: PATH, content: BODY, size: BODY.length, binary: false, tooLarge: false },
        modified: "2026-01-01",
        error: null,
        lastAccess: 1,
      },
    } as any,
  });
}

// Type a change to dirty the buffer, then click Save.
function editAndSave() {
  const textarea = screen.getByLabelText("Code editor");
  fireEvent.change(textarea, { target: { value: BODY + "\n// edit" } });
  fireEvent.click(screen.getByRole("button", { name: /Save/ }));
}

describe("CodeArtifact save feedback (F8)", () => {
  beforeEach(() => {
    useStore.setState({ toasts: [] });
  });

  it("toasts 'Saved' AFTER a successful save resolves", async () => {
    seed(() => Promise.resolve());
    render(
      <>
        <CodeArtifact path={PATH} />
        <Toaster />
      </>
    );
    editAndSave();
    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
  });

  it("toasts the real error message when the save fails", async () => {
    seed(() => Promise.reject(new Error("permission denied")));
    render(
      <>
        <CodeArtifact path={PATH} />
        <Toaster />
      </>
    );
    editAndSave();
    await waitFor(() => expect(screen.getByText("Couldn't save design.v")).toBeInTheDocument());
    // The real message surfaces (both inline and in the toast detail).
    expect(screen.getAllByText("permission denied").length).toBeGreaterThan(0);
  });
});
