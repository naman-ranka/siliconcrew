import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Store imports the API layer at module load.
vi.mock("@/lib/api", () => ({
  projectsApi: { list: vi.fn().mockResolvedValue([]) },
  sessionsApi: { list: vi.fn().mockResolvedValue([]) },
  threadsApi: {},
  modelsApi: { list: vi.fn().mockResolvedValue({ models: [], default: "x" }) },
  chatApi: {},
  workspaceApi: {},
  workbenchApi: {},
  keysApi: { list: vi.fn(), save: vi.fn(), remove: vi.fn() },
}));
// Isolate ChatArea's banner logic from the heavy children.
vi.mock("@/components/chat/MessageList", () => ({ MessageList: () => null }));
vi.mock("@/components/chat/ChatInput", () => ({ ChatInput: () => null }));
vi.mock("@/components/chat/ThreadSwitcher", () => ({ ThreadSwitcher: () => null }));

import { ChatArea } from "@/components/chat/ChatArea";
import { useStore } from "@/lib/store";

beforeEach(() => {
  useStore.setState({ currentSession: null, chatError: null, chatErrorCode: null, settingsOpen: false } as any);
});

describe("chat 'Add an API key' CTA (Slice 3)", () => {
  it("a no_key WS error renders the CTA; clicking it opens Settings and clears the error", () => {
    useStore.setState({ chatError: "No key available for provider 'anthropic'.", chatErrorCode: "no_key" } as any);
    render(<ChatArea />);

    expect(screen.getByTestId("chat-no-key-cta")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("chat-add-key"));

    expect(useStore.getState().settingsOpen).toBe(true);
    expect(useStore.getState().chatError).toBeNull();
    expect(useStore.getState().chatErrorCode).toBeNull();
  });

  it("hosted_tier_exhausted also surfaces the CTA", () => {
    useStore.setState({ chatError: "Hosted free tier reached. Add your own API key.", chatErrorCode: "hosted_tier_exhausted" } as any);
    render(<ChatArea />);
    expect(screen.getByTestId("chat-add-key")).toBeInTheDocument();
  });

  it("a generic error (no key code) does NOT show the add-key CTA", () => {
    useStore.setState({ chatError: "Some other failure", chatErrorCode: null } as any);
    render(<ChatArea />);
    expect(screen.queryByTestId("chat-add-key")).toBeNull();
  });
});
