import { describe, it, expect, beforeEach, vi } from "vitest";

// Issue #93 Bug 1, data layer: the v2 file explorer renders from `dirCache`,
// which `refreshWorkspace` does NOT touch — so without an explicit
// invalidation an upload succeeds, the manifest updates, and the uploaded
// files stay INVISIBLE in the tree. This is the assertion that fails if that
// line is ever dropped in a refactor of the refresh path.

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  threadsApi: {},
  modelsApi: {},
  workspaceApi: {},
  workbenchApi: {
    uploadFiles: vi.fn(),
  },
}));

import { useStore } from "@/lib/store";
import { workbenchApi } from "@/lib/api";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "m",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const manifest = (names: string[]) => ({
  sessionId: "s1",
  files: names.map((name) => ({ name, role: "rtl" as const, path: name })),
  synthTop: null,
  simTop: null,
  clockPeriodNs: null,
  platform: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({
    currentSession: SESSION,
    toasts: [],
  } as never);
});

describe("uploadFiles", () => {
  it("invalidates the workspace-root dirCache so the tree shows the new files", async () => {
    const invalidateDirs = vi.fn();
    const refreshWorkspace = vi.fn().mockResolvedValue(undefined);
    useStore.setState({ invalidateDirs, refreshWorkspace } as never);
    vi.mocked(workbenchApi.uploadFiles).mockResolvedValue({
      ok: true,
      uploaded: ["alu.v"],
      manifest: manifest(["alu.v"]),
    } as never);

    const file = new File(["module alu; endmodule"], "alu.v");
    const res = await useStore.getState().uploadFiles([file]);

    // Filenames are basenamed server-side, so exactly one directory changes —
    // here the default target, the root.
    expect(invalidateDirs).toHaveBeenCalledWith([""]);
    expect(refreshWorkspace).toHaveBeenCalledTimes(1);
    expect(useStore.getState().manifest?.files.map((f) => f.name)).toEqual(["alu.v"]);
    expect(res.uploaded).toEqual(["alu.v"]);
  });

  it("reports files the server stored but the manifest does not surface", async () => {
    useStore.setState({ invalidateDirs: vi.fn(), refreshWorkspace: vi.fn() } as never);
    vi.mocked(workbenchApi.uploadFiles).mockResolvedValue({
      ok: true,
      uploaded: ["alu.v", "notes.txt"],
      manifest: manifest(["alu.v"]),
    } as never);

    const res = await useStore.getState().uploadFiles([new File(["x"], "alu.v")]);

    // Honest state: a stored-but-unlisted file is named, not silently dropped.
    expect(res.notShown).toEqual(["notes.txt"]);
    const toast = useStore.getState().toasts.at(-1);
    expect(toast?.title).toBe("Uploaded 2 file(s)");
    expect(toast?.detail).toContain("1 non-design file(s)");
  });

  it("uploads into a target directory and invalidates THAT directory", async () => {
    const invalidateDirs = vi.fn();
    const refreshWorkspace = vi.fn().mockResolvedValue(undefined);
    useStore.setState({ invalidateDirs, refreshWorkspace } as never);
    vi.mocked(workbenchApi.uploadFiles).mockResolvedValue({
      ok: true,
      uploaded: ["rtl/core/alu.v"],
      manifest: { ...manifest([]), files: [{ name: "alu.v", role: "rtl", path: "rtl/core/alu.v" }] },
    } as never);

    const res = await useStore
      .getState()
      .uploadFiles([new File(["x"], "alu.v")], "rtl/core");

    expect(workbenchApi.uploadFiles).toHaveBeenCalledWith("s1", expect.anything(), "rtl/core");
    // Invalidating the ROOT would leave the uploaded file invisible inside the
    // folder the user actually right-clicked.
    expect(invalidateDirs).toHaveBeenCalledWith(["rtl/core"]);
    expect(res.uploaded).toEqual(["rtl/core/alu.v"]);
  });

  it("does not call a subdirectory upload 'not shown' (manifest keys on path, not name)", async () => {
    useStore.setState({ invalidateDirs: vi.fn(), refreshWorkspace: vi.fn() } as never);
    vi.mocked(workbenchApi.uploadFiles).mockResolvedValue({
      ok: true,
      uploaded: ["rtl/core/alu.v"],
      // The manifest's `name` is a display basename ("alu.v"); `path` is the
      // canonical key. Comparing against `name` would report this file as
      // stored-but-unlisted even though the tree shows it.
      manifest: { ...manifest([]), files: [{ name: "alu.v", role: "rtl", path: "rtl/core/alu.v" }] },
    } as never);

    const res = await useStore.getState().uploadFiles([new File(["x"], "alu.v")], "rtl/core");

    expect(res.notShown).toEqual([]);
    expect(useStore.getState().toasts.at(-1)?.detail).toBeUndefined();
  });

  it("does not cross-write a late upload into the session the user switched to", async () => {
    // Adversarial review: uploadFiles read currentSession once and then wrote
    // the response manifest into whatever session was current when it landed,
    // so A's design description appeared inside B (roles, top markers, toast).
    const invalidateDirs = vi.fn();
    const refreshWorkspace = vi.fn().mockResolvedValue(undefined);
    useStore.setState({
      invalidateDirs,
      refreshWorkspace,
      manifest: manifest(["b_only.v"]),
    } as never);
    vi.mocked(workbenchApi.uploadFiles).mockImplementation(async () => {
      // The user switches away while the upload is in flight.
      useStore.setState({ currentSession: { ...SESSION, id: "s2" } } as never);
      return { ok: true, uploaded: ["a.v"], manifest: manifest(["a.v"]) } as never;
    });

    const res = await useStore.getState().uploadFiles([new File(["x"], "a.v")]);

    expect(useStore.getState().manifest?.files.map((f) => f.name)).toEqual(["b_only.v"]);
    expect(useStore.getState().toasts).toHaveLength(0);
    expect(invalidateDirs).not.toHaveBeenCalled();
    expect(refreshWorkspace).not.toHaveBeenCalled();
    // The files really were uploaded — the caller is told so, honestly.
    expect(res.uploaded).toEqual(["a.v"]);
  });

  it("is a no-op with no session or no files (never calls the API)", async () => {
    useStore.setState({ currentSession: null } as never);
    await useStore.getState().uploadFiles([new File(["x"], "a.v")]);
    useStore.setState({ currentSession: SESSION } as never);
    await useStore.getState().uploadFiles([]);
    expect(workbenchApi.uploadFiles).not.toHaveBeenCalled();
  });
});
