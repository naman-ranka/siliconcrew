import { describe, it, expect } from "vitest";

import {
  filterSessions,
  groupSessions,
  flattenSections,
  moveHighlight,
} from "@/lib/quickSwitch";
import type { Project, Session } from "@/types";

const session = (over: Partial<Session> & { id: string }): Session => ({
  name: over.id,
  model_name: null,
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
  ...over,
});

const P1: Project = { id: "g1", name: "asu_hackathon", created_at: null };
const P2: Project = { id: "g2", name: "tapeout_q3", created_at: null };

const FIFO = session({ id: "sync_fifo", project_id: "g1", updated_at: "2026-07-03T09:00:00Z" });
const UART = session({ id: "uart_tx", updated_at: "2026-07-02T10:00:00Z" });
const SPI = session({ id: "spi_master", project_id: "g2", updated_at: "2026-07-01T10:00:00Z" });
const ORPHAN = session({ id: "old_block", project_id: "gone", created_at: "2026-06-01T10:00:00Z" });

describe("quickSwitch: filterSessions", () => {
  it("orders by recency (updated_at falling back to created_at, newest first)", () => {
    expect(filterSessions([SPI, ORPHAN, FIFO, UART], "").map((s) => s.id)).toEqual([
      "sync_fifo",
      "uart_tx",
      "spi_master",
      "old_block",
    ]);
  });

  it("filters case-insensitively over the display name", () => {
    expect(filterSessions([FIFO, UART, SPI], "FIFO").map((s) => s.id)).toEqual(["sync_fifo"]);
    expect(filterSessions([FIFO, UART, SPI], "  uart ").map((s) => s.id)).toEqual(["uart_tx"]);
    expect(filterSessions([FIFO, UART, SPI], "zzz")).toEqual([]);
  });

  it("falls back to the id when name is null", () => {
    const unnamed = session({ id: "raw_id", name: null });
    expect(filterSessions([unnamed], "raw").map((s) => s.id)).toEqual(["raw_id"]);
  });
});

describe("quickSwitch: groupSessions / flattenSections", () => {
  it("groups in projects order, ungrouped (incl. unknown project ids) last, empties dropped", () => {
    const filtered = filterSessions([SPI, ORPHAN, FIFO, UART], "");
    const sections = groupSessions(filtered, [P1, P2]);
    expect(sections.map((s) => s.project?.id ?? null)).toEqual(["g1", "g2", null]);
    expect(sections[0].sessions.map((s) => s.id)).toEqual(["sync_fifo"]);
    expect(sections[1].sessions.map((s) => s.id)).toEqual(["spi_master"]);
    // Ungrouped bucket: no project_id AND project ids the list doesn't know.
    expect(sections[2].sessions.map((s) => s.id)).toEqual(["uart_tx", "old_block"]);
  });

  it("drops sections with no matches so the empty group never renders", () => {
    const sections = groupSessions(filterSessions([FIFO], ""), [P1, P2]);
    expect(sections.map((s) => s.project?.id ?? null)).toEqual(["g1"]);
  });

  it("flattenSections yields the visual order — the keyboard ↑↓ order", () => {
    const filtered = filterSessions([SPI, ORPHAN, FIFO, UART], "");
    const flat = flattenSections(groupSessions(filtered, [P1, P2]));
    expect(flat.map((s) => s.id)).toEqual(["sync_fifo", "spi_master", "uart_tx", "old_block"]);
  });
});

describe("quickSwitch: moveHighlight", () => {
  it("moves and clamps at both ends (no wrap)", () => {
    expect(moveHighlight(0, 1, 3)).toBe(1);
    expect(moveHighlight(2, 1, 3)).toBe(2); // bottom clamp
    expect(moveHighlight(0, -1, 3)).toBe(0); // top clamp
    expect(moveHighlight(2, -1, 3)).toBe(1);
  });

  it("is safe on an empty list", () => {
    expect(moveHighlight(0, 1, 0)).toBe(0);
    expect(moveHighlight(5, -1, 0)).toBe(0);
  });
});
