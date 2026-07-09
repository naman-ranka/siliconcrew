import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: { list: vi.fn().mockResolvedValue([]) },
  threadsApi: { patch: vi.fn().mockResolvedValue({}) },
  modelsApi: { list: vi.fn() },
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
}));

import { useStore } from "@/lib/store";
import { modelsApi, threadsApi } from "@/lib/api";

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "gemini-3-flash-preview",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const MODELS = [
  { id: "claude-opus-4-6", label: "Claude Opus 4.6", provider: "anthropic", tier: "capable", available: true },
  { id: "gpt-5.4", label: "GPT-5.4", provider: "openai", tier: "capable", available: false },
  { id: "gemini-3-flash-preview", label: "Gemini 3 Flash", provider: "gemini", tier: "fast", available: true },
];

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({
    currentSession: SESSION as any,
    threads: [{ id: "s1", session_id: "s1", title: "Chat 1", model: null, created_at: null, last_active: null }],
    activeThreadId: "s1",
    models: [],
    modelsLoaded: false,
  } as any);
});

describe("model picker store", () => {
  it("loadModels fetches once and caches the registry with availability", async () => {
    (modelsApi.list as any).mockResolvedValue({ models: MODELS, default: "gemini-3-flash-preview" });
    await useStore.getState().loadModels();
    expect(useStore.getState().models).toHaveLength(3);
    expect(useStore.getState().models.find((m) => m.id === "gpt-5.4")?.available).toBe(false);
    // Cached: a second call does not re-fetch.
    await useStore.getState().loadModels();
    expect(modelsApi.list).toHaveBeenCalledTimes(1);
  });

  it("setActiveThreadModel persists on the active thread (PATCH) and updates state", async () => {
    await useStore.getState().setActiveThreadModel("claude-opus-4-6");
    expect(threadsApi.patch).toHaveBeenCalledWith("s1", "s1", { model: "claude-opus-4-6" });
    expect(useStore.getState().threads.find((t) => t.id === "s1")?.model).toBe("claude-opus-4-6");
  });

  it("setActiveThreadModel targets the active thread (different chat keeps its own model)", async () => {
    useStore.setState({
      threads: [
        { id: "s1", session_id: "s1", title: "Chat 1", model: "gemini-3-flash-preview", created_at: null, last_active: null },
        { id: "t2", session_id: "s1", title: "Chat 2", model: null, created_at: null, last_active: null },
      ],
      activeThreadId: "t2",
    } as any);
    await useStore.getState().setActiveThreadModel("claude-opus-4-6");
    expect(threadsApi.patch).toHaveBeenCalledWith("s1", "t2", { model: "claude-opus-4-6" });
    const s = useStore.getState();
    expect(s.threads.find((t) => t.id === "t2")?.model).toBe("claude-opus-4-6");
    // Chat 1 keeps its own model.
    expect(s.threads.find((t) => t.id === "s1")?.model).toBe("gemini-3-flash-preview");
  });
});
