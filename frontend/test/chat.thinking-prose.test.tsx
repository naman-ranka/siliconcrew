import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// The store module imports the API layer at load; stub it so the component
// tree mounts without a backend.
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

import { MessageContent } from "@/components/chat/MessageList";
import type { Message } from "@/types";

function msg(blocks: Message["blocks"]): Message {
  return { id: "m1", role: "assistant", content: "", blocks };
}

describe("chat 'Thinking' heuristic no longer eats real prose (#2)", () => {
  it("assistant text that precedes a tool call renders as VISIBLE prose (not collapsed)", () => {
    // This is the pre-fix failure: isThinkingBlock() collapsed any text block
    // followed by a tool call, so this explanation rendered inside a closed
    // "Thinking" toggle and its words were absent from the DOM.
    render(
      <MessageContent
        message={msg([
          { type: "text", content: "Fixing the reset polarity to active-low first." },
          { type: "tool", toolCall: { id: "t1", name: "write_file", args: {} } },
        ])}
      />
    );

    // Prose is present and visible (would be absent pre-fix — collapsed).
    expect(screen.getByText(/Fixing the reset polarity to active-low first\./)).toBeInTheDocument();
    // No "Thinking" toggle was manufactured for genuine prose.
    expect(screen.queryByText("Thinking")).toBeNull();
  });

  it("a genuine reasoning-stream block still collapses behind the Thinking toggle", () => {
    render(
      <MessageContent
        message={msg([
          { type: "reasoning", content: "internal-scratchpad-reasoning" },
        ])}
      />
    );

    // The toggle exists and the reasoning content is hidden until expanded.
    expect(screen.getByText("Thinking")).toBeInTheDocument();
    expect(screen.queryByText(/internal-scratchpad-reasoning/)).toBeNull();

    // Expanding reveals it — proving it was collapsed, not dropped.
    fireEvent.click(screen.getByText("Thinking"));
    expect(screen.getByText(/internal-scratchpad-reasoning/)).toBeInTheDocument();
  });
});
