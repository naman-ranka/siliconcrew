import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock the API layer (Tier 1, jsdom, no backend).
vi.mock("@/lib/api", () => {
  return {
    projectsApi: { list: vi.fn().mockResolvedValue([]) },
    sessionsApi: { list: vi.fn().mockResolvedValue([]) },
    threadsApi: {
      list: vi.fn(),
      create: vi.fn(),
      patch: vi.fn().mockResolvedValue({}),
      delete: vi.fn().mockResolvedValue({ status: "deleted" }),
      getHistory: vi.fn().mockResolvedValue([]),
    },
    chatApi: {
      getHistory: vi.fn().mockResolvedValue([]),
      getThreadHistory: vi.fn().mockResolvedValue([]),
      createConnection: vi.fn(),
    },
    workspaceApi: {},
    workbenchApi: {},
  };
});

import { useStore } from "@/lib/store";
import { threadsApi, chatApi } from "@/lib/api";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "claude-sonnet-4-6",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const thread = (id: string, title: string, last = "2026-06-22T10:00:00Z") => ({
  id,
  session_id: "s1",
  title,
  model: null,
  created_at: "2026-06-22T09:00:00Z",
  last_active: last,
});

beforeEach(() => {
  vi.clearAllMocks();
  (chatApi.getThreadHistory as any).mockResolvedValue([]);
  (threadsApi.patch as any).mockResolvedValue({});
  useStore.setState({
    currentSession: SESSION as any,
    threads: [],
    activeThreadId: null,
    messages: [],
    ws: null,
    wsSessionId: null,
    wsThreadId: null,
    codexModels: [],
    agentRuntime: "langchain",
  } as any);
});

describe("chat threads store", () => {
  it("loadThreads sets threads and lands on the newest-active (first) thread", async () => {
    (threadsApi.list as any).mockResolvedValue([thread("s1", "Chat 1", "z"), thread("t2", "Chat 2", "a")]);
    await useStore.getState().loadThreads();
    const s = useStore.getState();
    expect(s.threads.map((t) => t.id)).toEqual(["s1", "t2"]);
    expect(s.activeThreadId).toBe("s1"); // backend returns newest-active first
  });

  it("loadThreads keeps the active thread if it still exists", async () => {
    useStore.setState({ activeThreadId: "t2" } as any);
    (threadsApi.list as any).mockResolvedValue([thread("s1", "Chat 1"), thread("t2", "Chat 2")]);
    await useStore.getState().loadThreads();
    expect(useStore.getState().activeThreadId).toBe("t2");
  });

  it("newThread creates, prepends, activates, and clears the message list", async () => {
    useStore.setState({ threads: [thread("s1", "Chat 1")], activeThreadId: "s1", messages: [{ id: "m" }] } as any);
    (threadsApi.create as any).mockResolvedValue(thread("new", "Chat 2"));
    await useStore.getState().newThread();
    const s = useStore.getState();
    // newThread always passes (sid, title?, model?, runtime?) — a plain
    // newThread() sends undefined for the optionals (native runtime).
    expect(threadsApi.create).toHaveBeenCalledWith("s1", undefined, undefined, undefined);
    expect(s.threads[0].id).toBe("new");
    expect(s.activeThreadId).toBe("new");
    expect(s.messages).toEqual([]);
  });

  it("selectThread switches the active thread and loads its history", async () => {
    useStore.setState({ threads: [thread("s1", "Chat 1"), thread("t2", "Chat 2")], activeThreadId: "s1" } as any);
    (chatApi.getThreadHistory as any).mockResolvedValue([{ role: "user", content: "hi from t2" }]);
    await useStore.getState().selectThread("t2");
    const s = useStore.getState();
    expect(s.activeThreadId).toBe("t2");
    expect(chatApi.getThreadHistory).toHaveBeenCalledWith("s1", "t2");
    expect(s.messages[0].content).toBe("hi from t2");
  });

  it("a stale history response cannot overwrite the newly active thread", async () => {
    let resolveOld!: (value: any[]) => void;
    let resolveNew!: (value: any[]) => void;
    (chatApi.getThreadHistory as any).mockImplementation((_sid: string, tid: string) => (
      new Promise<any[]>((resolve) => {
        if (tid === "t1") resolveOld = resolve;
        else resolveNew = resolve;
      })
    ));
    useStore.setState({
      threads: [thread("t1", "Chat 1"), thread("t2", "Chat 2")],
      activeThreadId: "t1",
    } as any);

    const oldLoad = useStore.getState().loadChatHistory();
    useStore.setState({ activeThreadId: "t2" } as any);
    const newLoad = useStore.getState().loadChatHistory();
    resolveNew([{ role: "user", content: "current thread" }]);
    await newLoad;
    resolveOld([{ role: "user", content: "stale thread" }]);
    await oldLoad;

    expect(useStore.getState().messages.map((message) => message.content)).toEqual(["current thread"]);
  });

  it("new Codex chats use available Terra at low effort", async () => {
    useStore.setState({
      codexModels: [{
        id: "gpt-5.6-terra", label: "GPT-5.6 Terra", provider: "openai",
        available: true, reasoning_efforts: [{ id: "low" }, { id: "medium" }],
      }],
    } as any);
    (threadsApi.create as any).mockResolvedValue({
      ...thread("cx", "Codex chat"), runtime: "codex", model: "gpt-5.6-terra",
    });

    await useStore.getState().newThread("codex");

    expect(threadsApi.create).toHaveBeenCalledWith(
      "s1", undefined, "gpt-5.6-terra", "codex",
    );
    expect(threadsApi.patch).toHaveBeenCalledWith(
      "s1", "cx", { reasoning_effort: "low" },
    );
    expect(useStore.getState().threads[0]).toMatchObject({
      id: "cx", model: "gpt-5.6-terra", reasoning_effort: "low",
    });
  });

  it("selectThread flips agentRuntime to FOLLOW the target thread (URL-selected Codex chat)", async () => {
    useStore.setState({
      threads: [thread("s1", "Chat 1"), { ...thread("cx", "Codex chat"), runtime: "codex" }],
      activeThreadId: "s1",
      agentRuntime: "langchain",
    } as any);
    await useStore.getState().selectThread("cx");
    expect(useStore.getState().agentRuntime).toBe("codex");

    await useStore.getState().selectThread("s1");
    expect(useStore.getState().agentRuntime).toBe("langchain");
  });

  it("deleteThread on the active thread reloads and lands on a remaining thread", async () => {
    useStore.setState({ threads: [thread("s1", "Chat 1"), thread("t2", "Chat 2")], activeThreadId: "t2" } as any);
    (threadsApi.list as any).mockResolvedValue([thread("s1", "Chat 1")]);
    await useStore.getState().deleteThread("t2");
    const s = useStore.getState();
    expect(threadsApi.delete).toHaveBeenCalledWith("s1", "t2");
    expect(s.activeThreadId).toBe("s1");
    expect(s.threads.map((t) => t.id)).toEqual(["s1"]);
  });

  it("renameThread patches the title and updates local state", async () => {
    useStore.setState({ threads: [thread("t2", "Chat 2")], activeThreadId: "t2" } as any);
    await useStore.getState().renameThread("t2", "Counter design");
    expect(threadsApi.patch).toHaveBeenCalledWith("s1", "t2", { title: "Counter design" });
    expect(useStore.getState().threads[0].title).toBe("Counter design");
  });

  it("sendMessage connects with the active thread_id and sends it in the payload", () => {
    const sent: string[] = [];
    const fakeSocket: any = { readyState: 0, send: (m: string) => sent.push(m), close: vi.fn(), onopen: null };
    (chatApi.createConnection as any).mockReturnValue(fakeSocket);
    useStore.setState({ threads: [thread("t2", "Chat 2")], activeThreadId: "t2" } as any);

    useStore.getState().sendMessage("build a counter");
    // Connection opened against the active thread.
    expect(chatApi.createConnection).toHaveBeenCalledWith("s1", "t2");
    expect(useStore.getState().wsThreadId).toBe("t2");
    // On open, the message carries the thread_id.
    fakeSocket.onopen?.();
    const payload = JSON.parse(sent[0]);
    expect(payload).toMatchObject({ message: "build a counter", thread_id: "t2" });
  });

  it("sendMessage falls back to session id as the default thread (Chat 1)", () => {
    const fakeSocket: any = { readyState: 0, send: vi.fn(), close: vi.fn(), onopen: null };
    (chatApi.createConnection as any).mockReturnValue(fakeSocket);
    // Reset the streaming state the previous test's un-terminated turn left
    // behind — a message sent mid-stream now queues instead of connecting.
    useStore.setState({ threads: [], activeThreadId: null, isStreaming: false, streamingMessage: null, ws: null } as any);
    useStore.getState().sendMessage("hello");
    expect(chatApi.createConnection).toHaveBeenCalledWith("s1", "s1");
  });
});
