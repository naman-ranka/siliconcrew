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
  it("appends an 'interrupted' marker when the last assistant turn ends on a tool call", async () => {
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
    expect((lastBlock as any).content).toMatch(/interrupted/i);
  });

  it("does NOT add a marker when the turn ends with a text summary", async () => {
    (chatApi.getHistory as any).mockResolvedValue([
      { role: "assistant", content: "All done — 8/8 tests pass.", tool_calls: [], tool_results: [] },
    ]);

    await useStore.getState().loadChatHistory();

    const msgs = useStore.getState().messages;
    const last = msgs[msgs.length - 1];
    const texts = last.blocks.filter((b: any) => b.type === "text");
    expect(texts.every((b: any) => !/interrupted/i.test(b.content))).toBe(true);
  });
});
