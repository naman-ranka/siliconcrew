import { describe, it, expect, beforeEach, vi } from "vitest";
import { render as rtlRender, screen, fireEvent, waitFor } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";

// The app wraps everything in TooltipProvider (app/layout.tsx); mirror that here.
const render = (ui: React.ReactElement) => rtlRender(<TooltipProvider>{ui}</TooltipProvider>);

// Mock auth so we can drive each mode.
vi.mock("@/lib/auth", () => ({ useAuth: vi.fn() }));

// Mock the API layer (the store imports it at module load; the modal uses keysApi).
vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: { list: vi.fn().mockResolvedValue([]) },
  threadsApi: { patch: vi.fn().mockResolvedValue({}) },
  modelsApi: { list: vi.fn().mockResolvedValue({ models: [], default: "gemini-3-flash-preview" }) },
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
  keysApi: { list: vi.fn(), save: vi.fn(), remove: vi.fn() },
}));

import { SettingsModal } from "@/components/settings/SettingsModal";
import { useStore } from "@/lib/store";
import { useAuth } from "@/lib/auth";
import { keysApi, modelsApi } from "@/lib/api";

function setAuth(over: Partial<{ enabled: boolean; status: string }>) {
  (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    enabled: false,
    status: "anonymous",
    user: null,
    token: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    ...over,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({ settingsOpen: true, models: [], modelsLoaded: true, toasts: [] } as any);
});

describe("SettingsModal — mode-adaptive", () => {
  it("self-host: shows env-key guidance and NO entry fields", async () => {
    setAuth({ enabled: false, status: "anonymous" });
    useStore.setState({ models: [{ id: "g", label: "G", provider: "gemini", tier: "fast", available: true }] as any });
    render(<SettingsModal />);

    expect(screen.getByTestId("byok-section").getAttribute("data-mode")).toBe("self_host");
    expect(screen.getByText(/environment keys/i)).toBeInTheDocument();
    // Per-provider env status derived from model availability.
    expect(screen.getByTestId("byok-env-gemini")).toHaveTextContent(/configured/i);
    expect(screen.getByTestId("byok-env-openai")).toHaveTextContent(/not set/i);
    // No password entry fields in local mode.
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });

  it("hosted + signed out: shows a sign-in prompt", async () => {
    setAuth({ enabled: true, status: "anonymous" });
    render(<SettingsModal />);
    expect(screen.getByTestId("byok-signin")).toBeInTheDocument();
    expect(keysApi.list).not.toHaveBeenCalled();
  });

  it("hosted + signed in: lists providers, marks configured, save → toast + models refetch", async () => {
    setAuth({ enabled: true, status: "signed_in" });
    (keysApi.list as any).mockResolvedValue({ providers: ["anthropic"] });
    (keysApi.save as any).mockResolvedValue({ ok: true, provider: "openai", stored: true });

    render(<SettingsModal />);

    await waitFor(() => expect(screen.getByTestId("byok-row-anthropic")).toBeInTheDocument());
    expect(screen.getByTestId("byok-configured-anthropic")).toBeInTheDocument();
    const modelsCallsBefore = (modelsApi.list as any).mock.calls.length;

    // Save an OpenAI key.
    const input = screen.getByLabelText("OpenAI API key") as HTMLInputElement;
    expect(input.type).toBe("password");
    fireEvent.change(input, { target: { value: "sk-openai-123" } });
    fireEvent.click(screen.getByTestId("byok-save-openai"));

    await waitFor(() => expect(keysApi.save).toHaveBeenCalledWith("openai", "sk-openai-123"));
    // Toast pushed + picker availability refetched.
    await waitFor(() => expect(useStore.getState().toasts.some((t) => /saved/i.test(t.title))).toBe(true));
    await waitFor(() => expect((modelsApi.list as any).mock.calls.length).toBeGreaterThan(modelsCallsBefore));
    // The secret is cleared from the input after save (never retained in state).
    await waitFor(() =>
      expect((screen.getByLabelText("OpenAI API key") as HTMLInputElement).value).toBe("")
    );
  });

  it("hosted: remove is confirm-gated (no DELETE until confirmed)", async () => {
    setAuth({ enabled: true, status: "signed_in" });
    (keysApi.list as any).mockResolvedValue({ providers: ["anthropic"] });
    (keysApi.remove as any).mockResolvedValue({ ok: true, provider: "anthropic", deleted: true });

    render(<SettingsModal />);
    await waitFor(() => expect(screen.getByTestId("byok-remove-anthropic")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("byok-remove-anthropic"));
    expect(keysApi.remove).not.toHaveBeenCalled(); // confirm first
    fireEvent.click(screen.getByTestId("byok-remove-confirm-anthropic"));
    await waitFor(() => expect(keysApi.remove).toHaveBeenCalledWith("anthropic"));
  });

  it("hosted, vault off (503): graceful message, no CRUD rows", async () => {
    setAuth({ enabled: true, status: "signed_in" });
    (keysApi.list as any).mockRejectedValue(Object.assign(new Error("vault off"), { status: 503 }));

    render(<SettingsModal />);
    await waitFor(() => expect(screen.getByTestId("byok-section").getAttribute("data-mode")).toBe("vault_off"));
    expect(screen.queryByTestId("byok-row-anthropic")).toBeNull();
  });
});
