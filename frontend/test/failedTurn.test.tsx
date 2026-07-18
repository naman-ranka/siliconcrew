import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MessageList } from "@/components/chat/MessageList";
import { useStore } from "@/lib/store";

// S2a (blind-test both personas' #1): a failed turn must show up IN the
// conversation with remedies, not only as a distant dismissible banner.
const USER_MSG = { id: "m1", role: "user" as const, content: "Tour the tools please" };

describe("FailedTurnCard", () => {
  beforeEach(() => {
    cleanup();
    useStore.setState({
      currentSession: "s1",
      messages: [USER_MSG],
      isStreaming: false,
      chatError: null,
      chatErrorCode: null,
      models: [
        { id: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite", provider: "gemini", tier: "fast", available: true, free: true },
        { id: "claude-sonnet-5", label: "Claude Sonnet 5", provider: "anthropic", tier: "capable", available: false },
      ],
    } as never);
  });

  it("renders nothing without an error", () => {
    render(<MessageList />);
    expect(screen.queryByTestId("failed-turn-card")).toBeNull();
  });

  it("shows the error in-thread with free-model, key, and retry actions", () => {
    useStore.setState({
      chatError: "No key available for Anthropic. Add your own Anthropic API key in Settings, or switch to the free model (gemini-3.1-flash-lite).",
      chatErrorCode: "no_key",
    } as never);
    render(<MessageList />);
    const card = screen.getByTestId("failed-turn-card");
    expect(card.textContent).toContain("No key available for Anthropic");
    expect(screen.getByTestId("failed-turn-use-free").textContent).toContain("Gemini 3.1 Flash-Lite");
    expect(screen.getByTestId("failed-turn-retry")).toBeTruthy();
  });

  it("'use free and retry' switches the thread model then resends the failed message", async () => {
    const setActiveThreadModel = vi.fn().mockResolvedValue(undefined);
    const sendMessage = vi.fn();
    useStore.setState({
      chatError: "Hosted free-tier daily token limit reached (200000).",
      chatErrorCode: "hosted_tier_exhausted",
      setActiveThreadModel,
      sendMessage,
    } as never);
    render(<MessageList />);
    fireEvent.click(screen.getByTestId("failed-turn-use-free"));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledWith(USER_MSG.content));
    expect(setActiveThreadModel).toHaveBeenCalledWith("gemini-3.1-flash-lite");
    expect(useStore.getState().chatError).toBeNull();
  });

  it("plain retry resends the last user message", () => {
    const sendMessage = vi.fn();
    useStore.setState({ chatError: "transient failure", chatErrorCode: null, sendMessage } as never);
    render(<MessageList />);
    expect(screen.queryByTestId("failed-turn-use-free")).toBeNull(); // not a key error
    fireEvent.click(screen.getByTestId("failed-turn-retry"));
    expect(sendMessage).toHaveBeenCalledWith(USER_MSG.content);
  });
});
