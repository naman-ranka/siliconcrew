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

    // Review finding: the panel must NOT claim "no session" here. On a hard
    // load of /w/{sid} this is also the state while the session is still
    // resolving, so a confident verdict would be a lie (invariant #4) —
    // the honest surface is the loading skeleton the tree already shows.
    expect(screen.queryByText(/No session open yet/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /session/i })).not.toBeInTheDocument();
  });

  it("skips dropped folders instead of writing zero-byte junk files", async () => {
    // Adversarial review: Chrome lists directories in `dataTransfer.files`,
    // and the backend basenames and writes whatever arrives — dropping `rtl/`
    // produced an empty file called `rtl` and a "Uploaded 1 file(s)" toast.
    const uploadFiles = vi.fn().mockResolvedValue({ uploaded: ["ok.v"], notShown: [] });
    const pushToast = vi.fn();
    useStore.setState({ uploadFiles, pushToast } as any);
    render(<FileExplorer />);

    const dir = new File([""], "rtl");
    const file = new File(["x"], "ok.v");
    const entry = (isDirectory: boolean) => ({ webkitGetAsEntry: () => ({ isDirectory }) });
    fireEvent.drop(screen.getByRole("tree"), {
      dataTransfer: {
        types: ["Files"],
        files: [dir, file],
        items: [entry(true), entry(false)],
      },
    });

    await waitFor(() => expect(uploadFiles).toHaveBeenCalledTimes(1));
    expect(uploadFiles.mock.calls[0][0]).toEqual([file]);
    expect(pushToast.mock.calls[0][0]).toMatchObject({ title: "Skipped 1 folder(s)" });
  });

  it("swallows a near-miss file drop so the browser never navigates away", async () => {
    // The tree is the app's only drop target; an uncaught drop anywhere else
    // makes the tab navigate to file:///… and tears down the workbench.
    useStore.setState({ uploadFiles: vi.fn() } as any);
    render(<FileExplorer />);

    const ev = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(ev, "dataTransfer", { value: { types: ["Files"], files: [] } });
    window.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
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
