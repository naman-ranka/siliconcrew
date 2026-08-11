import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
}));

import { useStore } from "@/lib/store";
import { FileExplorer } from "@/components/workbench/FileExplorer";

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

const UPLOAD_LABEL = "Upload files to workspace root";

// jsdom reports 0x0 boxes, which makes @tanstack/react-virtual render no rows —
// give the scroll viewport a real size so the tree materializes.
let hSpy: ReturnType<typeof vi.spyOn>;
let wSpy: ReturnType<typeof vi.spyOn>;

function seed(session: unknown = SESSION) {
  useStore.setState({
    currentSession: session as any,
    manifest: null,
    runs: [],
    runsLoading: false,
    dirCache: {
      "": {
        status: "ready",
        entries: [{ name: "decoder.v", path: "decoder.v", kind: "file" }],
        error: null,
      },
    },
    toasts: [],
  });
}

beforeEach(() => {
  hSpy = vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(600);
  wSpy = vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(300);
  seed();
});

afterEach(() => {
  hSpy.mockRestore();
  wSpy.mockRestore();
});

describe("FileExplorer upload", () => {
  it("picks files through the hidden input and hands them to store.uploadFiles", async () => {
    const uploadFiles = vi.fn().mockResolvedValue({ uploaded: ["a.v"], notShown: [] });
    useStore.setState({ uploadFiles } as any);
    render(<FileExplorer />);

    const file = new File(["module a; endmodule"], "a.v", { type: "text/plain" });
    const input = screen.getByLabelText(UPLOAD_LABEL, { selector: "input" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(uploadFiles).toHaveBeenCalledTimes(1));
    expect(uploadFiles.mock.calls[0][0]).toEqual([file]);
  });

  it("uploads files dropped on the tree", async () => {
    const uploadFiles = vi.fn().mockResolvedValue({ uploaded: ["b.v"], notShown: [] });
    useStore.setState({ uploadFiles } as any);
    render(<FileExplorer />);

    const file = new File(["x"], "b.v", { type: "text/plain" });
    const tree = screen.getByRole("tree");
    const dataTransfer = { types: ["Files"], files: [file], dropEffect: "" };
    fireEvent.dragEnter(tree, { dataTransfer });
    // The overlay names where uploads actually land (the backend basenames).
    expect(screen.getByText(/Drop to upload into the workspace root/)).toBeInTheDocument();
    fireEvent.drop(tree, { dataTransfer });

    await waitFor(() => expect(uploadFiles).toHaveBeenCalledTimes(1));
    expect(uploadFiles.mock.calls[0][0]).toEqual([file]);
  });

  it("ignores drags without files and disables the button with no session", () => {
    const uploadFiles = vi.fn();
    useStore.setState({ uploadFiles } as any);
    seed(null);
    render(<FileExplorer />);

    expect(screen.getByRole("button", { name: UPLOAD_LABEL })).toBeDisabled();

    const tree = screen.getByRole("tree");
    fireEvent.dragEnter(tree, { dataTransfer: { types: ["text/plain"], files: [] } });
    expect(screen.queryByText(/Drop to upload/)).not.toBeInTheDocument();

    // A file drop with no session is swallowed (no upload, no crash).
    const file = new File(["x"], "c.v", { type: "text/plain" });
    fireEvent.drop(tree, { dataTransfer: { types: ["Files"], files: [file] } });
    expect(uploadFiles).not.toHaveBeenCalled();

    // …and the panel is not just a wall of greyed-out buttons: it says why
    // and offers the way out (#93 Bug 3).
    expect(screen.getByTestId("files-no-session")).toHaveTextContent("No session open yet.");
    expect(screen.getByRole("link", { name: "Start a session" })).toHaveAttribute("href", "/");
  });

  it("pushes an error toast when the upload rejects", async () => {
    const uploadFiles = vi.fn().mockRejectedValue(new Error("boom: 413 too large"));
    const pushToast = vi.fn();
    useStore.setState({ uploadFiles, pushToast } as any);
    render(<FileExplorer />);

    const file = new File(["x"], "d.v", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText(UPLOAD_LABEL, { selector: "input" }), {
      target: { files: [file] },
    });

    await waitFor(() => expect(pushToast).toHaveBeenCalledTimes(1));
    expect(pushToast.mock.calls[0][0]).toMatchObject({
      kind: "error",
      title: "Upload failed",
      detail: "boom: 413 too large",
    });
    // The in-flight row clears even on failure.
    await waitFor(() => expect(screen.queryByText(/Uploading/)).not.toBeInTheDocument());
  });
});
