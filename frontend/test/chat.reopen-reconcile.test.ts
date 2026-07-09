import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: { list: vi.fn().mockResolvedValue([]) },
  threadsApi: { list: vi.fn().mockResolvedValue([]), getHistory: vi.fn() },
  modelsApi: { list: vi.fn().mockResolvedValue({ models: [], default: "x" }) },
  chatApi: { getHistory: vi.fn(), getThreadHistory: vi.fn() },
  workspaceApi: {},
  workbenchApi: {},
  keysApi: {},
}));

import { useStore } from "@/lib/store";
import { chatApi } from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({ currentSession: { id: "s1", name: "s1" } as any, activeThreadId: null, messages: [] } as any);
});

describe("reopen reconciliation of an interrupted trace (F4)", () => {
  it("appends a connection-lost marker when the last assistant turn ends on a tool call", async () => {
    (chatApi.getHistory as any).mockResolvedValue([
      { role: "user", content: "synthesize it", tool_calls: [], tool_results: [] },
      {
        role: "assistant",
        content: "",
        tool_calls: [{ id: "t1", name: "wait_for_synthesis", args: {} }],
        tool_results: [{ tool_call_id: "t1", status: "running", content: "running" }],
      },
    ]);

    await useStore.getState().loadChatHistory();

    const msgs = useStore.getState().messages;
    const last = msgs[msgs.length - 1];
    const lastBlock = last.blocks[last.blocks.length - 1];
    expect(lastBlock.type).toBe("text");
    // Honest phrasing: the run may STILL be running server-side after a drop,
    // so the marker must not declare it dead.
    expect((lastBlock as any).content).toMatch(/connection was lost/i);
    expect((lastBlock as any).content).toMatch(/may still be running/i);
  });

  it("points at the Runs panel only for a synthesis dispatch (X2A-5)", async () => {
    (chatApi.getHistory as any).mockResolvedValue([
      {
        role: "assistant",
        content: "",
        tool_calls: [{ id: "t1", name: "start_synthesis", args: {} }],
        tool_results: [{ tool_call_id: "t1", status: "running", content: "running" }],
      },
    ]);
    await useStore.getState().loadChatHistory();
    const last = useStore.getState().messages.at(-1)!;
    const content = (last.blocks.at(-1) as any).content as string;
    expect(content).toMatch(/synthesis may still be running/i);
    expect(content).toMatch(/Runs panel/i);
  });

  it("does NOT point at Runs for an ephemeral sim — says results are inline (X2A-5)", async () => {
    (chatApi.getHistory as any).mockResolvedValue([
      {
        role: "assistant",
        content: "",
        tool_calls: [{ id: "t1", name: "simulation_tool", args: {} }],
        tool_results: [{ tool_call_id: "t1", status: "running", content: "running" }],
      },
    ]);
    await useStore.getState().loadChatHistory();
    const content = (useStore.getState().messages.at(-1)!.blocks.at(-1) as any).content as string;
    expect(content).toMatch(/connection was lost/i);
    expect(content).not.toMatch(/Runs panel/i);
    expect(content).toMatch(/inline only/i);
  });

  it("does NOT add a marker when the turn ends with a text summary", async () => {
    (chatApi.getHistory as any).mockResolvedValue([
      { role: "assistant", content: "All done — 8/8 tests pass.", tool_calls: [], tool_results: [] },
    ]);

    await useStore.getState().loadChatHistory();

    const msgs = useStore.getState().messages;
    const last = msgs[msgs.length - 1];
    const texts = last.blocks.filter((b: any) => b.type === "text");
    expect(texts.every((b: any) => !/connection was lost/i.test(b.content))).toBe(true);
  });
});
