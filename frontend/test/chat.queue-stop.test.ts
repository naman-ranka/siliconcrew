import { describe, it, expect, beforeEach, vi } from "vitest";

// One fake socket the store's createConnection hands back; tests drive its
// on* handlers to simulate frames (same harness as chat.ws-drop.test.ts).
const fake: any = { readyState: 0, onopen: null, onmessage: null, onerror: null, onclose: null, send: vi.fn(), close: vi.fn() };

vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: { list: vi.fn().mockResolvedValue([]) },
  threadsApi: { list: vi.fn().mockResolvedValue([]), getHistory: vi.fn().mockResolvedValue([]) },
  modelsApi: { list: vi.fn().mockResolvedValue({ models: [], default: "x" }) },
  chatApi: {
    createConnection: vi.fn(() => fake),
    getHistory: vi.fn().mockResolvedValue([]),
    getThreadHistory: vi.fn().mockResolvedValue([]),
  },
  workspaceApi: {
    listFiles: vi.fn().mockResolvedValue([]),
    listWaveforms: vi.fn().mockResolvedValue([]),
    listLayouts: vi.fn().mockResolvedValue([]),
    listSchematics: vi.fn().mockResolvedValue([]),
    listSynthesisRuns: vi.fn().mockResolvedValue([]),
  },
  workbenchApi: { listRuns: vi.fn().mockResolvedValue([]) },
  keysApi: {},
}));

import { useStore, MAX_QUEUED_MESSAGES } from "@/lib/store";

const frame = (obj: unknown) => ({ data: JSON.stringify(obj) });
const flush = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  vi.clearAllMocks();
  fake.onopen = fake.onmessage = fake.onerror = fake.onclose = null;
  fake.readyState = 0;
  useStore.setState({
    currentSession: { id: "s1", name: "s1" } as any,
    messages: [], queuedMessages: [], activeThreadId: null,
    ws: null, wsSessionId: null, wsThreadId: null,
    isStreaming: false, streamingMessage: null, chatError: null, chatErrorCode: null,
    stopPending: false, activeTurnId: null,
  } as any);
});

describe("message queue while streaming", () => {
  it("a message typed mid-stream is queued (not sent) and is removable", () => {
    useStore.getState().sendMessage("first");
    expect(useStore.getState().isStreaming).toBe(true);

    useStore.getState().sendMessage("follow-up");
    const st = useStore.getState();
    expect(st.queuedMessages).toHaveLength(1);
    expect(st.queuedMessages[0].content).toBe("follow-up");
    // Not added to the transcript, not sent on the wire.
    expect(st.messages.filter((m) => m.content === "follow-up")).toHaveLength(0);

    useStore.getState().removeQueuedMessage(st.queuedMessages[0].id);
    expect(useStore.getState().queuedMessages).toHaveLength(0);
  });

  it("queued message dispatches automatically after `done`", async () => {
    useStore.getState().sendMessage("first");
    const sock = useStore.getState().ws as any;
    useStore.getState().sendMessage("follow-up");

    sock.onmessage(frame({ type: "text", content: "answer one" }));
    sock.onmessage(frame({ type: "done", tokens: { input: 1, output: 1 } }));
    await flush();

    const st = useStore.getState();
    expect(st.queuedMessages).toHaveLength(0);
    // The follow-up became a real user turn and a new stream started.
    expect(st.messages.some((m) => m.role === "user" && m.content === "follow-up")).toBe(true);
    expect(st.isStreaming).toBe(true);
  });

  it("queued messages dispatch in order, one per completed turn", async () => {
    useStore.getState().sendMessage("first");
    let sock = useStore.getState().ws as any;
    useStore.getState().sendMessage("second");
    useStore.getState().sendMessage("third");
    expect(useStore.getState().queuedMessages.map((q) => q.content)).toEqual(["second", "third"]);

    sock.onmessage(frame({ type: "done", tokens: {} }));
    await flush();
    expect(useStore.getState().queuedMessages.map((q) => q.content)).toEqual(["third"]);

    sock = useStore.getState().ws as any;
    sock.onmessage(frame({ type: "done", tokens: {} }));
    await flush();
    expect(useStore.getState().queuedMessages).toHaveLength(0);
  });
});

describe("stop → server-confirmed `stopped` frame", () => {
  it("stop sends a stop frame (socket stays open) and `stopped` finalizes with a marker", () => {
    useStore.getState().sendMessage("long task");
    const sock = useStore.getState().ws as any;
    sock.readyState = WebSocket.OPEN;
    sock.onmessage(frame({ type: "text", content: "working on it" }));

    useStore.getState().stopStreaming();
    // Cancel is server-side now: a control frame, not a socket teardown —
    // scoped to the active turn by id.
    const stopPayload = JSON.parse(sock.send.mock.calls.at(-1)![0]);
    expect(stopPayload.type).toBe("stop");
    expect(stopPayload.turn_id).toBe(useStore.getState().activeTurnId);
    expect(sock.close).not.toHaveBeenCalled();
    expect(useStore.getState().isStreaming).toBe(true); // awaiting server confirm
    expect(useStore.getState().stopPending).toBe(true); // "Stopping…" state

    // Duplicate stop clicks are no-ops while the confirm is pending.
    const sends = sock.send.mock.calls.length;
    useStore.getState().stopStreaming();
    expect(sock.send.mock.calls.length).toBe(sends);

    sock.onmessage(frame({ type: "stopped", tokens: { input: 1, output: 1 } }));
    const st = useStore.getState();
    expect(st.isStreaming).toBe(false);
    expect(st.stopPending).toBe(false); // confirmed — button resets
    expect(st.streamingMessage).toBeNull();
    const last = st.messages[st.messages.length - 1];
    expect(last.role).toBe("assistant");
    expect(last.content).toContain("[Stopped]");
    expect(st.ws).toBeTruthy(); // reusable for the next message
    expect(st.chatErrorCode).toBeNull(); // a stop is not an error
  });

  it("a `busy` error frame is informational and does not end the stream", () => {
    useStore.getState().sendMessage("long task");
    const sock = useStore.getState().ws as any;
    sock.onmessage(frame({ type: "error", code: "busy", error: "A response is already in progress." }));
    const st = useStore.getState();
    expect(st.isStreaming).toBe(true);
    expect(st.chatError).toBeNull();
  });

  it("the user message carries a turn_id and frames from other turns are ignored", () => {
    useStore.getState().sendMessage("hi");
    const sock = useStore.getState().ws as any;
    sock.onopen?.();
    const payload = JSON.parse(sock.send.mock.calls[0][0]);
    expect(payload.turn_id).toBeTruthy();
    expect(payload.turn_id).toBe(useStore.getState().activeTurnId);

    // A stale frame from a previous turn must not touch this turn's state…
    sock.onmessage(frame({ type: "text", content: "ghost", turn_id: "some-old-turn" }));
    expect(useStore.getState().streamingMessage?.content ?? "").toBe("");
    // …while frames tagged with THIS turn (and untagged legacy frames) apply.
    sock.onmessage(frame({ type: "text", content: "real", turn_id: payload.turn_id }));
    expect(useStore.getState().streamingMessage?.content).toBe("real");
  });

  it("the queue is capped at MAX_QUEUED_MESSAGES", () => {
    useStore.getState().sendMessage("first");
    for (let i = 0; i < MAX_QUEUED_MESSAGES + 3; i++) {
      useStore.getState().sendMessage(`q${i}`);
    }
    expect(useStore.getState().queuedMessages).toHaveLength(MAX_QUEUED_MESSAGES);
  });

  it("`done` resets streaming state even if the local placeholder is missing", () => {
    // Regression: the composer showed Stop forever after a turn ended when the
    // placeholder had been lost (odd refresh/reconnect paths) because the
    // terminal frame was skipped by the placeholder guard.
    useStore.getState().sendMessage("hi");
    const sock = useStore.getState().ws as any;
    useStore.setState({ streamingMessage: null } as any);
    sock.onmessage(frame({ type: "done", tokens: {} }));
    expect(useStore.getState().isStreaming).toBe(false);
    expect(useStore.getState().stopPending).toBe(false);
  });

  it("cumulative text_delta frames render into the streaming message", () => {
    useStore.getState().sendMessage("hi");
    const sock = useStore.getState().ws as any;
    sock.onmessage(frame({ type: "text_delta", content: "hel" }));
    expect(useStore.getState().streamingMessage?.content).toBe("hel");
    sock.onmessage(frame({ type: "text_delta", content: "hello" }));
    expect(useStore.getState().streamingMessage?.content).toBe("hello");
    sock.onmessage(frame({ type: "text", content: "hello" }));
    sock.onmessage(frame({ type: "done", tokens: {} }));
    const last = useStore.getState().messages.at(-1)!;
    expect(last.content).toBe("hello");
  });
});
