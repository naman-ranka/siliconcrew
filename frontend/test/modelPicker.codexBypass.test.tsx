import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  modelsApi: { list: vi.fn().mockResolvedValue({ models: [], default: "gemini-3.5-flash" }) },
  threadsApi: { patch: vi.fn().mockResolvedValue({}) },
}));

import { useStore } from "@/lib/store";
import { ModelPicker } from "@/components/chat/ModelPicker";

const SESSION = {
  id: "s1", name: "s1", model_name: "gpt-5.3-codex", project_id: null,
  created_at: null, updated_at: null, total_tokens: 0, total_cost: 0,
};

const MODELS = [
  { id: "gpt-5.3-codex", label: "GPT-5.3 Codex", provider: "openai" as const, tier: "capable" as const, available: false },
  { id: "gpt-5.5", label: "GPT-5.5", provider: "openai" as const, tier: "capable" as const, available: false },
  { id: "claude-opus-4-6", label: "Claude Opus 4.6", provider: "anthropic" as const, tier: "capable" as const, available: true },
];

function setup(overrides: Partial<{ agentRuntime: "langchain" | "codex"; codexAccountConnected: boolean }>) {
  useStore.setState({
    currentSession: SESSION as any,
    threads: [{ id: "s1", session_id: "s1", title: "Chat 1", model: "gpt-5.3-codex", created_at: null, last_active: null }],
    activeThreadId: "s1",
    models: MODELS as any,
    modelsLoaded: true,
    agentRuntime: "codex",
    codexAccountConnected: false,
    ...overrides,
  } as any);
}

describe("ModelPicker — Codex ChatGPT-account key bypass", () => {
  beforeEach(() => vi.clearAllMocks());

  it("greys out OpenAI models as 'needs key' when no ChatGPT account is connected", () => {
    setup({ codexAccountConnected: false });
    render(<ModelPicker />);
    fireEvent.click(screen.getByRole("button", { name: /Change model/i }));

    const gpt55 = screen.getByRole("menuitemradio", { name: /GPT-5.5/i });
    expect(gpt55).toBeDisabled();
    expect(screen.getAllByText("needs key").length).toBeGreaterThan(0);
  });

  it("does NOT grey out OpenAI models once a ChatGPT account is connected — codex_runtime skips key resolution entirely", () => {
    setup({ codexAccountConnected: true });
    render(<ModelPicker />);
    fireEvent.click(screen.getByRole("button", { name: /Change model/i }));

    const gpt55 = screen.getByRole("menuitemradio", { name: /GPT-5.5/i });
    expect(gpt55).not.toBeDisabled();
    expect(screen.queryByText("needs key")).toBeNull();
  });
});
