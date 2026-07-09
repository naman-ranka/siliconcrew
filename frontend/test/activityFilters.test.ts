import { describe, it, expect } from "vitest";

import { filterActivity, toolKind } from "@/lib/activityFilters";
import type { ActivityEvent } from "@/types";

function ev(overrides: Partial<ActivityEvent>): ActivityEvent {
  return {
    id: `ev-${Math.random().toString(36).slice(2)}`,
    ts: "2026-07-02T10:00:00Z",
    source: "agent",
    tool: "linter_tool",
    args: {},
    status: "ok",
    resultSummary: "",
    durationMs: null,
    runId: null,
    threadId: null,
    ...overrides,
  };
}

describe("toolKind", () => {
  it("maps each tool to its kind", () => {
    expect(toolKind("linter_tool")).toBe("lint");
    expect(toolKind("simulation_tool")).toBe("sim");
    expect(toolKind("run_isolated_simulation")).toBe("sim");
    expect(toolKind("start_synthesis")).toBe("synth");
    expect(toolKind("retry_pd")).toBe("synth");
    expect(toolKind("write_spec")).toBe("writes");
    expect(toolKind("write_file")).toBe("writes");
    expect(toolKind("edit_file_tool")).toBe("writes");
    expect(toolKind("apply_patch_tool")).toBe("writes");
  });

  it("maps get_synthesis_* (prefix) to synth", () => {
    expect(toolKind("get_synthesis_status")).toBe("synth");
    expect(toolKind("get_synthesis_report")).toBe("synth");
  });

  it("unknown tools are 'other'", () => {
    expect(toolKind("generate_report_tool")).toBe("other");
    expect(toolKind("")).toBe("other");
    expect(toolKind("get_synthesis")).toBe("other"); // no trailing underscore segment
  });
});

describe("filterActivity", () => {
  const events: ActivityEvent[] = [
    ev({ id: "1", tool: "linter_tool", source: "agent", status: "ok", resultSummary: "passed · 0 error(s)" }),
    ev({ id: "2", tool: "run_isolated_simulation", source: "user", status: "error", runId: "sim_0003", resultSummary: "sim_0003 failed @ 120ns" }),
    ev({ id: "3", tool: "start_synthesis", source: "mcp", status: "running", runId: "synth_0001", resultSummary: "" }),
    ev({ id: "4", tool: "write_file", source: "agent", status: "ok", resultSummary: "wrote counter.v" }),
    ev({ id: "5", tool: "generate_report_tool", source: "user", status: "error", resultSummary: "boom" }),
  ];
  const base = { kind: "all", errorsOnly: false, actor: "both", query: "" } as const;

  it("kind=all with no other filters keeps everything (including 'other')", () => {
    expect(filterActivity(events, { ...base }).map((e) => e.id)).toEqual(["1", "2", "3", "4", "5"]);
  });

  it("filters by kind", () => {
    expect(filterActivity(events, { ...base, kind: "lint" }).map((e) => e.id)).toEqual(["1"]);
    expect(filterActivity(events, { ...base, kind: "sim" }).map((e) => e.id)).toEqual(["2"]);
    expect(filterActivity(events, { ...base, kind: "synth" }).map((e) => e.id)).toEqual(["3"]);
    expect(filterActivity(events, { ...base, kind: "writes" }).map((e) => e.id)).toEqual(["4"]);
  });

  it("errorsOnly keeps only status=error", () => {
    expect(filterActivity(events, { ...base, errorsOnly: true }).map((e) => e.id)).toEqual(["2", "5"]);
  });

  it("actor 'agent' = agent|mcp sources; 'you' = user source", () => {
    expect(filterActivity(events, { ...base, actor: "agent" }).map((e) => e.id)).toEqual(["1", "3", "4"]);
    expect(filterActivity(events, { ...base, actor: "you" }).map((e) => e.id)).toEqual(["2", "5"]);
  });

  it("query matches tool, runId and resultSummary case-insensitively", () => {
    expect(filterActivity(events, { ...base, query: "LINTER" }).map((e) => e.id)).toEqual(["1"]);
    expect(filterActivity(events, { ...base, query: "SIM_0003" }).map((e) => e.id)).toEqual(["2"]);
    expect(filterActivity(events, { ...base, query: "counter.v" }).map((e) => e.id)).toEqual(["4"]);
    expect(filterActivity(events, { ...base, query: "  " }).map((e) => e.id)).toHaveLength(5); // whitespace = no query
    expect(filterActivity(events, { ...base, query: "nomatch" })).toEqual([]);
  });

  it("filters compose (kind + errorsOnly + actor + query)", () => {
    const out = filterActivity(events, {
      kind: "sim",
      errorsOnly: true,
      actor: "you",
      query: "120ns",
    });
    expect(out.map((e) => e.id)).toEqual(["2"]);
    // Same query but wrong actor → nothing.
    expect(
      filterActivity(events, { kind: "sim", errorsOnly: true, actor: "agent", query: "120ns" })
    ).toEqual([]);
  });
});
