import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ExampleCard } from "@/components/launcher/ExampleCard";
import type { TemplateSummary } from "@/types";

const TEMPLATE: TemplateSummary = {
  id: "sync_fifo",
  name: "Synchronous FIFO",
  description: "A tiny FIFO example that lints and simulates.",
  highlights: ["Lint clean (iverilog)", "Self-checking testbench", "Fail → fix → pass"],
  top_module: "sync_fifo",
  platform: "sky130hd",
  source_note: null,
  file_count: 12,
  run_count: 2,
};

describe("ExampleCard", () => {
  it("renders name, description, highlights and file/run counts", () => {
    render(<ExampleCard template={TEMPLATE} selected={false} onSelect={vi.fn()} onOpen={vi.fn()} />);
    expect(screen.getByText("Synchronous FIFO")).toBeInTheDocument();
    expect(screen.getByText(/tiny FIFO example/)).toBeInTheDocument();
    expect(screen.getByText("Lint clean (iverilog)")).toBeInTheDocument();
    expect(screen.getByText("12 files")).toBeInTheDocument();
    expect(screen.getByText("2 runs")).toBeInTheDocument();
  });

  it("caps highlights at three", () => {
    const many = { ...TEMPLATE, highlights: ["a", "b", "c", "d", "e"] };
    render(<ExampleCard template={many} selected={false} onSelect={vi.fn()} onOpen={vi.fn()} />);
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.queryByText("d")).not.toBeInTheDocument();
  });

  it("select on click, open on the Fork button and double-click", () => {
    const onSelect = vi.fn();
    const onOpen = vi.fn();
    render(<ExampleCard template={TEMPLATE} selected={false} onSelect={onSelect} onOpen={onOpen} />);
    fireEvent.click(screen.getByTestId("example-card-sync_fifo"));
    expect(onSelect).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Fork Synchronous FIFO/ }));
    expect(onOpen).toHaveBeenCalled();
    fireEvent.doubleClick(screen.getByTestId("example-card-sync_fifo"));
    expect(onOpen).toHaveBeenCalledTimes(2);
  });
});
