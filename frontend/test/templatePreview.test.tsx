import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const get = vi.fn();
vi.mock("@/lib/api", () => ({
  templatesApi: { get: (...a: unknown[]) => get(...a) },
}));

import { TemplatePreview } from "@/components/launcher/TemplatePreview";
import type { TemplateSummary } from "@/types";

const TEMPLATE: TemplateSummary = {
  id: "sync_fifo",
  name: "Synchronous FIFO",
  description: "A tiny FIFO example.",
  highlights: ["Lint clean"],
  top_module: "sync_fifo",
  platform: "sky130hd",
  source_note: null,
  file_count: 12,
  run_count: 2,
};

const DETAIL = {
  ...TEMPLATE,
  files: ["sync_fifo.v", "sync_fifo_tb.v", "spec.md"],
  conversations: ["chat-1-design.md"],
};

beforeEach(() => {
  get.mockReset();
});

describe("TemplatePreview", () => {
  it("loads and shows what's inside (files + conversations)", async () => {
    get.mockResolvedValue(DETAIL);
    render(<TemplatePreview template={TEMPLATE} onClose={vi.fn()} onFork={vi.fn()} />);
    expect(screen.getByTestId("template-preview")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("sync_fifo.v")).toBeInTheDocument());
    expect(screen.getByText("chat-1-design.md")).toBeInTheDocument();
    expect(screen.getByText("Lint clean")).toBeInTheDocument();
  });

  it("Fork button calls onFork with the template id", async () => {
    get.mockResolvedValue(DETAIL);
    const onFork = vi.fn().mockResolvedValue(undefined);
    render(<TemplatePreview template={TEMPLATE} onClose={vi.fn()} onFork={onFork} />);
    fireEvent.click(screen.getByTestId("fork-template"));
    await waitFor(() => expect(onFork).toHaveBeenCalledWith("sync_fifo"));
  });

  it("surfaces a fork error without navigating", async () => {
    get.mockResolvedValue(DETAIL);
    const onFork = vi.fn().mockRejectedValue(new Error("Fork failed — please try again"));
    render(<TemplatePreview template={TEMPLATE} onClose={vi.fn()} onFork={onFork} />);
    fireEvent.click(screen.getByTestId("fork-template"));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Fork failed")
    );
  });
});
