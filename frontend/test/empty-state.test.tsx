import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FileText } from "lucide-react";
import { EmptyState } from "@/components/workbench/EmptyState";

describe("EmptyState", () => {
  it("renders headline, copy, assistant hint, CTA and optional header", () => {
    render(
      <EmptyState
        icon={<FileText />}
        headline="No report yet"
        assistantHint="…or ask the assistant."
        header={<div data-testid="hero">hero</div>}
        cta={<button type="button">Generate Report</button>}
      >
        Run synthesis to generate a report.
      </EmptyState>
    );
    expect(screen.getByText("No report yet")).toBeInTheDocument();
    expect(screen.getByText("Run synthesis to generate a report.")).toBeInTheDocument();
    expect(screen.getByText("…or ask the assistant.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Report" })).toBeInTheDocument();
    expect(screen.getByTestId("hero")).toBeInTheDocument();
  });

  it("renders without optional props", () => {
    render(<EmptyState icon={<FileText />} headline="No waveforms yet" />);
    expect(screen.getByText("No waveforms yet")).toBeInTheDocument();
  });
});
