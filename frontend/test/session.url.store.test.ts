import { describe, it, expect, beforeEach, vi } from "vitest";

// S1: URL-driven session selection — selectSessionById resolves an id from
// the URL (list → direct fetch fallback) and reports a miss honestly so the
// /w page can render "Session not found" instead of an empty workbench. The
// miss carries a REASON: only a real 404 is "not found"; anything else is a
// retryable outage and must not claim the session is gone (#93 Bug 2).
vi.mock("@/lib/api", () => {
  return {
    projectsApi: { list: vi.fn().mockResolvedValue([]) },
    sessionsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn() },
    threadsApi: { list: vi.fn().mockResolvedValue([]) },
    chatApi: {
      getHistory: vi.fn().mockResolvedValue([]),
      getThreadHistory: vi.fn().mockResolvedValue([]),
      createConnection: vi.fn(),
    },
    modelsApi: { list: vi.fn().mockResolvedValue({ models: [] }) },
    workspaceApi: {},
    workbenchApi: {
      getWorkbench: vi.fn().mockResolvedValue({
        ok: true, manifest: null, runs: [], files: [], spec: null, code: [],
        report: null, synthesisRuns: [], activity: [], rootDir: [],
      }),
    },
  };
});

import { useStore } from "@/lib/store";
import { sessionsApi } from "@/lib/api";

const session = (id: string) => ({
  id,
  name: id,
  model_name: "claude-sonnet-4-6",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
});

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({
    sessions: [],
    currentSession: null,
    threads: [],
    activeThreadId: null,
    messages: [],
    ws: null,
    wsSessionId: null,
    wsThreadId: null,
  } as any);
});

describe("selectSessionById (S1 URL-driven selection)", () => {
  it("loads the session list when empty and selects the matching session", async () => {
    (sessionsApi.list as any).mockResolvedValue([session("a"), session("b")]);
    const res = await useStore.getState().selectSessionById("b");
    expect(res).toEqual({ ok: true });
    expect(useStore.getState().currentSession?.id).toBe("b");
    expect(sessionsApi.get).not.toHaveBeenCalled();
  });

  it("falls back to a direct fetch for a deep link not in the list", async () => {
    (sessionsApi.list as any).mockResolvedValue([session("a")]);
    (sessionsApi.get as any).mockResolvedValue(session("proj/blk"));
    const res = await useStore.getState().selectSessionById("proj/blk");
    expect(res).toEqual({ ok: true });
    expect(sessionsApi.get).toHaveBeenCalledWith("proj/blk");
    expect(useStore.getState().currentSession?.id).toBe("proj/blk");
    // The fetched session joins the list (picker shows it).
    expect(useStore.getState().sessions.some((s) => s.id === "proj/blk")).toBe(true);
  });

  it("reports not_found for a real 404 (no silent empty session)", async () => {
    (sessionsApi.list as any).mockResolvedValue([session("a")]);
    const err = Object.assign(new Error("Session not found"), { status: 404 });
    (sessionsApi.get as any).mockRejectedValue(err);
    const res = await useStore.getState().selectSessionById("nope");
    expect(res).toEqual({ ok: false, reason: "not_found", message: "Session not found" });
    expect(useStore.getState().currentSession).toBeNull();
  });

  it("reports unreachable — not not_found — when the backend fails to answer", async () => {
    // A proxy 502 / transport error is indistinguishable from a 404 to a bare
    // catch; claiming "not found" told users their work was gone (#93).
    (sessionsApi.list as any).mockResolvedValue([session("a")]);
    (sessionsApi.get as any).mockRejectedValue(new TypeError("fetch failed"));
    const res = await useStore.getState().selectSessionById("alive");
    expect(res).toEqual({ ok: false, reason: "unreachable", message: "fetch failed" });
    expect(useStore.getState().currentSession).toBeNull();
  });

  it("reports unreachable for a backend 5xx", async () => {
    (sessionsApi.list as any).mockResolvedValue([session("a")]);
    const err = Object.assign(new Error("Bad Gateway"), { status: 502 });
    (sessionsApi.get as any).mockRejectedValue(err);
    const res = await useStore.getState().selectSessionById("alive");
    expect(res).toEqual({ ok: false, reason: "unreachable", message: "Bad Gateway" });
  });

  it("no-ops when the session is already current (back/forward, URL sync)", async () => {
    (sessionsApi.list as any).mockResolvedValue([session("a")]);
    await useStore.getState().selectSessionById("a");
    useStore.setState({ messages: [{ id: "m1" } as any] } as any);
    const res = await useStore.getState().selectSessionById("a");
    expect(res).toEqual({ ok: true });
    // Compare-before-dispatch: no re-select, conversation state untouched.
    expect(useStore.getState().messages).toHaveLength(1);
  });
});
