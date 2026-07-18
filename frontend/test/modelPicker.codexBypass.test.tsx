import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  modelsApi: {
    list: vi.fn().mockResolvedValue({ models: [], default: "gemini-3.5-flash", codex_models: [], codex_default: "gpt-5.3-codex" }),
  },
  codexApi: {
    models: vi.fn().mockResolvedValue({ models: [], default: "gpt-5.6-sol", source: "fallback" }),
  },
  threadsApi: { patch: vi.fn().mockResolvedValue({}) },
}));

import { codexApi } from "@/lib/api";
import { useStore } from "@/lib/store";
import { CodexModelPicker } from "@/components/chat/CodexModelPicker";

const SESSION = {
  id: "s1", name: "s1", model_name: "gpt-5.3-codex", project_id: null,
  created_at: null, updated_at: null, total_tokens: 0, total_cost: 0,
};

// The Codex picker renders its OWN registry (codexModels), maintained
// separately from the native catalog — `models` here is a decoy that must
// never show up.
const NATIVE_MODELS = [
  { id: "claude-opus-4-6", label: "Claude Opus 4.6", provider: "anthropic" as const, tier: "capable" as const, available: true },
];

const CODEX_MODELS = [
  { id: "gpt-5.3-codex", label: "GPT-5.3 Codex", provider: "openai" as const, tier: "capable" as const, available: false },
  { id: "gpt-5.5", label: "GPT-5.5", provider: "openai" as const, tier: "capable" as const, available: false },
];

function setup(overrides: Partial<{ codexAccountConnected: boolean }>) {
  useStore.setState({
    currentSession: SESSION as any,
    threads: [{ id: "s1", session_id: "s1", title: "Chat 1", model: "gpt-5.3-codex", runtime: "codex", created_at: null, last_active: null }],
    activeThreadId: "s1",
    models: NATIVE_MODELS as any,
    codexModels: CODEX_MODELS as any,
    codexDefaultModel: "gpt-5.3-codex",
    modelsLoaded: true,
    agentRuntime: "codex",
    codexAccountConnected: false,
    ...overrides,
  } as any);
}

describe("CodexModelPicker — separate SDK-backed registry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(codexApi.models).mockResolvedValue({ models: [], default: "gpt-5.6-sol", source: "fallback" });
  });

  it("renders ONLY the codex registry — native catalog models never appear", () => {
    setup({});
    render(<CodexModelPicker />);
    fireEvent.click(screen.getByRole("button", { name: /Change model/i }));

    expect(screen.getByRole("menuitemradio", { name: /GPT-5.5/i })).toBeInTheDocument();
    expect(screen.queryByText(/Claude Opus/i)).toBeNull();
  });

  it("greys out models as 'needs key' when no ChatGPT account is connected", () => {
    setup({ codexAccountConnected: false });
    render(<CodexModelPicker />);
    fireEvent.click(screen.getByRole("button", { name: /Change model/i }));

    const gpt55 = screen.getByRole("menuitemradio", { name: /GPT-5.5/i });
    expect(gpt55).toBeDisabled();
    expect(screen.getAllByText("needs key").length).toBeGreaterThan(0);
  });

  it("does not guess model access from the account connection alone", () => {
    setup({ codexAccountConnected: true });
    render(<CodexModelPicker />);
    fireEvent.click(screen.getByRole("button", { name: /Change model/i }));

    const gpt55 = screen.getByRole("menuitemradio", { name: /GPT-5.5/i });
    expect(gpt55).toBeDisabled();
    expect(screen.getAllByText("needs key").length).toBeGreaterThan(0);
    expect(screen.getByText("Using your ChatGPT account.")).toBeInTheDocument();
  });

  it("renders SDK-discovered models and their reasoning controls", async () => {
    setup({ codexAccountConnected: true });
    useStore.setState({
      threads: [{ id: "s1", session_id: "s1", title: "Chat 1", model: "gpt-5.6-sol", runtime: "codex", created_at: null, last_active: null }] as any,
    });
    vi.mocked(codexApi.models).mockResolvedValue({
      models: [{
        id: "gpt-5.6-sol", label: "GPT-5.6 Sol", provider: "openai", available: true,
        default_reasoning_effort: "high",
        reasoning_efforts: [{ id: "medium" }, { id: "high", description: "Deep reasoning" }],
      }],
      default: "gpt-5.6-sol",
      source: "sdk",
    });
    render(<CodexModelPicker />);

    await waitFor(() => expect(screen.getByRole("button", { name: /GPT-5.6 Sol/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Change model/i }));
    expect(screen.getByRole("menuitemradio", { name: /GPT-5.6 Sol/i })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "high" })).toHaveAttribute("aria-pressed", "true");
  });

  it("falls back to the codex default for a thread with no pinned model", () => {
    setup({});
    useStore.setState({
      threads: [{ id: "s1", session_id: "s1", title: "Chat 1", model: null, runtime: "codex", created_at: null, last_active: null }] as any,
    });
    render(<CodexModelPicker />);
    expect(screen.getByRole("button", { name: /GPT-5.3 Codex/i })).toBeInTheDocument();
  });
});
