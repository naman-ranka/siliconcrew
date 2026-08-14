import { describe, it, expect, vi } from "vitest";
import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { ComboInput, MultiComboInput } from "@/components/workbench/ComboInput";

// Controlled harness — mirrors how CommandModal/CommandSurface use it.
function Harness({
  suggestions,
  initial = "",
  onChangeSpy,
}: {
  suggestions: string[];
  initial?: string;
  onChangeSpy?: (v: string) => void;
}) {
  const [value, setValue] = React.useState(initial);
  return (
    <ComboInput
      value={value}
      onChange={(v) => {
        setValue(v);
        onChangeSpy?.(v);
      }}
      suggestions={suggestions}
      ariaLabel="sim_top"
    />
  );
}

const input = () => screen.getByRole("combobox", { name: "sim_top" });

describe("ComboInput", () => {
  it("opens the full suggestion list on focus", () => {
    render(<Harness suggestions={["cpu_tb", "alu_tb"]} />);
    expect(screen.queryByRole("listbox")).toBeNull();
    fireEvent.focus(input());
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "cpu_tb",
      "alu_tb",
    ]);
  });

  it("filters suggestions by case-insensitive substring while typing", () => {
    render(<Harness suggestions={["cpu_tb", "alu_tb", "fifo_tb"]} />);
    fireEvent.change(input(), { target: { value: "ALU" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["alu_tb"]);
  });

  it("clicking a suggestion selects it and closes the dropdown", () => {
    const spy = vi.fn();
    render(<Harness suggestions={["cpu_tb", "alu_tb"]} onChangeSpy={spy} />);
    fireEvent.focus(input());
    fireEvent.click(screen.getByRole("option", { name: "alu_tb" }));
    expect(spy).toHaveBeenLastCalledWith("alu_tb");
    expect(input()).toHaveValue("alu_tb");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("↑/↓ navigate and Enter selects the highlighted suggestion", () => {
    render(<Harness suggestions={["cpu_tb", "alu_tb"]} />);
    fireEvent.focus(input());
    fireEvent.keyDown(input(), { key: "ArrowDown" }); // → cpu_tb
    fireEvent.keyDown(input(), { key: "ArrowDown" }); // → alu_tb
    expect(screen.getByRole("option", { name: "alu_tb" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(input()).toHaveValue("alu_tb");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("free text is always allowed — Enter with no highlight keeps the typed value", () => {
    const spy = vi.fn();
    render(<Harness suggestions={["cpu_tb"]} onChangeSpy={spy} />);
    fireEvent.change(input(), { target: { value: "my_custom_tb" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(input()).toHaveValue("my_custom_tb");
    expect(spy).toHaveBeenLastCalledWith("my_custom_tb");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("Esc closes the dropdown (consumed) without touching the value", () => {
    render(<Harness suggestions={["cpu_tb"]} initial="cpu" />);
    fireEvent.focus(input());
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.keyDown(input(), { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(input()).toHaveValue("cpu");
  });

  it("renders no dropdown when nothing matches", () => {
    render(<Harness suggestions={["cpu_tb"]} />);
    fireEvent.change(input(), { target: { value: "zzz" } });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  // ---- W2/A10: richer suggestion rows (value + subtitle) ---------------------

  it("renders subtitles while the accessible name stays the value alone", () => {
    render(
      <ComboInput
        value=""
        onChange={() => {}}
        ariaLabel="sim_top"
        suggestions={[
          { value: "cpu_tb", subtitle: "tb/cpu_tb.v" },
          { value: "alu_tb" }, // no subtitle — value only
        ]}
      />
    );
    fireEvent.focus(input());
    // Name-based queries survive the subtitle (aria-label = value).
    const row = screen.getByRole("option", { name: "cpu_tb" });
    expect(row.textContent).toBe("cpu_tbtb/cpu_tb.v"); // value + trailing subtitle
    expect(screen.getByRole("option", { name: "alu_tb" }).textContent).toBe("alu_tb");
  });

  // ---- owner refinement (2026-08-14): two-tier suggestions -------------------
  // The dropdown shows what this field MEANS (the suggested tier) on focus;
  // typing also reaches the rest of the workspace index, under a divider.

  const TwoTier = ({ initial = "" }: { initial?: string }) => {
    const [v, setV] = React.useState(initial);
    return (
      <ComboInput
        value={v}
        onChange={setV}
        ariaLabel="sim_top"
        suggestions={["alu.v", "top.v"]}
        moreSuggestions={["alu.v", "old/legacy.v", "docs/notes.md"]}
      />
    );
  };

  it("focus with an empty query shows the SUGGESTED tier only — no index dump", () => {
    render(<TwoTier />);
    fireEvent.focus(input());
    expect(screen.getAllByRole("option").map((o) => o.getAttribute("aria-label"))).toEqual([
      "alu.v",
      "top.v",
    ]);
    expect(screen.queryByTestId("combo-tier-divider")).toBeNull();
  });

  it("typing surfaces non-suggested workspace files under the 'other files' divider", () => {
    render(<TwoTier />);
    fireEvent.change(input(), { target: { value: "old" } });
    // Suggested tier first (nothing matches "old" here), then the wider index.
    expect(screen.getAllByRole("option").map((o) => o.getAttribute("aria-label"))).toEqual([
      "old/legacy.v",
    ]);
    expect(screen.getByTestId("combo-tier-divider")).toHaveTextContent("other files");
    fireEvent.click(screen.getByRole("option", { name: "old/legacy.v" }));
    expect(input()).toHaveValue("old/legacy.v"); // free-index values are selectable
  });

  it("the suggested tier leads and never repeats in the second tier", () => {
    render(<TwoTier />);
    fireEvent.change(input(), { target: { value: ".v" } });
    // alu.v is suggested — it appears ONCE, above the divider, and top.v with it.
    expect(screen.getAllByRole("option").map((o) => o.getAttribute("aria-label"))).toEqual([
      "alu.v",
      "top.v",
      "old/legacy.v",
    ]);
    expect(screen.getByTestId("combo-tier-divider")).toBeInTheDocument();
  });

  it("no second-tier match → no divider (the tier is never an empty header)", () => {
    render(<TwoTier />);
    fireEvent.change(input(), { target: { value: "top" } });
    expect(screen.getAllByRole("option").map((o) => o.getAttribute("aria-label"))).toEqual([
      "top.v",
    ]);
    expect(screen.queryByTestId("combo-tier-divider")).toBeNull();
  });

  it("↑/↓ walk both tiers as one list", () => {
    render(<TwoTier />);
    fireEvent.change(input(), { target: { value: ".v" } });
    fireEvent.keyDown(input(), { key: "ArrowDown" }); // alu.v (suggested)
    fireEvent.keyDown(input(), { key: "ArrowDown" }); // top.v (suggested)
    fireEvent.keyDown(input(), { key: "ArrowDown" }); // old/legacy.v (other files)
    expect(screen.getByRole("option", { name: "old/legacy.v" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(input()).toHaveValue("old/legacy.v");
  });

  it("selecting a rich suggestion yields the VALUE, never the subtitle", () => {
    const spy = vi.fn();
    render(
      <ComboInput
        value=""
        onChange={spy}
        ariaLabel="rich"
        suggestions={[{ value: "cpu_tb", subtitle: "tb/cpu_tb.v" }]}
      />
    );
    fireEvent.focus(screen.getByRole("combobox", { name: "rich" }));
    fireEvent.click(screen.getByRole("option", { name: "cpu_tb" }));
    expect(spy).toHaveBeenLastCalledWith("cpu_tb");
  });
});

// ---- MultiComboInput (the W2 multi-combo: chips + suggesting input) -----------

function MultiHarness({
  suggestions,
  moreSuggestions,
  initial = [],
  onChangeSpy,
}: {
  suggestions: (string | { value: string; subtitle?: string })[];
  moreSuggestions?: (string | { value: string; subtitle?: string })[];
  initial?: string[];
  onChangeSpy?: (v: string[]) => void;
}) {
  const [values, setValues] = React.useState<string[]>(initial);
  return (
    <MultiComboInput
      values={values}
      onChange={(v) => {
        setValues(v);
        onChangeSpy?.(v);
      }}
      suggestions={suggestions}
      moreSuggestions={moreSuggestions}
      ariaLabel="Add files"
    />
  );
}

const multiInput = () => screen.getByRole("combobox", { name: "Add files" });

describe("MultiComboInput", () => {
  it("picking a suggestion adds a chip and clears the draft", () => {
    const spy = vi.fn();
    render(<MultiHarness suggestions={["alu.v", "tb.v"]} onChangeSpy={spy} />);
    fireEvent.focus(multiInput());
    fireEvent.click(screen.getByRole("option", { name: "alu.v" }));
    expect(spy).toHaveBeenLastCalledWith(["alu.v"]);
    expect(multiInput()).toHaveValue("");
    expect(screen.getByLabelText("Remove alu.v")).toBeInTheDocument();
  });

  it("free entry: typed text + Enter becomes a chip (suggestions can miss files)", () => {
    const spy = vi.fn();
    render(<MultiHarness suggestions={["alu.v"]} onChangeSpy={spy} />);
    fireEvent.change(multiInput(), { target: { value: "rtl/custom.v" } });
    fireEvent.keyDown(multiInput(), { key: "Enter" });
    expect(spy).toHaveBeenLastCalledWith(["rtl/custom.v"]);
    expect(multiInput()).toHaveValue("");
  });

  it("already-chosen values disappear from the dropdown; chips are removable", () => {
    render(<MultiHarness suggestions={["alu.v", "tb.v"]} initial={["alu.v"]} />);
    fireEvent.focus(multiInput());
    expect(screen.queryByRole("option", { name: "alu.v" })).toBeNull();
    expect(screen.getByRole("option", { name: "tb.v" })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Remove alu.v"));
    expect(screen.queryByLabelText("Remove alu.v")).toBeNull();
  });

  it("two tiers ride through the multi-combo, and chips are hidden from BOTH", () => {
    render(
      <MultiHarness
        suggestions={["alu.v", "top.v"]}
        moreSuggestions={["old/legacy.v", "docs/notes.md"]}
        initial={["old/legacy.v"]}
      />
    );
    // Focus: suggested tier only — the manifest set, not the whole workspace.
    fireEvent.focus(multiInput());
    expect(screen.getAllByRole("option").map((o) => o.getAttribute("aria-label"))).toEqual([
      "alu.v",
      "top.v",
    ]);
    // Typing reaches the index — minus what is already a chip.
    fireEvent.change(multiInput(), { target: { value: "o" } });
    const labels = screen.getAllByRole("option").map((o) => o.getAttribute("aria-label"));
    expect(labels).toContain("docs/notes.md");
    expect(labels).not.toContain("old/legacy.v"); // already chosen
  });

  it("duplicates and empty drafts are ignored", () => {
    const spy = vi.fn();
    render(<MultiHarness suggestions={[]} initial={["alu.v"]} onChangeSpy={spy} />);
    fireEvent.change(multiInput(), { target: { value: "alu.v" } });
    fireEvent.keyDown(multiInput(), { key: "Enter" });
    expect(spy).not.toHaveBeenCalled(); // duplicate — no change
    fireEvent.change(multiInput(), { target: { value: "   " } });
    fireEvent.keyDown(multiInput(), { key: "Enter" });
    expect(spy).not.toHaveBeenCalled();
  });
});
