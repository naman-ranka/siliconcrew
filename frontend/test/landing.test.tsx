import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { Hero } from "@/components/branding/Hero";
import { LandingFooter } from "@/components/branding/LandingFooter";
import { Logo } from "@/components/branding/Logo";
import { REPO_URL, ISSUES_URL, DOCS_URL, LICENSE_URL, CVDP_RESULT } from "@/components/branding/links";

describe("Logo", () => {
  it("renders a themeable svg mark (currentColor stroke)", () => {
    const { container } = render(<Logo />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("stroke")).toBe("currentColor");
  });
});

describe("Hero (open-source identity strip)", () => {
  it("shows the honest README tagline and the flow line", () => {
    render(<Hero />);
    expect(
      screen.getByText("An autonomous LLM agent for RTL design, verification, and synthesis.")
    ).toBeInTheDocument();
    expect(screen.getByText(/spec → RTL → lint → simulate/)).toBeInTheDocument();
  });

  it("links to the real repo and issues (no fabricated social proof)", () => {
    render(<Hero />);
    const gh = screen.getByRole("link", { name: /View on GitHub/i });
    expect(gh).toHaveAttribute("href", REPO_URL);
    expect(gh).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: /^Issues$/ })).toHaveAttribute("href", ISSUES_URL);
  });

  it("cites the CVDP result only as sourced from the README", () => {
    render(<Hero />);
    expect(screen.getByText(CVDP_RESULT.value)).toBeInTheDocument();
    expect(screen.getByText(CVDP_RESULT.label)).toBeInTheDocument();
  });

  it("names the open EDA tools for designer credibility", () => {
    render(<Hero />);
    for (const tool of ["OpenROAD", "Yosys", "Icarus Verilog", "Verilator", "sky130"]) {
      expect(screen.getByText(tool)).toBeInTheDocument();
    }
  });
});

describe("LandingFooter", () => {
  it("carries the standard OSS links with real hrefs", () => {
    render(<LandingFooter />);
    const footer = screen.getByTestId("landing-footer");
    expect(within(footer).getByRole("link", { name: /GitHub/i })).toHaveAttribute("href", REPO_URL);
    expect(within(footer).getByRole("link", { name: /Issues/i })).toHaveAttribute("href", ISSUES_URL);
    expect(within(footer).getByRole("link", { name: /Docs/i })).toHaveAttribute("href", DOCS_URL);
    expect(within(footer).getByRole("link", { name: /License/i })).toHaveAttribute("href", LICENSE_URL);
  });

  it("mentions the MIT license honestly", () => {
    render(<LandingFooter />);
    expect(screen.getByText(/MIT-licensed/)).toBeInTheDocument();
  });
});
