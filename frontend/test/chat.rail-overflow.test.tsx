import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";

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

import { MessageList } from "@/components/chat/MessageList";
import { ChatDensityProvider } from "@/components/chat/density";
import { useStore } from "@/lib/store";
import type { Message } from "@/types";

// A realistic unbreakable token: the owner-reported workspace path that clipped
// past the right edge of the ~415px rail. No spaces, so it can only be contained
// by wrapping (overflow-wrap:anywhere) + capping the row to the pane width.
const LONG_PATH =
  "/tmp/siliconcrew-scratch/universal-bcd-seven-segment-decoder-a-very-long-unbreakable-path";

function seed(messages: Message[]) {
  useStore.setState({
    currentSession: { id: "s1" } as any,
    messages,
    isStreaming: false,
    streamingMessage: null,
  } as any);
}

beforeEach(() => {
  useStore.setState({
    currentSession: null,
    messages: [],
    isStreaming: false,
    streamingMessage: null,
  } as any);
});

describe("chat rail containment — long tokens can't overflow the pane", () => {
  it("compact (rail) caps the message row to the pane width (max-w-full, not max-w-3xl)", () => {
    // Pre-fix the row used max-w-3xl (768px) even in the ~415px rail, so an
    // unbreakable token grew the row past the pane. Compact must be max-w-full.
    seed([{ id: "u1", role: "user", content: LONG_PATH, blocks: [] }]);
    const { container } = render(
      <ChatDensityProvider value={true}>
        <MessageList />
      </ChatDensityProvider>
    );
    expect(container.querySelector(".max-w-full")).not.toBeNull();
    expect(container.querySelector(".max-w-3xl")).toBeNull();
  });

  it("the user bubble carries overflow-wrap:anywhere so an unbreakable path wraps", () => {
    seed([{ id: "u1", role: "user", content: LONG_PATH, blocks: [] }]);
    render(
      <ChatDensityProvider value={true}>
        <MessageList />
      </ChatDensityProvider>
    );
    const bubble = screen.getByText(LONG_PATH);
    expect(bubble.className).toContain("[overflow-wrap:anywhere]");
    expect(bubble.className).toContain("break-words");
  });

  it("wide (non-compact) agent view is unchanged — still max-w-3xl", () => {
    seed([{ id: "u1", role: "user", content: "hi there", blocks: [] }]);
    const { container } = render(
      <ChatDensityProvider value={false}>
        <MessageList />
      </ChatDensityProvider>
    );
    expect(container.querySelector(".max-w-3xl")).not.toBeNull();
    expect(container.querySelector(".max-w-full")).toBeNull();
  });
});
