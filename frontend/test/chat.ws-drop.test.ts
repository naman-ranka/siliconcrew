import { describe, it, expect, beforeEach, vi } from "vitest";

// One fake socket the store's createConnection hands back; tests drive its
// on* handlers to simulate frames + drops.
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
    listLayouts: vi.fn().mockResolvedValue({ layouts: [], missing_binaries: [] }),
    listSchematics: vi.fn().mockResolvedValue([]),
    listSynthesisRuns: vi.fn().mockResolvedValue([]),
  },
  workbenchApi: { listRuns: vi.fn().mockResolvedValue([]) },
  keysApi: {},
}));

import { useStore } from "@/lib/store";

const frame = (obj: unknown) => ({ data: JSON.stringify(obj) });

beforeEach(() => {
  vi.clearAllMocks();
  fake.onopen = fake.onmessage = fake.onerror = fake.onclose = null;
  fake.readyState = 0;
  useStore.setState({
    currentSession: { id: "s1", name: "s1" } as any,
    messages: [], activeThreadId: null,
    ws: null, wsSessionId: null, wsThreadId: null,
    isStreaming: false, streamingMessage: null, chatError: null, chatErrorCode: null,
  } as any);
});

describe("chat WS unexpected-drop recovery (F1/F2)", () => {
  it("close WITHOUT a terminal frame: exits streaming, preserves partial, surfaces ws_dropped", () => {
    useStore.getState().sendMessage("design a mux");
    expect(useStore.getState().isStreaming).toBe(true);
    const sock = useStore.getState().ws as any;
    expect(sock).toBeTruthy();

    // stream a tool call so there's a partial trace to preserve
    sock.onmessage(frame({ type: "tool_call", tool: { id: "t1", name: "linter_tool" } }));
    // unexpected drop (no done/error frame)
    sock.onclose();

    const st = useStore.getState();
    expect(st.isStreaming).toBe(false);          // no perpetual hang
    expect(st.streamingMessage).toBeNull();
    expect(st.chatErrorCode).toBe("ws_dropped");  // surfaced, not silent
    const last = st.messages[st.messages.length - 1];
    expect(last.role).toBe("assistant");
    expect((last.blocks || []).some((b: any) => b.type === "tool")).toBe(true); // partial kept
  });

  it("done frame → clean finish, and a following close does NOT raise ws_dropped", () => {
    useStore.getState().sendMessage("hi");
    const sock = useStore.getState().ws as any;
    sock.onmessage(frame({ type: "text", content: "hello" }));
    sock.onmessage(frame({ type: "done", tokens: { input: 1, output: 1 } }));
    sock.onclose(); // clean close after done

    const st = useStore.getState();
    expect(st.isStreaming).toBe(false);
    expect(st.chatError).toBeNull();
    expect(st.chatErrorCode).toBeNull();
  });

  it("ping frames are ignored (keepalive) and don't end the stream", () => {
    useStore.getState().sendMessage("hi");
    const sock = useStore.getState().ws as any;
    sock.onmessage(frame({ type: "ping" }));
    expect(useStore.getState().isStreaming).toBe(true);
  });
});
