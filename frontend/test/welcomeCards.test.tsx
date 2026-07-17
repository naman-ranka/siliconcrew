import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MessageList, WELCOME_CARDS } from "@/components/chat/MessageList";
import { useStore } from "@/lib/store";

// E4 (onboarding wave): the four welcome cards are validated research
// artifacts — these tests pin their contract, not their styling.
describe("welcome cards", () => {
  beforeEach(() => {
    cleanup();
    useStore.setState({
      messages: [],
      isStreaming: false,
      currentSession: "welcome-test",
    } as never);
  });

  it("ships exactly four cards with the locked labels", () => {
    expect(WELCOME_CARDS.map((c) => c.label)).toEqual([
      "Tour the tools",
      "Brief this workspace",
      "Design a FIFO",
      "Explain RTL to GDS",
    ]);
  });

  it("prompts are human-voice: non-empty, no em dashes, no method checklists", () => {
    for (const c of WELCOME_CARDS) {
      expect(c.prompt.length).toBeGreaterThan(80);
      expect(c.prompt).not.toContain("—"); // em dash
      expect(c.prompt).not.toMatch(/\(1\)|step 1|first,? call/i);
    }
  });

  it("the showcase card stops at simulation and asks before synthesis", () => {
    const fifo = WELCOME_CARDS.find((c) => c.label === "Design a FIFO")!;
    expect(fifo.prompt).toContain("passing simulation");
    expect(fifo.prompt).toMatch(/ask me/i);
    expect(fifo.prompt).toContain("cocotb");
    expect(fifo.prompt).toContain("SymbiYosys");
  });

  it("renders the tagline and sends the exact full prompt on click", () => {
    const sendMessage = vi.fn();
    useStore.setState({ sendMessage } as never);
    render(<MessageList />);
    expect(screen.getByText("What silicon will you design today?")).toBeTruthy();
    fireEvent.click(screen.getByTestId("welcome-card-tour-the-tools"));
    expect(sendMessage).toHaveBeenCalledWith(WELCOME_CARDS[0].prompt);
  });

  it("shows all four cards on the empty thread", () => {
    render(<MessageList />);
    for (const c of WELCOME_CARDS) {
      const id = `welcome-card-${c.label.toLowerCase().replace(/\s+/g, "-")}`;
      expect(screen.getByTestId(id)).toBeTruthy();
    }
  });
});
