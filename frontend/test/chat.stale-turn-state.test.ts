import { describe, it, expect, beforeEach, vi } from "vitest";

// Regression: a chatError banner (or a stuck isStreaming/Stop button) from
// one conversation must never leak into a DIFFERENT session/thread after
// navigation. This was the "error banner rendered above unrelated messages"
// and "Stop button stuck after switching away" bug.
vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn(),
  },
  threadsApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({ status: "deleted" }),
  },
  chatApi: {
    getHistory: vi.fn().mockResolvedValue([]),
    getThreadHistory: vi.fn().mockResolvedValue([]),
    createConnection: vi.fn(),
  },
  workspaceApi: {
    listFiles: vi.fn().mockResolvedValue([]),
    listWaveforms: vi.fn().mockResolvedValue([]),
    listLayouts: vi.fn().mockResolvedValue({ layouts: [], missing_binaries: [] }),
    listSchematics: vi.fn().mockResolvedValue([]),
    listSynthesisRuns: vi.fn().mockResolvedValue([]),
  },
  workbenchApi: { listRuns: vi.fn().mockResolvedValue([]) },
  keysApi: {},
}));

import { useStore } from "@/lib/store";
import { threadsApi } from "@/lib/api";

const SESSION_A = { id: "sA", name: "A", model_name: "gemini-3.5-flash", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 };
const SESSION_B = { id: "sB", name: "B", model_name: "gemini-3.5-flash", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 };

const dirtyTurnState = () => ({
  currentSession: SESSION_A as any,
  chatError: "Error code: 400 - stale failure from session A",
  chatErrorCode: "some_code",
  isStreaming: true,
  streamingMessage: { id: "m1", role: "assistant" as const, content: "partial", tool_calls: [], tool_results: [], blocks: [] },
  stopPending: true,
  activeTurnId: "turn-from-session-a",
});

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({ ...dirtyTurnState(), threads: [], activeThreadId: null } as any);
});

describe("per-turn chat state resets on navigation (no cross-conversation leakage)", () => {
  it("selectSession clears chatError/isStreaming/stopPending/activeTurnId", async () => {
    await useStore.getState().selectSession(SESSION_B as any);
    const s = useStore.getState();
    expect(s.chatError).toBeNull();
    expect(s.chatErrorCode).toBeNull();
    expect(s.isStreaming).toBe(false);
    expect(s.streamingMessage).toBeNull();
    expect(s.stopPending).toBe(false);
    expect(s.activeTurnId).toBeNull();
  });

  it("newThread clears stale turn state from the previous thread", async () => {
    (threadsApi.create as any).mockResolvedValue({ id: "t2", session_id: "sA", title: "Chat 2", model: null, created_at: null, last_active: null });
    await useStore.getState().newThread();
    const s = useStore.getState();
    expect(s.chatError).toBeNull();
    expect(s.isStreaming).toBe(false);
    expect(s.stopPending).toBe(false);
    expect(s.activeTurnId).toBeNull();
  });

  it("selectThread clears stale turn state from the previous thread", async () => {
    useStore.setState({ activeThreadId: "t1" } as any);
    await useStore.getState().selectThread("t2");
    const s = useStore.getState();
    expect(s.chatError).toBeNull();
    expect(s.isStreaming).toBe(false);
    expect(s.stopPending).toBe(false);
    expect(s.activeTurnId).toBeNull();
  });

  it("deleteThread clears stale turn state when the deleted thread was active", async () => {
    useStore.setState({
      threads: [
        { id: "t1", session_id: "sA", title: "Chat 1", model: null, created_at: null, last_active: null },
        { id: "t2", session_id: "sA", title: "Chat 2", model: null, created_at: null, last_active: null },
      ],
      activeThreadId: "t1",
    } as any);
    await useStore.getState().deleteThread("t1");
    const s = useStore.getState();
    expect(s.chatError).toBeNull();
    expect(s.isStreaming).toBe(false);
    expect(s.stopPending).toBe(false);
    expect(s.activeTurnId).toBeNull();
  });
});
