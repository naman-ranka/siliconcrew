import { describe, it, expect, vi } from "vitest";
import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { ComboInput } from "@/components/workbench/ComboInput";

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
});
